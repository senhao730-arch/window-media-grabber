"""Packaged regression: real tray, background save, restore and orderly exit."""
import threading
import time
import traceback
from PIL import Image
from media import STATE, Asset, save_asset


def verify_background(app):
    folder=STATE/'smoke/background'
    folder.mkdir(parents=True,exist_ok=True)
    source=folder/'fixture.png'
    Image.new('RGB',(640,360),'#1479f8').save(source)
    release=threading.Event();result=[];started=time.monotonic()
    def work():
        if not release.wait(12):raise RuntimeError('Background smoke release timed out')
        result.append(save_asset(Asset(source,'png','smoke',name='background'),folder,'JPEG','原始画质',app.job_stop))
    app.job(work);app.close()
    def poll():
        try:
            if time.monotonic()-started>20:raise RuntimeError('Background smoke timed out')
            if not release.is_set():
                if app.tray and app.tray.failed:raise RuntimeError(app.tray.failed)
                if app.background:
                    assert app.root.state()=='withdrawn' and app.busy
                    assert not app.job_stop.is_set() and not app.closing
                    assert app.tray.icon.visible
                    release.set()
            elif not app.busy:
                assert len(result)==1
                with Image.open(result[0]) as im:im.verify()
                app.send('tray_action','show')
                app.root.after(200,finish);return
            app.root.after(50,poll)
        except Exception:
            (STATE/'tray-smoke.txt').write_text('FAILED\n'+traceback.format_exc(),'utf-8')
            release.set();app.request_exit()
    def finish():
        try:
            assert not app.background and app.root.state()=='normal'
            (STATE/'tray-smoke.txt').write_text('PACKAGED_TRAY_OK\nPACKAGED_BACKGROUND_SAVE_OK\nPACKAGED_RESTORE_OK\n'+str(result[0]),'utf-8')
        except Exception:
            (STATE/'tray-smoke.txt').write_text('FAILED\n'+traceback.format_exc(),'utf-8')
        finally:app.request_exit()
    poll()
