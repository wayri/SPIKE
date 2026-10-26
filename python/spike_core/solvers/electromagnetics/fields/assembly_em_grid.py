# SPDX-License-Identifier: Apache-2.0
"""Original bounded Cartesian sampling of unchanged retained polyhedra.

Grid lines describe discretization, not geometric simplification. The opt-in
sampling policy preserves terminal planes and material Z extrema; XY contours
remain native polyhedra and require separate spatial-convergence qualification.
"""
import math


def retained_em_grid_axes(compiled, settings):
    edge=settings['mesh_resolution_m']; margin=settings['air_margin_m']
    sampled=settings.get('mesh_policy')=='cartesian_sampling_v1'
    axes=[]
    for axis in range(3):
        bounds=[(min(v[axis] for v in p['vertices_m']),max(v[axis] for v in p['vertices_m'])) for p in compiled['primitives']]
        low=min(a for a,b in bounds)-margin; high=max(b for a,b in bounds)+margin
        anchors={low,high}
        if not sampled or axis==2:
            for a,b in bounds:anchors.update((a,b))
        for port in compiled['ports']:anchors.update((port['start_m'][axis],port['stop_m'][axis]))
        anchors=sorted(anchors)
        count=sum(max(1,math.ceil((b-a)/edge)) for a,b in zip(anchors[:-1],anchors[1:]))+16
        if count>10000:raise ValueError('ASSEMBLY_EM_MESH: axis budget exceeded before allocation')
        lines=[low-edge*j for j in range(8,0,-1)]
        for a,b in zip(anchors[:-1],anchors[1:]):
            count=max(1,math.ceil((b-a)/edge))
            lines.extend(a+(b-a)*j/count for j in range(count))
        lines.append(high)
        lines.extend(high+edge*j for j in range(1,9))
        axes.append(lines)
    if math.prod(len(v)-1 for v in axes)>1_000_000:
        raise ValueError('ASSEMBLY_EM_MESH: cell budget exceeded before allocation')
    return axes
