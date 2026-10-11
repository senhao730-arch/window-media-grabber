"""Window Media Grabber — local Windows desktop application."""
import json
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from PIL import ImageTk
from native import windows,desktops,window_info,user32,set_dpi,set_app_id,Hotkeys
from media import STATE,Asset,save_asset,preview,validate_video
from scanner import scan,discover_roots,unique_roots,scan_summary
from browser import Edge

TITLE='窗口媒体抓取器 1.5'
QUALITIES=['原始画质','高画质（1080p）','均衡（720p）','省空间（480p）']
FORMATS=['保留原始格式','PNG','JPEG','WebP','GIF','MP4','WebM','MKV']
HELP='''快速开始

桌面抓取：顶部“抓取目标”可选择“整个桌面（全部屏幕）”或某一块屏幕。切换到“桌面 / 窗口”，点击截图或录制按钮，支持画质、格式和帧率设置，默认保存到 D:\\抓取内容。选择桌面后，Ctrl+Alt+F7/F8/F9会一直操作该桌面，即使其他软件在前台；Ctrl+Alt+F6仍用于选中活动软件并扫描缓存。快捷键可随时关闭。

桌面抓取保存屏幕上实际可见的画面，包含打开的窗口和本程序；可在开始录制后最小化本程序，录制继续。它不会从画面还原原始图片或视频文件。要提取原始文件，请选软件窗口扫描缓存或使用抓取用Edge。受保护的画面、锁屏可能无法录制。显示器排列改变后请刷新目标列表。多屏合成时，屏幕之间的空隙显示为黑色。

米哈游启动器：在顶部选择“米哈游启动器”，点击“扫描窗口缓存”。选择素材预览，点击“保存所选”。缓存中可能有以前浏览过的素材，不能把每个候选都认定为当前页。

三角洲行动启动器：选择它的窗口，点击“扫描窗口缓存”。程序根据安装位置读取 tpf_ui/res（含 videos）和网页 assets 素材目录；无法获取进程路径时，可手动选择安装目录下 launcher/tpf_ui/res。列表可能包括按钮、登录画面、历史素材，不保证每项均属于当前页。本适配读取普通媒体文件，不解析加密资源包。

Edge 网页：输入网页地址，点击“打开抓取用 Edge”。回到本程序刷新标签页，选择要抓取的标签页并点击“连接并分析”。图片可直接列出；开始播放视频或切换页面后，网络加载的媒体也会进入列表。选择资源后保存，程序会先下载未就绪的资源。

抓取用 Edge 使用独立配置，普通 Edge 的登录状态不会自动带入。需要登录的网站请在这个专用窗口中登录。关闭程序不会关闭你打开的 Edge。再次运行时，如果专用窗口仍开着但连接失败，请关闭专用窗口后重新打开。

普通 Edge 窗口也可扫描缓存。微信、其他软件或游戏：如果没有自动识别缓存目录，可点击“选择素材目录”，指定你知道的媒体目录。程序不会解密聊天数据库或游戏资源包；没有媒体文件的实时游戏画面不能当成原始视频提取。

原始资源提取不依赖目标窗口是否最小化。网页若暂停加载，不会产生新的资源；已经获得的地址、文件仍可处理。截图和录屏需要窗口恢复，最小化时会明确提示或结束录制。受保护的画面可能无法捕获。

格式与画质

“保留原始格式＋原始画质”直接复制文件，保留原文件字节、动画和已有音轨。所有新录屏、流媒体合并以及视频转码均不采集/输出声音。“原始画质”不能恢复网站没有提供的更高分辨率；选择格式转换仍可能有编码损失。GIF、动画 WebP 不会被静默当成静态图。

HLS/DASH 清单尝试合并网站提供的无保护视频流，不转码且无声。部分网站需要专门适配；只得到片段或受保护资源时，程序会报告失败，不会把不完整片段冒充完整视频。

视频缓存按原始资源的范围和覆盖记录拼接，缺少分段时列为“待下载”，保存时尝试下载完整原始资源。预览前检查容器和首帧；保存前全程解码检查，转换后再次校验，发现损坏时不生成最终文件。长视频的校验需要时间，可点击“停止任务”取消。检查不能保证所有系统播放器都支持原始编码；点击“打开/播放原文件”使用 Edge 播放视频。需要兼容常见播放器时，输出格式请选择 MP4。

目录发现与诊断：自动搜索所选软件安装目录、对应用户数据目录中的常见媒体目录；初次扫描无结果时，会在有限深度内补充搜索。手动选择的目录会记住到该软件，下次扫描继续使用。扫描结果会说明路径失效、不可读、超出大小限制、损坏文件或不支持的资源包。扫描无结果不能判断加密；该功能不会解密资源包。自动搜索有范围和数量限制，特殊软件仍可能需要手动指定目录。

快捷键（可随时关闭）

Ctrl+Alt+F6：选中当前活动窗口并扫描缓存。
Ctrl+Alt+F7：截取当前活动窗口；已选桌面时截取该桌面。
Ctrl+Alt+F8：开始/停止 GIF 录制；已选桌面时录制该桌面。
Ctrl+Alt+F9：开始/停止视频录制；已选桌面时录制该桌面。

如果本程序本身处于前台，截图或录制快捷键使用顶部已选窗口。取消右上角“启用快捷键”会释放按键，不会停止已经运行的任务；要停止任务请点击对应停止按钮。按键被其他软件占用时会在日志提示。

保存默认位置：D:\\抓取内容，按“图片/动图/视频”分类，不覆盖已有文件。
暂存和独立 Edge 配置：%LOCALAPPDATA%\\WindowMediaGrabber。
缓存读取只读，不修改来源文件。扫描只识别完整可读文件；大于扫描上限、被占用或未完成文件会被跳过并计数。可调高单文件扫描上限或缩小扫描目录。
使用“清理素材暂存”只删除本程序暂存，不删除原软件缓存或 Edge 配置。
'''

class App:
    def __init__(self,root):
        set_app_id()
        self.root=root;root.title(TITLE);root.geometry(f'1360x{min(960,root.winfo_screenheight()-100)}');root.minsize(1120,760)
        self.events=queue.Queue();self.items={};self.url_keys={};self.rows={};self.window_list=[];self.targets_list=[]
        self.busy=False;self.closing=False;self.job_stop=threading.Event();self.record_stop=threading.Event();self.record_thread=None
        self.hotkeys=None;self.hotkey_thread=None;self.watch_after=None;self.preview_serial=0;self.animation_after=None
        STATE.mkdir(parents=True,exist_ok=True)
        try:self.config=json.loads((STATE/'settings.json').read_text('utf-8'))
        except Exception:self.config={}
        self.scan_roots=self.config.get('scan_roots',{})
        if not isinstance(self.scan_roots,dict):self.scan_roots={}
        self.folder=tk.StringVar(value=self.config.get('folder',r'D:\抓取内容'))
        self.format=tk.StringVar(value=self.config.get('format','保留原始格式'))
        self.quality=tk.StringVar(value=self.config.get('quality','原始画质'))
        self.hotkey_enabled=tk.BooleanVar(value=self.config.get('hotkeys',True))
        self.watch=tk.BooleanVar(value=False);self.window_var=tk.StringVar();self.tab_var=tk.StringVar()
        self.url=tk.StringVar(value='https://www.bilibili.com')
        self.custom_root=tk.StringVar();self.filter_kind=tk.StringVar(value='全部');self.search=tk.StringVar()
        self.max_mb=tk.IntVar(value=512);self.fps=tk.IntVar(value=24)
        self.shot_format=tk.StringVar(value='PNG');self.video_format=tk.StringVar(value='MP4')
        self.status=tk.StringVar(value='就绪 · 先选择窗口或打开抓取用 Edge')
        self.edge=Edge(lambda a:self.send('asset',a),lambda text:self.send('log',text))
        self.build();self.refresh_windows();self.toggle_hotkeys()
        self.root.after(80,self.drain);self.root.protocol('WM_DELETE_WINDOW',self.close)

    def send(self,event,value=None):self.events.put((event,value))
    def log(self,text):
        self.logs.configure(state='normal');self.logs.insert('end',time.strftime('%H:%M:%S')+'  '+str(text)+'\n')
        self.logs.see('end');self.logs.configure(state='disabled');self.status.set(str(text)[:150])

    def build(self):
        from ui import build_ui
        build_ui(self,TITLE,FORMATS,QUALITIES,HELP)

    def selected_window(self):
        index=self.wincombo.current()
        if index<0 or index>=len(self.window_list):raise RuntimeError('请先选择一个目标窗口。')
        w=self.window_list[index]
        if w.desktop:return w
        if not user32.IsWindow(w.hwnd):raise RuntimeError('窗口已经关闭，请刷新窗口列表。')
        return window_info(w.hwnd)
    def choose_desktop(self):
        self.refresh_windows()
        index=next((i for i,w in enumerate(self.window_list) if w.desktop),None)
        if index is None:self.log('没有找到可用显示器。');return
        self.wincombo.current(index);self.custom_root.set('');self.watch.set(False)
        self.notebook.select(1)
        self.log('已选择整个桌面；可截图、录制GIF或无声视频，也可在目标列表选择单屏。')
    def refresh_windows(self):
        old=self.window_var.get();self.window_list=desktops()+windows();values=[w.label for w in self.window_list]
        self.wincombo['values']=values
        if old in values:self.window_var.set(old)
        elif values:
            idx=next((i for i,w in enumerate(self.window_list) if '米哈游' in w.title),0);self.wincombo.current(idx)
    def select_active(self,w):
        if w.pid==os.getpid():return
        self.refresh_windows()
        for i,current in enumerate(self.window_list):
            if current.hwnd==w.hwnd:self.wincombo.current(i);return
        self.window_list.append(w);self.wincombo['values']=[x.label for x in self.window_list];self.wincombo.current(len(self.window_list)-1)

    def toggle_hotkeys(self):
        if self.hotkeys:
            self.hotkeys.close()
            if self.hotkey_thread:self.hotkey_thread.join(timeout=1)
            self.hotkeys=None
        if self.hotkey_enabled.get():
            self.hotkeys=Hotkeys(self.send);self.hotkey_thread=threading.Thread(target=self.hotkeys.run,daemon=True);self.hotkey_thread.start()
            self.hot_status.configure(text='快捷键已启用',foreground='#1769ce')
        else:self.hot_status.configure(text='快捷键已关闭',foreground='#68758b')
        self.persist()
    def persist(self):
        values={'folder':self.folder.get(),'format':self.format.get(),'quality':self.quality.get(),'hotkeys':self.hotkey_enabled.get(),'scan_roots':self.scan_roots}
        try:(STATE/'settings.json').write_text(json.dumps(values,ensure_ascii=False,indent=2),'utf-8')
        except OSError:pass
    def choose_output(self):
        folder=filedialog.askdirectory(title='选择保存文件夹')
        if folder:self.folder.set(folder);self.persist()
    def open_output(self):
        try:p=Path(self.folder.get());p.mkdir(parents=True,exist_ok=True);os.startfile(p)
        except Exception as e:messagebox.showerror(TITLE,str(e))
    def job(self,func,done=None):
        if self.busy:self.log('已有任务正在执行，请等待或点击“停止任务”。');return False
        self.busy=True;self.job_stop=threading.Event()
        def run():
            try:
                result=func()
                if done:self.send('callback',(done,result))
            except Exception as e:self.send('error',str(e))
            finally:self.send('job_done')
        self.job_thread=threading.Thread(target=run,daemon=True);self.job_thread.start();return True
    def stop_job(self):self.watch.set(False);self.job_stop.set();self.log('正在停止任务…')
    def choose_scan(self):
        root=filedialog.askdirectory(title='选择媒体缓存或素材目录（只读扫描）')
        if root:
            self.custom_root.set(root)
            try:
                w=self.selected_window();self.scan_roots[self.scan_key(w)]=root;self.persist()
                self.log('已记住该软件的素材目录：'+root)
            except Exception:pass
            self.start_scan()
    def scan_key(self,w):return w.process.lower()+'|'+str(w.path).lower()
    def start_scan(self):
        try:
            manual=self.custom_root.get();window=None if manual else self.selected_window()
            if window and window.desktop:
                self.watch.set(False)
                raise RuntimeError('已选择桌面。请切换到“桌面 / 窗口”抓取桌面画面；提取原始媒体需选择软件窗口。')
            remembered=self.scan_roots.get(self.scan_key(window),'') if window else ''
            limit=self.max_mb.get()
            if not 16<=limit<=8192:raise RuntimeError('单文件扫描上限应为 16～8192 MB。')
        except Exception as e:self.log(str(e));return
        def work():
            log=lambda t:self.send('log',t)
            roots=[Path(manual)] if manual else discover_roots(window,self.job_stop,log)
            if remembered and isinstance(remembered,str):
                if Path(remembered).is_dir():roots=unique_roots([Path(remembered)]+roots);log('使用已记住的素材目录：'+remembered)
                else:log('此前记住的目录已不存在，尝试自动发现；可重新选择素材目录。')
            if not roots and not manual:roots=discover_roots(window,self.job_stop,log,expanded=True)
            if self.job_stop.is_set():log('目录搜索已停止。');return
            if not roots:
                log('没有找到可读取的素材目录。请先在目标软件加载媒体，或点击“选择素材目录”。无法读取进程路径时会尝试安装记录；无结果不能判断资源是否加密。');return
            c=scan(roots,lambda a:self.send('asset',a),lambda t:self.send('log',t),self.job_stop,limit)
            if not c['found'] and not manual and not self.job_stop.is_set():
                extra=[p for p in discover_roots(window,self.job_stop,log,expanded=True)
                       if not any(p==q or q in p.parents for q in roots)]
                if extra:
                    log('初次扫描没有媒体，正在扫描补充发现的素材目录…')
                    more=scan(extra,lambda a:self.send('asset',a),log,self.job_stop,limit)
                    for key,value in more.items():c[key]=max(c.get(key,0),value) if key in ('cancelled','limited') else c.get(key,0)+value
            log(scan_summary(c))
        self.job(work)
    def watch_changed(self):
        if self.watch.get():self.start_scan()
    def open_edge(self):
        url=self.url.get().strip()
        def work():self.edge.open(url);return self.edge.targets()
        self.job(work,self.set_tabs)
    def refresh_tabs(self):
        self.job(self.edge.targets,self.set_tabs)
    def set_tabs(self,targets):
        self.targets_list=targets;self.tabcombo['values']=[t['title'] or t['url'] for t in targets]
        if targets:self.tabcombo.current(0)
        else:self.tab_var.set('');self.log('未找到网页标签页，请先在抓取用 Edge 打开网页。')
    def connect_tab(self):
        i=self.tabcombo.current()
        if i<0:self.log('请先打开抓取用 Edge，并刷新/选择标签页。');return
        target=self.targets_list[i];self.job(lambda:self.edge.connect(target))

    def add_asset(self,a):
        key=a.digest or 'url:'+a.url
        previous=self.url_keys.get(a.url) if a.url else None
        if previous and previous!=key and a.path:
            self.items.pop(previous,None)
            if self.tree.exists(previous):self.tree.delete(previous)
        if key in self.items and self.items[key].path and not a.path:return
        if a.url:self.url_keys[a.url]=key
        if key in self.items and self.items[key].path:
            self.items[key]=a;self.update_row(key);return
        self.items[key]=a;self.update_row(key)
        self.count.configure(text=f'{len(self.items)} 个素材')
    def update_row(self,key):
        a=self.items[key];q=self.search.get().strip().lower();flt=self.filter_kind.get()
        visible=(flt=='全部' or a.category==flt) and (not q or q in (a.name+' '+a.source+' '+a.ext).lower())
        if not visible:
            if self.tree.exists(key):self.tree.detach(key)
            return
        size=(f'{a.size/1048576:.1f} MB' if a.size>=1048576 else f'{a.size/1024:.0f} KB') if a.size else '未知'
        status='待下载' if not a.path else ('全程已校验' if a.video_full_checked else '视频可预览' if a.video_checked else ('缓存候选' if a.note.startswith('缓存') else '原文件就绪'))
        vals=(a.name[:90],a.category,a.ext.upper(),a.dimensions or '—',size,status)
        if self.tree.exists(key):self.tree.item(key,values=vals);self.tree.reattach(key,'','end')
        else:self.tree.insert('','end',iid=key,values=vals)
    def filter_rows(self):
        if not hasattr(self,'tree'):return
        for key in self.items:self.update_row(key)
    def clear_assets(self):
        self.preview_serial+=1;self.preview_original=None
        for key in self.items:
            if self.tree.exists(key):self.tree.delete(key)
        self.items.clear();self.url_keys.clear();self.count.configure(text='0 个素材');self.image_label.configure(image='',text='选择素材查看预览')
    def selected_assets(self):return [self.items[key] for key in self.tree.selection() if key in self.items]
    def on_select(self,event=None):
        items=self.selected_assets()
        if not items:return
        a=items[0];self.preview_serial+=1;serial=self.preview_serial;self.preview_original=None
        self.details.configure(state='normal');self.details.delete('1.0','end')
        self.details.insert('1.0',f'{a.name}\n{a.category} · {a.ext.upper()} · {a.dimensions or "尺寸待识别"}\n来源：{a.source}\n{a.note}')
        self.details.configure(state='disabled');self.image_label.configure(image='',text='正在生成预览…' if a.path else '媒体地址已识别\n保存时下载原文件')
        if a.path:
            def work():
                try:self.send('preview',(serial,preview(a)))
                except Exception:self.send('preview',(serial,None))
            threading.Thread(target=work,daemon=True).start()
    def update_preview_image(self):
        if self.preview_original is None:return
        im=self.preview_original.copy();im.thumbnail((max(20,self.image_label.winfo_width()-4),max(20,self.image_label.winfo_height()-4)))
        self.preview_image=ImageTk.PhotoImage(im);self.image_label.configure(image=self.preview_image,text='')
    def open_selected(self):
        items=self.selected_assets()
        if not items:self.log('请先选择素材。');return
        if not items[0].path:self.log('请先下载原始资源。');return
        a=items[0]
        def work():
            if a.category=='视频':
                validate_video(a)
                for base in ('PROGRAMFILES(X86)','PROGRAMFILES','LOCALAPPDATA'):
                    edge=Path(os.environ.get(base,''))/'Microsoft/Edge/Application/msedge.exe'
                    if edge.is_file():
                        subprocess.Popen([str(edge),a.path.resolve().as_uri()]);return
            try:os.startfile(a.path)
            except OSError:raise RuntimeError('系统没有对应的打开程序；可先保存并使用播放器查看。')
        self.job(work)
    def export(self,download_only=False):
        items=self.selected_assets()
        if not items:self.log('请先选择至少一个素材，可按 Ctrl/Shift 多选。');return
        folder=self.folder.get();fmt=self.format.get();quality=self.quality.get();self.persist()
        def work():
            saved=0;failed=0
            for a in items:
                if self.job_stop.is_set():break
                try:
                    if not a.path:
                        self.send('log','正在下载网页原始媒体…');a=self.edge.download(a,self.job_stop);self.send('asset',a)
                    if not download_only:
                        if a.category=='视频':self.send('log','正在全程校验并保存视频…')
                        save_asset(a,folder,fmt,quality,self.job_stop);self.send('asset',a)
                    saved+=1
                except Exception as e:
                    failed+=1
                    # Never put network credentials/query strings in error logs.
                    text=str(e) if isinstance(e,RuntimeError) else f'{type(e).__name__}：资源不可读、网络请求失败或输出目录无法写入。'
                    self.send('log','处理失败：'+text)
            self.send('log',f'{"下载到暂存" if download_only else "保存"}完成：成功 {saved}，失败 {failed}。'+(' 保存位置：'+folder if not download_only and saved else ''))
        self.job(work)
    def clean_staging(self):
        if self.busy or (self.record_thread and self.record_thread.is_alive()):self.log('请先停止任务，再清理暂存。');return
        self.edge.disconnect()
        from media import STAGING
        count=0
        if STAGING.exists():
            for p in STAGING.iterdir():
                if p.is_file():
                    try:p.unlink();count+=1
                    except OSError:pass
        self.clear_assets();self.log(f'已清理 {count} 个本程序暂存文件。')
    def take_shot(self):
        try:w=self.selected_window()
        except Exception as e:self.log(str(e));return
        folder=self.folder.get();fmt=self.shot_format.get();quality=self.quality.get()
        def work():
            from capture import screenshot
            path=screenshot(w,folder,fmt,quality);self.send('log','截图已保存：'+str(path))
        self.job(work)
    def toggle_record(self,fmt):
        if self.record_thread and self.record_thread.is_alive():self.record_stop.set();self.record_status.set('正在结束并保存…');return
        try:w=self.selected_window();fps=12 if fmt=='GIF' else self.fps.get()
        except Exception as e:self.log(str(e));return
        folder=self.folder.get();quality=self.quality.get();self.record_stop=threading.Event()
        self.record_status.set('正在启动 '+fmt+' 录制…')
        def work():
            try:
                from capture import record
                self.send('log','开始无声录制 '+fmt+'：'+w.title)
                path=record(w,folder,fmt,quality,fps,self.record_stop,lambda t:self.send('log',t));self.send('log','录制已保存：'+str(path))
            except Exception as e:self.send('error',str(e))
            finally:self.send('record_done')
        self.record_thread=threading.Thread(target=work,daemon=True);self.record_thread.start()

    def drain(self):
        for _ in range(150):
            try:event,value=self.events.get_nowait()
            except queue.Empty:break
            if event=='asset':self.add_asset(value)
            elif event=='log':self.log(value)
            elif event=='error':self.log('失败：'+value)
            elif event=='callback':
                callback,result=value;callback(result)
            elif event=='job_done':
                self.busy=False
                if self.watch.get():
                    if self.watch_after:self.root.after_cancel(self.watch_after)
                    self.watch_after=self.root.after(5000,lambda:self.start_scan() if self.watch.get() else None)
            elif event=='record_done':self.record_status.set('未录制 · 文件状态见下方日志')
            elif event=='preview':
                serial,im=value
                if serial==self.preview_serial:
                    if im is None:self.image_label.configure(image='',text='暂时无法预览\n可用系统应用打开原文件')
                    else:
                        self.preview_original=im;self.update_preview_image()
            elif event=='hotkey' and self.hotkey_enabled.get():
                number,w=value
                index=self.wincombo.current()
                desktop_selected=0<=index<len(self.window_list) and self.window_list[index].desktop
                if number==1 or not desktop_selected:self.select_active(w)
                if number==1:self.custom_root.set('');self.start_scan()
                elif number==2:self.take_shot()
                elif number==3:self.toggle_record('GIF')
                elif number==4:self.toggle_record(self.video_format.get())
        if not self.closing:self.root.after(80,self.drain)
    def close(self):
        if self.closing:return
        self.closing=True;self.watch.set(False);self.job_stop.set();self.record_stop.set();self.persist()
        if self.hotkeys:self.hotkeys.close()
        self.edge.close()
        self.status.set('正在结束任务并保存录制…')
        deadline=time.monotonic()+35
        def finish():
            active=(self.record_thread and self.record_thread.is_alive()) or (hasattr(self,'job_thread') and self.job_thread.is_alive())
            if active and time.monotonic()<deadline:self.root.after(100,finish)
            else:self.root.destroy()
        finish()

def main():
    set_dpi();set_app_id()
    root=tk.Tk();app=App(root)
    if '--smoke-ui' in sys.argv:
        # Own-application launch check; not part of the normal user workflow.
        def done():
            if '--verify-runtime' in sys.argv:
                def verify():
                    try:
                        import windows_capture,cv2,numpy
                        from capture import screenshot,record
                        from media import run_ffmpeg
                        own=window_info(user32.GetAncestor(root.winfo_id(),2))
                        picture=screenshot(own,STATE/'smoke','PNG','原始画质')
                        stop=threading.Event();timer=threading.Timer(2,stop.set);timer.start()
                        video=record(own,STATE/'smoke','MP4','均衡（720p）',12,stop,lambda _:None);timer.cancel()
                        run_ffmpeg(['-i',str(video),'-f','null','-'])
                        status='UI_READY\nPACKAGED_CAPTURE_OK\n'+str(picture)+'\n'+str(video)
                        if '--verify-desktop' in sys.argv:
                            target=desktops()[0]
                            picture=screenshot(target,STATE/'smoke','PNG','省空间（480p）')
                            stop=threading.Event();timer=threading.Timer(2,stop.set);timer.start()
                            desktop_video=record(target,STATE/'smoke','MP4','省空间（480p）',12,stop,lambda _:None);timer.cancel()
                            run_ffmpeg(['-xerror','-i',str(desktop_video),'-f','null','-'])
                            status+='\nPACKAGED_DESKTOP_OK\n'+str(picture)+'\n'+str(desktop_video)
                        (STATE/'ui-smoke.txt').write_text(status,'utf-8')
                    except Exception:
                        (STATE/'ui-smoke.txt').write_text('FAILED\n'+traceback.format_exc(),'utf-8')
                    finally:app.send('callback',(lambda _:app.close(),None))
                threading.Thread(target=verify,daemon=True).start()
            else:
                (STATE/'ui-smoke.txt').write_text('UI_READY\n'+str(len(app.window_list))+' windows\n','utf-8');app.close()
        root.after(1800,done)
    root.mainloop()

if __name__=='__main__':
    try:main()
    except Exception:
        STATE.mkdir(parents=True,exist_ok=True);(STATE/'startup-error.txt').write_text(traceback.format_exc(),'utf-8')
        try:messagebox.showerror(TITLE,'程序启动失败。错误详情位于：'+str(STATE/'startup-error.txt'))
        except Exception:pass
        raise
