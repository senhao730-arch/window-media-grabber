"""Desktop UI: shared target/settings, navigation, media list and capture cards."""
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from PIL import Image,ImageTk

BG='#F4F7FC';WHITE='#FFFFFF';INK='#172B4D';MUTED='#6B7C96';BLUE='#1479F8';LINE='#E3EAF4'
RESOURCES=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'assets'

def build_ui(app,title,formats,qualities,help_text):
    root=app.root;root.configure(bg=BG)
    style=ttk.Style();style.theme_use('clam')
    style.configure('.',font=('Microsoft YaHei UI',9),foreground=INK,background=BG)
    style.configure('TFrame',background=BG)
    style.configure('TLabel',background=BG)
    style.configure('White.TFrame',background=WHITE)
    style.configure('Card.TFrame',background=WHITE,bordercolor=LINE,borderwidth=1,relief='solid')
    style.configure('White.TLabel',background=WHITE)
    style.configure('Muted.TLabel',background=WHITE,foreground=MUTED)
    style.configure('Title.TLabel',background=WHITE,font=('Microsoft YaHei UI',16,'bold'))
    style.configure('Count.TLabel',background='#EDF5FF',foreground='#1469CD',padding=(10,4))
    style.configure('TButton',background='#EFF4FB',foreground=INK,borderwidth=0,padding=(12,8),font=('Microsoft YaHei UI',9))
    style.map('TButton',background=[('disabled','#F3F5F8'),('pressed','#DDE8F8'),('active','#E3EDFB')],foreground=[('disabled','#9AA8BC')])
    style.configure('Accent.TButton',background=BLUE,foreground=WHITE,font=('Microsoft YaHei UI',9,'bold'))
    style.map('Accent.TButton',background=[('disabled','#BCD5F5'),('pressed','#0862D6'),('active','#096CE9')],foreground=[('disabled',WHITE)])
    style.configure('Danger.TButton',background='#FFF0F0',foreground='#D94B51')
    style.configure('Small.TButton',padding=(8,4),font=('Microsoft YaHei UI',8))
    style.map('Danger.TButton',background=[('active','#FFE0E2')])
    style.configure('Nav.TButton',background=BG,foreground=MUTED,anchor='w',padding=(15,13),font=('Microsoft YaHei UI',10))
    style.map('Nav.TButton',background=[('active','#E9F1FD')])
    style.configure('Selected.Nav.TButton',background='#E4EFFF',foreground='#126CE2',font=('Microsoft YaHei UI',10,'bold'))
    style.map('Selected.Nav.TButton',background=[('active','#D8E9FF')])
    style.configure('TEntry',fieldbackground=WHITE,bordercolor=LINE,lightcolor=LINE,darkcolor=LINE,padding=7)
    style.configure('TCombobox',fieldbackground=WHITE,background='#F5F8FC',bordercolor=LINE,lightcolor=LINE,darkcolor=LINE,arrowsize=12,padding=6)
    style.map('TCombobox',fieldbackground=[('readonly',WHITE)],foreground=[('readonly',INK)],selectbackground=[('readonly',WHITE)],selectforeground=[('readonly',INK)])
    style.configure('TSpinbox',fieldbackground=WHITE,bordercolor=LINE,lightcolor=LINE,darkcolor=LINE,padding=5)
    style.configure('TCheckbutton',background=WHITE,padding=3)
    style.map('TCheckbutton',background=[('active',WHITE)])
    style.configure('TScrollbar',background='#D7E2F1',troughcolor='#F6F9FD',borderwidth=0,arrowsize=11)
    style.configure('Treeview',background=WHITE,fieldbackground=WHITE,foreground=INK,rowheight=33,borderwidth=0,bordercolor=WHITE,lightcolor=WHITE,darkcolor=WHITE,font=('Microsoft YaHei UI',9))
    style.map('Treeview',background=[('selected','#E2EFFF')],foreground=[('selected','#104F9E')])
    style.configure('Treeview.Heading',background='#F4F8FE',foreground=MUTED,font=('Microsoft YaHei UI',9,'bold'),padding=(6,10),borderwidth=0)
    style.map('Treeview.Heading',background=[('active','#EAF2FE')])
    style.configure('Workspace.TNotebook',background=BG,borderwidth=0,tabmargins=0,bordercolor=BG,lightcolor=BG,darkcolor=BG)
    style.layout('Workspace.TNotebook.Tab',[])
    style.configure('TPanedwindow',background=BG)

    try:
        original=Image.open(RESOURCES/'app-icon.png').convert('RGBA')
        app.brand_image=ImageTk.PhotoImage(original.resize((54,54),Image.Resampling.LANCZOS))
        app.window_icons=[ImageTk.PhotoImage(original.resize((s,s),Image.Resampling.LANCZOS)) for s in (16,32,64,128)]
        root.iconphoto(True,*app.window_icons)
        root.iconbitmap(str(RESOURCES/'app-icon.ico'))
        root.iconbitmap(default=str(RESOURCES/'app-icon.ico'))
    except (OSError,tk.TclError):app.brand_image=None

    def card(parent,padding=14):return ttk.Frame(parent,style='Card.TFrame',padding=padding)
    def label(parent,text,style_name='White.TLabel',**kwargs):return ttk.Label(parent,text=text,style=style_name,**kwargs)
    def combo(parent,var,values,width=10):return ttk.Combobox(parent,textvariable=var,values=values,state='readonly',width=width)

    outer=ttk.Frame(root,padding=18);outer.pack(fill='both',expand=True)
    outer.columnconfigure(0,weight=1);outer.rowconfigure(2,weight=1)
    header=ttk.Frame(outer);header.grid(row=0,column=0,sticky='ew',pady=(0,16))
    if app.brand_image:ttk.Label(header,image=app.brand_image).pack(side='left',padx=(0,12))
    identity=ttk.Frame(header);identity.pack(side='left')
    ttk.Label(identity,text='窗口媒体抓取器',font=('Microsoft YaHei UI',21,'bold')).pack(anchor='w')
    ttk.Label(identity,text='原始素材提取  /  桌面与窗口记录',foreground=MUTED).pack(anchor='w',pady=(3,0))
    tools=card(header,padding=(12,8));tools.pack(side='right')
    ttk.Button(tools,text='退出',command=app.request_exit,style='Small.TButton').pack(side='right',padx=(10,0))
    ttk.Checkbutton(tools,text='启用快捷键',variable=app.hotkey_enabled,command=app.toggle_hotkeys).pack(side='right')
    app.hot_status=label(tools,'',style_name='Muted.TLabel');app.hot_status.pack(side='right',padx=(0,10))
    ttk.Label(header,text='v'+title.rsplit(' ',1)[-1],foreground=MUTED).pack(side='right',padx=18)

    settings=card(outer);settings.grid(row=1,column=0,sticky='ew',pady=(0,16));settings.columnconfigure(1,weight=1)
    label(settings,'抓取目标',style_name='Muted.TLabel').grid(row=0,column=0,sticky='w',padx=(0,12))
    app.wincombo=ttk.Combobox(settings,textvariable=app.window_var,state='readonly');app.wincombo.grid(row=0,column=1,sticky='ew',columnspan=5)
    app.wincombo.bind('<<ComboboxSelected>>',lambda _:app.custom_root.set(''))
    ttk.Button(settings,text='刷新目标',command=app.refresh_windows).grid(row=0,column=6,padx=(10,6))
    ttk.Button(settings,text='抓取桌面',command=app.choose_desktop,style='Accent.TButton').grid(row=0,column=7,sticky='e')
    label(settings,'保存位置',style_name='Muted.TLabel').grid(row=1,column=0,sticky='w',padx=(0,12),pady=(12,0))
    pathrow=ttk.Frame(settings,style='White.TFrame');pathrow.grid(row=1,column=1,sticky='ew',pady=(12,0));pathrow.columnconfigure(0,weight=1)
    ttk.Entry(pathrow,textvariable=app.folder,width=19).grid(row=0,column=0,sticky='ew')
    ttk.Button(pathrow,text='更改',command=app.choose_output).grid(row=0,column=1,padx=6)
    ttk.Button(pathrow,text='打开',command=app.open_output).grid(row=0,column=2)
    label(settings,'素材格式',style_name='Muted.TLabel').grid(row=1,column=2,padx=(18,8),pady=(12,0))
    combo(settings,app.format,formats,13).grid(row=1,column=3,pady=(12,0))
    label(settings,'画质',style_name='Muted.TLabel').grid(row=1,column=4,padx=(18,8),pady=(12,0))
    combo(settings,app.quality,qualities,17).grid(row=1,column=5,columnspan=3,sticky='e',pady=(12,0))

    workspace=ttk.Frame(outer);workspace.grid(row=2,column=0,sticky='nsew');workspace.columnconfigure(1,weight=1);workspace.rowconfigure(0,weight=1)
    nav=ttk.Frame(workspace,width=155);nav.grid(row=0,column=0,sticky='ns',padx=(0,16));nav.grid_propagate(False)
    ttk.Label(nav,text='工作台',foreground=MUTED,font=('Microsoft YaHei UI',9)).pack(anchor='w',padx=15,pady=(8,12))
    app.notebook=ttk.Notebook(workspace,style='Workspace.TNotebook');app.notebook.grid(row=0,column=1,sticky='nsew')
    pages=[ttk.Frame(app.notebook) for _ in range(3)]
    for page,name in zip(pages,['原始素材','画面抓取','使用说明']):app.notebook.add(page,text=name)
    navbuttons=[]
    for index,name in enumerate(['原始素材','桌面 / 窗口','使用说明']):
        button=ttk.Button(nav,text=name,style='Nav.TButton',command=lambda i=index:app.notebook.select(i));button.pack(fill='x',pady=3);navbuttons.append(button)
    def select_nav(event=None):
        selected=app.notebook.index(app.notebook.select())
        for i,button in enumerate(navbuttons):button.configure(style='Selected.Nav.TButton' if i==selected else 'Nav.TButton')
    app.notebook.bind('<<NotebookTabChanged>>',select_nav);select_nav()
    ttk.Label(nav,text='默认保存到\nD:\\抓取内容',foreground=MUTED,justify='left').pack(side='bottom',anchor='w',padx=15,pady=12)
    ttk.Label(nav,text='关闭窗口后\n任务在托盘继续',foreground=MUTED,justify='left').pack(side='bottom',anchor='w',padx=15,pady=8)

    assets,recording,help_page=pages
    assets.columnconfigure(0,weight=1);assets.rowconfigure(2,weight=1)
    browser=card(assets,padding=12);browser.grid(row=0,column=0,sticky='ew',pady=(0,10));browser.columnconfigure(0,weight=1)
    browser_head=ttk.Frame(browser,style='White.TFrame');browser_head.grid(row=0,column=0,sticky='ew',columnspan=4,pady=(0,8))
    label(browser_head,'网页媒体',font=('Microsoft YaHei UI',11,'bold')).pack(side='left')
    label(browser_head,'用抓取专用 Edge 识别原始图片、GIF 和视频',style_name='Muted.TLabel').pack(side='left',padx=12)
    web_toggle=ttk.Button(browser_head,text='收起网页设置',style='Small.TButton');web_toggle.pack(side='right')
    ttk.Entry(browser,textvariable=app.url).grid(row=1,column=0,sticky='ew')
    ttk.Button(browser,text='打开抓取用 Edge',command=app.open_edge,style='Accent.TButton').grid(row=1,column=1,columnspan=3,sticky='e',padx=(8,0))
    app.tabcombo=ttk.Combobox(browser,textvariable=app.tab_var,state='readonly');app.tabcombo.grid(row=2,column=0,sticky='ew',pady=(7,0))
    ttk.Button(browser,text='刷新标签页',command=app.refresh_tabs).grid(row=2,column=1,padx=6,pady=(7,0))
    ttk.Button(browser,text='连接并分析',command=app.connect_tab).grid(row=2,column=2,pady=(7,0))
    ttk.Button(browser,text='重新分析',command=lambda:app.job(app.edge.analyze)).grid(row=2,column=3,padx=(6,0),pady=(7,0))
    web_widgets=[w for w in browser.winfo_children() if w.grid_info().get('row') in (1,2)]
    web_open=[True]
    def show_web(expanded):
        web_open[0]=expanded
        for widget in web_widgets:
            if expanded:widget.grid()
            else:widget.grid_remove()
        browser_head.grid_configure(pady=(0,8) if expanded else 0)
        web_toggle.configure(text='收起网页设置' if expanded else '展开网页设置')
    web_toggle.configure(command=lambda:show_web(not web_open[0]))
    cache=card(assets,padding=(12,9));cache.grid(row=1,column=0,sticky='ew',pady=(0,10))
    ttk.Button(cache,text='扫描窗口缓存',command=app.start_scan,style='Accent.TButton').pack(side='left')
    ttk.Button(cache,text='选择素材目录',command=app.choose_scan).pack(side='left',padx=6)
    ttk.Checkbutton(cache,text='自动监测',variable=app.watch,command=app.watch_changed).pack(side='left',padx=5)
    label(cache,'上限 MB',style_name='Muted.TLabel').pack(side='left',padx=(12,6))
    ttk.Spinbox(cache,from_=16,to=8192,increment=128,textvariable=app.max_mb,width=5).pack(side='left')
    ttk.Button(cache,text='停止任务',command=app.stop_job,style='Danger.TButton').pack(side='right')
    library=card(assets,padding=12);library.grid(row=2,column=0,sticky='nsew');library.columnconfigure(0,weight=1);library.rowconfigure(2,weight=1)
    filterrow=ttk.Frame(library,style='White.TFrame');filterrow.grid(row=0,column=0,sticky='ew',pady=(0,8))
    label(filterrow,'素材库',font=('Microsoft YaHei UI',11,'bold')).pack(side='left',padx=(0,10))
    f=combo(filterrow,app.filter_kind,['全部','图片','动图','视频'],6);f.pack(side='left');f.bind('<<ComboboxSelected>>',lambda _:app.filter_rows())
    label(filterrow,'搜索',style_name='Muted.TLabel').pack(side='left',padx=(10,0))
    ttk.Entry(filterrow,textvariable=app.search,width=16).pack(side='left',padx=6);app.search.trace_add('write',lambda *args:app.filter_rows())
    ttk.Button(filterrow,text='全选',command=lambda:app.tree.selection_set(app.tree.get_children())).pack(side='left')
    ttk.Button(filterrow,text='清空',command=app.clear_assets).pack(side='left',padx=6)
    app.count=ttk.Label(filterrow,text='0 个素材',style='Count.TLabel');app.count.pack(side='right')
    directory_label=ttk.Label(library,textvariable=app.custom_root,style='Muted.TLabel',wraplength=900)
    def show_directory(*args):
        if app.custom_root.get():directory_label.grid(row=1,column=0,sticky='w',pady=(0,4))
        else:directory_label.grid_remove()
    app.custom_root.trace_add('write',show_directory);show_directory()
    split=ttk.Panedwindow(library,orient='horizontal');split.grid(row=2,column=0,sticky='nsew',pady=(3,10))
    left=ttk.Frame(split,style='White.TFrame');right=ttk.Frame(split,style='White.TFrame',padding=(15,0,0,0));split.add(left,weight=3);split.add(right,weight=2)
    cols=('name','kind','ext','dimensions','size','state');app.tree=ttk.Treeview(left,columns=cols,show='headings',selectmode='extended')
    for c,name,width in zip(cols,['素材名称','类型','格式','尺寸','大小','状态'],[180,46,50,100,75,90]):
        app.tree.heading(c,text=name);app.tree.column(c,width=width,minwidth=40,stretch=c=='name')
    sy=ttk.Scrollbar(left,command=app.tree.yview);app.tree.configure(yscrollcommand=sy.set)
    app.tree.pack(side='left',fill='both',expand=True);sy.pack(side='right',fill='y');app.tree.bind('<<TreeviewSelect>>',app.on_select)
    right.columnconfigure(0,weight=1);right.rowconfigure(1,weight=1)
    label(right,'素材预览',font=('Microsoft YaHei UI',10,'bold')).grid(row=0,column=0,sticky='w',pady=(4,8))
    app.preview_original=None
    app.image_label=ttk.Label(right,text='选择左侧素材\n查看图片或视频首帧',style='Muted.TLabel',anchor='center',justify='center');app.image_label.grid(row=1,column=0,sticky='nsew')
    app.image_label.bind('<Configure>',lambda _:app.update_preview_image())
    app.details=tk.Text(right,height=2,width=28,wrap='word',font=('Microsoft YaHei UI',9),bg='#F6F9FD',fg=MUTED,relief='flat',padx=8,pady=5,state='disabled');app.details.grid(row=2,column=0,sticky='ew',pady=(6,6))
    ttk.Button(right,text='打开 / 播放原文件',command=app.open_selected).grid(row=3,column=0,sticky='ew')
    actions=ttk.Frame(library,style='White.TFrame');actions.grid(row=3,column=0,sticky='ew')
    ttk.Button(actions,text='保存所选素材',command=app.export,style='Accent.TButton').pack(side='left')
    ttk.Button(actions,text='仅下载到暂存',command=lambda:app.export(download_only=True)).pack(side='left',padx=6)
    ttk.Button(actions,text='清理暂存',command=app.clean_staging).pack(side='right')
    asset_compact=[None]
    def adapt_assets(event):
        if event.widget!=assets:return
        compact=event.height<530
        if compact==asset_compact[0]:return
        asset_compact[0]=compact;show_web(not compact)
        if compact:app.details.grid_remove()
        else:app.details.grid()
    assets.bind('<Configure>',adapt_assets)

    recording.columnconfigure(0,weight=1)
    capture_heading=ttk.Label(recording,text='记录你看到的画面',font=('Microsoft YaHei UI',22,'bold'));capture_heading.grid(row=0,column=0,sticky='w',pady=(6,5))
    capture_subtitle=ttk.Label(recording,text='顶部选择桌面或窗口，选择一种方式开始抓取。',foreground=MUTED);capture_subtitle.grid(row=1,column=0,sticky='w',pady=(0,18))
    choices=ttk.Frame(recording);choices.grid(row=2,column=0,sticky='ew')
    for i in range(3):choices.columnconfigure(i,weight=1,uniform='capture')
    shots=card(choices);shots.grid(row=0,column=0,sticky='nsew',padx=(0,8))
    gifs=card(choices);gifs.grid(row=0,column=1,sticky='nsew',padx=4)
    videos=card(choices);videos.grid(row=0,column=2,sticky='nsew',padx=(8,0))
    capture_titles=[];capture_descriptions=[];capture_keys=[]
    for panel,name,desc,key in [(shots,'截图','保存此刻的画面','Ctrl + Alt + F7'),(gifs,'GIF 动图','记录连续动作 · 12 帧/秒','Ctrl + Alt + F8'),(videos,'无声视频','没有时长限制 · 手动停止','Ctrl + Alt + F9')]:
        heading=label(panel,name,style_name='Title.TLabel');heading.pack(anchor='w');capture_titles.append(heading)
        description=label(panel,desc,style_name='Muted.TLabel');description.pack(anchor='w',pady=(5,16));capture_descriptions.append(description)
        shortcut=label(panel,key,style_name='Muted.TLabel');shortcut.pack(side='bottom',anchor='w',pady=(12,0));capture_keys.append(shortcut)
    controls=ttk.Frame(shots,style='White.TFrame');controls.pack(fill='x',pady=(0,14));shot_controls=controls
    label(controls,'格式',style_name='Muted.TLabel').pack(side='left');combo(controls,app.shot_format,['PNG','JPEG','WebP'],8).pack(side='right')
    ttk.Button(shots,text='保存截图',command=app.take_shot,style='Accent.TButton').pack(fill='x')
    gif_format=label(gifs,'固定 GIF 格式',style_name='Muted.TLabel',padding=(0,8));gif_format.pack(anchor='w',pady=(0,14))
    ttk.Button(gifs,text='开始 / 停止 GIF',command=lambda:app.toggle_record('GIF'),style='Accent.TButton').pack(fill='x')
    controls=ttk.Frame(videos,style='White.TFrame');controls.pack(fill='x',pady=(0,14));video_controls=controls
    combo(controls,app.video_format,['MP4','WebM','MKV'],6).pack(side='left')
    combo(controls,app.fps,[12,24,30,60],3).pack(side='right');label(controls,'帧率',style_name='Muted.TLabel').pack(side='right',padx=5)
    ttk.Button(videos,text='开始 / 停止视频',command=lambda:app.toggle_record(app.video_format.get()),style='Accent.TButton').pack(fill='x')
    progress=card(recording,padding=16);progress.grid(row=3,column=0,sticky='ew',pady=(16,12))
    status=ttk.Frame(progress,style='White.TFrame');status.pack(side='left')
    label(status,'录制状态',style_name='Muted.TLabel').pack(anchor='w')
    app.record_status=tk.StringVar(value='未录制');ttk.Label(status,textvariable=app.record_status,style='White.TLabel',font=('Microsoft YaHei UI',14),foreground=BLUE).pack(anchor='w',pady=(5,0))
    ttk.Button(progress,text='停止录制',command=lambda:app.record_stop.set(),style='Danger.TButton').pack(side='right')
    capture_tips=ttk.Label(recording,text='桌面录制可在本程序最小化后继续；窗口录制在目标窗口最小化时结束。\n新录制的视频不采集电脑声音或麦克风。格式和画质可在顶部或对应卡片中设置。\n选择桌面后，F7 / F8 / F9 快捷键始终使用该桌面；快捷键可随时关闭。',foreground=MUTED,wraplength=920,justify='left');capture_tips.grid(row=4,column=0,sticky='w',pady=(5,0))
    compact_state=[None]
    def adapt_capture(event):
        if event.widget!=recording:return
        compact=event.height<530
        if compact==compact_state[0]:return
        compact_state[0]=compact
        capture_heading.configure(font=('Microsoft YaHei UI',18 if compact else 22,'bold'))
        capture_subtitle.grid_configure(pady=(0,10 if compact else 18))
        for panel in (shots,gifs,videos):panel.configure(padding=10 if compact else 14)
        for heading in capture_titles:heading.configure(font=('Microsoft YaHei UI',14 if compact else 16,'bold'))
        for description in capture_descriptions:description.pack_configure(pady=(4,6) if compact else (5,16))
        for shortcut in capture_keys:shortcut.pack_configure(pady=(6,0) if compact else (12,0))
        for control in (shot_controls,video_controls,gif_format):control.pack_configure(pady=(0,6 if compact else 14))
        progress.configure(padding=10 if compact else 16);progress.grid_configure(pady=(10,8) if compact else (16,12))
        if compact:capture_tips.grid_remove()
        else:capture_tips.grid()
    recording.bind('<Configure>',adapt_capture)

    help_card=card(help_page);help_card.pack(fill='both',expand=True)
    label(help_card,'使用说明',style_name='Title.TLabel').pack(anchor='w',pady=(0,12))
    text_frame=ttk.Frame(help_card,style='White.TFrame');text_frame.pack(fill='both',expand=True)
    ht=tk.Text(text_frame,wrap='word',font=('Microsoft YaHei UI',10),relief='flat',bg=WHITE,fg=INK,padx=6,pady=4,spacing3=7)
    hs=ttk.Scrollbar(text_frame,command=ht.yview);ht.configure(yscrollcommand=hs.set);ht.pack(side='left',fill='both',expand=True);hs.pack(side='right',fill='y');ht.insert('1.0',help_text);ht.configure(state='disabled')
    history=ttk.Frame(outer);history.grid(row=3,column=0,sticky='ew',pady=(14,0));history.columnconfigure(1,weight=1)
    ttk.Label(history,text='操作记录',foreground=MUTED).grid(row=0,column=0,sticky='nw',padx=(0,12),pady=5)
    app.logs=tk.Text(history,height=2,wrap='word',font=('Microsoft YaHei UI',9),bg='#ECF2FA',fg='#50627E',relief='flat',padx=10,pady=7,state='disabled');app.logs.grid(row=0,column=1,sticky='ew')
    scroll=ttk.Scrollbar(history,command=app.logs.yview);scroll.grid(row=0,column=2,sticky='ns');app.logs.configure(yscrollcommand=scroll.set)
    ttk.Label(outer,textvariable=app.status,foreground=MUTED,font=('Microsoft YaHei UI',8)).grid(row=4,column=0,sticky='w',pady=(6,0))
