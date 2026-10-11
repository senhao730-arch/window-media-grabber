import os
import subprocess
import threading
import time
from pathlib import Path
from PIL import Image,ImageGrab
from native import user32
from media import FFMPEG,CREATE_NO_WINDOW,Asset,save_asset,scale_filter,STATE,validate_video

class Surface:
    def __init__(self,hwnd):
        from windows_capture import WindowsCapture
        self.lock=threading.Lock();self.first=threading.Event();self.latest=None;self.closed=False
        self.capture=WindowsCapture(cursor_capture=False,draw_border=True,window_hwnd=hwnd)
        @self.capture.event
        def on_frame_arrived(frame,control):
            with self.lock:self.latest=(frame.frame_buffer.copy(),frame.width,frame.height)
            self.first.set()
        @self.capture.event
        def on_closed():self.closed=True
        self.control=self.capture.start_free_threaded()
    def frame(self):
        with self.lock:return self.latest
    def close(self):
        try:self.control.stop()
        except Exception:pass

class DesktopSurface:
    """Capture the visible desktop, including displays left of the primary screen."""
    def __init__(self,bounds):
        self.bounds=bounds;self.closed=False;self.first=threading.Event()
        self.initial=self._grab();self.first.set()
    def _grab(self):
        import numpy as np
        try:im=ImageGrab.grab(bbox=self.bounds,all_screens=True,include_layered_windows=True).convert('RGBA')
        except OSError:raise RuntimeError('无法读取桌面画面，请确认显示器已连接且桌面未锁定。')
        data=np.asarray(im)[:,:,[2,1,0,3]].copy()
        return data,im.width,im.height
    def frame(self):
        if self.initial is not None:
            first=self.initial;self.initial=None;return first
        return self._grab()
    def close(self):self.closed=True

def open_surface(window):return DesktopSurface(window.bounds) if window.desktop else Surface(window.hwnd)

def ensure_window(window):
    if window.desktop:
        if len(window.bounds)!=4 or window.bounds[2]<=window.bounds[0] or window.bounds[3]<=window.bounds[1]:
            raise RuntimeError('桌面范围无效，请刷新目标列表。')
        return
    if not user32.IsWindow(window.hwnd):raise RuntimeError('目标窗口已关闭。')
    if user32.IsIconic(window.hwnd):raise RuntimeError('截图和录屏需要窗口恢复；原始资源提取可在最小化时使用。')

def screenshot(window,folder,fmt,quality):
    ensure_window(window)
    surface=open_surface(window)
    try:
        if not surface.first.wait(8):raise RuntimeError('窗口没有提供画面：可能被保护、权限不足或停止绘制。')
        data,w,h=surface.frame()
        im=Image.frombytes('RGBA',(w,h),data.tobytes(),'raw','BGRA').convert('RGB')
        staging=STATE/'staging';staging.mkdir(parents=True,exist_ok=True)
        temp=staging/f'screenshot_{threading.get_ident()}.png';im.save(temp)
        try:return save_asset(Asset(temp,'png','桌面截图' if window.desktop else '窗口截图',name=window.title+'.png'),folder,fmt,quality)
        finally:temp.unlink(missing_ok=True)
    finally:surface.close()

def record(window,folder,fmt,quality,fps,stop,log):
    ensure_window(window)
    ext=fmt.lower();is_gif=ext=='gif'
    if ext not in ('gif','mp4','webm','mkv'):raise RuntimeError('录制格式请选择 GIF、MP4、WebM 或 MKV。')
    surface=open_surface(window);p=None;err_file=None;partial=None
    try:
        if not surface.first.wait(8):raise RuntimeError('窗口没有提供画面，无法开始录制。')
        data,w,h=surface.frame()
        folder=Path(folder)/('动图' if is_gif else '视频');folder.mkdir(parents=True,exist_ok=True)
        name=f'{time.strftime("%Y%m%d_%H%M%S")}_{"桌面录制" if window.desktop else "窗口录制"}_{time.time_ns()%1000000}'
        dest=folder/(name+'.'+ext);partial=folder/(name+'.working.'+ext)
        args=[FFMPEG,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','bgra',
            '-s',f'{w}x{h}','-r',str(fps),'-i','pipe:0','-an','-vf',scale_filter(quality)]
        if is_gif:args+=['-loop','0']
        elif ext=='webm':args+=['-c:v','libvpx-vp9','-crf','30','-b:v','0','-deadline','realtime']
        else:args+=['-c:v','libx264','-preset','veryfast','-crf','18' if quality=='原始画质' else '23','-pix_fmt','yuv420p']
        if ext=='mp4':args+=['-movflags','+faststart']
        STATE.mkdir(parents=True,exist_ok=True)
        err_file=(STATE/'encoder-errors.tmp').open('wb+')
        p=subprocess.Popen(args+[str(partial)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=err_file,creationflags=CREATE_NO_WINDOW)
        start=time.monotonic();n=0;last_log=start
        while not stop.is_set() and not surface.closed:
            if not window.desktop and user32.IsIconic(window.hwnd):
                log('目标窗口最小化，已结束画面录制；原始资源提取仍可继续。');break
            frame=surface.frame()
            if frame:
                data,fw,fh=frame
                if (fw,fh)!=(w,h):
                    # Keep encoder dimensions stable if the user resizes the window.
                    import cv2
                    data=cv2.resize(data,(w,h))
                p.stdin.write(data.tobytes());n+=1
            due=start+n/fps
            stop.wait(max(0,due-time.monotonic()))
            if time.monotonic()-last_log>2:
                log(f'正在录制：{int(time.monotonic()-start)} 秒；再次按快捷键或点击停止结束。');last_log=time.monotonic()
            # Stop if the GPU supplies no surface, rather than silently recording forever.
            if p.poll() is not None:raise RuntimeError('编码器提前退出，请检查剩余磁盘空间。')
        p.stdin.close()
        try:p.wait(timeout=30)
        except subprocess.TimeoutExpired:p.kill();p.wait();raise RuntimeError('编码器结束超时，文件未完成。')
        if p.returncode or not n or not partial.stat().st_size:raise RuntimeError('录制未能生成有效文件。')
        if not is_gif:validate_video(Asset(partial,ext,'录制输出'))
        os.replace(partial,dest);return dest
    finally:
        surface.close()
        if p and p.poll() is None:p.kill();p.wait()
        if err_file:err_file.close()
        if partial and partial.exists():partial.unlink()
