# SPDX-License-Identifier: Apache-2.0
"""Install an already verified optional Renode runtime without replacing Studio.

Never downloads, executes, overwrites an existing runtime or changes user data.
The complete upstream runtime and license tree are retained and hash checked.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'standalone/spikes_project/studio/python'))
from spikes_studio.renode_process import runtime_digest,ARCHIVE_SHA256,SOURCE_URL


def files(root):
    records=[]
    for path in sorted(root.rglob('*')):
        if path.is_symlink():raise ValueError('Runtime symlinks are not admitted for this Windows install')
        if path.is_file():
            with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            records.append({'path':path.relative_to(root).as_posix(),'bytes':path.stat().st_size,'sha256':digest})
    return records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();source=args.source.resolve(strict=True)
    runtime_digest(source/'Renode.exe')
    if not (source/'licenses/renode-license').is_file() or not (source/'licenses/tlib-license').is_file():
        raise ValueError('Complete upstream licenses are required')
    destination=Path(os.environ['LOCALAPPDATA'])/'Programs/SPIKES Studio Runtimes/Renode-1.17.0'
    destination=destination.resolve()
    expected=files(source)
    if destination.exists():
        if files(destination)!=expected:raise FileExistsError('Existing runtime differs; preserve it and review before replacing')
    else:
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(source,destination)
    if files(destination)!=expected:raise RuntimeError('Installed runtime file hashes differ')
    report={'version':'Renode 1.17.0','source_url':SOURCE_URL,'upstream_archive_sha256':ARCHIVE_SHA256,
            'destination':str(destination),'verified':True,'files':expected,'scope':'optional local runtime, not bundled in Studio installer'}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'verified':True,'destination':str(destination),'file_count':len(expected)}))


if __name__=='__main__':main()
