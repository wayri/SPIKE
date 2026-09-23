"""Ordered electrical terminals shared by routing, drawing and properties.

The v1 document orders semiconductor pins as [collector/drain, emitter/source,
base/gate, bulk]. Preserve that order when opening existing drawings. Pin IDs
derive from component identity and ordinal, never from a net name or position.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Pin:
    index: int
    label: str
    anchor: tuple[float, float]
    body: tuple[float, float]


def ordered_nodes(element):
    if element.semiconductor_nodes:
        nodes = element.semiconductor_nodes
        return [nodes[0], nodes[2], *[n for i, n in enumerate(nodes) if i not in (0, 2)]]
    result = [element.positive_node, element.negative_node]
    if element.control_positive_node is not None:
        result += [element.control_positive_node, element.control_negative_node]
    return result


def pins(part):
    count = len(part.get('nodes', (None, None)))
    labels = {
        'diode': ('A', 'K'), 'npn_ebers_moll': ('C', 'E', 'B'),
        'nmos_level1': ('D', 'S', 'G', 'B'), 'bsim_bulk': ('D', 'S', 'G', 'B'),
        'bsim_cmg': ('D', 'S', 'G', 'E'), 'gan_hemt': ('D', 'S', 'G', 'B'),
        'sic_mosfet': ('D', 'S', 'G', 'B'),
    }.get(part.get('kind'), ('+', '-', 'C+', 'C-') if count <= 4 else ())
    result = []
    for index in range(count):
        if index < 2:
            side = -1 if index == 0 else 1
            anchor, body = (side * 55, 0), (side * 28, 0)
        else:
            # Additional pins get outward vertical leads, not decorative labels.
            side = -1 if index % 2 == 0 else 1
            offset = ((index - 2) // 2) * 20
            anchor, body = (offset, side * 55), (offset, side * 22)
        result.append(Pin(index, labels[index] if index < len(labels) else str(index + 1), anchor, body))
    return result


def pin_id(part, index):
    if type(index) is not int or not 0 <= index < len(part['nodes']):
        raise ValueError('Unknown terminal index')
    return f"{part['id']}:pin:{index}"


def bounds(part):
    terminals = pins(part)
    return (min([-62] + [p.anchor[0] - 8 for p in terminals]),
            min([-45] + [p.anchor[1] - 8 for p in terminals]),
            max([62] + [p.anchor[0] + 8 for p in terminals]),
            max([47] + [p.anchor[1] + 8 for p in terminals]))
