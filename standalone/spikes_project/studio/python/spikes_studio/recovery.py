"""Atomic recovery snapshots, never overwriting a user's project file."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import os
import uuid
from .document import Document,write_json


class Recovery:
    def __init__(self,directory=None):
        self.directory=Path(directory or Path(os.environ.get('LOCALAPPDATA',Path.home()))/'SPIKES Studio'/'recovery')
        self.session=uuid.uuid4().hex;self.last=None

    def save(self,document,source,path=None):
        if not document.dirty and source==document.data['source']:return None
        value={'contract':'spikes/recovery/v1','document':deepcopy(document.data),'source_draft':source,'original_path':None if path is None else str(path)}
        encoded=json.dumps(value,sort_keys=True,allow_nan=False).encode()
        if len(encoded)>32*1024*1024:raise ValueError('Autosave snapshot exceeds 32 MiB')
        digest=hashlib.sha256(encoded).hexdigest()
        if self.last==digest:return None
        self.directory.mkdir(parents=True,exist_ok=True)
        ident=hashlib.sha256(str(document.data['id']).encode()).hexdigest()[:24]
        target=self.directory/(self.session+'-'+ident+'.spkrecovery')
        write_json(target,value);self.last=digest;return target


def restore(path):
    path=Path(path)
    if path.stat().st_size>32*1024*1024:raise ValueError('Recovery snapshot exceeds 32 MiB')
    value=json.loads(path.read_text(encoding='utf-8'))
    if value.get('contract')!='spikes/recovery/v1' or not isinstance(value.get('source_draft'),str):raise ValueError('Invalid recovery snapshot')
    document=Document(value['document'])
    # Recover as an unsaved copy; never silently overwrite original_path.
    document.saved_data={}
    return document,value['source_draft']
