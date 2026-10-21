"""Portable, explicit PDF-as-figure preview renderer with original-byte retention.

Windows: native WinRT renderer invoked through Windows PowerShell 5.1 (no pip or
Office dependency). Linux automated tests: poppler pdftoppm/pdfinfo in a bounded
subprocess. Failure is explicit; optional user-selected PNG companion works
without the system PDF renderer. No PDF source bytes are ever rewritten.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import zlib
import math

MAX_PDF = 12 * 1024 * 1024
MAX_PNG = 12 * 1024 * 1024
MAX_PIXELS = 12_000_000
MAX_EDGE = 4096
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


@dataclass(frozen=True)
class PdfPreview:
    png: bytes
    width: int
    height: int
    pages: int
    dpi: float
    engine: str


def validate_pdf(data: bytes, limit: int = MAX_PDF) -> None:
    if not isinstance(data,bytes) or not 32<=len(data)<=limit:
        raise ValueError(f'PDF 文件大小异常或超过 {limit//(1024*1024)} MiB')
    if not data[:1024].lstrip().startswith(b'%PDF-'):
        raise ValueError('文件不是标准 PDF')
    if b'%%EOF' not in data[-4096:]:
        raise ValueError('PDF 缺少结束标记，可能已损坏')


def png_dimensions(data: bytes) -> tuple[int,int]:
    if not isinstance(data,bytes) or len(data)>MAX_PNG or len(data)<33 or data[:8]!=PNG_SIGNATURE:
        raise ValueError('PDF 预览 PNG 不完整或大小超限')
    if data[12:16]!=b'IHDR' or struct.unpack_from('>I',data,8)[0]!=13:
        raise ValueError('PDF PNG 预览图头无效')
    w,h=struct.unpack_from('>II',data,16)
    if not (1<=w<=MAX_EDGE and 1<=h<=MAX_EDGE and w*h<=MAX_PIXELS):
        raise ValueError('PDF PNG 预览尺寸超出 4096px / 1200 万像素上限')
    # Check every chunk and the bounded scanline stream, not just IHDR.
    depth,color,compression,filtering,interlace=struct.unpack_from('5B',data,24)
    channels={0:1,2:3,3:1,4:2,6:4}
    depths={0:{1,2,4,8,16},2:{8,16},3:{1,2,4,8},4:{8,16},6:{8,16}}
    if depth not in depths.get(color,set()) or compression or filtering or interlace not in (0,1):
        raise ValueError('PNG 编码格式无效')
    at=8;compressed=[];palette=False;ended=False;idat_closed=False
    while at<len(data):
        if at+12>len(data):raise ValueError('PNG 数据块被截断')
        size=struct.unpack_from('>I',data,at)[0];kind=data[at+4:at+8];end=at+12+size
        if end>len(data):raise ValueError('PNG 数据块长度无效')
        payload=data[at+8:end-4]
        if zlib.crc32(kind+payload)&0xffffffff!=struct.unpack_from('>I',data,end-4)[0]:
            raise ValueError('PNG 数据块校验失败')
        if kind==b'IHDR':
            if at!=8:raise ValueError('PNG 重复图头')
        elif kind==b'PLTE':
            if palette or compressed or not size or size%3 or size>768 or color in (0,4) or color==3 and size//3>2**depth:
                raise ValueError('PNG 调色板无效')
            palette=True
        elif kind==b'IDAT':
            if idat_closed or color==3 and not palette:raise ValueError('PNG 图像块次序无效')
            compressed.append(payload)
        elif kind==b'IEND':
            if size or not compressed or end!=len(data):raise ValueError('PNG 结束块无效')
            ended=True;break
        elif not re.fullmatch(b'[A-Za-z]{4}',kind) or not kind[0]&32:
            raise ValueError('PNG 包含未知关键数据块')
        if compressed and kind!=b'IDAT':idat_closed=True
        at=end
    if not ended:raise ValueError('PNG 缺少完整图像或结束块')
    passes=[(0,0,1,1)] if not interlace else [(0,0,8,8),(4,0,8,8),(0,4,4,8),(2,0,4,4),(0,2,2,4),(1,0,2,2),(0,1,1,2)]
    rows=[]
    for x,y,dx,dy in passes:
        pw=max(0,(w-x+dx-1)//dx);ph=max(0,(h-y+dy-1)//dy)
        if pw and ph:rows.extend([1+(pw*channels[color]*depth+7)//8]*ph)
    expected=sum(rows)
    try:
        decoder=zlib.decompressobj();pixels=decoder.decompress(b''.join(compressed),expected+1)
        if len(pixels)!=expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError('PNG 压缩像素长度不符或数据不完整')
    except zlib.error as exc:raise ValueError('PNG 压缩数据损坏') from exc
    pos=0
    for length in rows:
        if pixels[pos]>4:raise ValueError('PNG 行过滤参数无效')
        pos+=length
    return w,h


def _render_win(pdf:Path,png:Path,dpi:int)->tuple[int,int,int,float]:
    script=Path(__file__).resolve().parent/'platform/render_pdf_winrt.ps1'
    executable=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    # Only this packaged script in this child process. Group Policy still wins.
    # No Set-ExecutionPolicy, Unblock-File, shell interpolation or user scripts.
    cmd=[str(executable),'-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
         '-File',str(script),'-InputPath',str(pdf),'-OutputPath',str(png),'-Dpi',str(dpi)]
    try:
        proc=subprocess.run(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                            timeout=35,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except (subprocess.TimeoutExpired,OSError) as exc:
        raise ValueError('Windows 原生 PDF 渲染器不可用或超时（不修改原件）：'+type(exc).__name__) from exc
    result=proc.stdout.decode('utf-8-sig',errors='replace')
    line=re.search(r'HF6_PDF\|(\d+)\|(\d+)\|(\d+)\|([0-9.]+)',result)
    if proc.returncode or line is None:
        try:error=proc.stderr.decode('utf-8-sig').strip()
        except UnicodeDecodeError:error=proc.stderr.decode('mbcs',errors='replace').strip()
        if re.search(r'PSSecurityException|UnauthorizedAccess|SecurityError|execution polic|执行策略|数字签名',error,re.I):
            raise ValueError('Windows 安全策略阻止 PDF 渲染脚本。未更改系统策略；请同时选择 PDF 原件和 PNG 备用图，或联系管理员允许随包脚本。')
        raise ValueError('Windows PDF 预览失败；可同时导入 PDF 和 PNG 备用图。'+error[-240:])
    return int(line[1]),int(line[2]),int(line[3]),float(line[4])


def _render_poppler(pdf:Path,png:Path,dpi:int)->tuple[int,int,int,float]:
    poppler=shutil.which('pdftoppm')
    info=shutil.which('pdfinfo')
    if not poppler or not info:
        raise ValueError('本机缺少 PDF 图形渲染组件；请同时选择原始 PDF 和预览 PNG')
    try:
        detail=subprocess.run([info,str(pdf)],capture_output=True,timeout=8,check=True).stdout.decode('utf8',errors='replace')
        page_match=re.search(r'^Pages:\s*(\d+)\s*$',detail,re.M)
        size_match=re.search(r'^Page size:\s*([\d.]+)\s+x\s+([\d.]+)\s+pts',detail,re.M)
        if not page_match or not size_match:raise ValueError('PDF 页数或页面尺寸无法读取')
        pages=int(page_match[1]);wpt,hpt=float(size_match[1]),float(size_match[2])
        if not 1<=pages<=80 or wpt<=0 or hpt<=0:raise ValueError('PDF 页面数量或尺寸无效')
        # 300 DPI target, bounded by same limits as Windows WinRT renderer.
        scale=min(1.0,MAX_EDGE/max(wpt,hpt)*72/dpi,(MAX_PIXELS/(wpt*hpt)*(72/dpi)**2)**.5)
        actual_dpi=dpi*scale*.9999
        stem=png.with_suffix('')
        subprocess.run([poppler,'-f','1','-l','1','-singlefile','-r',str(actual_dpi),
                        '-png',str(pdf),str(stem)],stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=35)
        if not png.is_file():raise ValueError('PDF 渲染器没有生成预览图')
        width,height=png_dimensions(png.read_bytes())
        return width,height,pages,round(min(width/wpt,height/hpt)*72,2)
    except (OSError,subprocess.TimeoutExpired,subprocess.CalledProcessError) as exc:
        raise ValueError('PDF 渲染失败，原件未修改：'+type(exc).__name__) from exc


def render_pdf_preview(data:bytes,*,dpi:int=300)->PdfPreview:
    validate_pdf(data)
    if not isinstance(dpi,int) or not 72<=dpi<=600:raise ValueError('PDF 预览 DPI 无效')
    with tempfile.TemporaryDirectory(prefix='hrs_pdf_figure_') as temp:
        pdf=Path(temp)/'input.pdf';png=Path(temp)/'preview.png'
        pdf.write_bytes(data)
        if os.name=='nt':
            requested_w,requested_h,pages,actual_dpi=_render_win(pdf,png,dpi)
            engine='winrt-pdf'
        else:
            requested_w,requested_h,pages,actual_dpi=_render_poppler(pdf,png,dpi)
            engine='poppler'
        raw=png.read_bytes()
        width,height=png_dimensions(raw)
        if (width,height)!=(requested_w,requested_h):
            raise ValueError('PDF 渲染器返回的尺寸与 PNG 文件不一致')
        if not 1<=pages<=80 or not math.isfinite(actual_dpi) or not 0<actual_dpi<=600:
            raise ValueError('PDF 渲染器返回的页数或分辨率无效')
        return PdfPreview(raw,width,height,pages,actual_dpi,engine)
