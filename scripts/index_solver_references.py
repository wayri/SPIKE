# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Index recorded public-tree links/DOIs; never infer adoption or fetch sources."""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ROOTS = ('docs', 'src', 'python/spike_core', 'python/spikes', 'tests/python', 'benchmarks')
EXCLUDE = {'docs/SOLVER_HANDBOOK.md', 'docs/SOLVER_REFERENCES.md'}
PATTERN = re.compile(r'https?://[^\s<>"\x27`\[\]|]+|\b10\.\d{4,9}/[^\s<>"\x27`\[\]|]+')


def references(text):
    found = set()
    for token in PATTERN.findall(text):
        token = token.rstrip('.,;:')
        while token.endswith(')') and token.count(')') > token.count('('):
            token = token[:-1]
        if token.startswith('10.'):
            token = 'https://doi.org/'+token
        found.add(token)
    return sorted(found)


def inventory(root=ROOT):
    entries = {}; files = 0
    for directory in ROOTS:
        for path in sorted((root/directory).rglob('*')):
            relative = path.relative_to(root).as_posix()
            if (not path.is_file() or path.is_symlink() or
                    path.suffix not in {'.md', '.py', '.cpp', '.hpp', '.h'} or
                    relative in EXCLUDE or 'generated' in path.parts or '__pycache__' in path.parts):
                continue
            files += 1
            for line, value in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
                for url in references(value):
                    entries.setdefault(url, []).append({'file': relative, 'line': line})
    return {'contract': 'spike/recorded-reference-inventory/v1',
            'scope_roots': list(ROOTS), 'files_scanned': files,
            'scope': 'Recorded links and DOIs only; not proof of reading, adoption, accuracy or license permission. Includes non-paper links.',
            'excluded': ['private repositories', 'build/runtime/downloads', 'generated files', *sorted(EXCLUDE)],
            'references': [{'url': url, 'occurrences': rows} for url, rows in sorted(entries.items())]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    destination = ROOT/'docs/generated/solver-reference-inventory.json'
    payload = json.dumps(inventory(), indent=2, ensure_ascii=True)+'\n'
    if args.check:
        raise SystemExit(0 if destination.exists() and destination.read_text(encoding='utf-8') == payload else 1)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding='utf-8')
    print(f'Indexed {len(json.loads(payload)["references"])} recorded references into {destination}')
