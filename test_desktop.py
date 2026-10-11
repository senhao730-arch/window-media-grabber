"""Actual desktop capture, silent encoding and desktop shortcut/stop controls."""
import json
import subprocess
import tempfile
import threading
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from native import desktops,set_dpi,Window,user32
from capture import screenshot,record
from media import Asset,validate_video,FFMPEG,CREATE_NO_WINDOW

ROOT=Path(__file__).resolve().parents[1]/'test-data/desktop';ROOT.mkdir(parents=True,exist_ok=True)

class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):set_dpi();cls.targets=desktops()

    def test_desktop_bounds_and_screenshot(self):
        self.assertGreaterEqual(len(self.targets),2)
        desktop=self.targets[0];left,top,right,bottom=desktop.bounds
        self.assertEqual((left,top,right-left,bottom-top),tuple(user32.GetSystemMetrics(i) for i in (76,77,78,79)))
        path=screenshot(desktop,ROOT,'PNG','原始画质')
        with Image.open(path) as im:self.assertEqual(im.size,(right-left,bottom-top))
        path=screenshot(self.targets[1],ROOT,'JPEG','省空间（480p）')
        with Image.open(path) as im:self.assertLessEqual(im.height,480);self.assertEqual(im.format,'JPEG')

    def test_desktop_gif_and_silent_video(self):
        outputs=[]
        for fmt in ('GIF','MP4'):
            stop=threading.Event();timer=threading.Timer(2.5,stop.set);timer.start()
            try:path=record(self.targets[0],ROOT,fmt,'省空间（480p）',6,stop,lambda _:None)
            finally:timer.cancel()
            outputs.append(str(path))
            if fmt=='GIF':
                with Image.open(path) as im:self.assertGreater(im.n_frames,1);self.assertLessEqual(im.height,480)
            else:
                asset=Asset(path,'mp4','desktop test');validate_video(asset,full=True)
                self.assertTrue(asset.video_full_checked)
                result=subprocess.run([FFMPEG,'-hide_banner','-i',str(path),'-f','null','-'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=CREATE_NO_WINDOW)
                self.assertEqual(result.returncode,0);self.assertNotIn(b'Audio:',result.stderr)
        (ROOT/'results.json').write_text(json.dumps({'outputs':outputs,'ok':True},ensure_ascii=False,indent=2),'utf-8')

    def test_desktop_shortcuts_stay_selected_and_stop_uses_current_event(self):
        import main
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            state=Path(temp);(state/'settings.json').write_text(json.dumps({'hotkeys':False}),'utf-8')
            with patch.object(main,'STATE',state):
                root=tk.Tk();root.withdraw();app=main.App(root)
                try:
                    app.choose_desktop();self.assertTrue(app.selected_window().desktop)
                    self.assertEqual(app.notebook.index(app.notebook.select()),1)
                    app.hotkey_enabled.set(True);calls=[]
                    app.take_shot=lambda:calls.append(('shot',app.selected_window().desktop))
                    app.toggle_record=lambda fmt:calls.append((fmt,app.selected_window().desktop))
                    active=Window(0,123,'Different foreground app','fixture.exe','',False)
                    for n in (2,3,4):app.send('hotkey',(n,active))
                    app.drain();self.assertEqual(calls,[('shot',True),('GIF',True),('MP4',True)])
                    app.hotkey_enabled.set(False);app.send('hotkey',(2,active));app.drain()
                    self.assertEqual(len(calls),3)
                    def widgets(w):
                        for child in w.winfo_children():yield child;yield from widgets(child)
                    stop_button=next(w for w in widgets(root) if isinstance(w,main.ttk.Button) and w.cget('text')=='停止录制')
                    old=app.record_stop;app.record_stop=threading.Event();stop_button.invoke()
                    self.assertTrue(app.record_stop.is_set());self.assertFalse(old.is_set())
                    app.start_scan();self.assertFalse(app.busy)
                finally:
                    for timer in root.tk.call('after','info'):root.after_cancel(timer)
                    app.close()

if __name__=='__main__':unittest.main(verbosity=2)
