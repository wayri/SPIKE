# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Whole-board focused meshing application boundary; no source geometry cropping."""
import copy
import hashlib
import importlib.util

from .gmsh_occ_mesher import validate_request
from .internal_meshing_engine import _canonical


def pcb_volume_mesh_capabilities():
    """Report normalized geometry support independently from runtime admission."""
    from .gmsh_occ_runtime import verify_installation
    preparation_available = importlib.util.find_spec('shapely') is not None
    try:
        runtime = {'available': True, **verify_installation()}
    except ValueError as exc:
        runtime = {'available': False, 'reason': str(exc)}
    if runtime['available'] and not preparation_available:
        runtime = {**runtime, 'available': False, 'reason': 'PCB_VOLUME_DEPENDENCY: Shapely unavailable'}
    return {'contract': 'spike/pcb-volume-mesh-capability/v1', 'prepare_available': preparation_available,
            'preparation_requires': ['shapely'],
            'prepare_method': 'prepare_pcb_volume_mesh', 'execute_method': 'generate_tetrahedral_mesh',
            'runtime': runtime, 'units': 'mm', 'mesh_contract': 'spike/solver-mesh/v1',
            'geometry': ['planar_concave_outline', 'cutouts', 'contiguous_layer_stack',
                         'copper_polygons_with_holes', 'plated_via_explicit_spans', 'drill_volumes'],
            'focus': ['net_union', 'source_union', 'manual_boxes', 'graded_coarse_background'],
            'retains': ['unselected_nets', 'layers', 'source_ownership', 'shared_material_interfaces'],
            'limits': {'solids': 10000, 'polygon_points': 131072, 'focus_boxes': 4096,
                       'cad_fragments': 4096, 'cells': 100000, 'vertices': 100000,
                       'prepared_control_bytes': 8*1024**2},
            'unsupported': ['automatic_source_format_conversion', 'bent_rigid_flex',
                            'castellations', 'high_order_cells', 'distributed_meshing'],
            'production_qualified': False}


def prepare_pcb_volume_mesh(request):
    """Compile declared complete planar PCB volumes into a focused CAD job.

    A net/source selection controls element size only. Unselected copper,
    dielectric layers, holes and via spans remain in the geometry. Dependency
    admission and resource-contained execution belong to the OCC runner.
    """
    encoded = _canonical(request)
    if (not isinstance(request, dict) or
            set(request) != {'contract', 'model', 'sizing', 'resources'} or
            request['contract'] != 'spike/pcb-volume-mesh-request/v1'):
        raise ValueError('Unexpected PCB volume meshing request fields or contract.')
    resources = request['resources']
    if not isinstance(resources, dict) or set(resources) != {'max_cells', 'max_vertices'}:
        raise ValueError('PCB mesh resources require max_cells and max_vertices.')
    if any(type(value) is not int or not 4 <= value <= 100000 for value in resources.values()):
        raise ValueError('PCB output budgets must be integers in [4, 100000].')
    from .pcb_volume_compiler import compile_pcb_volume_model
    from .pcb_focus_sizing import plan_focus_regions
    compiled = compile_pcb_volume_model(request['model'])
    policy = request['sizing']
    plan = plan_focus_regions(compiled['solids'], compiled['object_metadata'], policy, include_solids=False)
    job = {'contract': 'spike/gmsh-occ-mesh/v2', 'solids': compiled['solids'],
           'object_metadata': compiled['object_metadata'], 'focus': copy.deepcopy(policy),
           # Targets are desired maxima, not permission to erase smaller
           # copper/drill features by globally clamping curve resolution.
           'mesh': {'min_size_mm': 1e-6,
                    'max_size_mm': policy['coarse_size_mm'], **resources}}
    validate_request(job)
    _canonical(job)
    result = {'contract': 'spike/prepared-pcb-volume-mesh/v1', 'job': job,
            'focus_plan': plan, 'geometry_evidence': compiled['evidence'],
            'request_sha256': hashlib.sha256(encoded).hexdigest(),
            'job_sha256': hashlib.sha256(_canonical(job)).hexdigest(),
            'external_geometry_runtime': 'gmsh_occ_4.15.2_local_development',
            'production_qualified': False}
    _canonical(result)
    return result
