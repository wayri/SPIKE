"""Only pinned Berkeley modules may be loaded by a circuit document."""
import hashlib
import os
from pathlib import Path
import sys

MODELS={
    'bsim_bulk':('bsimbulk-107.2.1-windows-x64.osdi','bsimbulk','c78b891580105fa402431b2e0b50c0320a07092102d28abf771a6760a000ce03'),
    'bsim_cmg':('bsimcmg-112.1.0-windows-x64.osdi','bsimcmg_va','f85a3177eabebc123927d7443235305e55c656c5c8329f88970c7fe12bd3fad3'),
}

def resolve(family):
    if os.name!='nt':raise ValueError('Bundled BSIM modules currently require Windows x64')
    filename,module,expected=MODELS[family]
    roots=[Path(__file__).resolve().parents[2]/'artifacts/models']
    if getattr(sys,'frozen',False):roots.insert(0,Path(sys._MEIPASS)/'share/spikes/models')
    for root in roots:
        artifact=root/filename
        if artifact.is_file():
            with artifact.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
            if actual!=expected:raise ValueError('Berkeley BSIM module digest mismatch')
            return artifact,module
    raise ValueError('Pinned Berkeley BSIM module not installed')
