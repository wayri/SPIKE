# SPDX-License-Identifier: Apache-2.0
"""Independent, bounded geometry assertions for board import benchmarks."""
from __future__ import annotations

import math
import re


COLLECTIONS = ('materials', 'layers', 'nets', 'tracks', 'arcs', 'zones', 'pads',
               'vias', 'drills', 'castellations', 'pins', 'components', 'regions', 'models')


def _selector(row: dict) -> tuple[str, str]:
    keys = [key for key in ('source_id', 'name') if key in row]
    if len(keys) != 1 or not isinstance(row[keys[0]], str) or not row[keys[0]].strip():
        raise ValueError('assertion requires exactly one non-empty source_id or name')
    return keys[0], row[keys[0]]


def _select(design: dict, row: dict) -> list[dict]:
    key, value = _selector(row)
    return [entity for entity in design.get(row['collection'], []) if entity.get(key) == value]


def _field(entity: dict, path: str) -> object:
    value = entity
    parts = path[1:].split('/') if path.startswith('/') else path.split('.')
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def validate_assertions(value: object) -> list[dict]:
    if not isinstance(value, list) or len(value) > 1000:
        raise ValueError('expected_entities must be a list of at most 1000 assertions')
    seen = set()
    for row in value:
        if not isinstance(row, dict) or set(row) - {'collection', 'source_id', 'name', 'field', 'value', 'reference', 'tolerance'}:
            raise ValueError('invalid expected_entities assertion')
        if row.get('collection') not in COLLECTIONS:
            raise ValueError('assertion collection is unsupported')
        selector = _selector(row)
        field = row.get('field')
        parts = field[1:].split('/') if isinstance(field, str) and field.startswith('/') else (
            field.split('.') if isinstance(field, str) else [])
        if (not isinstance(field, str) or len(field) > 200 or not 1 <= len(parts) <= 8
                or any(not re.fullmatch(r'(?:[A-Za-z_][A-Za-z0-9_:.]*|\d+)', part) for part in parts)):
            raise ValueError('assertion field must be a bounded literal field/index path')
        identity = (row['collection'], selector, field)
        if identity in seen:
            raise ValueError('duplicate entity assertion')
        seen.add(identity)
        if ('value' in row) == ('reference' in row):
            raise ValueError('assertion requires exactly one value or reference')
        if 'reference' in row:
            reference = row['reference']
            if (not isinstance(reference, dict) or set(reference) - {'collection', 'source_id', 'name'}
                    or reference.get('collection') not in COLLECTIONS
                    or 'tolerance' in row):
                raise ValueError('invalid entity reference assertion')
            _selector(reference)
            continue
        expected = row['value']
        values = expected if isinstance(expected, list) else [expected]
        if not values or len(values) > 16 or any(
            not isinstance(item, (str, int, float)) or isinstance(item, bool)
            or (isinstance(item, (int, float)) and not math.isfinite(item)) for item in values
        ):
            raise ValueError('assertion value must be finite scalar or bounded flat vector')
        tolerance = row.get('tolerance', 0)
        if type(tolerance) not in (int, float) or not math.isfinite(tolerance) or tolerance < 0:
            raise ValueError('assertion tolerance must be finite and nonnegative')
    return value


def _matches(actual: object, expected: object, tolerance: float) -> bool:
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            _matches(a, e, tolerance) for a, e in zip(actual, expected)
        )
    if isinstance(expected, str):
        return isinstance(actual, str) and actual == expected
    if type(expected) not in (int, float):
        return False
    return type(actual) in (int, float) and math.isfinite(actual) and abs(actual - expected) <= tolerance


def inspect_geometry(design: dict, report: dict, assertions: list[dict], expected_sha256: str | None) -> dict:
    validate_assertions(assertions)
    mismatches = []
    frame = design.get('frame')
    if not isinstance(frame, dict) or frame.get('units') != 'mm' or frame.get('handedness') != 'right':
        mismatches.append({'check': 'canonical_frame', 'expected': 'right-handed mm', 'actual': frame})
    source = design.get('source', {})
    if not isinstance(source, dict):
        raise ValueError('design.source must be an object')
    if expected_sha256 is not None:
        if source.get('source_digest') != expected_sha256 or report.get('source_sha256') != expected_sha256:
            mismatches.append({'check': 'source_digest', 'expected': expected_sha256,
                               'design': source.get('source_digest'), 'report': report.get('source_sha256')})
    identities = set()
    for collection in COLLECTIONS:
        entities = design.get(collection, [])
        if not isinstance(entities, list) or any(not isinstance(e, dict) for e in entities):
            raise ValueError(f'{collection} must contain entity objects')
        for entity in entities:
            identifier = entity.get('id')
            if not isinstance(identifier, str) or not identifier.strip() or identifier in identities:
                mismatches.append({'check': 'unique_entity_id', 'collection': collection, 'actual': identifier})
            else:
                identities.add(identifier)
    for assertion in assertions:
        candidates = _select(design, assertion)
        actual = _field(candidates[0], assertion['field']) if len(candidates) == 1 else None
        expected = assertion.get('value')
        reference_count = 1
        if 'reference' in assertion:
            ref = assertion['reference']
            targets = _select(design, ref)
            reference_count = len(targets)
            expected = targets[0].get('id') if reference_count == 1 else None
        if (len(candidates) != 1 or reference_count != 1
                or not _matches(actual, expected, assertion.get('tolerance', 0))):
            mismatches.append({'check': 'entity_value', **assertion, 'matches': len(candidates), 'actual': actual})
    return {'geometry_mismatches': mismatches, 'entity_assertions_checked': len(assertions),
            'source_digest_checked': expected_sha256 is not None}
