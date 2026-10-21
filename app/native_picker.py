"""Windows Common Item Dialog, using only the embedded Python standard library.

Selections remain native user actions. History is navigation convenience, never
filesystem authority or a way for HTTP callers to supply arbitrary paths.
"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import secrets
import threading
import uuid


class PickerHistory:
    def __init__(self,workspace):
        self.path=Path(workspace)/'.picker-history.json';self.guard=threading.Lock()

    def _load(self):
        try:
            value=json.loads(self.path.read_text('utf8'))
            return value if isinstance(value,dict) else {}
        except (OSError,ValueError):return {}

    def get(self,purpose):
        with self.guard:value=self._load().get(purpose)
        if isinstance(value,str):
            path=Path(value)
            if path.is_absolute() and path.is_dir():return path
        return None

    def remember(self,purpose,selection,folder=False):
        if selection is None:return
        path=Path(selection).resolve(strict=True)
        directory=path if folder else path.parent
        if not directory.is_dir():raise ValueError('所选路径不是现有目录')
        with self.guard:
            value=self._load();value[purpose]=str(directory)
            temporary=self.path.with_name(self.path.name+'.'+secrets.token_hex(6)+'.tmp')
            try:
                temporary.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
                os.replace(temporary,self.path)
            finally:temporary.unlink(missing_ok=True)


_history=None
def configure(workspace):
    global _history
    _history=PickerHistory(workspace)


def choose(*,purpose,title,folder=False,filters=()):
    if os.name!='nt':raise NotImplementedError('本机路径选择需要 Windows')
    history=_history
    result=_dialog(purpose=purpose,title=title,folder=folder,filters=filters,
                   initial=history.get(purpose) if history else None)
    if history:history.remember(purpose,result,folder)
    return result


class GUID(ctypes.Structure):
    _fields_=[('Data1',ctypes.c_uint32),('Data2',ctypes.c_uint16),('Data3',ctypes.c_uint16),('Data4',ctypes.c_ubyte*8)]
    @classmethod
    def value(cls,text):return cls.from_buffer_copy(uuid.UUID(text).bytes_le)

def _show(dialog,call,owner):
    return call(dialog,3,[wintypes.HWND],[owner])

def _dialog(*,purpose,title,folder,filters,initial):
    ole=ctypes.WinDLL('ole32');shell=ctypes.WinDLL('shell32');user=ctypes.WinDLL('user32')
    ole.CoInitializeEx.argtypes=[ctypes.c_void_p,wintypes.DWORD];ole.CoInitializeEx.restype=ctypes.c_long
    ole.CoCreateInstance.argtypes=[ctypes.POINTER(GUID),ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)];ole.CoCreateInstance.restype=ctypes.c_long
    ole.CoTaskMemFree.argtypes=[ctypes.c_void_p]
    user.GetForegroundWindow.argtypes=[];user.GetForegroundWindow.restype=wintypes.HWND
    shell.SHCreateItemFromParsingName.argtypes=[wintypes.LPCWSTR,ctypes.c_void_p,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)];shell.SHCreateItemFromParsingName.restype=ctypes.c_long
    def check(hr):
        if hr<0:raise OSError('打开系统路径选择器失败，HRESULT=0x%08X'%(hr&0xffffffff))
    def call(obj,index,types=(),args=()):
        table=ctypes.cast(obj,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        method=ctypes.WINFUNCTYPE(ctypes.c_long,ctypes.c_void_p,*types)(table[index])
        return method(obj,*args)
    apartment=ole.CoInitializeEx(None,2);check(apartment)
    dialog=ctypes.c_void_p();item=ctypes.c_void_p();initial_item=ctypes.c_void_p();display=ctypes.c_void_p()
    try:
        clsid=GUID.value('dc1c5a9c-e88a-4dde-a5a1-60f82a20aef7');iid=GUID.value('d57c7288-d4ad-4768-be02-9d969532d960')
        check(ole.CoCreateInstance(ctypes.byref(clsid),None,1,ctypes.byref(iid),ctypes.byref(dialog)))
        client=GUID.value(str(uuid.uuid5(uuid.NAMESPACE_URL,'hrs-local-picker:'+purpose)))
        check(call(dialog,24,[ctypes.POINTER(GUID)],[ctypes.byref(client)]))
        options=wintypes.DWORD();check(call(dialog,10,[ctypes.POINTER(wintypes.DWORD)],[ctypes.byref(options)]))
        flags=options.value|0x40|0x800|0x8|(0x20 if folder else 0x1000)
        check(call(dialog,9,[wintypes.DWORD],[flags]));check(call(dialog,17,[wintypes.LPCWSTR],[title]))
        if folder:check(call(dialog,18,[wintypes.LPCWSTR],['选择此文件夹']))
        elif filters:
            class FILTER(ctypes.Structure):_fields_=[('name',wintypes.LPCWSTR),('pattern',wintypes.LPCWSTR)]
            specs=(FILTER*len(filters))(*(FILTER(*entry) for entry in filters))
            check(call(dialog,4,[wintypes.UINT,ctypes.POINTER(FILTER)],[len(specs),specs]))
        if initial:
            shell_iid=GUID.value('43826d1e-e718-42ee-bc55-a1e261c37bfe')
            if shell.SHCreateItemFromParsingName(str(initial),None,ctypes.byref(shell_iid),ctypes.byref(initial_item))>=0:
                # Explicit successful-selection history takes priority over a
                # directory merely visited before cancelling the last dialog.
                check(call(dialog,12,[ctypes.c_void_p],[initial_item]))
        owner=user.GetForegroundWindow()
        if os.environ.get('HRS_DESKTOP_HWND'):
            candidate=int(os.environ['HRS_DESKTOP_HWND'])
            user.IsWindow.argtypes=[wintypes.HWND];user.IsWindow.restype=wintypes.BOOL
            if user.IsWindow(candidate):owner=candidate
        hr=_show(dialog,call,owner)
        if hr&0xffffffff==0x800704c7:return None
        check(hr);check(call(dialog,20,[ctypes.POINTER(ctypes.c_void_p)],[ctypes.byref(item)]))
        check(call(item,5,[ctypes.c_uint,ctypes.POINTER(ctypes.c_void_p)],[0x80058000,ctypes.byref(display)]))
        return Path(ctypes.wstring_at(display)).resolve(strict=True)
    finally:
        if display:ole.CoTaskMemFree(display)
        for obj in (item,initial_item,dialog):
            if obj:call(obj,2)
        ole.CoUninitialize()
