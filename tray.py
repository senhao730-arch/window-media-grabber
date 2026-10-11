"""Windows notification-area icon. All actions are queued to the Tk thread."""
import threading
from pathlib import Path
from PIL import Image
import pystray


class Tray:
    def __init__(self, send, title, hotkeys_enabled):
        self.send = send
        self.ready = threading.Event()
        self.failed = None
        self.hotkeys_enabled = hotkeys_enabled
        with Image.open(Path(__file__).resolve().parent / 'assets/app-icon.png') as im:
            image = im.convert('RGBA').resize((64, 64), Image.Resampling.LANCZOS)
        def action(name):
            return lambda icon, item: send('tray_action', name)
        self.icon = pystray.Icon('WindowMediaGrabber', image, title, pystray.Menu(
            pystray.MenuItem('显示窗口', action('show'), default=True),
            pystray.MenuItem('打开保存文件夹', action('folder')),
            pystray.MenuItem('启用快捷键', action('hotkeys'), checked=lambda _: self.hotkeys_enabled),
            pystray.MenuItem('停止保存任务', action('stop')),
            pystray.MenuItem('停止录制并保存', action('record_stop')),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('退出程序（等待保存完成）', action('exit')),
        ))
        self.thread = threading.Thread(target=self.run, name='TrayIcon', daemon=True)

    def run(self):
        def setup(icon):
            try:
                icon.visible = True
                self.ready.set()
            except Exception as exc:
                self.failed = str(exc)
        try:
            self.icon.run(setup)
        except Exception as exc:
            self.failed = str(exc)
        finally:
            if not self.ready.is_set() and self.failed is None:
                self.failed = '托盘图标未能启动'

    def start(self):
        self.thread.start()

    def update(self, enabled):
        self.hotkeys_enabled = enabled
        if self.ready.is_set():
            self.icon.update_menu()

    def stop(self):
        self.icon.stop()
        if self.thread.is_alive():
            self.thread.join(timeout=2)
