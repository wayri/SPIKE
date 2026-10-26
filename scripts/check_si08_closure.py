# SPDX-License-Identifier: Apache-2.0
"""Reject scope drift and unsupported completion of the finite SI08 checklist."""
from pathlib import Path
import hashlib
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
FROZEN_SCOPE_SHA256='624d1c4d888eb4e47c603122a7ee3536ffeeb9d6f6fe945716439b3db7ede017'


def validate_checklist(payload,root=ROOT):
    keys=('id','title','covers','depends_on','requires','steps','acceptance')
    scope={k:payload[k] for k in ('contract','scope_version','frozen_on','original_targets','policy','execution_order')}
    for group in ('implementation','external_validation','release'):
        scope[group]=[{k:r[k] for k in keys if k in r} for r in payload[group]]
    digest=hashlib.sha256(json.dumps(scope,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    if digest!=FROZEN_SCOPE_SHA256:raise ValueError('Frozen SI08 scope changed; version and reviewed acceptance must be updated explicitly')
    rows=payload['implementation']+payload['external_validation']+payload['release'];by_id={r['id']:r for r in rows}
    expected={f'I{k:02}' for k in range(1,9)}|{'E01','E02','R01','R02'}
    if set(by_id)!=expected or len(rows)!=12:raise ValueError('Finite checklist point inventory differs')
    for row in rows:
        status=row.get('status');kind=row['id'][0]
        allowed={'planned','in_progress','verified'} if kind=='I' else {'pending_external','verified'} if kind=='E' else {'pending_release','verified'}
        if status not in allowed:raise ValueError('Invalid closure status')
        if status!='verified':continue
        if any(by_id[x]['status']!='verified' for x in row.get('depends_on',row.get('requires',[]))):
            raise ValueError('Verified point has unfinished dependencies')
        if row['id']=='I04':
            from scripts.verify_calibrated_fixture_uq import validate_receipt
        elif row['id']=='I01':
            from scripts.verify_si08_interoperability import validate_receipt
        elif row['id']=='I02':
            from functools import partial
            from scripts.verify_si08_interoperability import validate_receipt as validate_policy
            validate_receipt=partial(validate_policy,point_id='I02')
        else:raise ValueError('No accepted current completion gate for '+row['id'])
        raw=row.get('evidence')
        if not isinstance(raw,str) or Path(raw).is_absolute():raise ValueError('Current closure evidence required')
        path=(root/raw).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():raise ValueError('Closure evidence path invalid')
        validate_receipt(json.loads(path.read_text(encoding='utf-8')),root)
    done=[r['id'] for r in rows if r['status']=='verified']
    implementation_complete=all(r['id'] in done for r in payload['implementation'])
    family_complete=implementation_complete and all(r['id'] in done for r in payload['external_validation'])
    release_ready=family_complete and all(r['id'] in done for r in payload['release'])
    ready=[r['id'] for r in payload['implementation'] if r['status']!='verified'
           and all(x in done for x in r['depends_on'])]
    return {'verified':done,'ready_implementation':ready,'implementation_complete':implementation_complete,
            'full_family_complete':family_complete,'release_ready':release_ready,
            'pending_external':[r['id'] for r in payload['external_validation'] if r['status']!='verified'],
            'pending_release':[r['id'] for r in payload['release'] if r['status']!='verified']}


if __name__=='__main__':
    print(json.dumps(validate_checklist(json.loads((ROOT/'docs/si08-closure-checklist-v1.json').read_text(encoding='utf-8')))))
