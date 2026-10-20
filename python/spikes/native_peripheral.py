# SPDX-License-Identifier: Apache-2.0
"""Owned native peripheral clock/state service; Python transports only integers."""
import ctypes as C
from .native_abi import NativeABIError

PERIPHERAL_SYMBOLS=tuple('spikes_peripheral_'+name for name in
    ('create','destroy','last_error','command','next','resolve','write','read','gpio_inputs'))

class _Event(C.Structure):
    _fields_=[('time_ns',C.c_uint64)]+[(n,C.c_uint32) for n in
        ('drive_mask','high_mask','release_mask','sample_mask')]

def require_peripheral_api(library):
    lib=library._library
    missing=[name for name in PERIPHERAL_SYMBOLS if not hasattr(lib,name)]
    if missing:raise NativeABIError('Native peripheral API missing: '+', '.join(missing))
    signatures={
        'create':[C.c_uint64,C.c_uint64,C.c_uint64,C.POINTER(C.c_void_p)],
        'destroy':[C.c_void_p],'last_error':[],
        'command':[C.c_void_p,C.c_uint32,*([C.c_uint64]*4),C.POINTER(C.c_uint32)],
        'next':[C.c_void_p,C.c_uint64,C.POINTER(_Event),C.POINTER(C.c_uint32)],
        'resolve':[C.c_void_p,C.c_uint32],
        'write':[C.c_void_p,*([C.c_uint32]*4)],
        'read':[C.c_void_p,*([C.c_uint32]*3),C.POINTER(C.c_uint32)],
        'gpio_inputs':[C.c_void_p,*([C.c_uint32]*3)]}
    for name,types in signatures.items():
        fn=getattr(lib,'spikes_peripheral_'+name);fn.argtypes=types
        fn.restype=C.c_char_p if name=='last_error' else None if name=='destroy' else C.c_int
    return lib

def integer(n,maximum=(1<<64)-1):
    if type(n) is not int or not 0<=n<=maximum:raise ValueError('Expected bounded unsigned integer')
    return n

class NativePeripheral:
    def __init__(self,library,*,timer_hz=10_000_000,spi_hz=80_000_000,i2c_hz=8_000_000):
        self.api=require_peripheral_api(library);self.handle=C.c_void_p()
        self._check(self.api.spikes_peripheral_create(*(integer(v) for v in (timer_hz,spi_hz,i2c_hz)),C.byref(self.handle)))
    def _check(self,result):
        if result:raise NativeABIError(self.api.spikes_peripheral_last_error().decode('utf-8',errors='replace'))
    def _open(self):
        if not self.handle.value:raise ValueError('Native peripheral service closed')
        return self.handle
    def command(self,operation,*args):
        if len(args)>4:raise ValueError('At most four command arguments')
        out=C.c_uint32()
        self._check(self.api.spikes_peripheral_command(self._open(),integer(operation,0xffffffff),
            *(integer(v) for v in (*args,*([0]*(4-len(args))))),C.byref(out)))
        return out.value
    def next(self,deadline_ns):
        event=_Event();present=C.c_uint32()
        self._check(self.api.spikes_peripheral_next(self._open(),integer(deadline_ns),C.byref(event),C.byref(present)))
        return {key:getattr(event,key) for key,_ in event._fields_} if present.value else None
    def resolve(self,high_mask):
        self._check(self.api.spikes_peripheral_resolve(self._open(),integer(high_mask,63)))
    def write(self,device,offset,value,width=4):
        self._check(self.api.spikes_peripheral_write(self._open(),*(integer(v,0xffffffff) for v in (device,offset,value,width))))
    def read(self,device,offset,width=4):
        out=C.c_uint32()
        self._check(self.api.spikes_peripheral_read(self._open(),*(integer(v,0xffffffff) for v in (device,offset,width)),C.byref(out)))
        return out.value
    def close(self):
        if self.handle.value:self.api.spikes_peripheral_destroy(self.handle);self.handle.value=None
    def gpio_inputs(self,port,mask,high):
        self._check(self.api.spikes_peripheral_gpio_inputs(self._open(),*(integer(v,0xffffffff) for v in (port,mask,high))))
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
