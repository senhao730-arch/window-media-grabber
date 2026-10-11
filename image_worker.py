"""Isolated Pillow conversion; safe to terminate when the user cancels."""
from PIL import Image,ImageOps

def convert(source,destination,ext,quality):
    with Image.open(source) as original:
        im=ImageOps.exif_transpose(original)
        limit={'高画质（1080p）':1080,'均衡（720p）':720,'省空间（480p）':480}.get(quality)
        if limit and im.height>limit:
            im=im.resize((max(1,round(im.width*limit/im.height)),limit),Image.Resampling.LANCZOS)
        if ext=='jpg':im=im.convert('RGB')
        opts={'quality':95 if quality in ('原始画质','高画质（1080p）') else 85}
        im.save(destination,**(opts if ext in ('jpg','webp') else {}))

def worker(source,destination,ext,quality,sender):
    try:
        convert(source,destination,ext,quality)
        sender.send(None)
    except Exception:
        sender.send('图片转换失败：格式不受支持、源文件损坏或输出目录不可写。')
    finally:sender.close()
