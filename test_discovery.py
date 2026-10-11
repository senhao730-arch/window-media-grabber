"""Discovery, diagnostic and remembered-directory integration regressions."""
import json
import os
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from native import Window
from scanner import discover_roots,scan,scan_summary,unique_roots

ROOT=Path(__file__).resolve().parents[1]/'test-data';ROOT.mkdir(exist_ok=True)

class DiscoveryTests(unittest.TestCase):
    def test_nested_resources_are_discovered_without_scanning_game(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            base=Path(temp);install=base/'install';media=install/'client/ui/res'
            media.mkdir(parents=True);hidden=install/'Game/Content/images';hidden.mkdir(parents=True)
            Image.new('RGB',(40,30),'blue').save(media/'banner.png')
            Image.new('RGB',(40,30),'red').save(hidden/'unrelated.png')
            roaming=base/'roaming';local=base/'local';roaming.mkdir();local.mkdir()
            with patch.dict(os.environ,{'APPDATA':str(roaming),'LOCALAPPDATA':str(local)}):
                window=Window(0,0,'Fixture','fixture.exe',str(install/'fixture.exe'),False)
                self.assertFalse(discover_roots(window,threading.Event(),lambda _:None))
                roots=discover_roots(window,threading.Event(),lambda _:None,expanded=True)
            assets=[];counts=scan(roots,assets.append,lambda _:None,threading.Event())
            self.assertEqual(counts['found'],1);self.assertEqual(assets[0].path.read_bytes(),(media/'banner.png').read_bytes())
            self.assertEqual(unique_roots([media,media/'child',media]),[media.resolve()])

    def test_registry_fallback_for_real_delta_launcher(self):
        path=Path('D:/Delta Force/launcher/tpf_ui/res')
        if not path.exists():self.skipTest('Delta launcher not installed on this host')
        window=Window(0,0,'三角洲行动','delta_force_launcher.exe','',True)
        roots=discover_roots(window,threading.Event(),lambda _:None)
        self.assertIn(path.resolve(),roots)

    def test_empty_missing_package_and_cancel_have_distinct_diagnostics(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            base=Path(temp);(base/'packed.pak').write_bytes(b'ordinary unsupported package')
            counts=scan([base,base/'missing'],lambda _:None,lambda _:None,threading.Event())
            summary=scan_summary(counts)
            self.assertEqual(counts['unsupported'],1);self.assertEqual(counts['missing'],1)
            self.assertIn('资源包不等于加密',summary);self.assertIn('目录已不存在',summary)
            self.assertIn('不能判断资源是否加密',summary)
            stop=threading.Event();stop.set()
            self.assertIn('已停止',scan_summary(scan([base],lambda _:None,lambda _:None,stop)))

    def test_selected_directory_survives_application_restart(self):
        import main
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            base=Path(temp);state=base/'state';state.mkdir()
            (state/'settings.json').write_text(json.dumps({'hotkeys':False}),'utf-8')
            chosen=base/'unusual-materials';chosen.mkdir()
            Image.new('RGB',(40,30),'green').save(chosen/'photo.png')
            window=Window(0,0,'Fixture','memory-fixture.exe',str(base/'install/app.exe'),False)
            with patch.object(main,'STATE',state),patch.dict(os.environ,{'APPDATA':str(base),'LOCALAPPDATA':str(base)}):
                for restart in (False,True):
                    root=tk.Tk();root.withdraw();app=main.App(root)
                    app.selected_window=lambda:window
                    try:
                        if not restart:
                            with patch.object(main.filedialog,'askdirectory',return_value=str(chosen)):app.choose_scan()
                        else:
                            self.assertEqual(app.custom_root.get(),'')
                            self.assertEqual(app.scan_roots[app.scan_key(window)],str(chosen));app.start_scan()
                        deadline=time.monotonic()+10
                        while app.busy and time.monotonic()<deadline:root.update();time.sleep(.02)
                        root.update();app.drain()
                        self.assertFalse(app.busy);self.assertEqual(len(app.items),1)
                    finally:
                        for timer in root.tk.call('after','info'):root.after_cancel(timer)
                        app.request_exit()

if __name__=='__main__':unittest.main(verbosity=2)
