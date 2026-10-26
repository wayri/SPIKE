# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Offline whole-board net/source/manual focus examples using admitted OCC."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from python.spike_core.solvers.geometry_meshing.preparation.pcb_volume_mesh import prepare_pcb_volume_mesh
from python.spike_core.solvers.geometry_meshing.preparation.gmsh_occ_runtime import run_occ_case


def audit_case(result):
    """Original fixture oracles, separate from native successful execution."""
    cells = result['mesh']['cells']
    source_counts = {source: 0 for source in result['mesh']['object_map']}
    materials = {}
    for cell in cells:
        materials[cell['id']] = cell['material_id']
        for source in cell['source_object_ids']:
            source_counts[source] += 1
    if min(source_counts.values()) <= 0:
        raise RuntimeError('A declared source has no actual tetrahedral coverage.')
    # Fixture area: 12*8 + 8*2 minus a 1*1 cutout. Entire 1.55-mm
    # stack includes internal copper/air, so its union has this exact volume.
    expected = (12*8+8*2-1)*1.55
    relative_volume_error = abs(result['metrics']['tetrahedron_volume_mm3']/expected-1)
    if relative_volume_error > 1e-10:
        raise RuntimeError('Full-board tetrahedron volume differs from analytical fixture union.')
    source_errors = {}
    for source, cad_volume in result['metrics']['source_cad_volumes_mm3'].items():
        recovered = sum(result['metrics']['fragment_mesh_volumes_mm3'][tag]
                        for tag, ownership in result['fragment_ownership'].items()
                        if source in ownership['source_object_ids'])
        source_errors[source] = abs(recovered/cad_volume-1)
    # Fixed distant bulk-core window, chosen outside every local refinement box.
    distant = [cell['longest_edge_mm'] for cell in result['focus_assessment']['cell_assessments']
               if cell['centroid_mm'][1] > 7 and cell['centroid_mm'][0] < 5
               and .6 < cell['centroid_mm'][2] < 1.4 and materials[cell['cell_id']] == 'fr4']
    if not distant:
        raise RuntimeError('Distant core comparison window has no tetrahedra.')
    return {'analytical_board_union_volume_mm3': expected, 'relative_board_volume_error': relative_volume_error,
            'actual_source_cell_counts': source_counts, 'source_mesh_cad_volume_relative_errors': source_errors,
            'far_bulk_core_cells': len(distant), 'far_bulk_core_median_longest_edge_mm': statistics.median(distant)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New directory; never overwrite a prior run.')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    base = json.loads((Path(__file__).parent/'whole_board.json').read_text(encoding='utf-8'))
    sources = ['pcb_volume_compiler.py', 'pcb_focus_sizing.py', 'pcb_volume_mesh.py',
               'gmsh_occ_mesher.py', 'gmsh_occ_runtime.py']
    source_hashes = {name: hashlib.sha256((ROOT/'python/spike_core'/name).read_bytes()).hexdigest()
                     for name in sources}
    report = {'contract': 'spike/pcb-focus-mesh-example-evidence/v1',
              'environment': {'python': sys.version.split()[0], 'platform': platform.platform()},
              'source_sha256': source_hashes, 'cases': {}, 'production_qualified': False}
    for name in ('selected_net', 'selected_trace', 'manual_region', 'uniform_fine'):
        request = copy.deepcopy(base)
        if name == 'selected_trace':
            request['sizing']['net_names'] = []
            request['sizing']['source_ids'] = ['sig_trace']
        elif name == 'manual_region':
            request['sizing']['net_names'] = []
            request['sizing']['regions'] = [{'id': 'connector-area', 'bounds_mm': [[5.5,1.5,-.1],[6.5,2.5,1.7]],
                                             'target_size_mm': .25}]
        elif name == 'uniform_fine':
            request['sizing']['coarse_size_mm'] = request['sizing']['fine_size_mm']
        prepared = prepare_pcb_volume_mesh(request)
        directory = output/name
        started = time.perf_counter()
        result = run_occ_case(prepared['job'], directory, timeout_s=600, memory_limit_mb=2048)
        elapsed = time.perf_counter()-started
        if not result['whole_model_retained']:
            raise RuntimeError('Whole-model source coverage failed.')
        nets = {metadata['net'] for metadata in result['mesh']['object_map'].values() if 'net' in metadata}
        if nets != {'SIG', 'OTHER', 'GND'}:
            raise RuntimeError('Net selection discarded background copper.')
        assessment = {key: value for key, value in result['focus_assessment'].items()
                      if key != 'cell_assessments'}
        report['cases'][name] = {'elapsed_seconds': elapsed, 'counts': result['mesh']['counts'],
                                 'metrics': result['metrics'], 'focus_assessment': assessment,
                                 'independent_fixture_checks': audit_case(result),
                                 'retained_nets': sorted(nets), 'job_sha256': prepared['job_sha256'],
                                 'mesh_msh_sha256': hashlib.sha256((directory/'mesh.msh').read_bytes()).hexdigest()}
        (directory/'prepared.json').write_text(json.dumps(prepared, indent=2, allow_nan=False), encoding='utf-8')
    uniform = report['cases']['uniform_fine']
    for name in ('selected_net', 'selected_trace', 'manual_region'):
        info = report['cases'][name]
        info['cell_reduction_vs_uniform_fine'] = 1-info['counts']['cells']/uniform['counts']['cells']
        distant_ratio = (info['independent_fixture_checks']['far_bulk_core_median_longest_edge_mm'] /
                         uniform['independent_fixture_checks']['far_bulk_core_median_longest_edge_mm'])
        if info['cell_reduction_vs_uniform_fine'] <= 0 or distant_ratio < 2:
            raise RuntimeError('Focused fixture failed cell-reduction or distant-core coarsening checks.')
        info['far_bulk_core_edge_ratio_vs_uniform_fine'] = distant_ratio
    after = {name: hashlib.sha256((ROOT/'python/spike_core'/name).read_bytes()).hexdigest() for name in sources}
    if after != source_hashes:
        raise RuntimeError('Source changed during qualification; reject this evidence.')
    (output/'evidence.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    hashes = {str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(output.rglob('*')) if path.is_file()}
    (output/'sha256.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    print(json.dumps({'artifact_directory': str(output), 'counts': {name: info['counts']
                     for name, info in report['cases'].items()}}, indent=2))


if __name__ == '__main__':
    main()
