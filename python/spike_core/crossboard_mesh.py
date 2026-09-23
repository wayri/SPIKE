# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Nested benchmark grids in millimetres, with fixed physical PML interfaces."""
import math


def plan_crossboard_mesh(compiled, ports, *, base_spacing_mm=3., level=0):
    """Bisect every interior interval, including thin material/port intervals.

    PML cells deliberately remain fixed: their sensitivity is a separate study.
    This controlled fixture grid is not a general PCB mesh generator.
    """
    if type(level) is not int or not 0 <= level <= 2:
        raise ValueError('Mesh level must be 0, 1 or 2')
    if type(base_spacing_mm) not in (int, float) or not .5 <= base_spacing_mm <= 3:
        raise ValueError('Base spacing must be .5..3 mm')
    grids = []; bounds = []
    for axis in range(3):
        low = min(b['start_mm'][axis] for b in compiled['boxes']) - 10.
        high = max(b['stop_mm'][axis] for b in compiled['boxes']) + 10.
        pins = {low, high}
        for box in compiled['boxes']:
            pins.update((box['start_mm'][axis], box['stop_mm'][axis]))
        for start, stop in ports:
            pins.update((start[axis], stop[axis], (start[axis]+stop[axis])/2))
        anchors = sorted(pins)
        interior = []
        for a, b in zip(anchors, anchors[1:]):
            count = math.ceil((b-a)/base_spacing_mm) * 2**level
            interior.extend(a+(b-a)*i/count for i in range(count))
        interior.append(high)
        grids.append([low-3*i for i in range(8, 0, -1)] + interior +
                     [high+3*i for i in range(1, 9)])
        bounds.append([low, high])
    dimensions = [len(g)-1 for g in grids]
    cells = math.prod(dimensions)
    if cells > 1500000:
        raise ValueError('Cross-board fixture exceeds 1.5 million cells')
    return {'policy': 'nested-interior-fixed-pml/v1', 'level': level,
            'base_spacing_mm': base_spacing_mm, 'lines_mm': grids,
            'dimensions': dimensions, 'cells': cells,
            'inner_pml_bounds_mm': bounds}
