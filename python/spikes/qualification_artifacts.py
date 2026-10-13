# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original immutable numerical CSV/SVG evidence export, without model copying."""
import csv
import hashlib
from html import escape
import json
from pathlib import Path


def export_qualification_evidence(report,directory):
    """Create a new directory; publish the hash manifest last. Never overwrite."""
    root = Path(directory)
    payload = json.dumps(report,sort_keys=True,indent=2,allow_nan=False).encode()
    if len(payload)>8*1024*1024:
        raise ValueError('QUALIFICATION_EXPORT: result byte budget exceeded')
    root.mkdir(parents=True,exist_ok=False)
    (root/'result.json').write_bytes(payload)
    for index,run in enumerate(report.get('runs',[])):
        if 'traces' not in run:
            continue
        names = list(run['traces'])
        times = run['time_s']
        with (root/f'run-{index}.csv').open('x',newline='',encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(['time_s',*names])
            writer.writerows(zip(times,*(run['traces'][name] for name in names),strict=True))
        for signal,name in enumerate(names):
            values = run['traces'][name]
            xmin,xmax,ymin,ymax = times[0],times[-1],min(values),max(values)
            xspan,yspan = max(xmax-xmin,1e-300),max(ymax-ymin,1e-300)
            selected = range(0,len(times),max(1,len(times)//1000))
            points = ' '.join(f'{60+640*(times[i]-xmin)/xspan:.3f},{340-280*(values[i]-ymin)/yspan:.3f}' for i in selected)
            unit = {'V':'V','I':'A','P':'W','T':'K'}.get(name[0],'declared units')
            svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="760" height="410" viewBox="0 0 760 410">'
                   f'<rect width="760" height="410" fill="white"/>'
                   f'<g font-family="sans-serif" font-size="13" fill="#17202a">'
                   f'<text x="60" y="22">{escape(report["id"])}: {escape(name)} [{unit}]</text>'
                   f'<text x="60" y="42">Experimental numerical evidence; not hardware qualification</text>'
                   f'<path d="M60 60 V340 H700" fill="none" stroke="#17202a"/>'
                   f'<polyline points="{points}" fill="none" stroke="#007a99" stroke-width="2"/>'
                   f'<circle cx="{60+640*(times[-1]-xmin)/xspan:.3f}" cy="{340-280*(values[-1]-ymin)/yspan:.3f}" r="3" fill="#007a99"/>'
                   f'<text x="60" y="362">{xmin:.6g} s</text><text x="640" y="362">{xmax:.6g} s</text>'
                   f'<text x="5" y="70">{ymax:.6g}</text><text x="5" y="340">{ymin:.6g}</text>'
                   f'<text x="280" y="390">Time [s]; display decimated, full CSV retained</text></g></svg>')
            (root/f'run-{index}-signal-{signal}.svg').write_text(svg,encoding='utf-8')
    inventory = [{'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
                 for path in sorted(root.iterdir())]
    manifest = {'contract':'spikes/qualification-artifacts/v1','files':inventory,'status':report['status'],
                'hardware_qualified':False,'vendor_models_redistributed':False}
    (root/'COMMITTED.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    return manifest
