"""Data-only exchange package; import never executes or downloads models."""
from pathlib import Path
from copy import deepcopy
import json
from .component_catalog import validate_record,FAMILIES,NATIVE
from .symbol_validation import validate_symbol
from .document import write_json

CONTRACT='spikes/library-package/v1'


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
    if path.stat().st_size>32*1024*1024:raise ValueError('Library package exceeds 32 MiB')
    return validate(json.loads(path.read_text(encoding='utf-8')))


def save(path,records,symbols):
    value=validate({'contract':CONTRACT,'records':records,'symbols':symbols,
                    'notice':'Generic presets and symbol geometry, not a qualified manufacturer library. Preserve individual license/provenance fields.'})
    if len(json.dumps(value).encode())>32*1024*1024:raise ValueError('Library package exceeds 32 MiB')
    write_json(path,value)


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
