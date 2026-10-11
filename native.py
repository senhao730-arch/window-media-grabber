"""Small Windows helpers for window and desktop capture targets."""
import ctypes as C
from ctypes import wintypes as W
import os
import msvcrt
import threading
from dataclasses import dataclass
import psutil

user32 = C.WinDLL('user32', use_last_error=True)
kernel32 = C.WinDLL('kernel32', use_last_error=True)
user32.GetForegroundWindow.restype = W.HWND
user32.GetWindowTextLengthW.argtypes = [W.HWND]
user32.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
user32.IsWindowVisible.argtypes = [W.HWND]
user32.IsIconic.argtypes = [W.HWND]
user32.IsWindow.argtypes = [W.HWND]
user32.GetAncestor.argtypes = [W.HWND,W.UINT]
user32.GetAncestor.restype = W.HWND
user32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
kernel32.CreateFileW.argtypes = [W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE]
kernel32.CreateFileW.restype = W.HANDLE

@dataclass
class Window:
    hwnd: int
    pid: int
    title: str
    process: str
    path: str
    minimized: bool
    desktop: bool=False
    bounds: tuple=()

    @property
    def label(self):
        if self.desktop:return self.title
        return f'{self.title}  [{self.process} · {self.pid}]' + (' （最小化）' if self.minimized else '')

def desktops():
    class MonitorInfo(C.Structure):
        _fields_=[('size',W.DWORD),('monitor',W.RECT),('work',W.RECT),('flags',W.DWORD),('device',W.WCHAR*32)]
    user32.GetMonitorInfoW.argtypes=[W.HANDLE,C.POINTER(MonitorInfo)]
    found=[]
    callback=C.WINFUNCTYPE(W.BOOL,W.HANDLE,W.HDC,C.POINTER(W.RECT),W.LPARAM)
    @callback
    def collect(handle,dc,rect,param):
        info=MonitorInfo();info.size=C.sizeof(info)
        if user32.GetMonitorInfoW(handle,C.byref(info)):
            r=info.monitor;bounds=(r.left,r.top,r.right,r.bottom)
            title='桌面 · '+('主屏' if info.flags&1 else '屏幕')+' '+info.device.rsplit('\\',1)[-1]+f'（{r.right-r.left} × {r.bottom-r.top}）'
            found.append(Window(0,0,title,'桌面','',False,True,bounds))
        return True
    user32.EnumDisplayMonitors(None,None,collect,0)
    if not found:return []
    bounds=(min(w.bounds[0] for w in found),min(w.bounds[1] for w in found),max(w.bounds[2] for w in found),max(w.bounds[3] for w in found))
    return [Window(0,0,'整个桌面（全部屏幕）','桌面','',False,True,bounds)]+found

def window_info(hwnd):
    title = C.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd)+1)
    user32.GetWindowTextW(hwnd, title, len(title))
    pid=W.DWORD()
    user32.GetWindowThreadProcessId(hwnd,C.byref(pid))
    name='未知进程'; path=''
    try:
        p=psutil.Process(pid.value); name=p.name()
        try: path=p.exe()
        except (psutil.AccessDenied,psutil.NoSuchProcess): pass
    except (psutil.AccessDenied,psutil.NoSuchProcess): pass
    return Window(int(hwnd),pid.value,title.value,name,path,bool(user32.IsIconic(hwnd)))

def windows():
    found=[]
    callback=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    @callback
    def collect(hwnd,_):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd)>0:
            info=window_info(hwnd)
            if info.pid!=os.getpid(): found.append(info)
        return True
    user32.EnumWindows(collect,0)
    return sorted(found,key=lambda w:w.title.casefold())

def shared_open(path):
    """Respect ACLs, allow the owning app to retain read/write/delete handles."""
    handle=kernel32.CreateFileW(str(path),0x80000000,7,None,3,0x80,None)
    if handle==C.c_void_p(-1).value:
        raise C.WinError(C.get_last_error())
    try: fd=msvcrt.open_osfhandle(int(handle),os.O_RDONLY|os.O_BINARY)
    except Exception:
        kernel32.CloseHandle(handle); raise
    return os.fdopen(fd,'rb')

def read_shared(path,offset=0,size=-1):
    with shared_open(path) as f:
        f.seek(offset); return f.read(size)

def set_dpi():
    try: user32.SetProcessDpiAwarenessContext(C.c_void_p(-4))
    except Exception: pass

def set_app_id():
    # Give the desktop app its own taskbar identity rather than Python's group.
    try:C.windll.shell32.SetCurrentProcessExplicitAppUserModelID('WindowMediaGrabber.Desktop')
    except OSError:pass

class Hotkeys:
    def __init__(self,send):
        self.send=send; self.tid=None; self.registered=[]; self.stopping=threading.Event()
    def run(self):
        self.tid=kernel32.GetCurrentThreadId()
        if self.stopping.is_set():return
        # Ctrl + Alt + F6/F7/F8/F9: select+scan / screenshot / GIF / video.
        for i,key in enumerate([0x75,0x76,0x77,0x78],1):
            if user32.RegisterHotKey(None,i,0x4000|2|1,key): self.registered.append(i)
            else: self.send('log',f'快捷键 Ctrl+Alt+F{i+5} 注册失败，可能已被其他软件占用。')
        msg=W.MSG()
        while not self.stopping.is_set() and user32.GetMessageW(C.byref(msg),None,0,0)>0:
            if msg.message==0x312:
                hwnd=user32.GetForegroundWindow()
                self.send('hotkey',(int(msg.wParam),window_info(hwnd)))
        for i in self.registered:user32.UnregisterHotKey(None,i)
    def close(self):
        self.stopping.set()
        if self.tid: user32.PostThreadMessageW(self.tid,0x12,0,0)
