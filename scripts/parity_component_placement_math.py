# SPDX-License-Identifier: Apache-2.0
"""Independent cuboid oracle for the bounded native component reference cohort.

Column vectors; degrees at source; millimetres throughout. This is a validation
oracle, not an importer or automatic source-model placement implementation.
"""
from __future__ import annotations

import itertools
import math


def multiply(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def vector(a, p):
    return [sum(a[i][j] * p[j] for j in range(3)) for i in range(3)]


def rotation(axis, degrees):
    angle = math.radians(degrees)
    c, s = math.cos(angle), math.sin(angle)
    if axis == 'x':
        return [[1., 0., 0.], [0., c, -s], [0., s, c]]
    if axis == 'y':
        return [[c, 0., s], [0., 1., 0.], [-s, 0., c]]
    if axis == 'z':
        return [[c, -s, 0.], [s, c, 0.], [0., 0., 1.]]
    raise ValueError('Unknown rotation axis')


def native_vertices(side, angle, offset, angles, scale, *, surface_z=None):
    """Predict KiCad's right-handed X/-board-Y, midplane-Z reference frame.

    Cohort: footprint (20,10), board thickness 1.6, local STEP cuboid 2x3x4.
    WRL coordinate conversion is absent: STEP dimensions are already mm.
    """
    if side not in ('front', 'back'):
        raise ValueError('Unknown side')
    base = multiply(rotation('z', angle), rotation('x', 180. if side == 'back' else 0.))
    model = multiply(rotation('z', -angles[2]),
                     multiply(rotation('y', -angles[1]), rotation('x', -angles[0])))
    transform = multiply(base, model)
    elevation = (-.8 if side == 'back' else .8) if surface_z is None else surface_z
    translation = [a + b for a, b in zip([20., -10., elevation], vector(base, offset))]
    return [[a + b for a, b in zip(translation, vector(transform, [s * x for s, x in zip(scale, p)]))]
            for p in itertools.product([0., 2.], [0., 3.], [0., 4.])]


def spike_vertices(points, *, top_z=.8):
    """Explicit reference datum mapping: X=x, Y=-y, depth Z=0.8-z.

    The two axis flips preserve handedness. Top surface maps to depth zero;
    the 1.6 mm bottom surface maps to depth 1.6. No production projection.
    """
    return [[x, -y, top_z - z] for x, y, z in points]


def bounds(points):
    return [min(p[i] for p in points) for i in range(3)] + [max(p[i] for p in points) for i in range(3)]
