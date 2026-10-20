# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded positive-volume tetra overlap exclusion, not contact qualification.

Original convex separating-axis implementation with certified floating signs
and binary-rational fallback. No external predicate or collision code is used.
"""
from fractions import Fraction
import itertools

import numpy as np

MAX_CANDIDATES = 100000
MAX_EXACT_PREDICATES = 200000
MAX_AXIS_TESTS = 2000000
# A six-term determinant has three rounded differences and two products per
# monomial, then at most five additions. 128 eps conservatively bounds these
# errors plus the rounding of the positive permanent; eps is 2u, not u.
_EPS = np.finfo(float).eps
_ERROR_FACTOR = 128.*_EPS/(1.-128.*_EPS)
_PERMUTATIONS = ((0, 1, 2), (1, 2, 0), (2, 0, 1),
                 (0, 2, 1), (2, 1, 0), (1, 0, 2))


class TetraIntersectionError(ValueError):
    """Positive-volume overlap or exhausted geometry predicate budget."""


def _filtered_determinants(edge1, edge2, differences):
    terms = [edge1[..., a]*edge2[..., b]*differences[..., c] for a, b, c in _PERMUTATIONS]
    determinant = terms[0]+terms[1]+terms[2]-terms[3]-terms[4]-terms[5]
    permanent = sum(abs(term) for term in terms)
    error = _ERROR_FACTOR*permanent
    # The caller raises on IEEE inexact underflow. Exactly representable
    # subnormal operations have zero rounding error and do not break the bound.
    return np.where(determinant > error, 1, np.where(determinant < -error, -1, 0))


def _separated(vertices, left, right, exact_points, exact_axes, diagnostics):
    left_points, right_points = vertices[left], vertices[right]
    differences = right_points[None, :, :]-left_points[:, None, :]
    edge_pairs = []
    for cell in (left, right):
        for a, b, c in itertools.combinations(cell, 3):
            edge_pairs.append(((a, b), (a, c)))

    def exact_point(index):
        if index not in exact_points:
            exact_points[index] = tuple(Fraction.from_float(float(v)) for v in vertices[index])
        return exact_points[index]

    def exact_difference(first, second):
        return tuple(a-b for a, b in zip(exact_point(first), exact_point(second)))

    deferred = []
    indices = np.asarray(edge_pairs)
    edges = vertices[indices[:, :, 1]]-vertices[indices[:, :, 0]]
    face_signs = _filtered_determinants(edges[:, 0, None, None, :],
                                       edges[:, 1, None, None, :], differences[None, ...])
    diagnostics["axis_tests"] += 8
    if diagnostics["axis_tests"] > MAX_AXIS_TESTS:
        raise TetraIntersectionError("Intersection axis-test budget exceeded")
    for axis_number, ((a, b), (c, d)) in enumerate(edge_pairs):
        signs = face_signs[axis_number]
        positive, negative = bool(np.any(signs > 0)), bool(np.any(signs < 0))
        if positive and negative:
            continue
        if not np.any(signs == 0):
            return True
        deferred.append((int(np.count_nonzero(signs == 0)), axis_number, a, b, c, d))

    def exact_separation(candidates):
        for _, number, a, b, c, d in sorted(candidates):
            key = tuple(sorted((int(a), int(b), int(d)))) if number < 8 else None
            if key is not None and key in exact_axes:
                axis, projections = exact_axes[key]
            else:
                e, f = exact_difference(b, a), exact_difference(d, c)
                axis = (e[1]*f[2]-e[2]*f[1], e[2]*f[0]-e[0]*f[2], e[0]*f[1]-e[1]*f[0])
                projections = {}
                if key is not None:
                    exact_axes[key] = axis, projections
            if not any(axis):
                continue
            for vertex in set(left) | set(right):
                if vertex in projections:
                    continue
                diagnostics["exact_predicates"] += 1
                if diagnostics["exact_predicates"] > MAX_EXACT_PREDICATES:
                    raise TetraIntersectionError("Exact intersection predicate budget exceeded")
                point = exact_point(vertex)
                projections[vertex] = sum(axis[j]*point[j] for j in range(3))
            a_values = [projections[i] for i in left]
            b_values = [projections[i] for i in right]
            if max(a_values) <= min(b_values) or max(b_values) <= min(a_values):
                return True
        return False

    if exact_separation(deferred):
        return True
    # Face axes usually suffice; cross-edge axes remain necessary in general.
    deferred = []
    pairs = itertools.product(itertools.combinations(left, 2), itertools.combinations(right, 2))
    for number, ((a, b), (c, d)) in enumerate(pairs, start=8):
        diagnostics["axis_tests"] += 1
        if diagnostics["axis_tests"] > MAX_AXIS_TESTS:
            raise TetraIntersectionError("Intersection axis-test budget exceeded")
        signs = _filtered_determinants(vertices[b]-vertices[a], vertices[d]-vertices[c], differences)
        positive, negative = bool(np.any(signs > 0)), bool(np.any(signs < 0))
        if positive and negative:
            continue
        if not np.any(signs == 0):
            return True
        deferred.append((int(np.count_nonzero(signs == 0)), number, a, b, c, d))
    return exact_separation(deferred)


def screen_positive_volume_intersections(vertices, cells, face_owners, *, cancel_check=None):
    """Check all pairs through AABBs; return diagnostics or raise, never repair.

    Requires positive-volume, manifold tetra topology already admitted. Only
    pairs sharing a verified opposite-sided facet can skip the convex test.
    No assertion about nonshared zero-measure tangencies is made.
    """
    diagnostics = {"candidate_pairs": 0, "axis_tests": 0, "exact_predicates": 0,
                   "positive_volume_overlap_checked": True,
                   "nonshared_zero_measure_contacts_qualified": False}
    adjacent = {tuple(sorted((int(a), int(b)))) for a, b in face_owners if b >= 0}
    minima, maxima = vertices[cells].min(axis=1), vertices[cells].max(axis=1)
    exact_points, exact_axes = {}, {}
    with np.errstate(all="raise"):
        for i in range(len(cells)):
            if cancel_check and cancel_check():
                raise InterruptedError("Tetra intersection screening cancelled")
            # Strict inequalities exclude exact axis-aligned touching safely.
            possible = np.flatnonzero(np.all(maxima[i] > minima[i+1:], axis=1)
                                      & np.all(maxima[i+1:] > minima[i], axis=1))+i+1
            for j in possible:
                if cancel_check and cancel_check():
                    raise InterruptedError("Tetra intersection screening cancelled")
                if (i, int(j)) in adjacent:
                    continue
                diagnostics["candidate_pairs"] += 1
                if diagnostics["candidate_pairs"] > MAX_CANDIDATES:
                    raise TetraIntersectionError("Intersection candidate budget exceeded")
                if not _separated(vertices, cells[i], cells[j], exact_points, exact_axes, diagnostics):
                    raise TetraIntersectionError(f"Positive-volume tetrahedron overlap: cells {i} and {j}")
    return diagnostics
