# SPDX-License-Identifier: Apache-2.0
"""Bounded exact STEP admission for the separately installed OCC process.

STEP bytes are retained project data, never GEO/Python scripts. The existing
OCC worker provides time/memory containment and dependency hash admission.
"""
import hashlib
from pathlib import Path

from .assembly_frames import validate_rigid_transform
from .assembly_field_handoff import digest
from .gmsh_occ_mesher import _keys, _require, _number

MAX_STEP_BYTES = 64 * 1024**2


def validate_step_job(request):
    _keys(request, ('contract', 'solids', 'mesh'))
    _require(isinstance(request['solids'], list) and len(request['solids']) == 1,
             'STEP meshing requires exactly one source model per job.')
    solid = request['solids'][0]
    _keys(solid, ('id', 'material_id', 'priority', 'shape'))
    _require(all(isinstance(solid[k], str) and 0 < len(solid[k]) <= 256 for k in ('id', 'material_id')),
             'Invalid STEP source/material identity.')
    _require(type(solid['priority']) is int and solid['priority'] == 0, 'STEP priority must be zero.')
    shape = solid['shape']
    _keys(shape, ('kind', 'path', 'sha256', 'transform'))
    _require(shape['kind'] == 'step_solid', 'Only exact STEP solid data admitted.')
    digest(shape['sha256'])
    _require(isinstance(shape['path'], str), 'STEP path must be text.')
    path = Path(shape['path'])
    _require(path.is_absolute() and path.suffix.lower() in ('.step', '.stp') and
             not path.is_symlink() and path.is_file() and 0 < path.stat().st_size <= MAX_STEP_BYTES,
             'Missing or oversized retained STEP artifact.')
    _require(hashlib.sha256(path.read_bytes()).hexdigest() == shape['sha256'],
             'Retained STEP source digest changed.')
    transform = shape['transform']
    _require(isinstance(transform, list) and len(transform) == 16, 'STEP transform must be rigid.')
    for value in transform:
        _number(value)
    validate_rigid_transform(transform, 'Retained STEP model')
    options = request['mesh']
    _keys(options, ('min_size_mm', 'max_size_mm', 'max_cells', 'max_vertices'))
    _require(1e-6 <= _number(options['min_size_mm']) <= _number(options['max_size_mm']), 'Invalid mesh size.')
    for key in ('max_cells', 'max_vertices'):
        _require(type(options[key]) is int and 4 <= options[key] <= 100000, 'Invalid output budget.')


def import_step_solid(occ, shape, model, *, apply_transform=True):
    """Import one closed source volume; reject open sheets and compounds.

No automatic healing, sewing, solidification, material split, or dimensional
scaling is requested. OCC reads STEP units and returns millimetres.
"""
    entities = occ.importShapes(shape['path'], highestDimOnly=False, format='step')
    volumes = [tag for dim, tag in entities if dim == 3]
    _require(len(volumes) == 1, 'STEP_SOURCE_VOLUME: expected one closed solid; split compound models explicitly.')
    occ.synchronize()
    # Every imported surface must bound the retained volume; loose display
    # sheets mixed into an otherwise solid STEP must not disappear silently.
    import_surfaces = {tag for dim, tag in entities if dim == 2}
    boundary = {abs(tag) for dim, tag in model.getBoundary([(3, volumes[0])], oriented=False) if dim == 2}
    _require(import_surfaces <= boundary, 'STEP_SOURCE_SURFACE: source contains unattached/open surfaces.')
    _require(occ.getMass(3, volumes[0]) > 0, 'STEP_SOURCE_VOLUME: source lacks positive volume.')
    if apply_transform:
        # General OCC affine transforms convert analytic surfaces to splines,
        # even for identity. This contract admits only proper rigid placement.
        import numpy as np
        from .assembly_thermal_encapsulation_occ import rigid_place
        rigid_place(occ, (3, volumes[0]), np.asarray(shape['transform'], dtype=float).reshape(4, 4))
    return volumes[0]
