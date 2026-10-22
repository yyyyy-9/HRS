"""Win32 clipboard graphics -> self-contained PNG, with optional original EMF.

No third-party or WPS/Office dependency; Windows entrypoints only run on Windows.
The clipboard is accessed *only* on an explicit paste or toolbar action.

Security: native metafiles are untrusted Win32 GDI input; only enable the native
endpoint for same-origin user actions. Native Windows testing is required before
this bridge is considered production-hardened.
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import os
import struct
import time
import zlib

MAX_SOURCE = 12 * 1024 * 1024
MAX_PIXELS = 12_000_000
MAX_EDGE = 4096
CF_DIB = 8
CF_ENHMETAFILE = 14
CF_DIBV5 = 17
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


@dataclass(frozen=True)
class ClipboardGraphic:
    png: bytes
    origin: str
    emf: bytes | None = None


def validate_emf(data: bytes) -> None:
    """Cheap structural gate; native GDI validates the actual record sequence."""
    if not isinstance(data, bytes) or len(data) < 88 or len(data) > MAX_SOURCE:
        raise ValueError('EMF 文件大小异常')
    if struct.unpack_from('<I', data, 0)[0] != 1 or data[40:44] != b' EMF':
        raise ValueError('不是有效的 Windows EMF 图形')
    header_size, total_size = struct.unpack_from('<I', data, 4)[0], struct.unpack_from('<I', data, 48)[0]
    if header_size < 88 or header_size > len(data) or total_size != len(data):
        raise ValueError('EMF 图形头与文件长度不一致')


def emf_preview_size(data: bytes, dpi: int = 300) -> tuple[int,int]:
    validate_emf(data)
    left, top, right, bottom = struct.unpack_from('<4i', data, 24)
    if 0 < right-left <= 2_000_000 and 0 < bottom-top <= 2_000_000:
        # rclFrame has 0.01 mm units, i.e. 2540 units per inch.
        w, h = (right-left)*dpi/2540, (bottom-top)*dpi/2540
    else:
        x1,y1,x2,y2=struct.unpack_from('<4i',data,8)
        w,h=max(1,x2-x1),max(1,y2-y1)
    scale=min(1.0,MAX_EDGE/max(w,h), (MAX_PIXELS/max(1,w*h))**0.5)
    return max(1,int(round(w*scale))),max(1,int(round(h*scale)))


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data)&0xffffffff)


def bgra_to_png(pixels: bytes, width: int, height: int) -> bytes:
    if width<1 or height<1 or width>MAX_EDGE or height>MAX_EDGE or width*height>MAX_PIXELS:
        raise ValueError('图形预览尺寸过大')
    if len(pixels)!=width*height*4:
        raise ValueError('图形像素数据长度不正确')
    # Top-down DIB32 BGRA -> opaque RGBA; GDI commonly leaves alpha undefined.
    rgba=bytearray(pixels)
    rgba[0::4]=pixels[2::4]
    rgba[2::4]=pixels[0::4]
    rgba[3::4]=b'\xff'*(width*height)
    stride=width*4
    scan=b''.join(b'\x00'+rgba[i:i+stride] for i in range(0,len(rgba),stride))
    data=(PNG_MAGIC+_chunk(b'IHDR',struct.pack('>2I5B',width,height,8,6,0,0,0))+
          _chunk(b'IDAT',zlib.compress(scan,level=6))+_chunk(b'IEND',b''))
    if len(data)>MAX_SOURCE:raise ValueError('图片转换后超过 12 MB')
    return data


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_=[('biSize',wintypes.DWORD),('biWidth',wintypes.LONG),('biHeight',wintypes.LONG),
             ('biPlanes',wintypes.WORD),('biBitCount',wintypes.WORD),('biCompression',wintypes.DWORD),
             ('biSizeImage',wintypes.DWORD),('biXPelsPerMeter',wintypes.LONG),
             ('biYPelsPerMeter',wintypes.LONG),('biClrUsed',wintypes.DWORD),('biClrImportant',wintypes.DWORD)]


class _BITMAPINFO(ctypes.Structure):
    _fields_=[('bmiHeader',_BITMAPINFOHEADER),('bmiColors',wintypes.DWORD*3)]


class _RECT(ctypes.Structure):
    _fields_=[('left',wintypes.LONG),('top',wintypes.LONG),('right',wintypes.LONG),('bottom',wintypes.LONG)]


def _render_with_gdi(width: int, height: int, painter) -> bytes:
    if os.name!='nt':raise RuntimeError('EMF 绘制仅支持 Windows')
    if not(0<width<=MAX_EDGE and 0<height<=MAX_EDGE and width*height<=MAX_PIXELS):
        raise ValueError('图形尺寸过大')
    gdi=ctypes.WinDLL('gdi32',use_last_error=True)
    gdi.CreateCompatibleDC.argtypes=[wintypes.HDC];gdi.CreateCompatibleDC.restype=wintypes.HDC
    gdi.CreateDIBSection.argtypes=[wintypes.HDC,ctypes.POINTER(_BITMAPINFO),wintypes.UINT,
                                  ctypes.POINTER(ctypes.c_void_p),wintypes.HANDLE,wintypes.DWORD]
    gdi.CreateDIBSection.restype=wintypes.HBITMAP
    gdi.SelectObject.argtypes=[wintypes.HDC,wintypes.HGDIOBJ];gdi.SelectObject.restype=wintypes.HGDIOBJ
    gdi.DeleteObject.argtypes=[wintypes.HGDIOBJ];gdi.DeleteObject.restype=wintypes.BOOL
    gdi.DeleteDC.argtypes=[wintypes.HDC];gdi.DeleteDC.restype=wintypes.BOOL
    gdi.GdiFlush.argtypes=[];gdi.GdiFlush.restype=wintypes.BOOL
    dc=gdi.CreateCompatibleDC(None)
    if not dc:raise OSError('Windows 无法创建图形绘制上下文')
    bitmap=None;previous=None
    try:
        info=_BITMAPINFO()
        info.bmiHeader.biSize=40;info.bmiHeader.biWidth=width
        info.bmiHeader.biHeight=-height;info.bmiHeader.biPlanes=1
        info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=0
        bits=ctypes.c_void_p()
        bitmap=gdi.CreateDIBSection(dc,ctypes.byref(info),0,ctypes.byref(bits),None,0)
        if not bitmap or not bits.value:raise OSError('Windows 无法创建预览位图')
        previous=gdi.SelectObject(dc,bitmap)
        if not previous:raise OSError('Windows 无法选取预览位图')
        ctypes.memset(bits.value,255,width*height*4)
        painter(gdi,dc)
        gdi.GdiFlush()
        raw=ctypes.string_at(bits.value,width*height*4)
        return bgra_to_png(raw,width,height)
    finally:
        if previous:gdi.SelectObject(dc,previous)
        if bitmap:gdi.DeleteObject(bitmap)
        gdi.DeleteDC(dc)


def emf_to_png(data: bytes) -> bytes:
    validate_emf(data)
    if os.name!='nt':raise RuntimeError('EMF 预览转换需要 Windows')
    width,height=emf_preview_size(data)
    gdi=ctypes.WinDLL('gdi32',use_last_error=True)
    gdi.SetEnhMetaFileBits.argtypes=[wintypes.UINT,ctypes.c_void_p]
    gdi.SetEnhMetaFileBits.restype=wintypes.HANDLE
    gdi.PlayEnhMetaFile.argtypes=[wintypes.HDC,wintypes.HANDLE,ctypes.POINTER(_RECT)]
    gdi.PlayEnhMetaFile.restype=wintypes.BOOL
    gdi.DeleteEnhMetaFile.argtypes=[wintypes.HANDLE]
    gdi.DeleteEnhMetaFile.restype=wintypes.BOOL
    buffer=ctypes.create_string_buffer(data)
    handle=gdi.SetEnhMetaFileBits(len(data),buffer)
    if not handle:raise ValueError('Windows 无法读取此 EMF 图形')
    try:
        def draw(_,dc):
            if not gdi.PlayEnhMetaFile(dc,handle,ctypes.byref(_RECT(0,0,width,height))):
                raise ValueError('Windows 无法绘制 EMF 图形')
        return _render_with_gdi(width,height,draw)
    finally:gdi.DeleteEnhMetaFile(handle)


def _dib_dimensions(data: bytes) -> tuple[int,int,int,int]:
    if len(data)<40:raise ValueError('DIB 数据头不完整')
    size,w,h,planes,bpp,compression=struct.unpack_from('<IiiHHI',data,0)
    if size not in (40,108,124) or size>len(data) or planes!=1 or compression not in (0,3):
        raise ValueError('剪贴板 DIB 格式暂不支持')
    if w<1 or h==0 or w>MAX_EDGE or abs(h)>MAX_EDGE or w*abs(h)>MAX_PIXELS:
        raise ValueError('DIB 图片尺寸过大')
    if bpp not in (8,16,24,32):raise ValueError('DIB 位深暂不支持')
    colors=struct.unpack_from('<I',data,32)[0]
    offset=size+(12 if size==40 and compression==3 else 0)+(colors or (256 if bpp==8 else 0))*4
    stride=((w*bpp+31)//32)*4
    if offset+stride*abs(h)>len(data):raise ValueError('DIB 位图数据不完整')
    return w,abs(h),offset,size


def dib_to_png(data: bytes) -> bytes:
    if len(data)>MAX_SOURCE:raise ValueError('DIB 剪贴板数据过大')
    w,h,offset,_=_dib_dimensions(data)
    if os.name!='nt':raise RuntimeError('DIB 转换仅支持 Windows')
    def draw(gdi,dc):
        gdi.StretchDIBits.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,
              ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,
              wintypes.UINT,wintypes.DWORD]
        gdi.StretchDIBits.restype=ctypes.c_int
        bmi=ctypes.create_string_buffer(data[:offset]);bits=ctypes.create_string_buffer(data[offset:])
        result=gdi.StretchDIBits(dc,0,0,w,h,0,0,w,h,bits,bmi,0,0x00CC0020)
        if result in (0,-1):raise ValueError('Windows 无法绘制此 DIB 剪贴板图形')
    return _render_with_gdi(w,h,draw)


def _read_global_memory(user32,kernel32,handle,*,minimum=8,maximum=MAX_SOURCE) -> bytes:
    kernel32.GlobalSize.argtypes=[wintypes.HGLOBAL];kernel32.GlobalSize.restype=ctypes.c_size_t
    kernel32.GlobalLock.argtypes=[wintypes.HGLOBAL];kernel32.GlobalLock.restype=ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes=[wintypes.HGLOBAL];kernel32.GlobalUnlock.restype=wintypes.BOOL
    length=kernel32.GlobalSize(handle)
    if length<minimum or length>maximum:raise ValueError('剪贴板数据大小超过限制')
    ptr=kernel32.GlobalLock(handle)
    if not ptr:raise ValueError('无法读取剪贴板图片内存')
    try:return ctypes.string_at(ptr,length)
    finally:kernel32.GlobalUnlock(handle)


def _open_clipboard(user32):
    # Office releases the clipboard shortly after Copy. Reuse the original
    # bounded acquisition wait; never retry a document conversion or commit.
    for attempt in range(6):
        if user32.OpenClipboard(None):return
        time.sleep(0.06)
    raise RuntimeError('Windows 剪贴板被其他软件占用，请稍后再粘贴')


def read_windows_formats(formats):
    """One explicit clipboard snapshot of bounded HGLOBAL formats (no writes)."""
    if os.name!='nt':raise ValueError('读取本地 Word 图片需要 Windows 剪贴板')
    user32=ctypes.WinDLL('user32',use_last_error=True)
    kernel32=ctypes.WinDLL('kernel32',use_last_error=True)
    user32.OpenClipboard.argtypes=[wintypes.HWND];user32.OpenClipboard.restype=wintypes.BOOL
    user32.CloseClipboard.argtypes=[];user32.CloseClipboard.restype=wintypes.BOOL
    user32.GetClipboardData.argtypes=[wintypes.UINT];user32.GetClipboardData.restype=wintypes.HANDLE
    user32.RegisterClipboardFormatW.argtypes=[wintypes.LPCWSTR];user32.RegisterClipboardFormatW.restype=wintypes.UINT
    _open_clipboard(user32)
    try:
        result={}
        for name in formats:
            identifier=name if isinstance(name,int) else user32.RegisterClipboardFormatW(name)
            handle=user32.GetClipboardData(identifier)
            if handle:result[name]=_read_global_memory(user32,kernel32,handle,minimum=1,maximum=64*1024*1024)
        return result
    finally:user32.CloseClipboard()


def read_windows_graphic() -> ClipboardGraphic | None:
    """Prefer EMF vectors; fallback to registered PNG and DIB. Return None for text.

    Never call implicitly from page load or periodic polling; only user paste.
    """
    if os.name!='nt':return None
    user32=ctypes.WinDLL('user32',use_last_error=True)
    kernel32=ctypes.WinDLL('kernel32',use_last_error=True)
    gdi=ctypes.WinDLL('gdi32',use_last_error=True)
    user32.OpenClipboard.argtypes=[wintypes.HWND];user32.OpenClipboard.restype=wintypes.BOOL
    user32.CloseClipboard.argtypes=[];user32.CloseClipboard.restype=wintypes.BOOL
    user32.IsClipboardFormatAvailable.argtypes=[wintypes.UINT];user32.IsClipboardFormatAvailable.restype=wintypes.BOOL
    user32.GetClipboardData.argtypes=[wintypes.UINT];user32.GetClipboardData.restype=wintypes.HANDLE
    user32.RegisterClipboardFormatW.argtypes=[wintypes.LPCWSTR];user32.RegisterClipboardFormatW.restype=wintypes.UINT
    gdi.GetEnhMetaFileBits.argtypes=[wintypes.HANDLE,wintypes.UINT,ctypes.c_void_p]
    gdi.GetEnhMetaFileBits.restype=wintypes.UINT
    _open_clipboard(user32)
    emf=None;png=None;dib=None;fmt_name=None
    try:
        if user32.IsClipboardFormatAvailable(CF_ENHMETAFILE):
            h=user32.GetClipboardData(CF_ENHMETAFILE)
            if h:
                size=gdi.GetEnhMetaFileBits(h,0,None)
                if 88<=size<=MAX_SOURCE:
                    buf=ctypes.create_string_buffer(size)
                    if gdi.GetEnhMetaFileBits(h,size,buf)==size:emf=buf.raw
        png_fmt=user32.RegisterClipboardFormatW('PNG')
        if png_fmt and user32.IsClipboardFormatAvailable(png_fmt):
            h=user32.GetClipboardData(png_fmt)
            if h:
                raw=_read_global_memory(user32,kernel32,h)
                if raw.startswith(PNG_MAGIC):png=raw
        if not png:
            for fmt,label in ((CF_DIBV5,'DIBV5'),(CF_DIB,'DIB')):
                if user32.IsClipboardFormatAvailable(fmt):
                    h=user32.GetClipboardData(fmt)
                    if h:
                        try:dib=_read_global_memory(user32,kernel32,h);fmt_name=label;break
                        except ValueError:pass
    finally:user32.CloseClipboard()
    if emf:
        try:return ClipboardGraphic(emf_to_png(emf),'Windows EMF',emf)
        except (ValueError,OSError,RuntimeError):
            if not png and not dib:raise
    if png:
        if len(png)>MAX_SOURCE:raise ValueError('剪贴板 PNG 超出限制')
        return ClipboardGraphic(png,'Windows PNG')
    if dib:
        return ClipboardGraphic(dib_to_png(dib),'Windows '+str(fmt_name))
    return None


def list_clipboard_formats() -> list[str]:
    """Local troubleshooting, exposing only format names (never clipboard data)."""
    if os.name!='nt':return []
    user32=ctypes.WinDLL('user32')
    user32.OpenClipboard.argtypes=[wintypes.HWND];user32.OpenClipboard.restype=wintypes.BOOL
    user32.EnumClipboardFormats.argtypes=[wintypes.UINT];user32.EnumClipboardFormats.restype=wintypes.UINT
    user32.GetClipboardFormatNameW.argtypes=[wintypes.UINT,wintypes.LPWSTR,ctypes.c_int]
    user32.GetClipboardFormatNameW.restype=ctypes.c_int
    if not user32.OpenClipboard(None):raise RuntimeError('剪贴板正在被占用')
    try:
        formats=[];fmt=0
        while True:
            fmt=user32.EnumClipboardFormats(fmt)
            if not fmt:break
            text=ctypes.create_unicode_buffer(256)
            n=user32.GetClipboardFormatNameW(fmt,text,len(text))
            formats.append(f'{fmt}: '+(text.value if n else {14:'CF_ENHMETAFILE',8:'CF_DIB',17:'CF_DIBV5',2:'CF_BITMAP'}.get(fmt,'标准格式')))
        return formats
    finally:user32.CloseClipboard()


if __name__=='__main__':
    if os.name!='nt':print('本功能需要 Windows 环境')
    else:
        print('当前 Windows 剪贴板格式（只打印名称，不读取图像内容）:')
        print('\n'.join(list_clipboard_formats()))
