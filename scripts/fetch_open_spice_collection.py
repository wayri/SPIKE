"""Fetch a pinned Apache-2.0 SKY130 model-source subset; never execute it."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import urllib.request
import zipfile

REVISION='f62031a1be9aefe902d6d54cddd6f59b57627436'
REPOSITORY='https://github.com/google/skywater-pdk-libs-sky130_fd_pr'
URL=f'https://codeload.github.com/google/skywater-pdk-libs-sky130_fd_pr/zip/{REVISION}'

def fetch(destination):
    destination=Path(destination).resolve()
    if destination.exists():raise ValueError('Choose a new destination; existing collections are never overwritten')
    with urllib.request.urlopen(URL,timeout=60) as response:
        raw=response.read(128*1024*1024+1)
    if len(raw)>128*1024*1024:raise ValueError('Archive exceeds 128 MiB download limit')
    archive=zipfile.ZipFile(io.BytesIO(raw));selected=[];total=0
    for item in archive.infolist():
        parts=PurePosixPath(item.filename).parts[1:]
        if item.is_dir() or not parts:continue
        path=PurePosixPath(*parts)
        if '..' in parts or path.is_absolute() or stat.S_ISLNK(item.external_attr>>16):raise ValueError('Unsafe archive path')
        # Keep text model hierarchy and all license/attribution notices, not layout databases.
        if not (parts[0]=='models' or path.suffix.lower() in ('.spice','.sp','.lib','.model','.pm3') or path.name.upper().startswith(('LICENSE','NOTICE','COPYING')) or str(path)=='README.rst'):continue
        total+=item.file_size
        if total>256*1024*1024 or item.file_size>8*1024*1024:raise ValueError('Model source extraction limit exceeded')
        selected.append((item,path))
    license_item=next(item for item,path in selected if str(path)=='LICENSE')
    if b'Apache License' not in archive.read(license_item):raise ValueError('Expected upstream license not found')
    destination.mkdir(parents=True)
    manifest=[]
    for item,path in selected:
        output=destination.joinpath(*path.parts)
        if not output.resolve().is_relative_to(destination):raise ValueError('Unsafe destination')
        content=archive.read(item);output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(content)
        manifest.append({'path':str(path),'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)})
    record={'repository':REPOSITORY,'revision':REVISION,'archive_sha256':hashlib.sha256(raw).hexdigest(),
            'license':'Apache-2.0; upstream notices retained','subset':'Model text and model directory, not a full PDK',
            'execution':'not_qualified_for_SPIKES','files':manifest}
    (destination/'SPIKES-COLLECTION.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(json.dumps({'destination':str(destination),'files':len(manifest),'bytes':total,'archive_sha256':record['archive_sha256']}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destination');fetch(parser.parse_args().destination)
