import hashlib
import io
import os
import re
import shutil
import subprocess
import threading
import time
import tempfile
from dataclasses import dataclass,field
from pathlib import Path
from urllib.parse import unquote,urlsplit
from PIL import Image,ImageOps
import imageio_ffmpeg

CREATE_NO_WINDOW=0x08000000
STATE=Path(os.environ.get('LOCALAPPDATA',str(Path.cwd()))) / 'WindowMediaGrabber'
STAGING=STATE/'staging'
FFMPEG=imageio_ffmpeg.get_ffmpeg_exe()

def sniff(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):return 'png'
    if data.startswith(b'\xff\xd8\xff'):return 'jpg'
    if data.startswith((b'GIF87a',b'GIF89a')):return 'gif'
    if data.startswith(b'RIFF') and data[8:12]==b'WEBP':return 'webp'
    if data.startswith(b'BM'):return 'bmp'
    if data.startswith(b'\x1a\x45\xdf\xa3'):return 'mkv' if b'matroska' in data[:256] else 'webm'
    if len(data)>12 and data[4:8]==b'ftyp':
        if data[8:12] in [b'avif',b'avis']:return 'avif'
        return 'mp4'
    if data.lstrip().startswith(b'#EXTM3U'):return 'm3u8'
    if data.lstrip().startswith(b'<svg') or (data.lstrip().startswith(b'<?xml') and b'<svg' in data[:1024]):return 'svg'
    return ''

def kind(ext):
    if ext in ('mp4','webm','mkv','mov','m3u8','mpd'):return '视频'
    if ext=='gif':return '动图'
    return '图片'

def safe_name(name):
    text=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',name).strip(' .')[:100]
    if not text or text.upper().split('.')[0] in ['CON','PRN','AUX','NUL','COM1','LPT1']:text='素材'
    return text

@dataclass
class Asset:
    path: Path|None
    ext: str
    source: str
    name: str=''
    url: str=''
    size: int=0
    timestamp: float=0
    headers: dict=field(default_factory=dict,repr=False)
    digest: str=''
    dimensions: str=''
    animated: bool=False
    note: str=''
    video_checked: bool=False
    validation_stamp: tuple=field(default_factory=tuple,repr=False)
    video_full_checked: bool=False
    full_validation_stamp: tuple=field(default_factory=tuple,repr=False)

    @property
    def category(self):return '动图' if self.animated else kind(self.ext)

def inspect_asset(asset):
    if asset.path:
        asset.size=asset.path.stat().st_size
        if not asset.digest:
            h=hashlib.sha256()
            with asset.path.open('rb') as f:
                for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
            asset.digest=h.hexdigest()
        if kind(asset.ext)!='视频' and asset.ext!='svg':
            with Image.open(asset.path) as im:
                asset.dimensions=f'{im.width} × {im.height}'
                asset.animated=bool(getattr(im,'is_animated',False))
                im.verify()
        elif asset.ext not in ('m3u8','mpd'):
            validate_video(asset)
    if not asset.name:
        asset.name=safe_name(unquote(Path(urlsplit(asset.url).path).name) if asset.url else asset.path.name)
    return asset

def ebml_vint(data,offset):
    if offset>=len(data) or data[offset]==0:raise RuntimeError('视频 EBML 头损坏。')
    length=1
    while length<=8 and not data[offset]&(0x80>>(length-1)):length+=1
    if length>8 or offset+length>len(data):raise RuntimeError('视频 EBML 头不完整。')
    value=int.from_bytes(data[offset:offset+length],'big')&((1<<(7*length))-1)
    return value,length,value==(1<<(7*length))-1

def expected_webm_length(head):
    if not head.startswith(b'\x1a\x45\xdf\xa3'):return None
    size,n,unknown=ebml_vint(head,4)
    if unknown:return None
    pos=4+n+size
    # Segment follows the EBML header, optionally after a Void element.
    while pos<len(head) and head[pos]==0xec:
        size,n,unknown=ebml_vint(head,pos+1)
        if unknown:return None
        pos+=1+n+size
    if head[pos:pos+4]!=b'\x18\x53\x80\x67':raise RuntimeError('视频缺少 Matroska/WebM Segment。')
    size,n,unknown=ebml_vint(head,pos+4)
    return None if unknown else pos+4+n+size

def check_video_container(path,ext):
    size=path.stat().st_size
    with path.open('rb') as f:
        head=f.read(4096)
        if ext in ('webm','mkv'):
            expected=expected_webm_length(head)
            if expected is not None and expected>size:
                raise RuntimeError(f'视频不完整：只有 {size:,} 字节，容器声明需要 {expected:,} 字节。请重新扫描获取完整缓存或原始地址。')
        elif ext in ('mp4','mov'):
            offset=0;has_moov=False
            while offset<size:
                f.seek(offset);box=f.read(16)
                if len(box)<8:raise RuntimeError('MP4 尾部被截断。')
                length=int.from_bytes(box[:4],'big');header=8
                if length==1:
                    if len(box)<16:raise RuntimeError('MP4 扩展头被截断。')
                    length=int.from_bytes(box[8:16],'big');header=16
                if length==0:length=size-offset
                if length<header or offset+length>size:raise RuntimeError('MP4 不完整：媒体数据块超过文件长度。')
                if box[4:8]==b'moov':has_moov=True
                offset+=length
            if not has_moov:raise RuntimeError('只有 MP4 视频片段，缺少完整视频索引。')

def validate_video(asset,full=False,stop=None):
    stamp=(asset.path.stat().st_size,asset.path.stat().st_mtime_ns)
    if (asset.video_full_checked and asset.full_validation_stamp==stamp) or (not full and asset.video_checked and asset.validation_stamp==stamp):return
    check_video_container(asset.path,asset.ext)
    args=[FFMPEG,'-hide_banner','-loglevel','info','-xerror','-err_detect','explode','-i',str(asset.path),'-map','0:v:0']
    if not full:args+=['-frames:v','1']
    p=subprocess.Popen(args+['-f','null','-'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=CREATE_NO_WINDOW)
    started=time.monotonic()
    try:
        while True:
            if stop and stop.is_set():raise RuntimeError('已取消视频校验')
            if not full and time.monotonic()-started>20:raise RuntimeError('视频解码验证超时，请检查文件是否完整。')
            try:_,err=p.communicate(timeout=.25);break
            except subprocess.TimeoutExpired:pass
    finally:
        if p.poll() is None:
            p.terminate()
            try:p.communicate(timeout=3)
            except subprocess.TimeoutExpired:p.kill();p.communicate()
    text=err.decode('utf-8','replace')
    if p.returncode or any(t in text.lower() for t in ('file ended prematurely','invalid data found','error while decoding','packet corrupt','output file is empty','nothing was written')):
        raise RuntimeError('视频没有通过解码检查，可能是损坏文件或不完整缓存。')
    dims=re.search(r'Video:.*?\b(\d{2,5})x(\d{2,5})\b',text)
    if dims:asset.dimensions=f'{dims[1]} × {dims[2]}'
    asset.video_checked=True;asset.validation_stamp=stamp
    if full:asset.video_full_checked=True;asset.full_validation_stamp=stamp

def stage_bytes(data,ext):
    STAGING.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(data).hexdigest()
    path=STAGING/(digest+'.'+ext)
    if not path.exists():
        tmp=path.with_suffix('.'+str(threading.get_ident())+'.part')
        tmp.write_bytes(data);os.replace(tmp,path)
    return path,digest

def run_ffmpeg(args,stop=None):
    # Credentials, if supplied, remain in memory; logs are never displayed verbatim.
    p=subprocess.Popen([FFMPEG,'-hide_banner','-loglevel','error','-y']+args,
        stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=CREATE_NO_WINDOW)
    while True:
        try:
            _,err=p.communicate(timeout=.25);break
        except subprocess.TimeoutExpired:
            if stop and stop.is_set():
                p.terminate()
                try:p.communicate(timeout=3)
                except subprocess.TimeoutExpired:p.kill();p.communicate()
                raise RuntimeError('已取消')
    if p.returncode:raise RuntimeError('媒体转换失败：格式不受支持、文件不完整或网络资源不可访问。请尝试保留原始格式。')

def scale_filter(quality):
    height={'原始画质':0,'高画质（1080p）':1080,'均衡（720p）':720,'省空间（480p）':480}.get(quality,0)
    return (f"scale=-2:'trunc(min(ih,{height})/2)*2'" if height else "scale=trunc(iw/2)*2:trunc(ih/2)*2")

def output_path(folder,asset,ext):
    folder=Path(folder)/asset.category
    folder.mkdir(parents=True,exist_ok=True)
    stem=safe_name(Path(asset.name).stem)
    name=f'{time.strftime("%Y%m%d_%H%M%S")}_{stem}_{asset.digest[:8] or "url"}'
    path=folder/(name+'.'+ext)
    i=2
    while path.exists():path=folder/(f'{name}_{i}.'+ext);i+=1
    return path

def save_asset(asset,folder,fmt='保留原始格式',quality='原始画质',stop=None):
    if not asset.path:raise RuntimeError('当前只有媒体地址，请先下载原始资源。')
    if asset.ext in ('m3u8','mpd'):raise RuntimeError('这是播放清单。请在 Edge 抓取页下载或合并视频。')
    if asset.category=='视频':validate_video(asset,full=True,stop=stop)
    ext=asset.ext if fmt=='保留原始格式' else fmt.lower().replace('jpeg','jpg')
    if ext not in ('png','jpg','webp','gif','bmp','avif','svg','mp4','webm','mkv','mov'):
        raise RuntimeError('不支持这个输出格式')
    dest=output_path(folder,asset,ext)
    temp=dest.with_name(dest.stem+'.working.'+ext)
    try:
        # 原文件直接复制才能保持字节、动画和画质。转换不冒充无损原始文件。
        if fmt=='保留原始格式' and quality=='原始画质':shutil.copyfile(asset.path,temp)
        elif asset.category=='图片':
            if ext in ('mp4','webm','mkv','mov','gif'):raise RuntimeError('静态图片请使用 PNG、JPEG 或 WebP。')
            with Image.open(asset.path) as im:
                im=ImageOps.exif_transpose(im)
                limit={'高画质（1080p）':1080,'均衡（720p）':720,'省空间（480p）':480}.get(quality)
                if limit and im.height>limit:im=im.resize((max(1,round(im.width*limit/im.height)),limit),Image.Resampling.LANCZOS)
                if ext=='jpg':im=im.convert('RGB')
                opts={'quality':95 if quality in ('原始画质','高画质（1080p）') else 85}
                im.save(temp,**(opts if ext in ('jpg','webp') else {}))
        else:
            if ext not in ('gif','webp','mp4','webm','mkv','mov'):raise RuntimeError('动图或视频请选择 GIF、WebP、MP4、WebM 或 MKV；不会静默丢失动画。')
            vf=scale_filter(quality)
            # FFmpeg 7 does not decode animated WebP reliably. Pillow decodes the
            # frames onto disk, preserving timing without retaining all frames in RAM.
            with tempfile.TemporaryDirectory(prefix='animation_',dir=STATE) as animation_dir:
                args=['-i',str(asset.path),'-an']
                if asset.animated and asset.ext=='webp':
                    timeline=[];last=''
                    with Image.open(asset.path) as im:
                        for i in range(im.n_frames):
                            if stop and stop.is_set():raise RuntimeError('已取消')
                            im.seek(i);last=f'frame_{i:06d}.png';im.convert('RGBA').save(Path(animation_dir)/last)
                            timeline += [f"file '{last}'",f"duration {max(10,im.info.get('duration',100))/1000:.4f}"]
                    timeline.append(f"file '{last}'")
                    timeline_path=Path(animation_dir)/'timeline.txt';timeline_path.write_text('\n'.join(timeline),'utf-8')
                    args=['-f','concat','-safe','1','-i',str(timeline_path),'-an']
                if ext=='gif':args+=['-filter_complex',f'{vf},split[a][b];[a]palettegen[p];[b][p]paletteuse','-loop','0']
                elif ext=='webp':args+=['-vf',vf,'-c:v','libwebp_anim','-loop','0']
                elif ext=='webm':args+=['-vf',vf,'-c:v','libvpx-vp9','-crf','30','-b:v','0']
                else:
                    args+=['-vf',vf,'-c:v','libx264','-preset','fast','-crf','18' if quality=='原始画质' else '23','-pix_fmt','yuv420p']
                    if ext=='mp4':args+=['-movflags','+faststart']
                run_ffmpeg(args+[str(temp)],stop)
        if not temp.exists() or not temp.stat().st_size:raise RuntimeError('输出文件为空')
        if ext in ('mp4','webm','mkv','mov'):
            validate_video(Asset(temp,ext,'输出校验'),full=True,stop=stop)
        os.replace(temp,dest)
        return dest
    finally:
        if temp.exists():temp.unlink()

def preview(asset):
    if not asset.path:raise RuntimeError('请先下载资源再预览')
    if asset.category=='视频':
        validate_video(asset)
        tmp=STAGING/(asset.digest[:20]+'_preview.png')
        run_ffmpeg(['-i',str(asset.path),'-frames:v','1',str(tmp)])
        im=Image.open(tmp).copy()
    else:
        with Image.open(asset.path) as raw:im=ImageOps.exif_transpose(raw).convert('RGBA').copy()
    im.thumbnail((360,180),Image.Resampling.LANCZOS)
    return im
