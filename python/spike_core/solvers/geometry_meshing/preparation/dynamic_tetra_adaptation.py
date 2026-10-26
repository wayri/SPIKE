# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded one-pass adaptation for an existing conforming tetrahedral mesh.

The controller combines deterministic error/sizing marks with explicit edges,
then delegates complete edge-star bisection and optional interior smoothing to
the tested local mesh primitives.  Supplied scalar fields are transferred
only for pure refinement: nodal P1 data use midpoint interpolation and cell
data inherit the original parent value.  Field-aware vertex relocation and
general conservative remapping are intentionally unsupported.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import itertools
import math
import sys

from .tetra_mesh_optimization import optimize_tetra_mesh
from .tetra_mesh_refinement import MAX_EDGES, TetraRefinementError, _det, _require, _validate, refine_tetra_mesh

MAX_ADAPT_CELLS = 5_000
MAX_ADAPT_VERTICES = 10_000


def _finite_number(value, message):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    _require(valid, message)
    return float(value)


def _edge_length(points, edge):
    try:
        value = math.dist(points[edge[0]], points[edge[1]])
    except (OverflowError, ValueError) as exc:
        raise TetraRefinementError('Edge length is outside representable numerical range.') from exc
    _require(math.isfinite(value) and value > 0, 'Invalid mesh edge length.')
    return value


def _longest_edge(points, cell):
    edges = [tuple(sorted(edge)) for edge in itertools.combinations(cell['vertices'], 2)]
    # The vertex-index tie break makes equal-length choices independent of set/dict order.
    return min(edges, key=lambda edge: (-_edge_length(points, edge), edge))


def _field_map(value, expected_length, label):
    if value is None:
        return {}
    _require(isinstance(value, dict) and len(value) <= 32,
             f'Invalid {label} field map.')
    result = {}
    for name, samples in value.items():
        _require(isinstance(name, str) and 0 < len(name) <= 256 and
                 isinstance(samples, list) and len(samples) == expected_length,
                 f'Invalid {label} field name or length.')
        result[name] = [_finite_number(sample, f'{label.capitalize()} fields must be finite scalars.')
                        for sample in samples]
    return result


def _indicator_values(cell_indicators, cells):
    if cell_indicators is None:
        return None
    ids = [cell['id'] for cell in cells]
    _require(isinstance(cell_indicators, dict) and set(cell_indicators) == set(ids),
             'Cell indicators must contain exactly the mesh cell IDs.')
    values = {}
    for cell_id in ids:
        value = _finite_number(cell_indicators[cell_id],
                               'Cell indicators must be finite scalars.')
        _require(value >= 0, 'Cell indicators must be nonnegative.')
        values[cell_id] = value
    return values


def _dorfler_marks(indicators, marking_fraction):
    if indicators is None:
        return [], {'provided': False}
    scale = max(indicators.values(), default=0.0)
    if scale == 0:
        return [], {'provided': True, 'indicator_scale': 0.0,
                    'normalized_squared_sum': 0.0, 'target_bulk_fraction': marking_fraction,
                    'achieved_bulk_fraction': 0.0, 'marked_cell_ids': []}
    weights = {cell_id: (value / scale) ** 2 for cell_id, value in indicators.items()}
    total = math.fsum(weights.values())
    threshold = marking_fraction * total
    ordered = sorted(indicators, key=lambda cell_id: (-indicators[cell_id], cell_id))
    marked = []
    accumulated = 0.0
    for cell_id in ordered:
        if marking_fraction == 1:
            if indicators[cell_id] > 0:
                marked.append(cell_id)
            continue
        if accumulated >= threshold:
            break
        marked.append(cell_id)
        accumulated = math.fsum(weights[item] for item in marked)
    if marking_fraction == 1:
        accumulated = total
    achieved = accumulated / total
    return marked, {'provided': True, 'indicator_scale': scale,
                    'normalized_squared_sum': total, 'target_bulk_fraction': marking_fraction,
                    'achieved_bulk_fraction': achieved, 'marked_cell_ids': marked[:],
                    'squared_weight_underflow_count': sum(indicators[key] > 0 and weight == 0
                                                         for key, weight in weights.items())}


def _scalar_midpoint(a, b):
    # Evaluate the binary-rational midpoint before rounding; halving two
    # subnormals separately can lose even a constant field. Fail if the rounded
    # value has a material relative error, rather than claiming P1 exactness.
    exact = (Fraction(a) + Fraction(b)) / 2
    value = float(exact)
    _require(math.isfinite(value) and (not exact or
             abs(Fraction(value)-exact) <= abs(exact)*Fraction(1, 10**12)),
             'Nodal field interpolation is not representable accurately.')
    return value


def _integral_product(volume, sample):
    term = volume * sample
    _require(math.isfinite(term), 'Cell field integral is not representable.')
    if sample and abs(term) < sys.float_info.min:
        exact = Fraction(volume) * Fraction(sample)
        _require(abs(Fraction(term)-exact) <= abs(exact)*Fraction(1, 10**12),
                 'Cell field integral is not representable accurately.')
    return term


def _cell_integrals(mesh, fields):
    result = {}
    for name, samples in fields.items():
        by_material = {}
        material_absolute = {}
        contributions = []
        absolute = []
        for cell, sample in zip(mesh['cells'], samples):
            volume = _det(mesh['vertices'], cell['vertices']) / 6.0
            term = _integral_product(volume, sample)
            contributions.append(term)
            absolute.append(abs(term))
            by_material.setdefault(cell['material_id'], []).append(term)
            material_absolute.setdefault(cell['material_id'], []).append(abs(term))
        result[name] = {
            'global': math.fsum(contributions),
            'absolute_scale': math.fsum(absolute),
            'by_material': {key: math.fsum(values) for key, values in sorted(by_material.items())},
            'material_absolute_scale': {key: math.fsum(values)
                                        for key, values in sorted(material_absolute.items())},
        }
    return result


def _cell_transfer_metrics(before, after):
    metrics = {}
    for name in before:
        scale = max(before[name]['absolute_scale'], after[name]['absolute_scale'])
        tolerance = max(64.0 * math.ulp(scale), 2e-12 * scale) if scale else 0.0
        global_error = after[name]['global'] - before[name]['global']
        materials = {}
        all_conserved = abs(global_error) <= tolerance
        keys = sorted(set(before[name]['by_material']) | set(after[name]['by_material']))
        for material in keys:
            old = before[name]['by_material'].get(material, 0.0)
            new = after[name]['by_material'].get(material, 0.0)
            error = new - old
            material_scale = max(before[name]['material_absolute_scale'].get(material, 0.0),
                                 after[name]['material_absolute_scale'].get(material, 0.0))
            material_tolerance = max(64.0 * math.ulp(material_scale),
                                     2e-12 * material_scale) if material_scale else 0.0
            conserved = abs(error) <= material_tolerance
            all_conserved = all_conserved and conserved
            materials[material] = {'before_integral': old, 'after_integral': new,
                                   'absolute_error': abs(error), 'conserved': conserved}
        metrics[name] = {'method': 'piecewise_constant_parent_inheritance',
                         'before_integral': before[name]['global'],
                         'after_integral': after[name]['global'],
                         'absolute_error': abs(global_error),
                         'conserved': all_conserved, 'by_material': materials}
        _require(all_conserved, 'Cell field conservation check failed.')
    return metrics


def _size_violations(mesh, target_edge_length):
    if target_edge_length is None:
        return []
    violations = []
    for cell in mesh['cells']:
        edge = _longest_edge(mesh['vertices'], cell)
        length = _edge_length(mesh['vertices'], edge)
        if length > target_edge_length:
            violations.append({'cell_id': cell['id'], 'longest_edge': list(edge),
                               'edge_length': length})
    return sorted(violations, key=lambda item: item['cell_id'])


def adapt_tetra_mesh(mesh, boundary_triangles, *, cell_indicators=None,
                     marking_fraction=0.5, target_edge_length=None, manual_edges=None,
                     protected_vertices=None, optimize=True, iterations=3,
                     max_cells=MAX_ADAPT_CELLS, max_vertices=MAX_ADAPT_VERTICES,
                     nodal_fields=None, cell_fields=None):
    """Perform one deterministic, resource-bounded tetra adaptation pass.

    Error marks use a minimal deterministic Dörfler set of squared indicators.
    Sizing marks include every cell whose longest edge exceeds the requested
    length.  Each marked cell contributes its longest edge; explicit manual
    edges are unioned and duplicate adaptation edges are split once.

    ``nodal_fields`` and ``cell_fields`` are mappings of scalar field names to
    arrays in original vertex/cell order.  When either contains data,
    ``optimize`` must be false because relocation remapping is not implemented.
    """
    _require(type(max_cells) is int and 1 <= max_cells <= MAX_ADAPT_CELLS and
             type(max_vertices) is int and 4 <= max_vertices <= MAX_ADAPT_VERTICES,
             'Invalid adaptation resource budgets.')
    _require(type(optimize) is bool, 'Optimize must be a boolean.')
    _require(type(iterations) is int and 1 <= iterations <= 10,
             'Invalid iteration budget.')
    fraction = _finite_number(marking_fraction, 'Marking fraction must be finite.')
    _require(0 < fraction <= 1, 'Marking fraction must be in (0, 1].')
    if target_edge_length is not None:
        target_edge_length = _finite_number(target_edge_length,
                                             'Target edge length must be finite.')
        _require(target_edge_length > 0, 'Target edge length must be positive.')

    initial_quality = _validate(mesh, boundary_triangles, max_cells, max_vertices)
    points, cells = mesh['vertices'], mesh['cells']
    protected = [] if protected_vertices is None else protected_vertices
    _require(isinstance(protected, list) and len(protected) <= len(points) and
             all(type(index) is int and 0 <= index < len(points) for index in protected) and
             len(set(protected)) == len(protected), 'Invalid protected vertices.')

    nodal = _field_map(nodal_fields, len(points), 'nodal')
    cellular = _field_map(cell_fields, len(cells), 'cell')
    _require(not (optimize and (nodal or cellular)),
             'Optimization with supplied fields is unsupported; use optimize=False.')
    indicators = _indicator_values(cell_indicators, cells)

    all_edges = {tuple(sorted(edge)) for cell in cells
                 for edge in itertools.combinations(cell['vertices'], 2)}
    manual = [] if manual_edges is None else manual_edges
    _require(isinstance(manual, list) and len(manual) <= MAX_EDGES,
             'Invalid manual edge array.')
    canonical_manual = []
    for edge in manual:
        _require(isinstance(edge, list) and len(edge) == 2 and
                 all(type(index) is int and 0 <= index < len(points) for index in edge) and
                 edge[0] != edge[1], 'Invalid manual edge.')
        canonical = tuple(sorted(edge))
        _require(canonical in all_edges, 'Manual edge does not exist in the mesh.')
        canonical_manual.append(canonical)
    canonical_manual = sorted(set(canonical_manual))

    indicator_marks, indicator_evidence = _dorfler_marks(indicators, fraction)
    initial_size_violations = _size_violations(mesh, target_edge_length)
    size_marks = [item['cell_id'] for item in initial_size_violations]
    marked_ids = set(indicator_marks) | set(size_marks)
    cells_by_id = {cell['id']: cell for cell in cells}
    selected = {_longest_edge(points, cells_by_id[cell_id]) for cell_id in marked_ids}
    selected.update(canonical_manual)
    selected_edges = [list(edge) for edge in sorted(selected)]
    _require(len(selected_edges) <= MAX_EDGES, 'Adaptation selected edge budget exceeded.')

    refined = refine_tetra_mesh(mesh, selected_edges, boundary_triangles,
                                max_cells=max_cells, max_vertices=max_vertices)
    adapted_mesh = refined['mesh']
    adapted_boundary = refined['boundary_triangles']

    transferred_nodal = copy.deepcopy(nodal)
    for entry in refined['refinement_log']:
        a, b = entry['edge']
        for name, samples in transferred_nodal.items():
            midpoint = _scalar_midpoint(samples[a], samples[b])
            samples.append(midpoint)

    original_cell_index = {cell['id']: index for index, cell in enumerate(cells)}
    transferred_cellular = {
        name: [samples[original_cell_index[refined['parent_cell_ids'][cell['id']]]]
               for cell in adapted_mesh['cells']]
        for name, samples in cellular.items()
    }
    before_integrals = _cell_integrals(mesh, cellular)
    after_integrals = _cell_integrals(adapted_mesh, transferred_cellular)
    cell_metrics = _cell_transfer_metrics(before_integrals, after_integrals)

    optimization_log = {'requested': optimize, 'performed': False, 'moves': [],
                        'fixed_vertices': [], 'trial_moves': 0, 'budget_exhausted': False}
    if optimize:
        optimized = optimize_tetra_mesh(adapted_mesh, adapted_boundary,
                                        protected_vertices=protected, iterations=iterations)
        adapted_mesh = optimized['mesh']
        adapted_boundary = optimized['boundary_triangles']
        optimization_log = {'requested': True, 'performed': True,
                            'moves': optimized['moves'],
                            'fixed_vertices': optimized['fixed_vertices'],
                            'trial_moves': optimized['trial_moves'],
                            'budget_exhausted': optimized['budget_exhausted']}

    final_quality = _validate(adapted_mesh, adapted_boundary, max_cells, max_vertices)
    remaining_size_violations = _size_violations(adapted_mesh, target_edge_length)
    if indicators is not None:
        convergence_assessed = False
        converged = False
        convergence_reason = 'cell_indicators_were_not_recomputed_after_refinement'
    elif target_edge_length is not None:
        convergence_assessed = True
        converged = not remaining_size_violations
        convergence_reason = 'target_edge_length_met' if converged else 'target_edge_length_unmet'
    else:
        convergence_assessed = False
        converged = False
        convergence_reason = 'no_recomputed_adaptation_criterion'

    nodal_metrics = {name: {'method': 'original_P1_midpoint_interpolation',
                            'source_vertices': len(points),
                            'transferred_vertices': len(samples),
                            'created_vertices': len(samples) - len(points)}
                     for name, samples in transferred_nodal.items()}
    evidence = {
        'one_pass': True,
        'indicator_marking': indicator_evidence,
        'sizing': {'target_edge_length': target_edge_length,
                   'initial_violations': initial_size_violations,
                   'remaining_violations': remaining_size_violations,
                   'criterion_met': target_edge_length is not None and
                                    not remaining_size_violations},
        'manual_edges': [list(edge) for edge in canonical_manual],
        'marked_cell_ids': sorted(marked_ids),
        'selected_edges': copy.deepcopy(selected_edges),
        'convergence_assessed': convergence_assessed,
        'converged': converged,
        'convergence_reason': convergence_reason,
    }
    return {
        'mesh': adapted_mesh,
        'boundary_triangles': adapted_boundary,
        'parent_cell_ids': refined['parent_cell_ids'],
        'refinement_log': refined['refinement_log'],
        'optimization_log': optimization_log,
        'quality': {'before': initial_quality, 'after': final_quality},
        'nodal_fields': transferred_nodal,
        'cell_fields': transferred_cellular,
        'transfer_metrics': {'nodal': nodal_metrics, 'cell': cell_metrics,
                             'relocation_remap': 'not_implemented'},
        'adaptation_evidence': evidence,
        'production_qualified': False,
    }
