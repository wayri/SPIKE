# SPDX-License-Identifier: Apache-2.0
"""Bounded local Windows named-pipe rendezvous for owned MMIO callbacks.

This is trusted-runtime crash containment, not a hostile-code security sandbox.
No TCP listener, shell command or imported script is exposed by this protocol.
"""
import ctypes as C
import os
import secrets
import threading


def _kernel():
    from ctypes import wintypes as W
    api=C.WinDLL('kernel32',use_last_error=True)
    specs={
        'CreateNamedPipeW':([W.LPCWSTR,W.DWORD,W.DWORD,W.DWORD,W.DWORD,W.DWORD,W.DWORD,C.c_void_p],W.HANDLE),
        'ConnectNamedPipe':([W.HANDLE,C.c_void_p],W.BOOL),
        'ReadFile':([W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p],W.BOOL),
        'WriteFile':([W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p],W.BOOL),
        'DisconnectNamedPipe':([W.HANDLE],W.BOOL),'CloseHandle':([W.HANDLE],W.BOOL),
        'OpenThread':([W.DWORD,W.BOOL,W.DWORD],W.HANDLE),
        'CancelSynchronousIo':([W.HANDLE],W.BOOL)}
    for name,(args,result) in specs.items():
        fn=getattr(api,name);fn.argtypes=args;fn.restype=result
    return api


class FirmwarePipe:
    def __init__(self,callback):
        if os.name!='nt':raise ValueError('Reviewed firmware pipe requires Windows')
        self.api=_kernel();self.callback=callback
        self.name='spikes-mmio-'+secrets.token_hex(16)
        self.token=secrets.token_hex(32)
        self.handle=self.api.CreateNamedPipeW('\\\\.\\pipe\\'+self.name,
            3|0x80000,8,1,8192,8192,0,None)
        if self.handle==C.c_void_p(-1).value:raise C.WinError(C.get_last_error())
        self.stop=threading.Event();self.ready=threading.Event();self.error=None
        self.thread=threading.Thread(target=self._run,daemon=True,name='spikes-owned-mmio')
        self.thread.start()
        if not self.ready.wait(2):self.close();raise TimeoutError('MMIO pipe thread startup')

    def _write(self,text):
        data=(text+'\n').encode('ascii')
        if len(data)>8192:raise ValueError('MMIO response limit')
        count=C.c_ulong()
        if not self.api.WriteFile(self.handle,data,len(data),C.byref(count),None):
            raise C.WinError(C.get_last_error())
        if count.value!=len(data):raise RuntimeError('Incomplete MMIO response')

    def _lines(self):
        data=b'';buffer=C.create_string_buffer(1024);count=C.c_ulong()
        while not self.stop.is_set():
            if not self.api.ReadFile(self.handle,buffer,len(buffer),C.byref(count),None):
                raise C.WinError(C.get_last_error())
            if not count.value:raise EOFError('MMIO client closed')
            data+=buffer.raw[:count.value]
            if len(data)>8192:raise ValueError('MMIO request limit')
            while b'\n' in data:
                line,data=data.split(b'\n',1)
                yield line.decode('ascii',errors='strict')

    def _run(self):
        self.ready.set()
        try:
            if not self.api.ConnectNamedPipe(self.handle,None) and C.get_last_error()!=535:
                raise C.WinError(C.get_last_error())
            lines=self._lines()
            if next(lines)!='HELLO '+self.token:raise ValueError('MMIO authentication rejected')
            self._write('OK')
            for line in lines:
                fields=line.split()
                if len(fields)!=6 or any(not item.isascii() or not item.isdecimal() or len(item)>20 for item in fields):
                    raise ValueError('Malformed MMIO integer request')
                stamp,device,write,offset,value,width=map(int,fields)
                if stamp>1<<48 or device>11 or write>1 or offset>=1024 or value>0xffffffff or width not in (1,2,4):
                    raise ValueError('MMIO request outside admitted range')
                result=self.callback(stamp,device,bool(write),offset,value,width)
                values=result if isinstance(result,tuple) else (result,)
                if not 1<=len(values)<=8 or any(type(n) is not int or not 0<=n<=0xffffffff for n in values):raise ValueError('Invalid MMIO result')
                self._write('OK '+' '.join(str(n) for n in values))
        except BaseException as exc:
            if not self.stop.is_set():
                self.error=exc
                try:self._write('FAIL')
                except OSError:pass

    def close(self):
        if getattr(self,'handle',None) is None:return
        self.stop.set()
        if self.thread.is_alive() and self.thread.native_id:
            thread_handle=self.api.OpenThread(1,False,self.thread.native_id)
            if thread_handle:
                self.api.CancelSynchronousIo(thread_handle);self.api.CloseHandle(thread_handle)
        self.thread.join(timeout=2)
        self.api.DisconnectNamedPipe(self.handle);self.api.CloseHandle(self.handle);self.handle=None
        if self.thread.is_alive():raise RuntimeError('MMIO pipe did not stop cleanly')
