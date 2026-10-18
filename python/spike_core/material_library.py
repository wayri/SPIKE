# SPDX-License-Identifier: Apache-2.0
"""Inert, SI material evidence and immutable-by-value assignment snapshots.

No constitutive evaluation, curve interpolation, tensor reduction or solver
registration occurs here. A projection is an explicit admission boundary.
"""
import hashlib
import json
import math
from pathlib import Path
import re

SCHEMA_VERSION = 1
CATALOG_PATH = Path(__file__).resolve().parents[2] / 'data/materials/catalog.json'
# Bounds express basic admissibility, not material qualification.
PROPERTY_UNITS = {
    'density': 'kg/m^3', 'specific_heat': 'J/(kg*K)',
    'thermal_conductivity': 'W/(m*K)', 'youngs_modulus': 'Pa',
    'shear_modulus': 'Pa', 'poissons_ratio': '1',
    'thermal_expansion': '1/K', 'electrical_conductivity': 'S/m',
    'relative_permittivity': '1', 'dielectric_loss_tangent': '1',
    'relative_permeability': '1', 'yield_strength': 'Pa',
}
STATUSES = {'estimate', 'manufacturer', 'measured', 'user', 'unavailable'}


class MaterialError(ValueError):
    """Malformed evidence or unsupported property projection."""


def _require(condition, message):
    if not condition:
        raise MaterialError(message)


def _text(value, field):
    _require(isinstance(value, str) and bool(value.strip()), f'{field}: expected nonempty text')


def _number(value, field):
    _require(type(value) in (int, float) and math.isfinite(value), f'{field}: expected finite number')


def _value(name, value):
    _number(value, name)
    if name == 'poissons_ratio':
        _require(-1 < value < 0.5, 'poissons_ratio: isotropic admissibility requires -1 < nu < 0.5')
    elif name == 'thermal_expansion':
        pass  # Negative thermal expansion is physically possible.
    elif name in ('electrical_conductivity', 'dielectric_loss_tangent', 'yield_strength'):
        _require(value >= 0, f'{name}: must be nonnegative')
    else:
        _require(value > 0, f'{name}: must be positive')


def _applicability(raw, field):
    _require(isinstance(raw, dict), f'{field}: expected object')
    _require(raw.keys() <= {'notes', 'temperature_k', 'frequency_hz'}, f'{field}: unknown applicability fields')
    _text(raw.get('notes'), f'{field}.notes')
    for key, lower in (('temperature_k', 0), ('frequency_hz', 0)):
        if key in raw:
            bounds = raw[key]
            _require(isinstance(bounds, list) and len(bounds) == 2, f'{field}.{key}: expected [min,max]')
            for v in bounds:
                _number(v, f'{field}.{key}')
            _require(lower <= bounds[0] <= bounds[1], f'{field}.{key}: invalid range')
            if key == 'temperature_k':
                _require(bounds[0] > 0, f'{field}: temperature must exceed absolute zero')


def validate_material(record):
    """Validate and return a detached JSON-compatible record; reject unknown fields."""
    _require(isinstance(record, dict), 'material: expected object')
    required = {'schema_version', 'id', 'revision', 'name', 'family', 'description', 'properties'}
    allowed = required | {'tags', 'manufacturer', 'grade', 'notes'}
    _require(required <= record.keys() <= allowed, 'material: missing or unknown fields')
    _require(type(record['schema_version']) is int and record['schema_version'] == 1, 'material: unsupported schema version')
    for key in ('id', 'revision', 'name', 'family', 'description'):
        _text(record[key], key)
    _require(re.fullmatch(r'[a-z0-9][a-z0-9._-]*', record['id']) is not None, 'material: invalid stable id')
    for key in ('manufacturer', 'grade', 'notes'):
        if key in record:
            _text(record[key], key)
    if 'tags' in record:
        _require(isinstance(record['tags'], list), 'tags: expected list')
        for tag in record['tags']:
            _text(tag, 'tag')
    props = record['properties']
    _require(isinstance(props, dict) and bool(props), 'properties: expected nonempty object')
    for name, prop in props.items():
        _require(name in PROPERTY_UNITS, f'unsupported property: {name}')
        _require(isinstance(prop, dict), f'{name}: expected object')
        base = {'unit', 'status', 'provenance', 'applicability', 'shape'}
        _require(base <= prop.keys(), f'{name}: missing metadata')
        _require(prop['unit'] == PROPERTY_UNITS[name], f'{name}: wrong SI unit')
        _require(isinstance(prop['status'], str) and prop['status'] in STATUSES, f'{name}: unsupported evidence status')
        provenance = prop['provenance']
        _require(isinstance(provenance, dict), f'{name}: expected provenance object')
        _require({'source', 'reviewed', 'license'} == provenance.keys(), f'{name}: invalid provenance fields')
        for key in provenance:
            _text(provenance[key], f'{name}.provenance.{key}')
        _applicability(prop['applicability'], name)
        shape = prop['shape']
        if prop['status'] == 'unavailable':
            _require(shape == 'unavailable' and prop.keys() == base, f'{name}: unavailable must not carry values')
        elif shape == 'scalar':
            _require(prop.keys() == base | {'value'}, f'{name}: unexpected scalar fields')
            _value(name, prop['value'])
        elif shape == 'orthotropic':
            _require(prop.keys() == base | {'values', 'axes'}, f'{name}: invalid orthotropic fields')
            _require(name != 'poissons_ratio', 'coupled orthotropic Poisson ratios require a separate constitutive schema')
            axes, values = prop['axes'], prop['values']
            _require(isinstance(axes, list) and len(axes) == 3, f'{name}: three named material axes required')
            for axis in axes:
                _text(axis, name)
            _require(len(set(axes)) == 3, f'{name}: duplicate material axes')
            _require(isinstance(values, list) and len(values) == 3, f'{name}: three principal values required')
            for value in values:
                _value(name, value)
        elif shape == 'samples':
            _require(prop.keys() == base | {'samples'}, f'{name}: invalid sample fields')
            samples = prop['samples']
            _require(isinstance(samples, list) and bool(samples), f'{name}: samples required')
            coordinates = set()
            dimensions = None
            for sample in samples:
                _require(isinstance(sample, dict) and 'value' in sample, f'{name}: invalid sample')
                dims = set(sample) - {'value'}
                _require(bool(dims) and dims <= {'temperature_k', 'frequency_hz'}, f'{name}: invalid sample coordinates')
                _require(dimensions is None or dims == dimensions, f'{name}: inconsistent sample coordinates')
                dimensions = dims
                for dim in dims:
                    _number(sample[dim], dim)
                    _require(sample[dim] >= 0 and (dim != 'temperature_k' or sample[dim] > 0), f'{name}: invalid sample coordinate')
                    if dim in prop['applicability']:
                        lo, hi = prop['applicability'][dim]
                        _require(lo <= sample[dim] <= hi, f'{name}: sample outside applicability')
                coord = tuple((d, sample[d]) for d in sorted(dims))
                _require(coord not in coordinates, f'{name}: duplicate sample coordinate')
                coordinates.add(coord)
                _value(name, sample['value'])
        else:
            raise MaterialError(f'{name}: unsupported shape {shape}')
    try:
        return json.loads(json.dumps(record, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise MaterialError('material: not inert JSON data') from exc


def material_digest(record):
    """SHA-256 of canonical UTF-8 JSON, including all evidence metadata."""
    valid = validate_material(record)
    payload = json.dumps(valid, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def material_snapshot(record):
    """Detach a complete assignment snapshot from later catalog revisions."""
    valid = validate_material(record)
    return {'schema_version': 1, 'material_id': valid['id'], 'revision': valid['revision'],
            'digest': material_digest(valid), 'record': valid}


def validate_snapshot(snapshot):
    _require(isinstance(snapshot, dict) and snapshot.keys() == {'schema_version', 'material_id', 'revision', 'digest', 'record'}, 'snapshot: invalid fields')
    expected = material_snapshot(snapshot['record'])
    _require(type(snapshot['schema_version']) is int and snapshot == expected, 'snapshot: identity or digest mismatch')
    return expected


def load_catalog(path=None):
    """Load a bounded local catalog. Duplicate IDs and nonfinite data fail closed."""
    source = Path(path) if path is not None else CATALOG_PATH
    _require(source.stat().st_size <= 8_000_000, 'catalog exceeds 8 MB limit')
    raw = json.loads(source.read_text(encoding='utf-8'))
    _require(isinstance(raw, dict) and raw.keys() == {'schema_version', 'license', 'materials'}, 'catalog: invalid fields')
    _require(type(raw['schema_version']) is int and raw['schema_version'] == 1, 'catalog: unsupported version')
    _text(raw['license'], 'catalog.license')
    _require(isinstance(raw['materials'], list) and len(raw['materials']) <= 10000, 'catalog: invalid materials')
    records = [validate_material(r) for r in raw['materials']]
    _require(len({r['id'] for r in records}) == len(records), 'catalog: duplicate material IDs')
    return records


def project_scalar_properties(record, property_names, *, allow_estimates=False):
    """Explicitly select constants only; never flatten axes or evaluate samples.

    The caller must still enforce property applicability, solver-specific
    constitutive requirements, and its numerical evidence/release gates.
    """
    valid = validate_material(record)
    _require(isinstance(property_names, (list, tuple)) and bool(property_names), 'projection: property list required')
    _require(type(allow_estimates) is bool, 'projection: allow_estimates must be boolean')
    result = {}
    for name in property_names:
        _require(isinstance(name, str) and name in valid['properties'], f'projection: missing property {name}')
        prop = valid['properties'][name]
        _require(prop['shape'] == 'scalar', f'{name}: scalar projection unavailable for {prop["shape"]}')
        _require(prop['status'] != 'estimate' or allow_estimates, f'{name}: estimate requires explicit acceptance')
        result[name] = prop['value']
    return result
