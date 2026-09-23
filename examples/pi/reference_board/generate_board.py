# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yawar Badri
"""Generate the original, deliberately synthetic SPIKE PI reference board."""

from pathlib import Path
from uuid import uuid5, NAMESPACE_URL


OUT = Path(__file__).with_name("spike-pi-reference.kicad_pcb")


def uid(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, "spike-pi-reference-v1/" + name))


def segment(name: str, x1: float, y1: float, x2: float, y2: float, width: float, layer: str, net: int) -> str:
    return f'(segment (start {x1} {y1}) (end {x2} {y2}) (width {width}) (layer "{layer}") (net {net}) (uuid "{uid(name)}"))'


def via(name: str, x: float, y: float, net: int) -> str:
    return f'(via (at {x} {y}) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu") (net {net}) (uuid "{uid(name)}"))'


def footprint(ref: str, value: str, x: float, y: float, pads: list[tuple[str, float, float, int, str]]) -> str:
    chunks = [f'(footprint "SPIKE:PI_Test" (layer "F.Cu") (at {x} {y}) (uuid "{uid(ref)}")',
              f'  (property "Reference" "{ref}") (property "Value" "{value}")']
    for number, px, py, net, net_name in pads:
        chunks.append(f'  (pad "{number}" smd rect (at {px} {py}) (size 1 1) (layers "F.Cu") (net {net} "{net_name}") (uuid "{uid(ref+number)}"))')
    return "\n".join(chunks + [")"])


parts = [
    '(kicad_pcb (version 20241229) (generator "SPIKE-PI-reference")',
    '  (general (thickness 1.6)) (paper "A4")',
    '  (title_block (title "SPIKE PI Reference Board") (rev "1.0") (company "Yawar Badri")',
    '    (comment 1 "Synthetic benchmark fixture; not production hardware"))',
    '  (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))',
    '  (setup (stackup (layer "F.Cu" (type "copper") (thickness 0.035))'
    '    (layer "dielectric 1" (type "core") (thickness 1.53) (material "FR4")'
    '      (epsilon_r 4.2) (loss_tangent 0.02))'
    '    (layer "B.Cu" (type "copper") (thickness 0.035))))',
    '  (net 0 "") (net 1 "VIN") (net 2 "VLOAD") (net 3 "VAUX") (net 4 "GND")',
]

# Rail 1: a source trace, an explicit series part, then trace-via-bottom-trace-via-zone.
parts += [
    segment("vin-left", 5, 10, 14, 10, 1.0, "F.Cu", 1),
    segment("vin-right", 14, 10, 20, 10, 1.0, "F.Cu", 1),
    segment("vload-front", 22, 10, 29, 10, 1.0, "F.Cu", 2),
    via("vload-down", 29, 10, 2),
    segment("vload-back", 29, 10, 35, 10, 1.0, "B.Cu", 2),
    via("vload-up", 35, 10, 2),
    segment("vload-load", 35, 10, 40, 10, 1.0, "F.Cu", 2),
    segment("vaux", 5, 18, 40, 18, 0.8, "F.Cu", 3),
]
parts += [
    footprint("J1", "VIN source", 5, 10, [("1", 0, 0, 1, "VIN")]),
    footprint("R1", "series interface", 21, 10, [("1", -1, 0, 1, "VIN"), ("2", 1, 0, 2, "VLOAD")]),
    footprint("J2", "VLOAD load", 40, 10, [("1", 0, 0, 2, "VLOAD")]),
    footprint("J3", "VAUX source", 5, 18, [("1", 0, 0, 3, "VAUX")]),
    footprint("J4", "VAUX load", 40, 18, [("1", 0, 0, 3, "VAUX")]),
    footprint("C1", "47u placed VIN decoupler", 12, 12, [("1", 0, -2, 1, "VIN"), ("2", 0, 0, 4, "GND")]),
    footprint("C2", "47u placed VLOAD decoupler", 38, 12, [("1", 0, -2, 2, "VLOAD"), ("2", 0, 0, 4, "GND")]),
    footprint("C3", "DNP VLOAD comparison site", 27, 12, [("1", 0, -2, 2, "VLOAD"), ("2", 0, 0, 4, "GND")]),
]
parts += [
    '(zone (net 2) (net_name "VLOAD") (layer "F.Cu") (uuid "' + uid("zone-vload") + '")'
    ' (polygon (pts (xy 36 8) (xy 42 8) (xy 42 11) (xy 36 11)))'
    ' (filled_polygon (pts (xy 36 8) (xy 42 8) (xy 42 11) (xy 36 11))))',
    '(zone (net 4) (net_name "GND") (layer "B.Cu") (uuid "' + uid("zone-gnd") + '")'
    ' (polygon (pts (xy 3 22) (xy 43 22) (xy 43 27) (xy 3 27)))'
    ' (filled_polygon (pts (xy 3 22) (xy 43 22) (xy 43 27) (xy 3 27))))',
]
for name, x1, y1, x2, y2 in [
    ("top", 2, 2, 44, 2), ("right", 44, 2, 44, 29),
    ("bottom", 44, 29, 2, 29), ("left", 2, 29, 2, 2),
]:
    parts.append(f'(gr_line (start {x1} {y1}) (end {x2} {y2}) (stroke (width 0.05) (type default)) (layer "Edge.Cuts") (uuid "{uid(name)}"))')
parts.append(")")
OUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
print(OUT)
