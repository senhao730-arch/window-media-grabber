"""Meaningful end-to-end checks. Everything generated lives under work/test-data."""
import base64
import hashlib
import http.server
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import unittest
from functools import partial
from pathlib import Path
from PIL import Image
from media import Asset,inspect_asset,save_asset,sniff,FFMPEG,run_ffmpeg
from scanner import scan,simple_body,suggested_roots
from native import Hotkeys,user32,Window
from browser import Edge

ROOT=Path(__file__).resolve().parents[1]/'test-data';ROOT.mkdir(parents=True,exist_ok=True)

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images=ROOT/'fixtures';cls.images.mkdir(exist_ok=True)
        Image.new('RGB',(640,360),'#2786bb').save(cls.images/'photo.png')
        frames=[Image.new('RGB',(160,90),c) for c in ('red','green','blue')]
        frames[0].save(cls.images/'animated.gif',save_all=True,append_images=frames[1:],duration=150,loop=0)
        frames[0].save(cls.images/'animated.webp',save_all=True,append_images=frames[1:],duration=150,loop=0)
        run_ffmpeg(['-f','lavfi','-i','testsrc=size=160x90:rate=12','-t','2','-an','-c:v','libx264','-pix_fmt','yuv420p',str(cls.images/'clip.mp4')])
        run_ffmpeg(['-i',str(cls.images/'clip.mp4'),'-c:v','copy','-an','-hls_time','1','-hls_list_size','0',str(cls.images/'stream.m3u8')])
    def test_original_and_animation(self):
        for name in ('photo.png','animated.gif','animated.webp','clip.mp4'):
            p=self.images/name;a=inspect_asset(Asset(p,p.suffix[1:],'fixture',name=name))
            dest=save_asset(a,ROOT/'saved')
            self.assertEqual(hashlib.sha256(p.read_bytes()).digest(),hashlib.sha256(dest.read_bytes()).digest())
            if name.startswith('animated'):self.assertEqual(a.category,'动图')
        a=inspect_asset(Asset(self.images/'animated.webp','webp','fixture',name='motion'))
        out=save_asset(a,ROOT/'saved','GIF')
        with Image.open(out) as im:self.assertGreater(im.n_frames,1)
        with self.assertRaises(RuntimeError):save_asset(a,ROOT/'saved','PNG')
    def test_conversion_and_cache(self):
        a=inspect_asset(Asset(self.images/'photo.png','png','fixture',name='photo'))
        out=save_asset(a,ROOT/'saved','JPEG','省空间（480p）')
        with Image.open(out) as im:self.assertEqual(im.size,(640,360))  # Never enlarge.
        cache=ROOT/'cache';cache.mkdir(exist_ok=True)
        body=(self.images/'photo.png').read_bytes();key=b'https://example.invalid/photo.png'
        header=struct.pack('<Q4I',0xfcfb6d1ba7725c30,9,len(key),0,0)
        footer1=struct.pack('<Q4I',0xf4fa6f45970d41d8,0,0,0,0)
        footer0=struct.pack('<Q4I',0xf4fa6f45970d41d8,0,0,0,0)
        (cache/'abc_0').write_bytes(header+key+body+footer1+footer0)
        (cache/'rawfile').write_bytes(body)
        (cache/'badpng').write_bytes(b'\x89PNG\r\n\x1a\n' + b'invalid'*10)
        candidates=[];counts=scan([cache],candidates.append,lambda _:None,threading.Event())
        self.assertEqual(counts['found'],1);self.assertEqual(counts['invalid'],1)
        self.assertEqual(simple_body((cache/'abc_0').read_bytes())[0],body)
    def test_hotkeys_release(self):
        hk=Hotkeys(lambda *args:None);thread=threading.Thread(target=hk.run,daemon=True);thread.start()
        for _ in range(30):
            if len(hk.registered)==4:break
            time.sleep(.05)
        self.assertEqual(len(hk.registered),4)
        hk.close();thread.join(2);self.assertFalse(thread.is_alive())
        self.assertTrue(user32.RegisterHotKey(None,500,0x4000|2|1,0x75))
        user32.UnregisterHotKey(None,500)
    def test_real_hyp_cache(self):
        cache=Path(os.environ['APPDATA'])/'miHoYo/HYP/1_1/fedata/Cache'
        if not cache.exists():self.skipTest('No HYP cache on this computer')
        out=[];counts=scan([cache],out.append,lambda _:None,threading.Event())
        self.assertGreater(counts['found'],0)
        png=next(a for a in out if a.ext=='png')
        dest=save_asset(png,ROOT/'real-saved')
        self.assertEqual(dest.read_bytes(),png.path.read_bytes())
        roots=suggested_roots(Window(0,0,'米哈游启动器','HYP.exe','',True))
        self.assertIn(cache,roots)
        (ROOT/'hyp-results.json').write_text(json.dumps({'counts':counts,'formats':{e:sum(a.ext==e for a in out) for e in {a.ext for a in out}}},indent=2),'utf-8')
    def test_edge_dom_network_original_and_hls(self):
        # Isolated local fixture, no user pages, credentials or account changes.
        html='<html><title>Media Grabber Test</title><img src="/photo.png"><img src="/animated.gif"><video src="/clip.mp4"></video></html>'
        (self.images/'index.html').write_text(html,'utf-8')
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(self.images)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));debug=sock.getsockname()[1]
        profile=ROOT/('edge-profile-'+str(time.time_ns()))
        p=subprocess.Popen([r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe','--headless=new','--no-first-run',
            f'--user-data-dir={profile}',f'--remote-debugging-port={debug}','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
        e=Edge(lambda a:assets.append(a),lambda _:None);e.port=debug;assets=[]
        try:
            url=f'http://127.0.0.1:{server.server_port}/index.html'
            import requests
            for _ in range(80):
                try:
                    r=e.session.put(f'http://127.0.0.1:{debug}/json/new?'+url,timeout=1)
                    target=r.json();break
                except Exception:time.sleep(.2)
            else:self.fail('Headless Edge did not start')
            time.sleep(1);e.connect(target)
            self.assertTrue(any('/photo.png' in a.url for a in assets))
            candidate=next(a for a in assets if '/photo.png' in a.url)
            ready=e.download(candidate,threading.Event())
            self.assertEqual(ready.path.read_bytes(),(self.images/'photo.png').read_bytes())
            # Observe actual browser network response bodies after reloading the fixture.
            e.cdp.call('Page.reload',{'ignoreCache':True})
            for _ in range(80):
                if any(a.path and '/animated.gif' in a.url for a in assets):break
                time.sleep(.1)
            self.assertTrue(any(a.path and '/animated.gif' in a.url for a in assets))
            stream=e.url_asset(f'http://127.0.0.1:{server.server_port}/stream.m3u8','视频')
            ready=e.download(stream,threading.Event())
            self.assertEqual(sniff(ready.path.read_bytes()[:100]),'mp4')
            self.assertGreater(ready.size,100)
        finally:
            e.close();p.terminate()
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait()
            server.shutdown();server.server_close()

if __name__=='__main__':unittest.main(verbosity=2)
