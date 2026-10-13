# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Read-only SAS source/model integrity and owned-parser admission inventory."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from python.spikes.netlist import parse_netlist, NetlistParseError


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def audit(root):
    root = Path(root).resolve(strict=True)
    package = root/'reports/review/qualification_20261006'
    binding_path = package/'source_binding.json'
    binding = json.loads(binding_path.read_text())
    authority = (root/binding['source_manifest']).resolve()
    if not authority.is_relative_to(root): raise ValueError('Source manifest path escape')
    authority_digest = digest(authority)
    source = []
    for name,expected in binding['source_files'].items():
        if not name.endswith(('.kicad_pcb','.kicad_sch')): continue
        path = (root/name).resolve()
        if not path.is_relative_to(root): raise ValueError('Source binding path escape')
        observed = digest(path) if path.is_file() else None
        source.append({'path':name,'expected_sha256':expected,'observed_sha256':observed,'matches':observed==expected})
    models = []
    for row in json.loads((package/'models/acquisition.json').read_text()):
        path = package/'models'/(row['part']+'.zip')
        observed = digest(path)
        entry = {'part':row['part'],'origin':row['url'],'archive_sha256':observed,'archive_matches':observed==row['sha256'],
                 'authenticity':'not_independently_authenticated','redistributed':False,'members':[]}
        if entry['archive_matches']:
            with zipfile.ZipFile(path) as archive:
                for name in row['model_members']:
                    if archive.getinfo(name).file_size>2*1024*1024: raise ValueError('Model byte budget exceeded')
                    expected = hashlib.sha256(archive.read(name)).hexdigest()
                    extracted = package/'models'/row['part']/Path(name).name
                    actual = digest(extracted)
                    entry['members'].append({'name':Path(name).name,'sha256':actual,'matches_archive_member':actual==expected})
        models.append(entry)
    fixtures = []
    for path in sorted((package/'fixtures').glob('*.cir')):
        item = {'fixture':path.name,'sha256':digest(path),'native_status':'NOT_RUN','hardware_qualified':False}
        try:
            project = parse_netlist(path.read_text(),source_name=str(path),native_extensions=True)
            item.update(compatibility_status='PARSED_NOT_EXECUTED',analysis=project.analysis.mode,
                        expanded_source_sha256=project.source_sha256)
        except (NetlistParseError,UnicodeError,ValueError) as error:
            item.update(compatibility_status='BLOCKED',diagnostic=str(error))
        fixtures.append(item)
    return {'contract':'spikes/sas-input-audit/v1','source_binding_sha256':digest(binding_path),
            'source_manifest_sha256':authority_digest,
            'source_manifest_matches':authority_digest==binding['source_manifest_sha256'],
            'source_files':source,'models':models,'fixtures':fixtures,'hardware_qualified':False,
            'cooling_basis':'Four Blades at declared 36 mm pitch; optional thin low-profile heatsinks permitted. Declared native +X to -X airflow and two Wakefield DC0922512V2B-BT0 fans per case require reviewed installed P-Q/system-pressure, blockage and downstream-air inputs. Local air limits 40 C normal / 50 C absolute; package, via, contact and Base heat paths remain unresolved.',
            'scope':'Read-only integrity and parser admission. No SAS CAD or third-party model changes; no physical qualification.'}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sas-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    options = parser.parse_args()
    report = audit(options.sas_root)
    with options.output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
    print(json.dumps({'sources':len(report['source_files']),'models':len(report['models']),
                      'fixtures':len(report['fixtures']),'native_blocked':sum(f['compatibility_status']=='BLOCKED' for f in report['fixtures'])}))
