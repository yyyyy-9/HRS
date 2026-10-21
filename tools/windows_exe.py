"""Apply the existing HRS icon and derived product identity to its Windows EXE."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import struct


def version_resource(version,product_name):
    parts=tuple(map(int,version.split('.')))+(0,)
    if len(parts)!=4 or any(not 0<=p<=65535 for p in parts):raise ValueError('Invalid PE version')
    def pad(raw):return raw+b'\0'*((-len(raw))%4)
    def block(key,value=b'',children=b'',text=False):
        head=struct.pack('<HHH',0,len(value)//2 if text else len(value),1 if text else 0)+key.encode('utf-16-le')+b'\0\0'
        result=pad(head)+value
        if children:result=pad(result)+children
        return struct.pack('<H',len(result))+result[2:]
    strings={'FileDescription':product_name,'FileVersion':version,
             'InternalName':'HRS','OriginalFilename':'HRS.exe','ProductName':product_name,'ProductVersion':version}
    children=b''.join(pad(block(k,(v+'\0').encode('utf-16-le'),text=True)) for k,v in strings.items())
    string_info=block('StringFileInfo',children=block('040904B0',children=children,text=True),text=True)
    variables=block('VarFileInfo',children=block('Translation',struct.pack('<HH',0x409,1200)))
    ms=parts[0]<<16|parts[1];ls=parts[2]<<16|parts[3]
    fixed=struct.pack('<13I',0xFEEF04BD,0x10000,ms,ls,ms,ls,0x3F,0,0x40004,1,0,0,0)
    return block('VS_VERSION_INFO',fixed,pad(string_info)+variables)


def brand(executable,icon,version,product_name):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    begin=kernel.BeginUpdateResourceW;begin.argtypes=[wintypes.LPCWSTR,wintypes.BOOL];begin.restype=wintypes.HANDLE
    put=kernel.UpdateResourceW;put.argtypes=[wintypes.HANDLE,ctypes.c_void_p,ctypes.c_void_p,wintypes.WORD,ctypes.c_void_p,wintypes.DWORD];put.restype=wintypes.BOOL
    end=kernel.EndUpdateResourceW;end.argtypes=[wintypes.HANDLE,wintypes.BOOL];end.restype=wintypes.BOOL
    handle=begin(str(Path(executable)),False)
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    try:
        def write(kind,number,language,raw):
            buffer=ctypes.create_string_buffer(raw)
            if not put(handle,ctypes.c_void_p(kind),ctypes.c_void_p(number),language,buffer,len(raw)):raise ctypes.WinError(ctypes.get_last_error())
        raw=Path(icon).read_bytes();reserved,kind,count=struct.unpack_from('<HHH',raw)
        if reserved or kind!=1 or not 1<=count<=64:raise ValueError('Invalid HRS ICO')
        entries=[]
        for i in range(count):
            w,h,colors,reserved,planes,bits,size,offset=struct.unpack_from('<BBBBHHII',raw,6+16*i)
            image=raw[offset:offset+size]
            if len(image)!=size:raise ValueError('Truncated HRS ICO')
            for lang in (0,0x409):write(3,i+1,lang,image)
            entries.append(struct.pack('<BBBBHHIH',w,h,colors,reserved,planes,bits,size,i+1))
        group=struct.pack('<HHH',0,1,count)+b''.join(entries)
        for lang in (0,0x409):
            write(14,1,lang,group);write(16,1,lang,version_resource(version,product_name))
        if not end(handle,False):raise ctypes.WinError(ctypes.get_last_error())
        handle=None
    finally:
        if handle:end(handle,True)
