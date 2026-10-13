# SPDX-License-Identifier: Apache-2.0
"""Private Xyce input admission and bounded numeric CSV parsing."""
from __future__ import annotations
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import uuid

MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
SAFE_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z')
DIRECTIVES = {'.AC', '.DC', '.TRAN', '.OP', '.MODEL', '.SUBCKT', '.ENDS',
              '.END', '.PARAM', '.GLOBAL', '.TEMP', '.IC', '.NODESET',
              '.PRINT', '.INCLUDE', '.INC'}


def regular(path: Path) -> None:
    for item in (path, *path.parents):
        if item.exists():
            stat = item.lstat()
            if item.is_symlink() or getattr(stat, 'st_file_attributes', 0) & 0x400:
                raise ValueError('XYCE_PATH: symlinks/reparse points are not admitted.')


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def store_root() -> Path:
    base = os.environ.get('SPIKE_STATE_HOME') or os.environ.get('LOCALAPPDATA')
    root = (Path(base) if base else Path.home() / '.local' / 'state') / 'SPIKE' / 'xyce-cases'
    regular(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root.resolve()


def case_path(case_id) -> Path:
    if not isinstance(case_id, str) or not re.fullmatch(r'[0-9a-f]{32}', case_id):
        raise ValueError('XYCE_CASE: invalid private case ID.')
    path = store_root() / case_id
    regular(path)
    if not path.is_dir():
        raise ValueError('XYCE_CASE: case missing; prepare the netlist first.')
    return path


def admit_inputs(netlist, libraries) -> dict[str, str]:
    if not isinstance(netlist, str) or not netlist.strip():
        raise ValueError('XYCE_INPUT: native Xyce netlist text is required.')
    if not isinstance(libraries, list) or len(libraries) > 32:
        raise ValueError('XYCE_INPUT: at most 32 inert text libraries are admitted.')
    files = {'circuit.cir': netlist}
    names = {'circuit.cir'}
    for library in libraries:
        if not isinstance(library, dict) or set(library) != {'name', 'text'}:
            raise ValueError('XYCE_INPUT: library requires exactly name and text.')
        name, text = library['name'], library['text']
        if not isinstance(name, str) or not SAFE_NAME.fullmatch(name) or name.casefold() in names:
            raise ValueError('XYCE_INPUT: library names must be unique plain filenames.')
        if not name.lower().endswith(('.lib', '.inc', '.cir')) or not isinstance(text, str):
            raise ValueError('XYCE_INPUT: only inert .lib/.inc/.cir text is admitted.')
        names.add(name.casefold())
        files[name] = text
    if sum(len(t.encode('utf-8')) for t in files.values()) > MAX_INPUT_BYTES:
        raise ValueError('XYCE_INPUT: total input exceeds 2 MiB.')
    graph = {}
    prints = 0
    for name, text in files.items():
        graph[name] = []
        if any(ord(c) < 32 and c not in '\n\r\t' for c in text):
            raise ValueError('XYCE_INPUT: control characters are not admitted.')
        for index, line in enumerate(text.splitlines()):
            if len(line) > 8192:
                raise ValueError('XYCE_INPUT: line exceeds 8192 characters.')
            stripped = line.strip()
            if not stripped or stripped.startswith('*') or (name == 'circuit.cir' and index == 0):
                continue
            head = stripped.split()[0].upper()
            if not head.startswith('.') and head[0] not in 'RCLVIDQMBGEFHKSXJNZW+':
                raise ValueError('XYCE_DIALECT: device outside inert native subset.')
            if head.startswith('.') and head not in DIRECTIVES:
                raise ValueError(f'XYCE_DIALECT: {head} is outside the safe native subset.')
            if head in {'.INC', '.INCLUDE'}:
                tokens = shlex.split(stripped, posix=True)
                if len(tokens) != 2 or tokens[1] not in files or tokens[1] == 'circuit.cir':
                    raise ValueError('XYCE_INPUT: include must name a supplied inert text file.')
                graph[name].append(tokens[1])
            elif re.search(r'(?i)\b(file|filename|output|restart|load|plugin)\b|[\\]|\.\.', stripped):
                raise ValueError('XYCE_INPUT: external files and native plugins are not admitted.')
            if head == '.PRINT':
                prints += 1
                if not re.search(r'(?i)\bFORMAT\s*=\s*CSV\b', stripped):
                    raise ValueError('XYCE_OUTPUT: .PRINT requires FORMAT=CSV.')
    if prints > 8:
        raise ValueError('XYCE_OUTPUT: at most eight .PRINT statements are admitted.')
    visited = set()
    def visit(name, chain):
        if name in chain:
            raise ValueError('XYCE_INPUT: recursive includes are not admitted.')
        if name in visited:
            return
        for target in graph[name]:
            visit(target, chain | {name})
        visited.add(name)
    for name in files:
        visit(name, set())
    return files


def prepare(netlist, libraries) -> Path:
    files = admit_inputs(netlist, libraries)
    root = store_root()
    if len(list(root.iterdir())) >= 256:
        raise ValueError('XYCE_STORAGE: case limit reached; remove reviewed old cases locally.')
    path = root / uuid.uuid4().hex
    path.mkdir(mode=0o700)
    digests = {}
    for name, text in files.items():
        contents = text.encode('utf-8')
        (path / name).write_bytes(contents)
        digests[name] = hashlib.sha256(contents).hexdigest()
    (path / 'inputs.json').write_text(json.dumps(digests), encoding='utf-8')
    return path


def verify_case(path: Path) -> None:
    marker = path / 'inputs.json'
    regular(marker)
    if not marker.is_file() or marker.stat().st_size > 8192:
        raise ValueError('XYCE_CASE: integrity record missing or oversized.')
    digests = json.loads(marker.read_text(encoding='utf-8'))
    if not isinstance(digests, dict) or len(digests) > 33 or 'circuit.cir' not in digests:
        raise ValueError('XYCE_CASE: invalid integrity record.')
    files = {}
    for name, digest in digests.items():
        if not isinstance(name, str) or not SAFE_NAME.fullmatch(name):
            raise ValueError('XYCE_CASE: invalid input filename.')
        source = path / name
        regular(source)
        if not source.is_file() or source.stat().st_size > MAX_INPUT_BYTES:
            raise ValueError('XYCE_CASE: input missing or oversized.')
        contents = source.read_bytes()
        if hashlib.sha256(contents).hexdigest() != digest:
            raise ValueError('XYCE_CASE: input changed; prepare a fresh case.')
        files[name] = contents.decode('utf-8')
    admit_inputs(files.pop('circuit.cir'), [{'name': n, 'text': t} for n, t in files.items()])


def waveform(path: Path) -> dict:
    regular(path)
    if not path.is_file() or path.stat().st_size > MAX_OUTPUT_BYTES:
        raise ValueError('XYCE_OUTPUT: waveform missing or exceeds 4 MiB.')
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.reader(stream)
        headers = next(reader, [])
        if not headers or len(headers) > 64 or any(not h or len(h) > 256 for h in headers):
            raise ValueError('XYCE_OUTPUT: invalid CSV columns.')
        if len(set(headers)) != len(headers):
            raise ValueError('XYCE_OUTPUT: duplicate CSV columns.')
        rows = []
        for record in reader:
            if not record:
                continue
            if len(record) != len(headers) or len(rows) >= 20000:
                raise ValueError('XYCE_OUTPUT: inconsistent or excessive CSV rows.')
            try:
                values = [float(v) for v in record]
            except ValueError as error:
                raise ValueError('XYCE_OUTPUT: nonnumeric CSV data.') from error
            if not all(math.isfinite(v) for v in values):
                raise ValueError('XYCE_OUTPUT: nonfinite solver output.')
            rows.append(values)
    if not rows:
        raise ValueError('XYCE_OUTPUT: empty waveform.')
    def unit(header):
        name = header.upper()
        if name == 'TIME': return 's'
        if name in {'FREQ', 'FREQUENCY'}: return 'Hz'
        if re.match(r'V(R|I|M)?\(', name): return 'V'
        if re.match(r'I(R|I|M)?\(', name): return 'A'
        if re.match(r'[VI]P\(', name): return 'deg'
        if re.match(r'[VI]DB\(', name): return 'dB'
        return None
    return {'name': path.name, 'columns': [{'name': h, 'unit': unit(h)} for h in headers], 'rows': rows}


def artifacts(path: Path) -> list[dict]:
    entries = list(path.iterdir())
    if len(entries) > 96:
        raise ValueError('XYCE_OUTPUT: excessive artifact count.')
    output, total = [], 0
    for item in sorted(entries):
        regular(item)
        if not item.is_file():
            raise ValueError('XYCE_OUTPUT: unexpected non-file artifact.')
        size = item.stat().st_size
        total += size
        if total > 32 * 1024 * 1024 or size > 8 * 1024 * 1024:
            raise ValueError('XYCE_OUTPUT: artifact budget exceeded.')
        output.append({'name': item.name, 'bytes': size, 'sha256': file_digest(item)})
    return output
