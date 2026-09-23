# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Fetch pinned inert CERN hardware fixtures; never run upstream code."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request

COMMIT = '54f8a604978bdc65bbde5b1f4c7ec9bee3505a44'
REPOSITORY = 'https://gitlab.com/ohwr/project/wr-switch-hw'
FILES = (
    'circuit_board/wrs_v3/README.md',
    'circuit_board/wrs_v3/LICENSE.txt',
    'circuit_board/wrs_v3/SCB_SAM9G45/uTCA_MCH_PCB3.pcbdoc',
    'circuit_board/wrs_v3/mini_backplane_18SFP/miniBackplane.PcbDoc',
)


def decode_member(metadata, path):
    if metadata.get('file_path') != path or metadata.get('encoding') != 'base64':
        raise ValueError('Unexpected repository member')
    payload = base64.b64decode(metadata['content'], validate=True)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != metadata.get('content_sha256') or len(payload) != metadata.get('size'):
        raise ValueError('Repository member integrity mismatch')
    if len(payload) > 32*1024**2:
        raise ValueError('Board fixture size limit exceeded')
    return payload, digest


def fetch(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for path in FILES:
        url = ('https://gitlab.com/api/v4/projects/ohwr%2Fproject%2Fwr-switch-hw/'
               'repository/files/'+urllib.parse.quote(path, safe='')+'?ref='+COMMIT)
        request = urllib.request.Request(url, headers={'User-Agent': 'SPIKE-fixture-evaluation'})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read(48*1024**2+1)
        if len(data) > 48*1024**2:
            raise ValueError('Repository response size limit exceeded')
        payload, digest = decode_member(json.loads(data), path)
        target = output/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        rows.append({'path': path, 'sha256': digest, 'bytes': len(payload), 'url': url})
    report = {'repository': REPOSITORY, 'commit': COMMIT, 'files': rows,
              'license': 'CERN-OHL-1.2', 'use': 'local unmodified evaluation fixtures only',
              'complete_upstream_package': False, 'redistribution_reviewed': False,
              'solver_qualified': False}
    (output/'manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(fetch(parser.parse_args().output), indent=2))
