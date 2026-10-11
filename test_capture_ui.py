"""Capture only our own animated Tk fixture, then verify encoded frames."""
import json
import threading
import time
import tkinter as tk
from pathlib import Path
from native import user32,window_info,set_dpi
from capture import screenshot,record
from media import run_ffmpeg

ROOT=Path(__file__).resolve().parents[1]/'test-data';ROOT.mkdir(exist_ok=True)
set_dpi();root=tk.Tk();root.title('Window Media Grabber Capture Test');root.geometry('480x300+80+80')
canvas=tk.Canvas(root,bg='#eee',highlightthickness=0);canvas.pack(fill='both',expand=True)
box=canvas.create_rectangle(10,70,60,120,fill='#1981d1',outline='');canvas.create_text(230,30,text='Capture fixture',font=('Arial',17))
tick=0;finished=threading.Event();errors=[];outputs=[]
def animate():
    global tick
    tick+=1;x=20+tick*4%350;canvas.coords(box,x,70,x+50,120)
    if not finished.is_set():root.after(40,animate)
def worker():
    try:
        hwnd=user32.GetAncestor(root.winfo_id(),2);window=window_info(hwnd)
        outputs.append(str(screenshot(window,ROOT/'captures','PNG','原始画质')))
        for fmt in ('MP4','GIF'):
            stop=threading.Event();timer=threading.Timer(2.5,stop.set);timer.start()
            path=record(window,ROOT/'captures',fmt,'原始画质',12,stop,lambda _:None);outputs.append(str(path));timer.cancel()
            run_ffmpeg(['-i',str(path),'-f','null','-'])
        (ROOT/'capture-results.json').write_text(json.dumps({'outputs':outputs,'ok':True},indent=2),'utf-8')
    except Exception as e:
        errors.append(str(e));(ROOT/'capture-results.json').write_text(json.dumps({'errors':errors,'ok':False},indent=2),'utf-8')
    finally:finished.set()
def start():
    root.update();threading.Thread(target=worker,daemon=True).start()
def poll():
    if finished.is_set():
        for timer in root.tk.call('after','info'):root.after_cancel(timer)
        root.destroy()
    else:root.after(100,poll)
animate();root.after(500,start);root.after(100,poll);root.mainloop()
if errors:raise RuntimeError(errors[0])
print('Window screenshot / MP4 / GIF capture passed')
