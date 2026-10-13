# SPDX-License-Identifier: Apache-2.0
"""First-party typed mesh contributions for the optional Gmsh runtime."""
from pathlib import Path
import tempfile

from .extension_analysis_results import design_binding
from .gmsh_extension_mesh import mesh_result
from .pcb_volume_mesh import prepare_pcb_volume_mesh


def execute(request):
    contribution = request.get('contribution_id')
    context = request.get('context', {})
    parameters = context.get('parameters', {})
    if not isinstance(parameters, dict):
        raise ValueError('GMSH_PARAMETERS: expected an object')
    envelope = lambda title, data: {'contract': 'spike/extension-result/v1', 'status': 'completed', 'title': title, 'data': data}
    if contribution == 'gmsh-probe':
        if parameters:
            raise ValueError('GMSH_PARAMETERS: runtime probe accepts no parameters')
        from .gmsh_occ_runtime import verify_installation
        try:
            state = {'available': True, 'runtime': verify_installation()}
        except ValueError as error:
            state = {'available': False, 'reason': str(error)}
        return envelope('Gmsh development runtime', {**state, 'geometry_only': True,
            'domains': ['thermal', 'em', 'si'], 'physics_solvers': [], 'production_qualified': False,
            'supported': ['normalized_whole_pcb_copper_vias_layers', 'reviewed_effective_board_layers', 'single_closed_step_parts']})
    if contribution == 'gmsh-mesh-assembly':
        from .service_project_thermal_mesh import run_assembly_thermal_mesh_in_project
        result = run_assembly_thermal_mesh_in_project(parameters)
        return envelope('Retained assembly thermal volumes', {'assembly_mesh_result': result, 'solved': False})
    if contribution not in ('gmsh-prepare-pcb', 'gmsh-mesh-pcb'):
        raise ValueError('GMSH_CONTRIBUTION: unsupported contribution')
    if set(parameters) - {'request', 'expected_design_sha256', 'timeout_s', 'memory_limit_mb'} or 'request' not in parameters:
        raise ValueError('GMSH_PARAMETERS: only typed PCB requests and resource limits are admitted')
    binding = design_binding(context.get('design'))
    expected = parameters.get('expected_design_sha256')
    if (context.get('design_binding', binding) != binding or
            (contribution == 'gmsh-mesh-pcb' or expected is not None) and expected != binding['digest_sha256']):
        raise ValueError('GMSH_DESIGN_STALE: explicit normalized volumes must bind to the current design digest')
    prepared = prepare_pcb_volume_mesh(parameters['request'])
    if contribution == 'gmsh-prepare-pcb':
        return envelope('Prepared complete PCB solids; mesh not generated', {**prepared, 'design_binding': binding, 'solved': False})
    from .gmsh_occ_runtime import run_occ_case
    with tempfile.TemporaryDirectory(prefix='spike-gmsh-extension-') as directory:
        case = Path(directory)/'case'
        try:
            generated = run_occ_case(prepared['job'], case, timeout_s=parameters.get('timeout_s', 180),
                                     memory_limit_mb=parameters.get('memory_limit_mb', 2048))
        except RuntimeError as error:
            log = case/'worker.log'
            detail = str(error)
            if log.is_file() and not log.is_symlink():
                with log.open('rb') as stream:
                    detail = stream.read(8192).decode('utf-8', errors='replace')
            raise ValueError('GMSH_EXECUTION: '+detail) from error
    return envelope('Complete PCB tetrahedral mesh; no field solve',
                    {'mesh_result': mesh_result(generated, prepared, binding), 'solved': False})
