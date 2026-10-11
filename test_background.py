import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch
from main import App
from media import STATE
from background_check import verify_background


class BackgroundTests(unittest.TestCase):
    def app(self):
        root=tk.Tk()
        with patch.object(App,'toggle_hotkeys',lambda _:None),patch.object(App,'persist',lambda _:None):
            app=App(root)
        return root,app

    def test_real_tray_background_conversion_and_restore(self):
        root,app=self.app()
        verify_background(app)
        root.mainloop()
        report=(STATE/'tray-smoke.txt').read_text('utf-8')
        self.assertIn('PACKAGED_BACKGROUND_SAVE_OK',report)
        self.assertIn('PACKAGED_RESTORE_OK',report)
        self.assertTrue(app.destroyed)
        self.assertIsNone(app.tray)

    def test_explicit_exit_waits_for_save_and_blocks_new_jobs(self):
        root,app=self.app();release=threading.Event();completed=[]
        def save():
            release.wait(3)
            completed.append(not app.job_stop.is_set())
        app.job(save);app.request_exit()
        self.assertTrue(app.closing)
        self.assertFalse(app.job_stop.is_set())
        self.assertFalse(app.job(lambda:None))
        self.assertFalse(app.destroyed)
        root.after(100,release.set);root.mainloop()
        self.assertEqual(completed,[True]);self.assertTrue(app.destroyed)

    def test_tray_failure_keeps_window_accessible(self):
        root,app=self.app();root.update()
        try:
            with patch('tray.Tray',side_effect=RuntimeError('fixture unavailable')):
                app.close()
            self.assertEqual(root.state(),'normal')
            self.assertFalse(app.background);self.assertFalse(app.job_stop.is_set())
            self.assertIn('窗口保持打开',app.status.get())
        finally:app.request_exit()
