# SPDX-License-Identifier: Apache-2.0
"""Reproduce original transient thermal accuracy evidence with actual CCX/OCC.

Run with the admitted Windows CPython 3.11 interpreter and local Gmsh runtime.
No third-party solver source, mesh, reference results or example deck is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import shutil
import platform

import numpy as np
from scipy.linalg import eigh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from python.spike_core.assembly_tetra_thermal_validation import validate_request
from python.spike_core.assembly_tetra_transient import run_assembly_tetra_transient
from python.spike_core.assembly_field_transient import run_assembly_field_transient
from python.spike_core.calculix_runtime import probe_calculix_runtime
from python.spike_core.calculix_transient import (run_calculix_transient, run_calculix_field_transient,
    compare_transient_fields, compare_thermal_transient_results)
from tests.python.test_calculix_transient import settings, sine_case
from tests.python.test_assembly_tetra_thermal import request


def execution(field):
    return {k:v for k,v in field['execution'].items() if k != 'log_tail'}


def semidiscrete(raw, initial, duration, centroid):
    """Independent matrix exponential via generalized symmetric eigendecomposition."""
    data = validate_request(raw)
    n = len(data['xyz'])
    k, m = np.zeros((n,n)), np.zeros((n,n))
    for cell, (volume, gradients) in zip(data['cells'], data['geometry']):
        ix = np.ix_(cell['vertices'], cell['vertices'])
        k[ix] += volume*gradients @ data['tensors'][cell['material_id']] @ gradients.T
        m[ix] += 6*volume*(np.ones((4,4))/16 if centroid else (np.eye(4)+np.ones((4,4)))/20)
    free = sorted(set(range(n))-set(data['fixed']))
    stiffness, mass = k[np.ix_(free,free)], m[np.ix_(free,free)]
    values, vectors = eigh(stiffness, mass)
    initial = np.array(initial)[free]-300
    final = vectors @ (np.exp(-values*duration)*(vectors.T @ mass @ initial)) + 300
    return free, final


def accuracy_cases():
    cases = {}
    raw = request()
    raw['boundaries'] = []
    raw['heat_sources_w_m3'] = {c['id']:12. for c in raw['mesh']['cells']}
    transient = settings(.1)
    internal, external = run_assembly_tetra_transient(raw, transient), run_calculix_transient(raw, transient)
    exact_error = max(abs(t-(300+2*f['time_s'])) for f in external['frames'] for t in f['node_temperatures_k'])
    assert exact_error < 6e-5
    cases['uniform_insulated_heating'] = {'analytic_equation': 'T(t)=300+12*t/(2*3) K',
        'maximum_analytic_error_k': exact_error, 'comparison': compare_transient_fields(internal, external,
            absolute_tolerance_k=6e-5, relative_tolerance=0.), 'execution': execution(external)}
    refinement = []
    for dt in (.04, .02, .01, .005):
        raw, transient = sine_case(2, dt)
        transient['output_interval_s'] = .2
        internal, external = run_assembly_tetra_transient(raw, transient), run_calculix_transient(raw, transient)
        row = {'time_step_s': dt, 'execution': execution(external)}
        for name, field, centroid in [('spike',internal,False), ('calculix',external,True)]:
            free, exact = semidiscrete(raw, transient['initial_temperature_k'], .2, centroid)
            row[name+'_semidiscrete_error_k'] = float(np.max(np.abs(np.array(field['node_temperatures_k'])[free]-exact)))
        refinement.append(row)
    for name in ('spike', 'calculix'):
        errors = [row[name+'_semidiscrete_error_k'] for row in refinement]
        assert all(b < .65*a for a,b in zip(errors, errors[1:])), (name,errors)
    cases['timestep_refinement'] = refinement
    spatial = []
    for n in (2,4,6):
        raw, transient = sine_case(n, .002)
        transient['output_interval_s'] = .2
        internal, external = run_assembly_tetra_transient(raw, transient), run_calculix_transient(raw, transient)
        exact = np.array([300+10*math.sin(math.pi*p[0])*math.exp(-2/6*math.pi**2*.2)
                          for p in raw['mesh']['vertices']])
        errors = {name+'_analytic_rms_error_k': float(np.sqrt(np.mean((np.array(field['node_temperatures_k'])-exact)**2)))
                  for name,field in [('spike',internal), ('calculix',external)]}
        comparison = compare_transient_fields(internal, external, absolute_tolerance_k=.05, relative_tolerance=.05)
        spatial.append({'subdivisions':n,'nodes':len(exact),'tetrahedra':len(raw['mesh']['cells']),
                        **errors,'comparison':comparison,'execution':execution(external)})
    for name in ('spike','calculix'):
        errors = [row[name+'_analytic_rms_error_k'] for row in spatial]
        assert all(b < a for a,b in zip(errors,errors[1:])), (name,errors)
    assert spatial[-1]['comparison']['passed'], spatial[-1]
    cases['spatial_refinement'] = spatial
    return cases


def board_step_case(directory):
    """Create an original STEP, import/mesh it with two retained PCB occurrences."""
    from tests.python.test_assembly_joint_thermal_mesh import RealJointMeshTests
    from tests.python.test_thermal_component_promotion import pure_fixture
    from python.spike_core.assembly_thermal_components import promote_thermal_components
    from python.spike_core.assembly_thermal_meshing import run_assembly_thermal_mesh
    from python.spike_core.assembly_thermal_autolink import autolink_assembly_thermal_contacts
    RealJointMeshTests.setUpClass()
    try:
        payload, assignments, options, selection, reader = pure_fixture()
        source = RealJointMeshTests.step
        (directory/'original-package.step').write_bytes(source)
        payload['models']['models'][0]['digest'] = hashlib.sha256(source).hexdigest()
        transform = selection['component_to_board_transform_mm']
        transform[3], transform[7], transform[11] = 0.,0.,1.
        artifacts = lambda uri: source if uri.startswith('package:models/') else reader(uri)
        promoted = promote_thermal_components(payload,[selection],assignments['materials'],artifact_reader=artifacts)
        package = promoted['promoted_parts'][0]['id']
        promoted['payload']['assembly_ir']['thermal_contacts'] = [{'id':'package-contact',
            'endpoint_a':'board-a','endpoint_b':package,'contact_area_mm2':4.,'thermal_resistance_k_per_w':50.}]
        assignments['parts'].update(promoted['part_material_assignments'])
        options.update(min_size_mm=.5,max_size_mm=.5)
        with tempfile.TemporaryDirectory(prefix='transient-mesh-', dir=directory) as temporary:
            meshed = run_assembly_thermal_mesh(promoted['payload'],assignments,options,
                Path(temporary)/'mesh',artifact_reader=artifacts)
            shutil.copytree(Path(temporary)/'mesh', directory/'mesh-execution')
        assert meshed['status']=='completed',meshed.get('blockers')
        geometry = meshed['request']
        problem = {'contract':'spike/assembly-field-thermal-problem/v1','heat_sources':[],'boundaries':[],'contacts':[]}
        for body in geometry['bodies']:
            oid = body['occurrence_id']
            if oid == package:
                problem['heat_sources'] += [{'occurrence_id':oid,'cell_id':c['id'],'heat_source_w_m3':1e7}
                                           for c in body['mesh']['cells']]
            else:
                for face in body['boundary_faces']:
                    if all(math.isclose(body['mesh']['vertices'][v][2],0.,abs_tol=1e-10) for v in face['vertices']):
                        problem['boundaries'].append({'face':{'occurrence_id':oid,'face_id':face['id']},
                            'type':'temperature','temperature_k':300.})
        problem = autolink_assembly_thermal_contacts(geometry,problem,['package-contact'])['problem']
        transient = settings(.05,1.)
        transient['material_heat_capacity'] = [{'material_id':m['id'],'density_kg_m3':2000.,'specific_heat_j_kgk':1000.}
                                                for m in geometry['materials']]
        internal = run_assembly_field_transient(geometry,problem,transient)
        external = run_calculix_field_transient(geometry,problem,transient)
        comparison = compare_thermal_transient_results(geometry,problem,internal,external,
            absolute_tolerance_k=.05,relative_tolerance=.05)
        assert comparison['passed'],comparison
        for name,value in [('geometry',geometry),('problem',problem),('settings',transient),('spike',internal),('calculix',external)]:
            (directory/(name+'.json')).write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')
        export_study_project(directory, geometry, problem, transient, external, promoted['payload'], source)
        return {'occurrences':list(internal['occurrence_temperatures']), 'comparison':comparison,
                'spike_occurrence_temperatures':internal['occurrence_temperatures'],
                'calculix_occurrence_temperatures':external['occurrence_temperatures'],
                'execution':execution(external['field_result']), 'meshing_mode':meshed['meshing_mode'],
                'mesh_evidence':meshed['evidence'], 'geometry_digest':internal['handoff_digest'],
                'retained_artifacts_directory':str(directory.relative_to(ROOT)) if directory.is_relative_to(ROOT) else str(directory)}
    finally:
        RealJointMeshTests.tearDownClass()


def export_study_project(directory, geometry, problem, transient, internal, authored, source):
    from tests.python.test_project_assembly_field import _payload
    from python.spike_core.assembly_field_study import export_assembly_field_study
    from python.spike_core.project_package import write_spike_package, read_project
    from python.spike_core.service_project_assembly_field import (
        save_assembly_field_study_in_project, read_assembly_field_study_in_project)
    record = export_assembly_field_study(geometry,problem,internal,transient_settings=transient)
    (directory/'original-transient.fieldstudy.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    payload = _payload(geometry)
    payload['project']['name'] = 'Original transient thermal benchmark'
    payload['design_ir'].update(authored['design_ir'])
    payload['design_ir']['source']['source_format'] = 'spike-fixture'
    # The thermal body is one homogeneous dielectric layer. Zero-thickness
    # display layers give canonical top/bottom component placement real names;
    # no copper geometry or heat-spreading contribution is introduced.
    payload['design_ir']['layers'][0]['name'] = 'Homogeneous board'
    payload['design_ir']['layers'] += [
        {'id':'benchmark-front-display','name':'F.Cu','layer_type':'copper','order':-1,'z_mm':1.,'thickness_mm':0.},
        {'id':'benchmark-back-display','name':'B.Cu','layer_type':'copper','order':1,'z_mm':0.,'thickness_mm':0.}]
    payload['design_ir']['metadata']['board_bounds_mm'] = [0.,0.,2.,2.]
    payload['design_ir']['metadata']['board_outline_drawings'][0]['points'] = [[0.,0.],[2.,0.],[2.,2.],[0.,2.],[0.,0.]]
    payload['models'] = authored['models']
    path = directory/'original-transient.spike'
    manifest = write_spike_package(path,payload,model_artifacts={'component.step':source},
        preserved_members={'sources/board.kicad_pcb':b'Original minimal retained source fixture'})
    save_assembly_field_study_in_project({'project_path':str(path),
        'expected_manifest_payload_sha256':manifest['manifest_payload_sha256'],'record':record},application_version='validation')
    reopened = read_project(path)
    loaded = read_assembly_field_study_in_project({'project_path':str(path),
        'expected_manifest_payload_sha256':reopened.manifest['manifest_payload_sha256']},application_version='validation')
    assert loaded['state']=='current' and loaded['saved_result_present'],loaded


def plot_evidence(result, output):
    """Render numerical evidence using standard scientific plotting tools."""
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    time_rows = result['cases']['timestep_refinement']
    mesh_rows = result['cases']['spatial_refinement']
    figure, axes = plt.subplots(1,2,figsize=(10,4),layout='constrained')
    for name,label in [('spike','SPIKE: exact P1 capacity'),('calculix','CalculiX: centroid capacity')]:
        axes[0].loglog([r['time_step_s'] for r in time_rows],
            [r[name+'_semidiscrete_error_k'] for r in time_rows], 'o-', label=label)
        axes[1].loglog([1/r['subdivisions'] for r in mesh_rows],
            [r[name+'_analytic_rms_error_k'] for r in mesh_rows], 'o-', label=label)
    axes[0].set(xlabel='Time step (s)',ylabel='Maximum temporal error (K)',title='Time refinement: separate mass-matrix oracles')
    axes[1].set(xlabel='Mesh interval (m)',ylabel='Nodal RMS error (K)',title='Mesh refinement: analytical sine decay')
    for axis in axes:
        axis.grid(True,which='both',alpha=.25)
        axis.legend(fontsize=8)
    figure.suptitle('SPIKE original transient thermal benchmark - numerical verification')
    figure.savefig(output,dpi=160)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/validation/ASSEMBLY_THERMAL_TRANSIENT_20261008.json')
    parser.add_argument('--artifacts',type=Path,default=ROOT/'.local/transient-thermal-validation')
    parser.add_argument('--plot-only',action='store_true',help='Render an existing JSON report using matplotlib; no solvers run.')
    parser.add_argument('--retained-step-only',action='store_true',help='Run actual STEP/meshing/transient/package workflow without repeating separate continuum studies.')
    args=parser.parse_args()
    if args.plot_only:
        plot_evidence(json.loads(args.output.read_text(encoding='utf-8')),args.output.with_suffix('.png'))
        return
    if not probe_calculix_runtime()['available']:
        raise SystemExit('Actual CalculiX is required; this benchmark never substitutes mock results.')
    from python.spike_core.gmsh_occ_runtime import verify_installation
    verify_installation()
    if args.output.exists() or args.artifacts.exists():
        raise ValueError('Use new output and artifact paths; historical evidence is never overwritten.')
    args.artifacts.mkdir(parents=True,exist_ok=False)
    sources = ['scripts/validate_transient_thermal.py', 'python/spike_core/gmsh_occ_runtime.py',
               'python/spike_core/gmsh_environment.py', 'python/spike_core/assembly_thermal_meshing.py',
               'python/spike_core/assembly_thermal_joint_mesh.py', 'python/spike_core/assembly_tetra_transient.py',
               'python/spike_core/calculix_transient.py']
    source_before = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources}
    result={'contract':'spike/transient-thermal-validation/v1','model_status':'experimental','production_qualified':False,
            'reference':'https://www.dhondt.de/ccx_2.20.pdf',
            'capacity_difference':'SPIKE integrates P1 capacity exactly; CCX DC3D4 centroid capacity independently reproduced.',
            'limitations':['No measured hardware calibration or Fang parity; synthetic independent fixtures.',
                           'Prescribed material properties, losses, boundaries and contacts; no airflow.'],
            'cases':{} if args.retained_step_only else accuracy_cases(),
            'retained_multiboard_step':board_step_case(args.artifacts)}
    source_after = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources}
    result['execution_binding'] = {'mode': 'retained_step_only' if args.retained_step_only else 'full',
        'command': [sys.executable, *sys.argv], 'python_version': sys.version,
        'host': platform.platform(), 'source_sha256_before': source_before,
        'source_sha256_after': source_after, 'source_identity': 'unchanged' if source_before == source_after else 'inconclusive'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(str(args.output))
    print(json.dumps({k:v['comparison'] for k,v in result['cases'].items() if isinstance(v,dict)},indent=2))
    print(json.dumps(result['retained_multiboard_step']['comparison'],indent=2))


if __name__=='__main__':
    main()
