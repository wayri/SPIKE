# SPDX-License-Identifier: Apache-2.0
"""Presentation routes from authoritative named nets; no connectivity guessing."""
import uuid
from .pin_geometry import pins
from .editor_geometry import transform


def source_routes(document):
    if document.data['wires']: return
    groups = {}
    for part in document.data['components']:
        for pin in pins(part):
            groups.setdefault(part['nodes'][pin.index].casefold(), []).append(
                ([part['id'], pin.index], transform(part, *pin.anchor)))
    wires = []
    for terminals in groups.values():
        connected, pending = terminals[:1], terminals[1:]
        while pending:
            if len(terminals) > 64:
                left, chosen = connected[-1], 0
            else:
                _, left, chosen = min((abs(a[1][0]-b[1][0])+abs(a[1][1]-b[1][1]), a, index)
                                      for a in connected for index, b in enumerate(pending))
            right = pending.pop(chosen)
            wires.append(dict(id=uuid.uuid4().hex, a=left[0], b=right[0], waypoints=[]))
            connected.append(right)
    document.data['wires'] = wires;document.validate()


def startup_layout(document):
    for part in document.data['components']:
        if part['ref'].upper() == 'V1': part.update(x=180, y=300, rotation=90)
        elif part['ref'].upper() == 'R1': part.update(x=380, y=220)
        elif part['ref'].upper() == 'C1': part.update(x=580, y=300, rotation=90)
    source_routes(document)
