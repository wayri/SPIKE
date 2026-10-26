# SPDX-License-Identifier: Apache-2.0
"""Observational current-process Windows memory diagnostics; no solver control."""
import os


def current_process_memory():
    if os.name!='nt':return {'available':False,'reason':'Windows diagnostic only'}
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
    data=Counters();data.cb=ctypes.sizeof(data)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.GetCurrentProcess.restype=wintypes.HANDLE
    psapi=ctypes.WinDLL('psapi',use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(data),data.cb):return {'available':False,'Windows_error':ctypes.get_last_error()}
    return {'available':True,'private_commit_bytes':int(data.PrivateUsage),'working_set_bytes':int(data.WorkingSetSize),'peak_commit_bytes':int(data.PeakPagefileUsage),'peak_working_set_bytes':int(data.PeakWorkingSetSize)}
