# SPDX-License-Identifier: Apache-2.0
"""Fixed guardian: wrapper death cancels its owned Palace process tree."""
import os
from pathlib import Path
import sys
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from extensions.palace_suite import runtime

def main():
    control=Path(sys.argv[1])
    request=runtime.strict_json(runtime.read_file(control/'request.json',4*1024**2))
    owner=int(request['owner_pid'])
    cancel=threading.Event()
    done=threading.Event()
    owner_handle=None
    if os.name=='nt':
        import ctypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=(ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong)
        kernel.OpenProcess.restype=ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes=(ctypes.c_void_p,ctypes.c_ulong)
        kernel.CloseHandle.argtypes=(ctypes.c_void_p,)
        owner_handle=kernel.OpenProcess(0x00100000,False,owner)
    def watch():
        while not done.wait(0.1):
            missing=(not owner_handle or kernel.WaitForSingleObject(owner_handle,0)==0) if os.name=='nt' else os.getppid()!=owner
            if missing or (control/'cancel').exists():
                cancel.set()
                return
    threading.Thread(target=watch,daemon=True).start()
    try:
        action=runtime.native_validate if request.get('operation')=='validate' else runtime.run
        result=action(request['parameters'],request['binding'],cancel)
    except Exception as exc:
        result={'status':'failed','solved':False,'issues':[{'code':'runtime_failure','message':str(exc)}]}
    finally:
        done.set()
        if owner_handle is not None:
            kernel.CloseHandle(owner_handle)
    (control/'result.json').write_bytes(runtime.encoded(result))

if __name__=='__main__':
    main()


