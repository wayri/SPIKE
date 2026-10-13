# SPDX-License-Identifier: Apache-2.0
"""Original bounded SI CalculiX thermal deck compiler; see CALCULIX_THERMAL.md."""
from __future__ import annotations

from .assembly_tetra_thermal_validation import validate_request, require
from .multiboard_identity import canonical_json_digest

FACE_NODES = ((0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0))


def compile_calculix_deck(request, *, require_steady_sink=True):
    """Return deterministic deck and identity maps, without launching a process."""
    data = validate_request(request)
    # A component must have its own physical sink. Coincidence is never a bond.
    parent = list(range(len(data['xyz'])))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for cell in data['cells']:
        for node in cell['vertices'][1:]:
            parent[find(node)] = find(cell['vertices'][0])
    for _, left, right, _, _ in data['contacts']:
        parent[find(left[0])] = find(right[0])
    anchors = set(data['fixed'])
    for face, _, _, _ in data['convection']:
        anchors.update(face)
    for face, _, emissivity, _ in data['radiation']:
        if emissivity > 0:
            anchors.update(face)
    require(not require_steady_sink or {find(i) for i in anchors} == {find(i) for i in range(len(parent))},
            'CALCULIX_UNANCHORED: every separate thermal body needs a temperature or ambient sink.')
    fmt = lambda x: format(float(x), '.17g')
    lines = ['*HEADING', 'SPIKE original steady thermal SI deck', '*NODE,NSET=NALL']
    lines += [f'{i},' + ','.join(map(fmt, point)) for i, point in enumerate(data['xyz'], 1)]
    materials = {mid: f'M{i}' for i, mid in enumerate(data['tensors'], 1)}
    element_ids = {cell['id']: i for i, cell in enumerate(data['cells'], 1)}
    face_map = {}
    for i, cell in enumerate(data['cells'], 1):
        for face_number, local in enumerate(FACE_NODES, 1):
            face_map[tuple(sorted(cell['vertices'][j] for j in local))] = (i, face_number)
    for mid, name in materials.items():
        tensor = data['tensors'][mid]
        lines += [f'*MATERIAL,NAME={name}', '*CONDUCTIVITY,TYPE=ANISO',
                  ','.join(fmt(tensor[i, j]) for i, j in ((0,0),(1,1),(2,2),(0,1),(0,2),(1,2))),
                  f'*ELEMENT,TYPE=DC3D4,ELSET=E{name}']
        lines += [f'{element_ids[c["id"]]},' + ','.join(str(v+1) for v in c['vertices'])
                  for c in data['cells'] if c['material_id'] == mid]
        lines += [f'*SOLID SECTION,ELSET=E{name},MATERIAL={name}']
    contact_map = {}
    for index, (cid, left, right, _, conductance) in enumerate(data['contacts'], 1):
        le, lf = face_map[tuple(sorted(left))]
        re, rf = face_map[tuple(sorted(right))]
        lines += [f'*SURFACE,NAME=L{index},TYPE=ELEMENT', f'{le},S{lf}',
                  f'*SURFACE,NAME=R{index},TYPE=ELEMENT', f'{re},S{rf}',
                  f'*SURFACE INTERACTION,NAME=C{index}',
                  '*SURFACE BEHAVIOR,PRESSURE-OVERCLOSURE=LINEAR', '1,1',
                  '*GAP CONDUCTANCE', f'{fmt(conductance)},,300',
                  f'*CONTACT PAIR,INTERACTION=C{index},TYPE=SURFACE TO SURFACE',
                  f'L{index},R{index}',
                  f'*CLEARANCE,SLAVE=L{index},MASTER=R{index},VALUE=0']
        contact_map[cid] = {'slave_element': le, 'slave_face': lf, 'master_element': re, 'master_face': rf}
    lines += ['*PHYSICAL CONSTANTS,ABSOLUTE ZERO=0,STEFAN BOLTZMANN=5.670374419E-8',
              '*INITIAL CONDITIONS,TYPE=TEMPERATURE', 'NALL,300',
              '*STEP,INC=100', '*HEAT TRANSFER,STEADY STATE,SOLVER=ITERATIVE CHOLESKY', '1,1,1E-6,1']
    if data['fixed']:
        lines += ['*BOUNDARY'] + [f'{node+1},11,11,{fmt(t)}' for node, t in sorted(data['fixed'].items())]
    if data['sources'] or data['fluxes']:
        lines += ['*DFLUX']
        lines += [f'{element_ids[cid]},BF,{fmt(q)}' for cid, q in data['sources'].items()]
        lines += [f'{face_map[f][0]},S{face_map[f][1]},{fmt(q)}' for f, _, q in data['fluxes']]
    if data['convection']:
        lines += ['*FILM'] + [f'{face_map[f][0]},F{face_map[f][1]},{fmt(t)},{fmt(h)}'
                              for f, _, h, t in data['convection']]
    if data['radiation']:
        lines += ['*RADIATE'] + [f'{face_map[f][0]},R{face_map[f][1]},{fmt(t)},{fmt(e)}'
                                 for f, _, e, t in data['radiation']]
    lines += ['*NODE PRINT,NSET=NALL,FREQUENCY=999999', 'NT', '*END STEP', '']
    return {'deck': '\n'.join(lines), 'tetra_request_digest': canonical_json_digest(request),
            'node_map': list(range(len(data['xyz']))), 'element_map': element_ids,
            'material_map': materials, 'contact_map': contact_map, 'boundary_map': {
                b['id']: {'element': face_map[tuple(sorted(b['vertices']))][0],
                          'face': face_map[tuple(sorted(b['vertices']))][1]}
                for b in request['boundaries']},
            'nodes': len(data['xyz']), 'tetrahedra': len(data['cells'])}
