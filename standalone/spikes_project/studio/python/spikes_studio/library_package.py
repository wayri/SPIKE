"""Data-only exchange package; import never executes or downloads models."""
from pathlib import Path
from copy import deepcopy
import hashlib
import json
import os
import re
import tempfile
from .component_catalog import validate_record,FAMILIES,NATIVE
from .symbol_validation import validate_symbol
from .document import write_json

CONTRACT='spikes/library-package/v1'
STORE_CONTRACT='spikes/library-store/v1'
MAX_BYTES=32*1024*1024
MAX_PACKAGES=1024
SCOPES=('installed','project','user')
_IDENTIFIER=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
_VERSION=re.compile(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9][A-Za-z0-9.-]{0,63})?\Z')


def _canonical(value):
    return json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')


def _atomic_bytes(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,name=tempfile.mkstemp(prefix='.spklib-',dir=path.parent)
    try:
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def validate(value):
    if value.get('contract')!=CONTRACT:raise ValueError('Unsupported library package')
    for key,limit,validator in [('records',10000,validate_record),('symbols',2000,validate_symbol)]:
        items=value.get(key)
        if not isinstance(items,list) or len(items)>limit:raise ValueError('Invalid '+key+' collection')
        seen=set()
        for item in items:
            validator(item)
            if not isinstance(item['id'],str) or item['id'] in seen:raise ValueError('Duplicate/invalid library ID')
            seen.add(item['id'])
            if key=='records':
                category=item.get('category')
                if category not in FAMILIES or item['family'] not in {f[0] for f in FAMILIES[category]}:raise ValueError('Invalid category/family mapping')
                status='native_subcircuit' if item['family'] in NATIVE else 'equation_bench_only'
                if item.get('status')!=status:raise ValueError('Execution status must match supported generic recipe')
                for field in ('name','parameter_unit','license','limitations'):
                    if not isinstance(item.get(field),str):raise ValueError('Missing library metadata: '+field)
    return value


def load(path):
    path=Path(path)
    if path.stat().st_size>MAX_BYTES:raise ValueError('Library package exceeds 32 MiB')
    return validate(json.loads(path.read_text(encoding='utf-8')))


def save(path,records,symbols):
    value=validate({'contract':CONTRACT,'records':records,'symbols':symbols,
                    'notice':'Generic presets and symbol geometry, not a qualified manufacturer library. Preserve individual license/provenance fields.'})
    if len(json.dumps(value).encode())>MAX_BYTES:raise ValueError('Library package exceeds 32 MiB')
    write_json(path,value)


class LibraryStore:
    """Persistent, data-only v1 packages; package identity is store metadata.

    root is an application-selected directory, not a path from a package.
    Installed, project and user scopes remain separate. No model is executed.
    """

    def __init__(self,root):
        self.root=Path(root)

    def _paths(self,scope):
        if scope not in SCOPES:raise ValueError('Invalid library scope')
        base=self.root/scope
        return base,base/'index.json',base/'blobs'

    @staticmethod
    def _identity(package_id,version=None):
        if not isinstance(package_id,str) or not _IDENTIFIER.fullmatch(package_id):raise ValueError('Invalid package ID')
        if version is not None and (not isinstance(version,str) or not _VERSION.fullmatch(version)):raise ValueError('Invalid package version')

    def _index(self,scope):
        _,path,_=self._paths(scope)
        if not path.exists():return {'contract':STORE_CONTRACT,'packages':{}}
        if path.stat().st_size>2*1024*1024:raise ValueError('Library index exceeds 2 MiB')
        value=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value,dict) or value.get('contract')!=STORE_CONTRACT or not isinstance(value.get('packages'),dict):raise ValueError('Invalid library index')
        if len(value['packages'])>MAX_PACKAGES:raise ValueError('Too many installed library packages')
        for package_id,item in value['packages'].items():
            self._identity(package_id)
            if not isinstance(item,dict) or not isinstance(item.get('versions'),dict) or not isinstance(item.get('history'),list):raise ValueError('Invalid library index entry')
            versions=item['versions'];active=item.get('active')
            if len(versions)>128 or active is not None and active not in versions or len(item['history'])>128:raise ValueError('Invalid library version state')
            for version,digest in versions.items():
                self._identity(package_id,version)
                if not isinstance(digest,str) or not re.fullmatch(r'[0-9a-f]{64}',digest):raise ValueError('Invalid library content hash')
            if any(version not in versions for version in item['history']):raise ValueError('Invalid library rollback history')
        return value

    def _write_index(self,scope,index):
        data=_canonical(index)
        if len(data)>2*1024*1024:raise ValueError('Library index exceeds 2 MiB')
        _,path,_=self._paths(scope)
        _atomic_bytes(path,data)

    def import_package(self,path,package_id,version,*,scope='user',activate=True):
        """Install a v1 package. A changed same-ID/version is a hard conflict."""
        self._identity(package_id,version)
        value=load(path)
        data=_canonical(value)
        if len(data)>MAX_BYTES:raise ValueError('Library package exceeds 32 MiB')
        digest=hashlib.sha256(data).hexdigest()
        index=self._index(scope);packages=index['packages']
        if package_id not in packages and len(packages)>=MAX_PACKAGES:raise ValueError('Too many installed library packages')
        entry=packages.setdefault(package_id,{'active':None,'versions':{},'history':[]})
        prior=entry['versions'].get(version)
        if prior is not None and prior!=digest:raise ValueError('Conflicting package ID and version')
        if prior is None and len(entry['versions'])>=128:raise ValueError('Too many package versions')
        _,_,blobs=self._paths(scope)
        blob=blobs/(digest+'.spklib')
        if blob.exists() and hashlib.sha256(blob.read_bytes()).hexdigest()!=digest:raise ValueError('Stored library content was modified')
        if not blob.exists():_atomic_bytes(blob,data)
        entry['versions'][version]=digest
        if activate or entry['active'] is None:self._activate_entry(entry,version)
        self._write_index(scope,index)
        return {'scope':scope,'package_id':package_id,'version':version,'sha256':digest}

    @staticmethod
    def _activate_entry(entry,version):
        previous=entry['active']
        if previous==version:return
        if previous is not None:entry['history']=(entry['history']+[previous])[-128:]
        entry['active']=version

    def activate(self,package_id,version,*,scope='user'):
        self._identity(package_id,version)
        index=self._index(scope);entry=index['packages'].get(package_id)
        if entry is None or version not in entry['versions']:raise ValueError('Package version is not installed')
        self.get_package(package_id,version,scope=scope)
        self._activate_entry(entry,version);self._write_index(scope,index)

    def rollback(self,package_id,*,scope='user'):
        self._identity(package_id)
        index=self._index(scope);entry=index['packages'].get(package_id)
        if entry is None or not entry['history']:raise ValueError('No prior active version')
        version=entry['history'][-1]
        self.get_package(package_id,version,scope=scope)
        entry['history'].pop();entry['active']=version
        self._write_index(scope,index)
        return version

    def get_package(self,package_id,version=None,*,scope='user'):
        self._identity(package_id,version)
        index=self._index(scope);entry=index['packages'].get(package_id)
        if entry is None:raise ValueError('Package is not installed')
        version=version or entry['active']
        if version not in entry['versions']:raise ValueError('Package version is not installed')
        digest=entry['versions'][version]
        _,_,blobs=self._paths(scope);path=blobs/(digest+'.spklib')
        if path.stat().st_size>MAX_BYTES:raise ValueError('Stored library exceeds 32 MiB')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Stored library content was modified')
        return validate(json.loads(data.decode('utf-8')))

    def export_package(self,path,package_id,version=None,*,scope='user'):
        value=self.get_package(package_id,version,scope=scope)
        _atomic_bytes(Path(path),_canonical(value))

    def list_packages(self,*,scope=None):
        scopes=(scope,) if scope is not None else SCOPES
        result=[]
        for selected in scopes:
            for package_id,entry in self._index(selected)['packages'].items():
                for version,digest in entry['versions'].items():
                    result.append({'scope':selected,'package_id':package_id,'version':version,'sha256':digest,'active':version==entry['active']})
        return sorted(result,key=lambda row:(row['scope'],row['package_id'],row['version']))

    def search(self,query,*,scope=None,limit=100):
        if not isinstance(query,str) or len(query)>512 or type(limit) is not int or not 1<=limit<=1000:raise ValueError('Invalid library search')
        query=query.casefold()
        return [item for item in self.list_packages(scope=scope) if query in item['package_id'].casefold()][:limit]


def merge(existing,incoming):
    result={item['id']:deepcopy(item) for item in existing}
    for item in incoming:
        if item['id'] in result and result[item['id']]!=item:raise ValueError('Conflicting library ID; rename before import: '+item['id'])
        result[item['id']]=deepcopy(item)
    return list(result.values())


def exchange(owner,export=False):
    if owner.job_running:raise ValueError('Stop active work before changing libraries')
    path=owner.choose_path('Export library package' if export else 'Import library package','SPIKES library package (*.spklib)|*.spklib',export)
    if not path:return
    panel=owner.catalog_panel
    if export:save(path,panel.catalog['records'],list(owner.symbols.values()));return
    value=load(path)
    records=merge(panel.catalog['records'],value['records']);symbols=merge(list(owner.symbols.values()),value['symbols'])
    from .library_browser import CatalogIndex
    index=CatalogIndex(records)
    panel.catalog['records']=records;panel.index=index;owner.symbols={s['id']:s for s in symbols}
    panel.reset_filters();panel.filter();owner.filter_library()
    owner.SetStatusText('Library imported into this session. Export .spklib to retain and exchange it; no model code was executed.')
