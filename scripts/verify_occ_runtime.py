# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Actual installed-kernel local mesh verification, not a CFD or release test."""
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.gmsh_occ_runtime import run_occ_case
from python.spike_core.gmsh_occ_mesher import OccMeshingError
from jsonschema import Draft202012Validator


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = ROOT/'build'/('occ-evidence-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'))
    output.mkdir()
    sources = [ROOT/'python/spike_core'/name for name in
        ('gmsh_occ_mesher.py','gmsh_occ_runtime.py','tetra_mesh_refinement.py','sparselizard_process.py')]
    sources += [Path(__file__),ROOT/'examples/mesh/pcb_occ_request.json',ROOT/'schemas/solver-mesh-v1.schema.json']
    before = {str(p.relative_to(ROOT)):sha(p) for p in sources}
    schema = Draft202012Validator(json.loads((ROOT/'schemas/solver-mesh-v1.schema.json').read_text()))
    request = json.loads((ROOT/'examples/mesh/pcb_occ_request.json').read_text())
    start = time.perf_counter()
    pcb = run_occ_case(request,output/'pcb')
    schema.validate(pcb['mesh'])
    assert len(pcb['interface_faces']) > 0
    assert {c['material_id'] for c in pcb['mesh']['cells']} == {'fr4','copper','air'}
    assert abs(pcb['metrics']['tetrahedron_volume_mm3']-pcb['metrics']['cad_volume_mm3']) < 1e-8
    rows = []
    for index,size in enumerate((.2,.1,.05)):
        curve = {'contract':'spike/gmsh-occ-mesh/v1','solids':[{'id':'tube','material_id':'copper','priority':0,
            'shape':{'kind':'tube','center_mm':[0,0],'outer_radius_mm':.3,'inner_radius_mm':.2,'z_min_mm':0,'z_max_mm':1}}],
            'mesh':{'min_size_mm':size/2,'max_size_mm':size,'max_cells':100000,'max_vertices':30000}}
        result = run_occ_case(curve,output/f'tube-{index}')
        schema.validate(result['mesh'])
        metrics = result['metrics']
        error = abs(metrics['tetrahedron_volume_mm3']/metrics['cad_volume_mm3']-1)
        rows.append({'max_size_mm':size,'relative_curved_volume_error':error,'counts':result['mesh']['counts']})
    assert rows[-1]['relative_curved_volume_error'] < rows[0]['relative_curved_volume_error']
    # Nonzero overlap between different equal-priority materials must fail in
    # the native fragment-ownership path, not silently choose a material.
    bad = json.loads(json.dumps(request))
    bad['solids'][1]['priority'] = 0
    rejected = False
    try:
        run_occ_case(bad,output/'ambiguous')
    except RuntimeError:
        rejected = 'equal-priority' in (output/'ambiguous/worker.log').read_text()
    assert rejected
    stable = before == {str(p.relative_to(ROOT)):sha(p) for p in sources}
    report = {'status':'passed' if stable else 'source_changed','production_qualified':False,
        'platform':platform.platform(),'source_sha256':before,'source_unchanged':stable,
        'pcb_counts':pcb['mesh']['counts'],'pcb_interface_triangles':len(pcb['interface_faces']),
        'pcb_metrics':pcb['metrics'],'tube_refinement':rows,'ambiguous_material_rejected':rejected,
        'elapsed_s':time.perf_counter()-start,'scope':'Typed OCC mesh geometry only, not arbitrary CAD or field validation'}
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    (output/'SHA256.json').write_text(json.dumps({str(p.relative_to(output)):sha(p) for p in output.rglob('*')
        if p.is_file()},indent=2),encoding='utf-8')
    print(json.dumps(report,allow_nan=False))
    print(output)
    return 0 if stable else 2


if __name__ == '__main__':
    raise SystemExit(main())
