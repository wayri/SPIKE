# SPDX-License-Identifier: Apache-2.0
"""Original multi-terminal schematic symbol descriptors.

These drawings describe terminal identity and conventional appearance only.
They do not select a simulator model or claim standards conformance.
"""


def _terminal(ident, name, at, endpoint, direction):
    return {
        "id": ident,
        "name": name,
        "at": list(at),
        "leg_endpoint": list(endpoint),
        "direction": direction,
        "connection_indicator": True,
    }


def _line(a, b):
    return {"kind": "line", "points": [list(a), list(b)]}


def _polygon(points, *, fill=False):
    return {"kind": "polygon", "points": [list(point) for point in points], "fill": fill}


def _circle(center, radius):
    return {"kind": "circle", "center": list(center), "radius": radius}


def _descriptor(ident, name, family, bounds, terminals, primitives, note):
    return {
        "id": ident,
        "name": name,
        "family": family,
        "standard": "common-convention",
        "conformance": "unverified",
        "source_note": note,
        "grid": 10,
        "body_keepout": {"min": list(bounds[0]), "max": list(bounds[1])},
        "label_keepouts": [
            {"role": "reference", "min": [-30, -70], "max": [30, -55]},
            {"role": "value", "min": [-30, 55], "max": [30, 70]},
        ],
        "terminals": terminals,
        "primitives": primitives,
    }


def _mos(channel):
    p_channel = channel == "p"
    terminals = [
        _terminal("d", "D", (10, -50), (10, -30), "north"),
        _terminal("g", "G", (-50, 0), (-20, 0), "west"),
        _terminal("s", "S", (10, 50), (10, 30), "south"),
        _terminal("b", "B", (50, 0), (30, 0), "east"),
    ]
    # The bulk-junction arrow follows P-to-N doping: NMOS points from the
    # right-side P bulk toward the channel; PMOS points toward the N bulk.
    arrow = ((29, 0), (19, -6), (19, 6), (29, 0)) if p_channel else (
        (19, 0), (29, -6), (29, 6), (19, 0)
    )
    primitives = [
        _line((10, -50), (10, -30)),
        _line((-50, 0), (-20, 0)),
        _line((10, 30), (10, 50)),
        _line((30, 0), (50, 0)),
        _line((-20, 0), (-8, 0)),
        _line((-8, -25), (-8, 25)),
        _line((5, -25), (15, -25)),
        _line((5, -12), (15, -12)),
        _line((5, 12), (15, 12)),
        _line((5, 25), (15, 25)),
        _line((10, -30), (10, -25)),
        _line((10, 25), (10, 30)),
        _line((15, 0), (30, 0)),
        _polygon(arrow, fill=True),
    ]
    return _descriptor(
        f"mosfet.{channel}_channel.4_terminal",
        f"{'P' if p_channel else 'N'}-channel MOSFET, four terminal",
        "mosfet",
        ((-20, -30), (30, 30)),
        terminals,
        primitives,
        "Independent common-convention geometry. Ordered symbol terminals are D, G, S, B; this order is not a SPICE model mapping.",
    )


def _bjt(polarity):
    pnp = polarity == "pnp"
    terminals = [
        _terminal("c", "C", (10, -50), (10, -30), "north"),
        _terminal("b", "B", (-50, 0), (-20, 0), "west"),
        _terminal("e", "E", (10, 50), (10, 30), "south"),
        _terminal("sub", "Sub", (50, 0), (30, 0), "east"),
    ]
    arrow = ((14, 25), (5, 21), (11, 15), (14, 25)) if not pnp else (
        (4, 14), (13, 18), (7, 24), (4, 14)
    )
    primitives = [
        _line((10, -50), (10, -30)),
        _line((-50, 0), (-20, 0)),
        _line((10, 30), (10, 50)),
        _line((30, 0), (50, 0)),
        _line((-20, 0), (-5, 0)),
        _line((-5, -22), (-5, 22)),
        _line((-5, -10), (10, -25)),
        _line((10, -30), (10, -25)),
        _line((-5, 10), (10, 25)),
        _line((10, 25), (10, 30)),
        _line((20, -8), (20, 8)),
        _line((20, 0), (30, 0)),
        _polygon(arrow, fill=True),
    ]
    return _descriptor(
        f"bjt.{polarity}.4_terminal",
        f"{polarity.upper()} bipolar transistor with substrate",
        "bipolar_transistor",
        ((-20, -30), (30, 30)),
        terminals,
        primitives,
        "Independent common-convention geometry. Ordered symbol terminals are C, B, E, Sub; substrate is explicit and no compact-model mapping is implied.",
    )


def _jfet(channel):
    p_channel = channel == "p"
    terminals = [
        _terminal("d", "D", (10, -50), (10, -30), "north"),
        _terminal("g", "G", (-50, 0), (-20, 0), "west"),
        _terminal("s", "S", (10, 50), (10, 30), "south"),
    ]
    # N-channel arrow points into the channel; P-channel points out.
    arrow = ((10, 0), (0, -6), (0, 6), (10, 0)) if not p_channel else (
        (0, 0), (10, -6), (10, 6), (0, 0)
    )
    primitives = [
        _line((10, -50), (10, -30)),
        _line((-50, 0), (-20, 0)),
        _line((10, 30), (10, 50)),
        _line((10, -30), (10, 30)),
        _line((-20, 0), (10, 0)),
        _polygon(arrow, fill=True),
    ]
    return _descriptor(
        f"jfet.{channel}_channel.3_terminal",
        f"{'P' if p_channel else 'N'}-channel JFET",
        "jfet",
        ((-20, -30), (30, 30)),
        terminals,
        primitives,
        "Independent common-convention geometry. Ordered symbol terminals are D, G, S; arrow direction distinguishes channel convention only.",
    )


def _dual_gate_mos():
    terminals = [
        _terminal("d", "D", (10, -50), (10, -30), "north"),
        _terminal("g1", "G1", (-50, -10), (-20, -10), "west"),
        _terminal("g2", "G2", (-50, 10), (-20, 10), "west"),
        _terminal("s", "S", (10, 50), (10, 30), "south"),
        _terminal("b", "B", (50, 0), (30, 0), "east"),
    ]
    primitives = [
        _line((10, -50), (10, -30)), _line((-50, -10), (-20, -10)),
        _line((-50, 10), (-20, 10)), _line((10, 30), (10, 50)),
        _line((30, 0), (50, 0)), _line((-20, -10), (-8, -10)),
        _line((-20, 10), (-8, 10)), _line((-8, -25), (-8, 25)),
        _line((8, -25), (8, 25)), _line((10, -30), (10, -25)),
        _line((10, 25), (10, 30)), _line((8, 0), (30, 0)),
        _polygon(((18, 0), (28, -6), (28, 6), (18, 0)), fill=True),
    ]
    return _descriptor(
        "mosfet.dual_gate.5_terminal", "Dual-gate MOSFET, five terminal", "mosfet",
        ((-20, -30), (30, 30)), terminals, primitives,
        "Schematic-only dual-gate interface. Ordered terminals are D, G1, G2, S, B; no available simulator model or device physics is claimed.",
    )


def _kelvin_resistor():
    terminals = [
        _terminal("fp", "FP", (-50, 0), (-20, 0), "west"),
        _terminal("fn", "FN", (50, 0), (20, 0), "east"),
        _terminal("sp", "SP", (-10, -40), (-10, -10), "north"),
        _terminal("sn", "SN", (10, 40), (10, 10), "south"),
    ]
    primitives = [
        _line((-50, 0), (-20, 0)), _line((20, 0), (50, 0)),
        _line((-10, -40), (-10, -10)), _line((10, 10), (10, 40)),
        _polygon(((-20, -10), (20, -10), (20, 10), (-20, 10), (-20, -10))),
        _line((-10, -10), (-20, 0)), _line((10, 10), (20, 0)),
    ]
    return _descriptor(
        "resistor.kelvin.4_terminal", "Kelvin resistor, four terminal", "kelvin_resistor",
        ((-20, -10), (20, 10)), terminals, primitives,
        "Independent four-terminal drawing. Ordered terminals are FP, FN, SP, SN; force and sense connectivity must be supplied by an explicit model.",
    )


def _substrate_resistor():
    terminals = [
        _terminal("1", "1", (-50, 0), (-20, 0), "west"),
        _terminal("2", "2", (50, 0), (20, 0), "east"),
        _terminal("sub", "SUB", (0, 50), (0, 20), "south"),
    ]
    primitives = [
        _line((-50, 0), (-20, 0)), _line((20, 0), (50, 0)),
        {"kind": "polyline", "points": [[-20, 0], [-15, -10], [-5, 10], [5, -10], [15, 10], [20, 0]]},
        _line((0, 50), (0, 20)), _line((-12, 20), (12, 20)),
    ]
    return _descriptor(
        "resistor.substrate.3_terminal", "Substrate resistor, three terminal", "substrate_resistor",
        ((-20, -20), (20, 20)), terminals, primitives,
        "Explicit three-terminal model interface with ordered terminals 1, 2, SUB. It is not an ordinary two-terminal resistor symbol or model claim.",
    )


def _feedthrough_capacitor():
    terminals = [
        _terminal("in", "IN", (-50, 0), (-20, 0), "west"),
        _terminal("out", "OUT", (50, 0), (20, 0), "east"),
        _terminal("gnd", "GND", (0, 50), (0, 20), "south"),
    ]
    primitives = [
        _line((-50, 0), (-20, 0)), _line((20, 0), (50, 0)), _line((-20, 0), (20, 0)),
        _line((0, 0), (0, 5)), _line((-12, 5), (12, 5)),
        _line((-12, 12), (12, 12)), _line((0, 12), (0, 20)), _line((0, 20), (0, 50)),
    ]
    return _descriptor(
        "capacitor.feedthrough.3_terminal", "Feedthrough capacitor with explicit ground", "feedthrough_capacitor",
        ((-20, -20), (20, 20)), terminals, primitives,
        "Three-terminal feedthrough drawing with ordered terminals IN, OUT, GND. GND is explicit; geometry does not create a global reference net.",
    )


def _coupled_inductor():
    terminals = [
        _terminal("w1_dot", "1+", (-10, -50), (-10, -30), "north"),
        _terminal("w1_return", "1-", (-10, 50), (-10, 30), "south"),
        _terminal("w2_dot", "2+", (10, -50), (10, -30), "north"),
        _terminal("w2_return", "2-", (10, 50), (10, 30), "south"),
    ]
    left = {"kind": "polyline", "points": [[-10, -30], [-20, -20], [-10, -10], [-20, 0], [-10, 10], [-20, 20], [-10, 30]]}
    right = {"kind": "polyline", "points": [[10, -30], [20, -20], [10, -10], [20, 0], [10, 10], [20, 20], [10, 30]]}
    primitives = [
        _line((-10, -50), (-10, -30)), _line((-10, 30), (-10, 50)),
        _line((10, -50), (10, -30)), _line((10, 30), (10, 50)),
        left, right, _circle((-25, -25), 3), _circle((25, -25), 3),
    ]
    return _descriptor(
        "inductor.coupled.2_winding", "Coupled inductor, two winding", "coupled_inductor",
        ((-30, -30), (30, 30)), terminals, primitives,
        "Two-winding schematic drawing with dot-polarity terminals ordered 1+, 1-, 2+, 2-. It does not claim core, coupling, or saturation physics.",
    )


def symbols():
    """Return fresh v1 symbol descriptors in stable terminal-order groups."""
    return [
        _mos("n"), _mos("p"), _bjt("npn"), _bjt("pnp"),
        _jfet("n"), _jfet("p"), _dual_gate_mos(), _kelvin_resistor(),
        _substrate_resistor(), _feedthrough_capacitor(), _coupled_inductor(),
    ]
