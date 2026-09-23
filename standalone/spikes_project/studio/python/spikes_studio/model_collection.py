"""Bounded, metadata-only indexing of untrusted local SPICE collections.

No dependency is followed, model executed, or redistribution right inferred.
The original directory is the dependency boundary; it is never flattened.
"""
import hashlib
import os
from pathlib import Path

from .vendor_intake import inspect_text

EXTENSIONS = frozenset(('.lib', '.cir', '.sp', '.spi', '.spice', '.mod', '.model', '.sub', '.ckt', '.inc'))


def _contained(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Model path must remain inside the collection')
    target = root
    for part in relative.parts:
        target = target / part
        if target.is_symlink() or getattr(target, 'is_junction', lambda: False)():
            raise ValueError('Links and junctions are not accepted in model paths')
    if not target.resolve().is_relative_to(root):
        raise ValueError('Model path escapes the collection')
    return target


def _read(path, limit):
    # Bounded read also protects against files growing after stat.
    with path.open('rb') as source:
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Model file exceeds the configured byte limit')
    return raw


def scan_collection(root, maximum_files=20000, maximum_bytes=256*1024*1024,
                    maximum_file_bytes=2*1024*1024, maximum_entries=100000):
    """Index declarations without embedding model text or resolving includes.

    Limits stop scanning with an explicit ``truncated`` flag, never a silent
    complete result. Files that cannot be reviewed have per-file issues.
    ``maximum_entries`` bounds all visited directory entries and declarations.
    """
    for value in (maximum_files, maximum_bytes, maximum_file_bytes, maximum_entries):
        if type(value) is not int or value < 1:
            raise ValueError('Collection limits must be positive integers')
    root = Path(root).absolute()
    if root.is_symlink() or getattr(root, 'is_junction', lambda: False)():
        raise ValueError('Choose the actual collection directory, not a link')
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Collection root must be a directory')
    result = {'contract': 'spikes/model-collection/v1', 'root': str(root),
              'files': [], 'entries': [], 'issues': [], 'truncated': False,
              'execution': 'not_approved', 'compatibility': 'not_qualified',
              'redistribution': 'not_reviewed', 'maximum_file_bytes': maximum_file_bytes}
    visited = byte_count = attempted = 0
    pending = [root]

    def issue(path, message):
        result['issues'].append({'path': str(path), 'message': str(message)})

    while pending and not result['truncated']:
        directory = pending.pop()
        try:
            with os.scandir(directory) as children:
                for child in children:
                    visited += 1
                    if visited > maximum_entries:
                        issue('.', 'Directory-entry limit reached'); result['truncated'] = True; break
                    relative = Path(child.path).relative_to(root).as_posix()
                    try:
                        target = _contained(root, relative)
                        if child.is_dir(follow_symlinks=False):
                            pending.append(target); continue
                        if not child.is_file(follow_symlinks=False) or target.suffix.lower() not in EXTENSIONS:
                            continue
                        if attempted >= maximum_files:
                            issue(relative, 'File-count limit reached'); result['truncated'] = True; break
                        attempted += 1
                        size = target.stat().st_size
                        if size > maximum_file_bytes:
                            issue(relative, 'Model file exceeds the configured byte limit'); continue
                        if byte_count + size > maximum_bytes:
                            issue(relative, 'Collection byte limit reached'); result['truncated'] = True; break
                        raw = _read(target, min(maximum_file_bytes, maximum_bytes-byte_count))
                        byte_count += len(raw)
                        digest = hashlib.sha256(raw).hexdigest()
                        record = {'path': relative, 'content_sha256': digest, 'bytes': len(raw)}
                        result['files'].append(record)
                        try:
                            report = inspect_text(raw.decode('utf-8-sig'), relative)
                        except (ValueError, UnicodeError) as exc:
                            record['parse_issue'] = str(exc); issue(relative, exc); continue
                        report.pop('original_source')
                        report['content_sha256'] = digest
                        record['report'] = report
                        for kind, declarations in (('model', report['models']), ('subcircuit', report['subcircuits'])):
                            for declaration in declarations:
                                if len(result['entries']) >= maximum_entries:
                                    issue(relative, 'Declaration limit reached'); result['truncated'] = True; break
                                entry = dict(declaration, kind=kind, path=relative, content_sha256=digest,
                                             features=report['inventory']['features_requiring_review'],
                                             dependencies_not_loaded=report['dependencies_not_loaded'],
                                             execution='not_approved', compatibility='not_qualified',
                                             manufacturer=None, redistribution='not_reviewed')
                                entry['id'] = hashlib.sha256(f'{relative}\0{kind}\0{declaration["line"]}\0{declaration["name"]}'.encode()).hexdigest()
                                result['entries'].append(entry)
                            if result['truncated']: break
                    except (OSError, ValueError) as exc:
                        issue(relative, exc)
                    if result['truncated']: break
        except OSError as exc:
            issue(directory.relative_to(root).as_posix(), exc)
    result['entries'].sort(key=lambda e: (e['name'].casefold(), e['path'], e['line']))
    result['files'].sort(key=lambda f: f['path'])
    result['counts'] = {'visited': visited, 'files_attempted': attempted, 'files_read': len(result['files']),
                        'bytes_read': byte_count, 'declarations': len(result['entries'])}
    return result


def search_entries(index, query='', kind=None):
    """Case-insensitive AND search of names, paths, types, pins and features."""
    terms = str(query).casefold().split()
    return [entry for entry in index['entries']
            if (kind is None or entry['kind'] == kind)
            and all(term in ' '.join(str(entry.get(key, '')) for key in
                                    ('name', 'path', 'type', 'pins', 'features')).casefold() for term in terms)]


def read_entry(index, entry_or_id):
    """Revalidate original bytes and return a fresh, unapproved static review."""
    identifier = entry_or_id['id'] if isinstance(entry_or_id, dict) else entry_or_id
    matches = [entry for entry in index['entries'] if entry['id'] == identifier]
    if len(matches) != 1:
        raise ValueError('Unknown or ambiguous collection entry')
    entry = matches[0]
    root = Path(index['root'])
    if root.is_symlink() or getattr(root, 'is_junction', lambda: False)():
        raise ValueError('Collection root has become a link')
    root = root.resolve(strict=True)
    path = _contained(root, entry['path'])
    raw = _read(path, min(index.get('maximum_file_bytes', 2*1024*1024), 2*1024*1024))
    if hashlib.sha256(raw).hexdigest() != entry['content_sha256']:
        raise ValueError('Model changed since indexing; rescan the collection')
    report = inspect_text(raw.decode('utf-8-sig'), entry['path'])
    report['content_sha256'] = entry['content_sha256']
    report['selected_declaration'] = dict(entry)
    report['collection_root'] = str(root)
    return report
