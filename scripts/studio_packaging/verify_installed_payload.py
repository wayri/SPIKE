# SPDX-License-Identifier: Apache-2.0
"""Read-only installed payload comparison; writes only a requested evidence file."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload',required=True,type=Path)
    parser.add_argument('--installed',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    payload=args.payload.resolve(strict=True);installed=args.installed.resolve(strict=True)
    root=Path(__file__).resolve().parents[2]
    studio=root/'standalone/spikes_project/studio/python'
    if not studio.is_dir():studio=root/'studio/python'
    sys.path.insert(0,str(studio))
    from spikes_studio.release_policy import qt_dependencies
    def digest(path):
        with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
    files=[p for p in payload.rglob('*') if p.is_file()]
    missing=[];changed=[]
    for source in files:
        relative=source.relative_to(payload);target=installed/relative
        if not target.is_file():missing.append(relative.as_posix())
        elif digest(source)!=digest(target):changed.append(relative.as_posix())
    forbidden=qt_dependencies(p.relative_to(installed).as_posix() for p in installed.rglob('*') if p.is_file())
    result={'passed':not(missing or changed or forbidden),'expected_files':len(files),
            'matched_files':len(files)-len(missing)-len(changed),'missing':missing,'changed':changed,
            'forbidden_qt':forbidden,'payload':str(payload),'installed':str(installed)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2));return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
