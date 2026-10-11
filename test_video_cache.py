"""Regression: real truncated exports and a controlled Chromium v3 sparse cache."""
import struct
import os
import threading
import unittest
from pathlib import Path
from media import Asset,inspect_asset,save_asset,run_ffmpeg
from scanner import scan,sparse_coverage,_SPARSE_READY

ROOT=Path(__file__).resolve().parents[1]/'test-data/video-regression'

def control(signature,length,gap=False):
    full,partial=divmod(length,1024)
    bitmap=(1<<full)-1
    if gap:bitmap &= ~1
    header=struct.pack('<QIiii',signature,0xc103cac3,0,full if partial else -1,partial)
    return header.ljust(64,b'\0')+bitmap.to_bytes(128,'little')

class VideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ROOT.mkdir(parents=True,exist_ok=True)
        cls.clip=ROOT/'clip.mp4'
        run_ffmpeg(['-f','lavfi','-i','testsrc=size=160x90:rate=12','-t','2','-an',
            '-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(cls.clip)])

    def test_truncated_container_and_save_rejected(self):
        bad=ROOT/'truncated.mp4';bad.write_bytes(self.clip.read_bytes()[:-300])
        with self.assertRaises(RuntimeError):inspect_asset(Asset(bad,'mp4','test'))
        with self.assertRaises(RuntimeError):save_asset(Asset(bad,'mp4','test'),ROOT/'bad-save')
        good=inspect_asset(Asset(self.clip,'mp4','test'))
        self.assertTrue(good.video_checked)
        out=save_asset(good,ROOT/'good-save')
        self.assertEqual(out.read_bytes(),self.clip.read_bytes())

    def test_coverage_including_partial_block(self):
        self.assertTrue(sparse_coverage(control(10,2700),10,2700))
        self.assertFalse(sparse_coverage(control(10,2700,True),10,2700))
        self.assertFalse(sparse_coverage(control(10,2700),11,2700))
        self.assertFalse(sparse_coverage(control(10,2700),10,2900))

    def test_mid_video_corruption_rejected_before_final_save(self):
        longer=ROOT/'longer.mp4'
        run_ffmpeg(['-f','lavfi','-i','testsrc2=size=320x180:rate=15','-t','12','-an',
            '-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(longer)])
        data=bytearray(longer.read_bytes());offset=0
        while offset<len(data):
            length=int.from_bytes(data[offset:offset+4],'big')
            if data[offset+4:offset+8]==b'mdat':
                start=offset+8+int((length-8)*.85)
                data[start:offset+length]=bytes(offset+length-start);break
            offset+=length
        corrupt=ROOT/'mid-corrupt.mp4';corrupt.write_bytes(data)
        asset=inspect_asset(Asset(corrupt,'mp4','test'))  # First frame still decodes.
        destination=ROOT/'corrupt-save'
        before=list(destination.rglob('*.mp4')) if destination.exists() else []
        with self.assertRaises(RuntimeError):save_asset(asset,destination)
        self.assertEqual(list(destination.rglob('*.mp4')) if destination.exists() else [],before)

    def test_full_validation_cancelled(self):
        from media import validate_video
        stop=threading.Event();stop.set()
        with self.assertRaisesRegex(RuntimeError,'取消'):
            validate_video(Asset(self.clip,'mp4','test'),full=True,stop=stop)

    def make_cache(self,name,gap=False):
        folder=ROOT/name;folder.mkdir(exist_ok=True)
        body=self.clip.read_bytes();base='1/0/https://example.invalid/clip.mp4';signature=10
        headers=f'content-range:bytes 0-{len(body)-1}/{len(body)}\0'.encode()
        child_control=control(signature,len(body),gap)
        parent_control=control(signature,0)
        for i,data in enumerate((body,child_control,headers,parent_control),1):
            (folder/f'f_{i:06x}').write_bytes(data)
        def entry(key,flags,sizes,addrs):
            b=bytearray(256);key=key.encode()
            struct.pack_into('<iI',b,32,len(key),0)
            struct.pack_into('<4i',b,40,*sizes)
            struct.pack_into('<4I',b,56,*addrs)
            struct.pack_into('<I',b,72,flags);b[96:96+len(key)]=key
            return b
        parent=entry(base,1,(len(headers),0,len(parent_control),0),(0x80000003,0,0x80000004,0))
        child=entry(f'Range_{base}:a:0',2,(0,len(body),len(child_control),0),(0,0x80000001,0x80000002,0))
        (folder/'data_1').write_bytes(bytes(8192)+parent+child)
        index=bytearray(368);struct.pack_into('<II',index,0,0xc103cac3,0x30000)
        (folder/'index').write_bytes(index+struct.pack('<II',0xa0010000,0xa0010001))
        return folder

    def test_v3_cache_joins_and_gap_cannot_bypass(self):
        _SPARSE_READY.clear()
        complete=self.make_cache('complete');assets=[]
        scan([complete],assets.append,lambda _:None,threading.Event())
        self.assertEqual(len(assets),1);self.assertTrue(assets[0].video_checked)
        self.assertEqual(assets[0].path.read_bytes(),self.clip.read_bytes())
        incomplete=self.make_cache('missing-block',True);assets=[]
        # A valid standalone MP4 body must still be rejected when cache coverage has a hole.
        scan([incomplete,incomplete],assets.append,lambda _:None,threading.Event())
        self.assertEqual(len(assets),1);self.assertIsNone(assets[0].path)
        self.assertEqual(assets[0].url,'https://example.invalid/clip.mp4')

    def test_partial_http_range_cannot_bypass_via_standalone_file(self):
        folder=self.make_cache('http-partial')
        body=self.clip.read_bytes()
        headers=f'content-range:bytes 0-{len(body)-1}/{len(body)+1000}\0'.encode()
        (folder/'f_000003').write_bytes(headers)
        entries=bytearray((folder/'data_1').read_bytes())
        struct.pack_into('<4i',entries,8192+40,len(headers),len(body),0,0)
        struct.pack_into('<4I',entries,8192+56,0x80000003,0x80000001,0,0)
        struct.pack_into('<I',entries,8192+72,0)
        (folder/'data_1').write_bytes(entries)
        index=bytearray((folder/'index').read_bytes());index[372:376]=bytes(4)
        (folder/'index').write_bytes(index)
        assets=[];scan([folder],assets.append,lambda _:None,threading.Event())
        self.assertEqual(len(assets),1);self.assertIsNone(assets[0].path)
        self.assertEqual(assets[0].url,'https://example.invalid/clip.mp4')

    def test_actual_seven_broken_exports(self):
        fixture=os.environ.get('WMG_TRUNCATED_FIXTURE_DIR')
        if not fixture:self.skipTest('Set WMG_TRUNCATED_FIXTURE_DIR to test external truncated WebM fixtures')
        paths=list(Path(fixture).glob('*.webm'))
        if not paths:self.skipTest('Original broken exports unavailable')
        self.assertEqual(len(paths),7)
        for p in paths:
            with self.subTest(file=p.name):
                self.assertEqual(p.stat().st_size,1048576)
                with self.assertRaises(RuntimeError):inspect_asset(Asset(p,'webm','regression'))

if __name__=='__main__':unittest.main(verbosity=2)
