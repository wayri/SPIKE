"""Data-only inspection of mixed-domain library bundles; never loads code."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import re

CONTRACT = 'spikes/mixed-library/v1'
KINDS = {'spice', 'equations', 'c', 'cpp', 'verilog', 'vhdl', 'dll'}
DOMAINS = {'electrical', 'magnetic', 'thermal', 'mechanical', 'digital'}


def inspect_library(path):
    path = Path(path)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Manifest exceeds 1 MiB')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('contract') != CONTRACT:
        raise ValueError('Unsupported mixed-library contract')
    for key in ('id', 'version', 'license'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f'Missing {key}')
    entries = data.get('modules')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 256:
        raise ValueError('Expected 1..256 modules')
    root = path.resolve().parent
    ids, checked, total = set(), [], 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('Module must be an object')
        ident = entry.get('id')
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,127}', ident) or ident in ids:
            raise ValueError('Invalid or duplicate module ID')
        ids.add(ident)
        if entry.get('kind') not in KINDS:
            raise ValueError('Unsupported module kind')
        domains = entry.get('domains')
        if not isinstance(domains, list) or not domains or any(not isinstance(d, str) or d not in DOMAINS for d in domains):
            raise ValueError('Invalid module domains')
        name = entry.get('path')
        if not isinstance(name, str) or not name or '\\' in name or ':' in name:
            raise ValueError('Use portable relative paths')
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Path escapes package')
        target = root.joinpath(*relative.parts)
        cursor = target
        while cursor != root:
            if cursor.is_symlink() or (hasattr(cursor, 'is_junction') and cursor.is_junction()):
                raise ValueError('Linked payloads are forbidden')
            cursor = cursor.parent
        if not target.resolve().is_relative_to(root) or not target.is_file():
            raise ValueError('Missing or escaping payload')
        size = target.stat().st_size
        total += size
        if total > 64 * 1024 * 1024:
            raise ValueError('Payloads exceed 64 MiB')
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if entry.get('sha256') != digest:
            raise ValueError(f'Payload digest mismatch: {ident}')
        checked.append({'id': ident, 'kind': entry['kind'], 'domains': domains,
                        'path': name, 'sha256': digest, 'bytes': size})
    return {'contract': CONTRACT, 'id': data['id'], 'version': data['version'],
            'license': data['license'], 'modules': checked, 'bytes': total,
            'status': 'integrity_checked', 'execution_enabled': False,
            'limitations': ['Integrity is not authenticity or solver compatibility.',
                            'No payload was compiled, imported, evaluated or loaded.']}
