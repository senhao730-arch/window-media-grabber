"""Explicit, isolated Edge session; no certificate changes or browser profile copying."""
import base64
import concurrent.futures
import json
import mimetypes
import os
import queue
import socket
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit,unquote
import requests
import websocket
from media import Asset,STATE,STAGING,sniff,stage_bytes,inspect_asset,run_ffmpeg

DOM_SCRIPT=r'''JSON.stringify((()=>{
 const out=new Map(); const add=(u,t)=>{if(u&&(u.startsWith('http')||u.startsWith('data:image')))out.set(u,{url:u,type:t});};
 const scan=d=>{
  d.querySelectorAll('img').forEach(e=>add(e.currentSrc||e.src,'图片'));
  d.querySelectorAll('video,video source').forEach(e=>add(e.currentSrc||e.src,'视频'));
  d.querySelectorAll('*').forEach(e=>{
    const bg=getComputedStyle(e).backgroundImage;
    for(const m of bg.matchAll(/url\(["']?(.*?)["']?\)/g))add(m[1],'图片');
    if(e.shadowRoot)scan(e.shadowRoot);
  });
  d.querySelectorAll('iframe').forEach(e=>{try{if(e.contentDocument)scan(e.contentDocument)}catch{}});
 };scan(document);
 performance.getEntriesByType('resource').forEach(e=>{
  if(['img','video'].includes(e.initiatorType)||/\.(png|jpe?g|gif|webp|avif|mp4|webm|m3u8)(\?|$)/i.test(e.name))add(e.name,/\.(mp4|webm|m3u8)/i.test(e.name)?'视频':'图片');
 });return [...out.values()];})())'''

class CDP:
    def __init__(self,url,event):
        self.ws=websocket.create_connection(url,timeout=1,suppress_origin=True,http_proxy_host=None)
        self.event=event;self.lock=threading.Lock();self.pending={};self.seq=0;self.closed=False
        self.reader=threading.Thread(target=self._read,daemon=True);self.reader.start()
    def _read(self):
        while not self.closed:
            try:message=json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:continue
            except Exception:break
            if 'id' in message:
                with self.lock:q=self.pending.get(message['id'])
                if q:q.put(message)
            elif 'method' in message:
                try:self.event(message['method'],message.get('params',{}))
                except Exception:pass
        self.closed=True
    def call(self,method,params=None,timeout=20):
        with self.lock:
            if self.closed:raise RuntimeError('Edge 连接已关闭，请重新连接标签页。')
            self.seq+=1;n=self.seq;q=queue.Queue();self.pending[n]=q
            self.ws.send(json.dumps({'id':n,'method':method,'params':params or {}}))
        try:
            result=q.get(timeout=timeout)
            if 'error' in result:raise RuntimeError(result['error'].get('message','Edge 接口失败'))
            return result.get('result',{})
        except queue.Empty:raise RuntimeError('Edge 响应超时，请重新连接或恢复标签页。')
        finally:
            with self.lock:self.pending.pop(n,None)
    def close(self):
        self.closed=True
        try:self.ws.close()
        except Exception:pass

class Edge:
    def __init__(self,on_asset,log):
        self.on_asset=on_asset;self.log=log;self.port=None;self.cdp=None;self.requests={}
        self.target=None;self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=3)
        self.session=requests.Session();self.session.trust_env=False;self.generation=0;self.referers={}
    def open(self,url):
        if urlsplit(url).scheme not in ('http','https'):raise RuntimeError('请输入 http:// 或 https:// 网页地址。')
        paths=[Path(os.environ.get('PROGRAMFILES(X86)','C:/Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe',
               Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Microsoft/Edge/Application/msedge.exe']
        exe=next((p for p in paths if p.exists()),None)
        if not exe:raise RuntimeError('未找到 Microsoft Edge。')
        if self.port:
            try:
                self.targets()
                subprocess.Popen([str(exe),f'--user-data-dir={STATE/"edge-profile"}',url],creationflags=0x08000000)
                return
            except Exception:pass
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        subprocess.Popen([str(exe),f'--user-data-dir={STATE/"edge-profile"}',
            f'--remote-debugging-port={self.port}','--remote-debugging-address=127.0.0.1',
            '--no-first-run','--disable-background-timer-throttling','--disable-renderer-backgrounding',url],creationflags=0x08000000)
        for _ in range(60):
            try:self.targets();return
            except Exception:time.sleep(.2)
        raise RuntimeError('抓取用 Edge 未能建立连接。如果其窗口已打开，请关闭该专用窗口后重试。')
    def targets(self):
        if not self.port:raise RuntimeError('请先点击“打开抓取用 Edge”。已有普通 Edge 窗口可用缓存扫描，但不能直接连接网页资源接口。')
        response=self.session.get(f'http://127.0.0.1:{self.port}/json/list',timeout=3)
        response.raise_for_status()
        return [t for t in response.json() if t.get('type')=='page' and t.get('url','').startswith(('http:','https:'))]
    def connect(self,target):
        if self.cdp:self.cdp.close()
        self.generation+=1;self.target=target;self.requests={};self.referers={}
        self.cdp=CDP(target['webSocketDebuggerUrl'],self._event)
        self.cdp.call('Network.enable',{'maxTotalBufferSize':128*1024*1024,'maxResourceBufferSize':64*1024*1024})
        self.cdp.call('Runtime.enable')
        self.log('已连接网页，后续加载的原始媒体会进入列表。可切换页面或播放视频。')
        self.analyze()
    def analyze(self):
        if not self.cdp:raise RuntimeError('请先选择并连接 Edge 标签页。')
        result=self.cdp.call('Runtime.evaluate',{'expression':DOM_SCRIPT,'returnByValue':True})
        if result.get('exceptionDetails'):raise RuntimeError('网页分析失败，请等页面加载后重试。')
        resources=json.loads(result.get('result',{}).get('value','[]'))
        for item in resources:
            url=item['url']
            if url.startswith('data:image'):
                try:
                    meta,body=url.split(',',1)
                    data=base64.b64decode(body) if ';base64' in meta else unquote(body).encode()
                    ext=sniff(data)
                    if ext:
                        p,h=stage_bytes(data,ext)
                        self.on_asset(inspect_asset(Asset(p,ext,'Edge 页面内嵌图片',digest=h)))
                except Exception:pass
            else:self.on_asset(self.url_asset(url,item['type']))
        self.log(f'页面分析得到 {len(resources)} 个资源候选；跨域子页面和流媒体可能需要开始播放后才能识别。')
    def url_asset(self,url,category='',mime=''):
        ext=Path(urlsplit(url).path).suffix.lower().lstrip('.')
        if ext not in ('png','jpg','jpeg','gif','webp','avif','svg','mp4','webm','m3u8','mpd'):
            ext={'image/jpeg':'jpg','image/png':'png','image/webp':'webp','image/gif':'gif','video/mp4':'mp4','video/webm':'webm',
                 'application/vnd.apple.mpegurl':'m3u8','application/x-mpegurl':'m3u8','application/dash+xml':'mpd'}.get(mime.split(';')[0],'mp4' if category=='视频' else 'png')
        return Asset(None,ext,'Edge 原始媒体地址',name=unquote(Path(urlsplit(url).path).name) or '网页媒体',url=url,
            note='待下载；画质由网页实际提供的资源决定')
    def _event(self,method,p):
        if method=='Network.requestWillBeSent':
            req=p.get('request',{});url=req.get('url','')
            if url.startswith(('http:','https:')):
                self.referers[p['requestId']]=req.get('headers',{}).get('Referer',p.get('documentURL',''))
        elif method=='Network.responseReceived':
            r=p.get('response',{});mime=r.get('mimeType','').lower();u=r.get('url','')
            if u.startswith(('http:','https:')) and (mime.startswith(('image/','video/')) or 'mpegurl' in mime or 'dash+xml' in mime):
                asset=self.url_asset(u,'视频' if mime.startswith('video/') or 'mpegurl' in mime or 'dash+xml' in mime else '图片',mime)
                asset.size=int(r.get('encodedDataLength',0));asset.headers={'Referer':self.referers.get(p['requestId'],self.target.get('url',''))}
                if r.get('status')==206:asset.note='服务器分段响应；下载时将重新获取完整文件'
                self.requests[p['requestId']]=(asset,r.get('status')==200,self.generation,self.cdp)
                self.on_asset(asset)
        elif method=='Network.loadingFinished':
            self.referers.pop(p.get('requestId'),None)
            info=self.requests.pop(p['requestId'],None)
            if info:self.pool.submit(self._body,p['requestId'],info)
        elif method=='Network.loadingFailed':
            self.requests.pop(p.get('requestId'),None);self.referers.pop(p.get('requestId'),None)
    def _body(self,rid,info):
        asset,complete,gen,cdp=info
        if not complete or gen!=self.generation or asset.ext in ('mpd','m3u8'):return
        try:
            result=cdp.call('Network.getResponseBody',{'requestId':rid},timeout=8)
            data=base64.b64decode(result['body']) if result.get('base64Encoded') else result['body'].encode()
            ext=sniff(data)
            if not ext:return
            path,h=stage_bytes(data,ext)
            ready=inspect_asset(Asset(path,ext,'Edge 网络响应原文件',name=asset.name,url=asset.url,digest=h,headers=asset.headers))
            self.on_asset(ready)
        except Exception:pass  # URL candidate remains available for explicit download.
    def download(self,asset,stop):
        if not asset.url.startswith(('http://','https://')):raise RuntimeError('资源地址不可下载')
        headers={'Referer':asset.headers.get('Referer',(self.target or {}).get('url',asset.url))};cookies=[]
        if self.cdp:
            try:
                headers['User-Agent']=self.cdp.call('Runtime.evaluate',{'expression':'navigator.userAgent','returnByValue':True})['result']['value']
                cookies=self.cdp.call('Network.getCookies',{'urls':[asset.url]}).get('cookies',[])
                if cookies:headers['Cookie']='; '.join(c['name']+'='+c['value'] for c in cookies)
            except Exception:pass
        STAGING.mkdir(parents=True,exist_ok=True)
        if asset.ext in ('m3u8','mpd'):
            with self.session.get(asset.url,headers=headers,timeout=(10,20),allow_redirects=False) as manifest:
                manifest.raise_for_status()
                text=manifest.text
            if ('<ContentProtection' in text or 'SAMPLE-AES' in text or 'skd://' in text):
                raise RuntimeError('此播放清单标记了内容保护，不能提取原始视频。')
            tmp=STAGING/f'stream_{threading.get_ident()}.mp4'
            header_text=''.join(k+': '+v+'\r\n' for k,v in headers.items() if k!='Cookie' and '\r' not in v and '\n' not in v)
            # FFmpeg's cookie jar applies domain/path matching to child requests.
            cookie_text=''.join(c['name']+'='+c['value']+'; domain='+c['domain']+'; path='+c.get('path','/')+'\r\n' for c in cookies)
            try:
                run_ffmpeg(['-protocol_whitelist','http,https,tcp,tls,crypto','-rw_timeout','15000000',
                    '-headers',header_text]+(['-cookies',cookie_text] if cookie_text else [])+[
                    '-i',asset.url,'-map','0:v:0','-an','-c:v','copy','-movflags','+faststart',str(tmp)],stop)
                if not tmp.exists() or tmp.stat().st_size<32:raise RuntimeError('播放清单没有可合并的视频流。')
                ready=inspect_asset(Asset(tmp,'mp4','Edge 流媒体合并（不转码、无声）',name=asset.name,url=asset.url,note='由网站实际提供的视频流合并'))
                dest=STAGING/(ready.digest+'.mp4');os.replace(tmp,dest);ready.path=dest
                return ready
            finally:
                if tmp.exists():tmp.unlink()
        tmp=STAGING/f'download_{threading.get_ident()}.part'
        import hashlib
        h=hashlib.sha256();prefix=b''
        try:
            # Supplying cookies only to the original host, not to cross-host redirects.
            s=requests.Session();s.trust_env=False
            with s.get(asset.url,headers=headers,stream=True,timeout=(10,30),allow_redirects=False) as r:
                if 300<=r.status_code<400:raise RuntimeError('资源发生重定向，请在 Edge 播放或刷新后选择最终媒体地址。')
                r.raise_for_status()
                if r.status_code!=200:
                    import re
                    m=re.fullmatch(r'bytes 0-(\d+)/(\d+)',r.headers.get('Content-Range',''))
                    if r.status_code!=206 or not m or int(m[1])+1!=int(m[2]):
                        raise RuntimeError('服务器只返回片段，无法将它冒充完整原文件。')
                expected=int(r.headers.get('Content-Length','0')) if r.headers.get('Content-Encoding','identity')=='identity' else 0
                total=0
                with tmp.open('wb') as out:
                    for chunk in r.iter_content(1024*1024):
                        if stop.is_set():raise RuntimeError('已取消')
                        if chunk:
                            if len(prefix)<4096:prefix=(prefix+chunk)[:4096]
                            out.write(chunk);h.update(chunk);total+=len(chunk)
                if expected and total!=expected:raise RuntimeError('下载不完整，请重试。')
            ext=sniff(prefix)
            if not ext or ext in ('m3u8','mpd'):raise RuntimeError('返回的不是可识别的完整图片或视频文件。')
            dest=STAGING/(h.hexdigest()+'.'+ext);os.replace(tmp,dest)
            return inspect_asset(Asset(dest,ext,'Edge 下载原文件',name=asset.name,url=asset.url,digest=h.hexdigest()))
        finally:
            if tmp.exists():tmp.unlink()
    def close(self):
        self.disconnect()
        self.pool.shutdown(wait=False,cancel_futures=True)
    def disconnect(self):
        self.generation+=1
        if self.cdp:self.cdp.close();self.cdp=None
