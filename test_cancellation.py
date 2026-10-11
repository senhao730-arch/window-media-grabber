"""Cancellation regressions: actual copying, codec processes and GUI controls."""
import multiprocessing
import subprocess
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import media
from media import Asset,TaskCancelled,save_asset,run_ffmpeg,validate_video

ROOT=Path(__file__).resolve().parents[1]/'test-data/cancellation'

class CancellationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ROOT.mkdir(parents=True,exist_ok=True)
        cls.image=ROOT/'image.png'
        Image.new('RGB',(320,180),'#1479f8').save(cls.image)
        cls.video=ROOT/'video.mp4'
        run_ffmpeg(['-f','lavfi','-i','testsrc=size=160x90:rate=12','-t','2','-an',
                    '-c:v','libx264','-pix_fmt','yuv420p',str(cls.video)])

    def test_cancelled_cached_validation_and_fast_conversion(self):
        asset=Asset(self.video,'mp4','fixture');validate_video(asset,full=True)
        stop=threading.Event();stop.set()
        with self.assertRaises(TaskCancelled):validate_video(asset,full=True,stop=stop)
        with self.assertRaises(TaskCancelled):save_asset(asset,ROOT/'already-cancelled',stop=stop)
        self.assertFalse((ROOT/'already-cancelled').exists())
        run_ffmpeg(['-i',str(self.video),'-f','null','-'],threading.Event())

    def test_cancel_while_full_validation_and_encoding_are_running(self):
        processes=[]
        real_popen=subprocess.Popen
        def launch(*args,**kwargs):
            process=real_popen(*args,**kwargs);processes.append(process);return process
        for mode in ('validate','encode'):
            stop=threading.Event()
            timer=threading.Timer(.45,stop.set)
            timer.start();started=time.monotonic()
            try:
                with patch.object(media.subprocess,'Popen',side_effect=launch):
                    with self.assertRaises(TaskCancelled):
                        if mode=='encode':
                            run_ffmpeg(['-re','-f','lavfi','-i','testsrc=size=160x90:rate=12',
                                        '-t','60','-c:v','libx264','-f','null','-'],stop)
                        else:
                            # Pace an actual decoder so cancellation happens mid-run,
                            # even on fast computers and for this short fixture.
                            def decoder(*args,**kwargs):
                                command=list(args[0]);command.insert(command.index('-i'),'-re')
                                return launch(command,**kwargs)
                            with patch.object(media.subprocess,'Popen',side_effect=decoder):
                                validate_video(Asset(self.video,'mp4','fixture'),full=True,stop=stop)
                self.assertLess(time.monotonic()-started,2.5)
                self.assertIsNotNone(processes[-1].poll(),'Cancelled FFmpeg still running')
            finally:timer.cancel()

    def test_cancel_at_encoder_completion_does_not_publish_file(self):
        stop=threading.Event();real_popen=subprocess.Popen
        def launch(*args,**kwargs):
            process=real_popen(*args,**kwargs);real_communicate=process.communicate
            def completed(*args,**kwargs):
                result=real_communicate(*args,**kwargs);stop.set();return result
            process.communicate=completed;return process
        destination=ROOT/f'completion-{time.time_ns()}'
        asset=Asset(self.video,'mp4','fixture',name='clip')
        validate_video(asset,full=True)
        with patch.object(media.subprocess,'Popen',side_effect=launch):
            with self.assertRaises(TaskCancelled):save_asset(asset,destination,'MP4','省空间（480p）',stop)
        self.assertFalse(list(destination.rglob('*.mp4')))

    def test_original_copy_cancelled_from_actual_stop_button(self):
        from main import App
        source=ROOT/'large-original.png'
        with source.open('wb') as f:
            f.write(self.image.read_bytes());f.truncate(512*1024*1024)
        destination=ROOT/f'copy-{time.time_ns()}'
        root=tk.Tk();root.withdraw()
        with patch.object(App,'toggle_hotkeys',lambda _:None),patch.object(App,'persist',lambda _:None):
            app=App(root);app.folder.set(str(destination))
            app.add_asset(Asset(source,'png','fixture',name='original.png',digest='copyfixture'))
            app.tree.selection_set('copyfixture')
            app.export();deadline=time.monotonic()+8;stopped=False;cancel_time=0
            try:
                while time.monotonic()<deadline:
                    root.update()
                    partial=next(destination.rglob('*.working.png'),None) if destination.exists() else None
                    if not stopped and partial and 0<partial.stat().st_size<source.stat().st_size:
                        app.stop_job();stopped=True;cancel_time=time.monotonic()
                    if stopped and not app.busy:break
                    time.sleep(.005)
                self.assertTrue(stopped,'Cancellation was never triggered during copying')
                self.assertFalse(app.busy,'Stop left the application busy')
                self.assertLess(time.monotonic()-cancel_time,2)
                self.assertFalse(list(destination.rglob('*.png')),'Cancelled output left behind')
                logs=app.logs.get('1.0','end')
                self.assertIn('保存已停止：成功 0，失败 0，未处理 1',logs)
                self.assertNotIn('处理失败',logs)
                # The very next job must be usable, with a fresh cancellation token.
                app.clear_assets();app.add_asset(Asset(self.image,'png','fixture',name='good.png',digest='nextfixture'))
                app.tree.selection_set('nextfixture');app.export()
                deadline=time.monotonic()+5
                while app.busy and time.monotonic()<deadline:root.update();time.sleep(.01)
                self.assertFalse(app.busy)
                self.assertEqual(len(list(destination.rglob('*.png'))),1)
            finally:
                app.job_stop.set();app.job_thread.join(3);app.edge.close()
                for timer in root.tk.call('after','info'):root.after_cancel(timer)
                root.destroy();source.unlink(missing_ok=True)

    def test_image_worker_cancel_and_success(self):
        large=ROOT/'large-image.bmp'
        Image.new('RGB',(6000,6000),'#1691de').save(large)
        before={process.pid for process in multiprocessing.active_children()}
        stop=threading.Event();timer=threading.Timer(.12,stop.set)
        destination=ROOT/f'image-{time.time_ns()}'
        timer.start();started=time.monotonic()
        try:
            with self.assertRaises(TaskCancelled):
                save_asset(Asset(large,'bmp','fixture',name='large'),destination,'WebP','原始画质',stop)
            self.assertLess(time.monotonic()-started,3)
            self.assertFalse(list(destination.rglob('*.webp')))
            self.assertEqual({p.pid for p in multiprocessing.active_children()},before)
            good=save_asset(Asset(self.image,'png','fixture',name='good'),destination,'JPEG','省空间（480p）',threading.Event())
            with Image.open(good) as im:self.assertEqual(im.size,(320,180))
        finally:timer.cancel();large.unlink(missing_ok=True)

if __name__=='__main__':
    multiprocessing.freeze_support()
    unittest.main()
