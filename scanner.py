"""Read-only media discovery, including validated Chromium sparse video caches."""
import os
import hashlib
import re
import struct
import time
import zlib
from pathlib import Path
from media import Asset,STAGING,sniff,stage_bytes,inspect_asset,expected_webm_length
from native import read_shared

SKIP={'network','local storage','session storage','indexeddb','databases','gpuCache'.lower(),
      'code cache','dawncache','logs','telemetry','cookies','games','node_modules'}
_SPARSE_READY={}
MEDIA_DIRS={'cache','cache_data','cachedata','blob_storage','images','image','videos','video','media','assets','res','resources'}
DISCOVERY_SKIP=SKIP|{'bin','binaries','engine','game','content','tenprotect','node_modules','.git','login','txsso','tcls'}

def unique_roots(paths):
    """Remove missing paths, junctions and overlapping subtrees before scanning."""
    valid=[]
    for path in paths:
        p=Path(path)
        try:
            if not p.is_dir() or p.is_symlink() or p.is_junction():continue
            p=p.resolve()
        except OSError:continue
        if any(p==q or q in p.parents for q in valid):continue
        valid=[q for q in valid if p not in q.parents];valid.append(p)
    return valid

def registered_install_folders(process):
    """Exact executable matches only; never guess unrelated installed applications."""
    import winreg
    process=process.lower()
    if process in ('未知进程','', 'applicationframehost.exe'):return []
    folders=[]
    for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
        for branch in (rf'Software\Microsoft\Windows\CurrentVersion\App Paths\{process}',
                       rf'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\{process}'):
            try:
                with winreg.OpenKey(hive,branch) as key:
                    exe=Path(winreg.QueryValueEx(key,'')[0].strip('"'))
                    if exe.name.lower()==process and exe.is_file():folders.append(exe.parent)
            except OSError:pass
        for branch in (r'Software\Microsoft\Windows\CurrentVersion\Uninstall',
                       r'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'):
            try:
                with winreg.OpenKey(hive,branch) as key:
                    for i in range(min(1500,winreg.QueryInfoKey(key)[0])):
                        try:
                            with winreg.OpenKey(key,winreg.EnumKey(key,i)) as app:
                                icon=winreg.QueryValueEx(app,'DisplayIcon')[0]
                                icon=re.sub(r',\s*-?\d+$','',icon).strip().strip('"')
                                exe=Path(os.path.expandvars(icon))
                                if exe.name.lower()==process and exe.is_file():folders.append(exe.parent)
                        except OSError:continue
            except OSError:pass
    return unique_roots(folders)

def app_folders(window):
    folders=[Path(window.path).parent] if window.path else registered_install_folders(window.process)
    stem=Path(window.process.lower()).stem
    # Generic names cannot identify one application's user-data directory.
    if stem not in ('launcher','hyp','weixin','wechat','msedge','applicationframehost','未知进程'):
        token=re.sub(r'[-_ ]?(launcher|client)$','',stem)
        def normalized(s):return re.sub(r'[-_ .]','',s.lower())
        names={normalized(stem),normalized(token)}-{''}
        for base in (Path(os.environ['APPDATA']),Path(os.environ['LOCALAPPDATA'])):
            try:
                for p in base.iterdir():
                    if p.is_dir() and normalized(p.name) in names:folders.append(p)
            except OSError:pass
    return unique_roots(folders)

def discover_roots(window,stop,log,expanded=False):
    roots=suggested_roots(window)
    bases=app_folders(window)
    for base in bases:
        for name in MEDIA_DIRS:roots.append(base/name)
        if window.process.lower()=='delta_force_launcher.exe' or '三角洲' in window.title:
            roots += [base/'tpf_ui/res',base/'data/client_ui/web/assets']
    if expanded:
        visited=0
        for base in bases:
            for folder,dirs,_ in os.walk(base):
                if stop.is_set():return unique_roots(roots)
                visited+=1
                if visited>600:
                    log('自动目录搜索达到600个目录上限；可手动选择更准确的素材目录。')
                    return unique_roots(roots)
                path=Path(folder);depth=len(path.relative_to(base).parts)
                if path.name.lower() in MEDIA_DIRS:roots.append(path);dirs[:]=[];continue
                dirs[:]=[d for d in dirs if d.lower() not in DISCOVERY_SKIP
                         and not Path(folder,d).is_symlink() and not Path(folder,d).is_junction()] if depth<4 else []
    return unique_roots(roots)

def suggested_roots(window):
    roaming=Path(os.environ['APPDATA']);local=Path(os.environ['LOCALAPPDATA'])
    n=window.process.lower(); roots=[]
    if n in ('hyp.exe','launcher.exe') or '米哈游' in window.title:
        base=roaming/'miHoYo'/'HYP'
        if base.exists():
            roots += [p/'fedata'/'Cache' for p in base.iterdir() if p.is_dir()]
    if 'bilibili' in n or '哔哩' in window.title:
        roots += [roaming/'bilibili'/'Cache',roaming/'bilibili'/'blob_storage']
    if 'msedge' in n:
        base=local/'Microsoft'/'Edge'/'User Data'
        if base.exists():
            roots += [p/'Cache' for p in base.iterdir() if p.is_dir() and (p.name=='Default' or p.name.startswith('Profile '))]
    # Only narrowly named caches; never guess a user's chat/account directory.
    stem=Path(n).stem
    if stem not in ('launcher','hyp','weixin','wechat','msedge','applicationframehost'):
        for base in (roaming,local):
            for appdir in base.iterdir():
                if appdir.is_dir() and stem and (appdir.name.lower()==stem):
                    roots += [appdir/'Cache',appdir/'cache',appdir/'Cache_Data',appdir/'blob_storage']
    if window.path:
        folder=Path(window.path).parent
        roots += [folder/'cache',folder/'Cache',folder/'images',folder/'media']
        if n=='delta_force_launcher.exe' or '三角洲' in window.title:
            # Launcher assets are ordinary files outside the conventional cache paths.
            roots += [folder/'tpf_ui'/'res',folder/'data'/'client_ui'/'web'/'assets']
    return unique_roots(roots)

def block_stream(root,address,size):
    if not address&0x80000000 or size<=0:return b''
    typ=(address>>28)&7
    if typ==0:return read_shared(root/f'f_{address&0x0fffffff:06x}',0,size)
    bs={1:36,2:256,3:1024,4:4096,5:8,6:104,7:48}[typ]
    return read_shared(root/f'data_{(address>>16)&255}',8192+(address&65535)*bs,size)

def block_records(root,stop,log):
    try:idx=read_shared(root/'index',0,4*1024*1024)
    except OSError:
        log('缓存索引正在被占用或权限不足，改为识别独立媒体文件。');return
    if len(idx)<368 or struct.unpack_from('<I',idx)[0]!=0xc103cac3:return
    version=struct.unpack_from('<I',idx,4)[0]
    if version not in (0x20000,0x20001,0x30000):
        log('此 Chromium 缓存索引版本暂不解析，仅识别独立文件。');return
    visited=set()
    for off in range(368,len(idx)-3,4):
        address=struct.unpack_from('<I',idx,off)[0]
        while address and address not in visited and not stop.is_set():
            visited.add(address)
            if len(visited)>50000:return
            try:
                entry=block_stream(root,address,256)
                if len(entry)!=256:break
                nxt=struct.unpack_from('<I',entry,4)[0]
                state=struct.unpack_from('<i',entry,20)[0]
                key_len,key_addr=struct.unpack_from('<iI',entry,32)
                sizes=struct.unpack_from('<4i',entry,40)
                addrs=struct.unpack_from('<4I',entry,56)
                if state==0 and 0<key_len<16384 and all(0<=s<=2**31-1 for s in sizes):
                    key=(block_stream(root,key_addr,key_len) if key_addr else block_stream(root,address,96+key_len)[96:]).decode('utf-8','replace')
                    flags=struct.unpack_from('<I',entry,72)[0]
                    yield {'key':key,'sizes':sizes,'addrs':addrs,'flags':flags}
                address=nxt
            except (OSError,ValueError,struct.error):break

def record_url(record):
    key=record['key'];start=key.find('http')
    return key[start:] if start>=0 else ''

def block_entries(root,max_bytes,stop,log,records=None):
    for record in (records if records is not None else block_records(root,stop,log)):
        if stop.is_set():return
        if record['flags']&3 or not 0<record['sizes'][1]<=max_bytes:continue
        try:
            body=block_stream(root,record['addrs'][1],record['sizes'][1])
            if len(body)!=record['sizes'][1]:continue
            headers=block_stream(root,record['addrs'][0],min(record['sizes'][0],262144))
            extent=re.search(rb'content-range\s*:\s*bytes\s+(\d+)-(\d+)/(\d+|\*)',headers,re.I)
            if extent and (extent[3]==b'*' or int(extent[1])!=0 or int(extent[2])+1!=int(extent[3]) or len(body)!=int(extent[3])):
                ext=sniff(body[:4096]);url=record_url(record)
                if ext in ('webm','mkv','mp4','mov') and url:
                    yield Asset(None,ext,'部分HTTP视频缓存',url=url,note='缓存只包含部分响应；保存时下载完整原始视频'),url,''
                continue
            yield body,record_url(record),str(root)+' · HTTP 缓存正文'
        except OSError:continue

def sparse_coverage(control,signature,length):
    if len(control)<192:return False
    actual,magic,_,last,last_len=struct.unpack_from('<QIiii',control,0)
    if actual!=signature or magic!=0xc103cac3:return False
    bitmap=int.from_bytes(control[64:192],'little')
    for block in range((length+1023)//1024):
        need=min(1024,length-block*1024)
        if bitmap&(1<<block):continue
        if block!=last or last_len<need:return False
    return True

def sparse_assets(root,records,max_bytes,stop,log):
    """Join only verified, contiguous ranges belonging to one parent generation."""
    groups={};parents={}
    for r in records:
        if r['flags']&1:parents[r['key']]=r
        if r['flags']&2:
            m=re.fullmatch(r'Range_(.*):([0-9a-fA-F]+):([0-9a-fA-F]+)',r['key'])
            if m:groups.setdefault((m[1],int(m[2],16)),{})[int(m[3],16)]=r
    for (base,signature),children in groups.items():
        if stop.is_set():return
        parent=parents.get(base);url=base[base.find('http'):] if 'http' in base else ''
        if not parent or not url or 0 not in children:continue
        first=children[0];temp=None;ext='webm'
        try:
            head=block_stream(root,first['addrs'][1],min(4096,first['sizes'][1]))
            ext=sniff(head)
            if ext not in ('webm','mkv','mp4','mov'):continue
            control=block_stream(root,parent['addrs'][2],min(parent['sizes'][2],192))
            if len(control)<64 or struct.unpack_from('<Q',control)[0]!=signature:continue
            headers=block_stream(root,parent['addrs'][0],min(parent['sizes'][0],262144))
            match=re.search(rb'content-range\s*:\s*bytes\s+\d+-\d+/(\d+)',headers,re.I)
            expected=int(match[1]) if match else (expected_webm_length(head) if ext in ('webm','mkv') else None)
            if not expected:
                match=re.search(rb'content-length\s*:\s*(\d+)',headers,re.I)
                expected=int(match[1]) if match else None
            incomplete=Asset(None,ext,'缓存原始视频地址',url=url,size=expected or 0,
                name=Path(url.split('?')[0]).name,note='缓存未覆盖完整视频；保存时下载原始文件')
            if not expected or expected>max_bytes:
                incomplete.note='视频超过缓存扫描上限或长度未知；保存时下载原始文件'
                yield incomplete;continue
            cache_key=(str(root),base,signature,expected)
            cached=_SPARSE_READY.get(cache_key)
            if cached and cached.path.exists():
                yield inspect_asset(cached);continue
            parts=[];complete=True
            for child_id in range((expected+1048575)//1048576):
                need=min(1048576,expected-child_id*1048576);child=children.get(child_id)
                if not child or child['sizes'][1]<need:complete=False;break
                ctrl=block_stream(root,child['addrs'][2],min(child['sizes'][2],192))
                if not sparse_coverage(ctrl,signature,need):complete=False;break
                parts.append((child,need))
            if not complete:
                log('发现视频缓存缺少分段，已保留原始地址供完整下载。');yield incomplete;continue
            STAGING.mkdir(parents=True,exist_ok=True)
            temp=STAGING/(f'sparse_{signature:x}_{os.getpid()}.part')
            digest=hashlib.sha256()
            with temp.open('wb') as out:
                for child,need in parts:
                    if stop.is_set():return
                    data=block_stream(root,child['addrs'][1],need)
                    if len(data)!=need:raise RuntimeError('缓存分段读取不完整')
                    out.write(data);digest.update(data)
            path=STAGING/(digest.hexdigest()+'.'+ext);os.replace(temp,path);temp=None
            asset=inspect_asset(Asset(path,ext,'Chromium 完整视频缓存（按范围拼接）',name=incomplete.name,
                url=url,digest=digest.hexdigest(),note='缓存候选；完整分段已拼接并通过视频校验'))
            _SPARSE_READY[cache_key]=asset
            yield asset
        except (OSError,ValueError,RuntimeError,struct.error):
            if url:
                yield Asset(None,ext,'缓存原始视频地址',url=url,
                    name=Path(url.split('?')[0]).name,note='缓存未通过完整性校验；保存时下载原始文件')
        finally:
            if temp and temp.exists():temp.unlink()

def simple_body(data):
    if len(data)<72 or struct.unpack_from('<Q',data)[0]!=0xfcfb6d1ba7725c30:return None
    _,version,key_len,_,_=struct.unpack_from('<Q4I',data)
    if not 0<key_len<65536 or 24+key_len>len(data)-48:return None
    magic,flags,crc,size,_=struct.unpack_from('<Q4I',data,len(data)-24)
    if magic!=0xf4fa6f45970d41d8 or size>len(data):return None
    end=len(data)-24-size-(32 if flags&2 else 0)-24
    if end<24+key_len:return None
    magic1,flags1,crc1,_,_=struct.unpack_from('<Q4I',data,end)
    if magic1!=0xf4fa6f45970d41d8:return None
    body=data[24+key_len:end]
    if flags1&1 and zlib.crc32(body)&0xffffffff!=crc1:return None
    key=data[24:24+key_len].decode('utf-8','replace')
    at=key.find('http')
    return body,key[at:] if at>=0 else ''

def scan(roots,on_asset,log,stop,max_mb=512):
    max_bytes=max_mb*1024*1024
    seen=set();counts={'checked':0,'found':0,'unreadable':0,'too_large':0,'invalid':0,
        'directories':0,'missing':0,'unsupported':0,'limited':0,'cancelled':0}
    def add(body,url,source,stamp=0):
        ext=sniff(body[:4096])
        if not ext or ext in ('m3u8','svg'):return
        try:
            path,digest=stage_bytes(body,ext)
            if digest in seen:return
            asset=inspect_asset(Asset(path,ext,source,url=url,timestamp=stamp,digest=digest,note='缓存候选；可能包含历史素材'))
            if not url:
                dims=asset.dimensions.replace(' × ','x')
                asset.name=f'{asset.category}_{dims or ext}_{Path(source).stem}.{ext}'
            seen.add(digest);counts['found']+=1;on_asset(asset)
        except Exception:counts['invalid']+=1
    parsed=set()
    def walk_error(error):counts['unreadable']+=1
    for root in roots:
        if stop.is_set():counts['cancelled']=1;break
        root=Path(root)
        if not root.is_dir():counts['missing']+=1;log('目录不存在：'+str(root));continue
        log('扫描 '+str(root))
        for folder,dirs,files in os.walk(root,onerror=walk_error):
            counts['directories']+=1
            dirs[:]=[d for d in dirs if d.lower() not in SKIP and not Path(folder,d).is_symlink() and not Path(folder,d).is_junction()]
            folder=Path(folder)
            sparse_files=set()
            if 'index' in files and 'data_1' in files and folder in parsed:continue
            if 'index' in files and 'data_1' in files and folder not in parsed:
                parsed.add(folder)
                records=list(block_records(folder,stop,log))
                # Indexed bodies must pass HTTP range/coverage checks. Raw discovery
                # must not bypass those checks by reading the same external file.
                sparse_files={f'f_{r["addrs"][1]&0x0fffffff:06x}' for r in records
                    if r['addrs'][1]&0xf0000000==0x80000000}
                for body,url,src in block_entries(folder,max_bytes,stop,log,records):
                    if isinstance(body,Asset):
                        if url not in seen:seen.add(url);counts['found']+=1;on_asset(body)
                    else:add(body,url,src)
                for asset in sparse_assets(folder,records,max_bytes,stop,log):
                    key=asset.digest or asset.url
                    if key not in seen:seen.add(key);counts['found']+=1;on_asset(asset)
            for name in files:
                if stop.is_set():counts['cancelled']=1;return counts
                counts['checked']+=1
                if counts['checked']%100==0:log(f'已检查 {counts["checked"]} 个文件，发现 {counts["found"]} 个素材…')
                if name in sparse_files:continue
                if counts['checked']>30000:
                    counts['limited']=1
                    log('本轮已检查 30,000 个文件；请缩小目录范围继续扫描。');return counts
                suffix=Path(name).suffix.lower()
                if suffix in ('.pak','.vfs','.zip','.bundle','.unity3d'):counts['unsupported']+=1;continue
                if name.startswith(('data_','index','Cookies','LOCK','LOG')) or suffix in ('.db','.log','.ldb','.dll','.exe','.json','.ini','.txt','.xml'):continue
                p=folder/name
                try:
                    before=p.stat()
                    if before.st_size>max_bytes:counts['too_large']+=1;continue
                    if before.st_size<12:continue
                    head=read_shared(p,0,4096)
                    simple=head[:8]==struct.pack('<Q',0xfcfb6d1ba7725c30)
                    if not simple and not sniff(head):continue
                    data=read_shared(p,0,max_bytes+1)
                    after=p.stat()
                    if len(data)!=before.st_size or before.st_size!=after.st_size or before.st_mtime_ns!=after.st_mtime_ns:
                        counts['invalid']+=1;continue
                    url=''
                    if simple:
                        extracted=simple_body(data)
                        if not extracted:counts['invalid']+=1;continue
                        data,url=extracted
                    add(data,url,str(p),before.st_mtime)
                except OSError:counts['unreadable']+=1
    return counts

def scan_summary(c):
    state='扫描已停止' if c.get('cancelled') else '扫描达到上限' if c.get('limited') else '扫描完成'
    text=f'{state}：检查 {c["checked"]} 个文件，识别 {c["found"]} 个媒体；不可读 {c["unreadable"]}，超过大小上限 {c["too_large"]}，未完成/无效 {c["invalid"]}。'
    if c.get('missing'):text+=f' {c["missing"]} 个目录已不存在，请重新选择。'
    if c.get('unsupported'):text+=f' 跳过 {c["unsupported"]} 个暂不支持的资源包；资源包不等于加密。'
    if not c['found'] and not c.get('cancelled'):
        if not c.get('directories'):text+=' 未能读取素材目录，请检查路径或访问权限。'
        else:text+=' 这些目录中没有识别到完整媒体；可以先在目标软件加载图片/视频，再重扫或手动选择素材目录。'
        text+=' 扫描无结果不能判断资源是否加密。'
    return text
