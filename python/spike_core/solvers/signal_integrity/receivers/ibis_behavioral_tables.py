# SPDX-License-Identifier: Apache-2.0
"""Original bounded IBIS table reconstruction and generated-circuit serialization.

See the independently authored IBIS behavioral derivation for conventions and
acceptance screens. This module emits data expressions, never source directives.
"""
from __future__ import annotations

from bisect import bisect_right
import math

from .si_ibis import parse_ibis
from .ibis_behavioral import UnsupportedIBIS, exact_fields, finite

CORNER = {"typ": 0, "min": 1, "max": 2}
TABLES = ("pullup", "pulldown", "gnd clamp", "power clamp")
REFERENCES = ("pullup_reference", "pulldown_reference", "gnd_clamp_reference", "power_clamp_reference")


def selected(values, corner, label):
    index = CORNER[corner]
    if not isinstance(values, list) or index >= len(values) or values[index] is None:
        raise UnsupportedIBIS(f"{label} has no explicit {corner} value.")
    return finite(values[index], label, -1e100)


def endpoint(binding, role):
    exact_fields(binding, {"text", "name", "model", "component", "pin", "corner", "capacitance_corner", "package_corner"}, role)
    for key in ("name", "model", "component", "pin"):
        if not isinstance(binding[key], str) or not binding[key] or len(binding[key]) > 512:
            raise UnsupportedIBIS(f"{role}.{key} must be a nonempty bounded string.")
    for key in ("corner", "capacitance_corner", "package_corner"):
        if not isinstance(binding[key], str) or binding[key] not in CORNER:
            raise UnsupportedIBIS(f"{role}.{key} must be typ, min or max.")
    inventory = parse_ibis(binding["text"], binding["name"])
    allowed = {name.replace("_", " ") for name in REFERENCES} | {"revision history"}
    unknown = set(inventory["unsupported_keywords"]) - allowed
    if unknown:
        raise UnsupportedIBIS(f"Unsupported IBIS primitives: {sorted(unknown)}.")
    model = inventory["models"].get(binding["model"])
    if model is None:
        raise UnsupportedIBIS("Selected model is absent.")
    types = {"output", "i/o", "3-state"} if role == "driver" else {"input", "i/o"}
    if model["model_type"].lower() not in types:
        raise UnsupportedIBIS(f"Unsupported {role} model type.")
    component = inventory["components"].get(binding["component"])
    if component is None:
        raise UnsupportedIBIS("Selected component is absent.")
    pins = [pin for pin in component["pins"] if pin["pin"] == binding["pin"]]
    if len(pins) != 1:
        raise UnsupportedIBIS("Selected pin must resolve exactly once.")
    pin = pins[0]
    candidates = [item["model"] for item in inventory["selectors"].get(pin["model"], [])] or [pin["model"]]
    if binding["model"] not in candidates:
        raise UnsupportedIBIS("Selected model does not belong to the selected pin.")
    if set(component["package"]) - {"r_pkg", "l_pkg", "c_pkg"}:
        raise UnsupportedIBIS("Unknown package parameter.")
    package = []
    for index, key in enumerate(("r_pkg", "l_pkg", "c_pkg")):
        value = pin["rlc"][index]
        if value is None:
            value = selected(component["package"].get(key), binding["package_corner"], key)
        package.append(finite(value, key))
    params = model["parameters"]
    supply = finite(selected(params.get("voltage_range"), binding["corner"], "Voltage Range"), "supply", 0, 1e6, positive=True)
    capacitance = finite(selected(params.get("c_comp"), binding["capacitance_corner"], "C_comp"), "C_comp", 0, 1)
    references = [selected(params.get(key, [default] * 3), binding["corner"], key)
                  for key, default in zip(REFERENCES, (supply, 0, 0, supply))]
    tables = {}
    lower, upper = -1e100, 1e100
    for name, reference in zip(TABLES, references):
        rows = model["tables"].get(name)
        if rows is None:
            if role == "driver" and name in {"pullup", "pulldown"}:
                raise UnsupportedIBIS(f"Driver requires {name} table.")
            continue
        if len(rows) > 2048:
            raise UnsupportedIBIS("I/V table exceeds 2048 rows.")
        table = [(row[0], selected(row[1:], binding["corner"], name)) for row in rows]
        tables[name] = table
        bounds = ((reference - table[-1][0], reference - table[0][0])
                  if name in {"pullup", "power clamp"} else (reference + table[0][0], reference + table[-1][0]))
        lower, upper = max(lower, bounds[0]), min(upper, bounds[1])
    if role == "receiver" and any(name in tables for name in ("pullup", "pulldown")):
        raise UnsupportedIBIS("Receiver output-drive tables are not admitted in the passive Input subset.")
    if not lower < upper:
        raise UnsupportedIBIS("I/V tables have no common die-voltage domain.")
    provenance = {key: value for key, value in binding.items() if key != "text"}
    provenance.update(source_sha256=inventory["sha256"], package_rlc=package, capacitance_f=capacitance,
                      supply_v=supply, references_v=dict(zip(TABLES, references)), die_voltage_domain_v=[lower, upper],
                      absent_clamps=[name for name in ("gnd clamp", "power clamp") if name not in tables])
    return {"model": model, "corner": binding["corner"], "capacitance": capacitance, "package": package,
            "supply": supply, "references": dict(zip(TABLES, references)), "tables": tables,
            "provenance": provenance, "domain": (lower, upper)}


def interpolate(table, x):
    if not table[0][0] <= x <= table[-1][0]:
        raise UnsupportedIBIS("Waveform or fixture evaluation exceeds its source table domain.")
    index = min(max(bisect_right([row[0] for row in table], x) - 1, 0), len(table) - 2)
    a, b = table[index:index + 2]
    return a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0])


def currents(endpoint, voltage):
    output = []
    for name in TABLES:
        reference = endpoint["references"][name]
        axis = reference - voltage if name in {"pullup", "power clamp"} else voltage - reference
        output.append(interpolate(endpoint["tables"][name], axis) if name in endpoint["tables"] else 0.0)
    return output


def fixture(endpoint, waveform):
    fields = waveform["fixture"]
    allowed = {"r_fixture", "v_fixture", "v_fixture_min", "v_fixture_max", "c_fixture", "l_fixture", "r_dut", "l_dut", "c_dut"}
    if set(fields) - allowed:
        raise UnsupportedIBIS(f"Unsupported waveform fixture parameters: {sorted(set(fields) - allowed)}.")
    def scalar(name, default=None):
        values = fields.get(name, [default])
        if len(values) != 1 or values[0] is None:
            raise UnsupportedIBIS(f"Fixture {name} requires one numeric value.")
        return finite(values[0], name, -1e100)
    resistance = finite(scalar("r_fixture"), "R_fixture", 0, 1e12, positive=True)
    voltage = scalar({"typ": "v_fixture", "min": "v_fixture_min", "max": "v_fixture_max"}[endpoint["corner"]],
                     scalar("v_fixture"))
    for name in ("c_fixture", "l_fixture", "r_dut", "l_dut", "c_dut"):
        if scalar(name, 0) != 0:
            raise UnsupportedIBIS("Only purely resistive fixture loads and zero DUT fixture parasitics are admitted.")
    rows = waveform["values"]
    if not 4 <= len(rows) <= 2048:
        raise UnsupportedIBIS("Each waveform requires 4..2048 plateau-bearing samples.")
    points = [(row[0], selected(row[1:], endpoint["corner"], "waveform")) for row in rows]
    if points[0][0] != 0 or any(b[0] <= a[0] for a, b in zip(points, points[1:])):
        raise UnsupportedIBIS("Waveform times must start at zero and increase strictly.")
    derivative = [0.0]
    for a, b, c in zip(points, points[1:], points[2:]):
        left, right = b[0] - a[0], c[0] - b[0]
        derivative.append(-right * a[1] / (left * (left + right)) +
                          (right - left) * b[1] / (left * right) + left * c[1] / (right * (left + right)))
    derivative.append(0.0)
    for a, b in (points[:2], points[-2:]):
        terms = currents(endpoint, a[1])
        scale = sum(abs(value) for value in terms) + abs((a[1] - voltage) / resistance)
        if abs(endpoint["capacitance"] * (b[1] - a[1]) / (b[0] - a[0])) > 1e-6 + 1e-3 * scale:
            raise UnsupportedIBIS("Fixture endpoints lack a static capacitance-current plateau.")
    return {"points": points, "derivative": list(zip([p[0] for p in points], derivative)),
            "resistance": resistance, "voltage": voltage}


def _terms(endpoint, load, time, derivative=None):
    voltage = interpolate(load["points"], time)
    u, d, g, p = currents(endpoint, voltage)
    capacitance = endpoint["capacitance"] * (interpolate(load["derivative"], time) if derivative is None else derivative)
    resistor = (voltage - load["voltage"]) / load["resistance"]
    return u, d, capacitance, g, p, resistor


def calibrate(endpoint, indices):
    waveforms = endpoint["model"]["waveforms"]
    if any(index >= len(waveforms) for index in indices):
        raise UnsupportedIBIS("Waveform index is absent.")
    if waveforms[indices[0]]["kind"] != waveforms[indices[1]]["kind"]:
        raise UnsupportedIBIS("Calibration pair must have the same edge kind.")
    loads = [fixture(endpoint, waveforms[index]) for index in indices]
    if (loads[0]["resistance"], loads[0]["voltage"]) == (loads[1]["resistance"], loads[1]["voltage"]):
        raise UnsupportedIBIS("Calibration requires two distinct resistive fixtures.")
    if loads[0]["points"][-1][0] != loads[1]["points"][-1][0]:
        raise UnsupportedIBIS("Fixture time supports must agree without alignment or shifting.")
    times = sorted({point[0] for load in loads for point in load["points"]})
    weights, max_condition, max_inverse, max_weight = [], 0.0, 0.0, 0.0
    for time in times:
        rows = [_terms(endpoint, load, time) for load in loads]
        a, b = rows[0][:2]
        c, d = rows[1][:2]
        determinant = a * d - b * c
        if determinant == 0:
            raise UnsupportedIBIS("Two-fixture reconstruction is singular.")
        norm = max(abs(a) + abs(b), abs(c) + abs(d))
        inverse_norm = max(abs(d) + abs(b), abs(c) + abs(a)) / abs(determinant)
        condition = norm * inverse_norm
        if not math.isfinite(condition) or condition > 1e6 or inverse_norm * 1e-9 > 1e-3:
            raise UnsupportedIBIS("Two-fixture reconstruction is ill-conditioned or too weak in absolute current units.")
        rhs = [-sum(row[2:]) for row in rows]
        ku, kd = (rhs[0] * d - b * rhs[1]) / determinant, (a * rhs[1] - rhs[0] * c) / determinant
        residual = max(abs(a * ku + b * kd - rhs[0]), abs(c * ku + d * kd - rhs[1]))
        if not all(math.isfinite(value) for value in (ku, kd)) or residual > 1e-12 + 1e-10 * (norm * max(abs(ku), abs(kd)) + max(map(abs, rhs))):
            raise UnsupportedIBIS("Two-fixture solve failed its backward residual screen.")
        max_condition = max(max_condition, condition)
        max_inverse = max(max_inverse, inverse_norm)
        max_weight = max(max_weight, abs(ku), abs(kd))
        weights.append((time, ku, kd))
    max_replay = replay(endpoint, loads, weights)
    return {"weights": weights, "loads": loads, "indices": indices, "condition_inf_max": max_condition,
            "inverse_gain_inf_per_a_max": max_inverse, "coefficient_abs_max": max_weight,
            "replay_current_residual_a_max": max_replay, "kind": waveforms[indices[0]]["kind"]}


def replay(endpoint, loads, weights):
    maximum = 0.0
    ku = [(point[0], point[1]) for point in weights]
    kd = [(point[0], point[2]) for point in weights]
    for load in loads:
        grid = sorted({point[0] for point in weights} | {point[0] for point in load["points"]})
        samples = [(time, None) for time in grid]
        for left, right in zip(grid, grid[1:]):
            middle = (left + right) / 2
            secant = (interpolate(load["points"], right) - interpolate(load["points"], left)) / (right - left)
            samples.extend(((middle, None), (middle, secant)))
        for time, derivative in samples:
            u, d, cap, g, p, resistor = _terms(endpoint, load, time, derivative)
            terms = [u * interpolate(ku, time), d * interpolate(kd, time), cap, g, p, resistor]
            if derivative is not None:
                defect = abs(endpoint["capacitance"] * (interpolate(load["derivative"], time) - derivative))
                if defect > 1e-6 + 1e-3 * sum(abs(value) for value in terms):
                    raise UnsupportedIBIS("Fixture midpoint capacitance derivative-defect screen failed.")
            residual = abs(sum(terms))
            if residual > 1e-6 + 1e-3 * sum(abs(value) for value in terms):
                raise UnsupportedIBIS("Fixture forward KCL replay or PWL derivative screen failed.")
            maximum = max(maximum, residual)
    return maximum


def _format(value):
    return format(value, ".17g")


def expression(points, axis):
    """Bounded constant continuation is for Newton iterations; outputs are audited."""
    parts = []
    for a, b in zip(points, points[1:]):
        slope = (b[1] - a[1]) / (b[0] - a[0])
        parts.append(f"({axis}<={_format(b[0])}?({_format(a[1])}+({_format(slope)})*({axis}-({_format(a[0])}))):")
    return f"({axis}<={_format(points[0][0])}?({_format(points[0][1])}):" + "".join(parts) + f"({_format(points[-1][1])})" + ")" * (len(parts) + 1)


def _package(lines, endpoint, role):
    resistance, inductance, capacitance = endpoint["package"]
    nodes = [f"{role}_pad", f"{role}_pkg", f"{role}_die"]
    lines.append(f"R{role}_package {nodes[0]} {nodes[1]} {_format(resistance)}" if resistance else f"V{role}_rshort {nodes[0]} {nodes[1]} 0")
    lines.append(f"L{role}_package {nodes[1]} {nodes[2]} {_format(inductance)}" if inductance else f"V{role}_lshort {nodes[1]} {nodes[2]} 0")
    if capacitance:
        lines.append(f"C{role}_package {nodes[0]} 0 {_format(capacitance)}")
    if endpoint["capacitance"]:
        lines.append(f"C{role}_comp {nodes[2]} 0 {_format(endpoint['capacitance'])}")


def generate_netlist(driver, receiver, request, step, stop):
    groups = {kind: [i for i, waveform in enumerate(driver["model"]["waveforms"]) if waveform["kind"] == kind]
              for kind in ("rising waveform", "falling waveform")}
    if any(len(indices) != 2 for indices in groups.values()):
        raise UnsupportedIBIS("This bounded compiler requires exactly two rising and two falling fixture waveforms.")
    calibrations = {kind: calibrate(driver, indices) for kind, indices in groups.items()}
    rising, falling = calibrations["rising waveform"], calibrations["falling waveform"]
    low, high = rising["weights"][0][1:], rising["weights"][-1][1:]
    for value, reference in ((falling["weights"][0][1:], high), (falling["weights"][-1][1:], low)):
        if any(abs(a - b) > 1e-3 + 1e-3 * max(abs(a), abs(b)) for a, b in zip(value, reference)):
            raise UnsupportedIBIS("Rising and falling static endpoint weights disagree.")
    falling["weights"][0] = (falling["weights"][0][0], *high)
    falling["weights"][-1] = (falling["weights"][-1][0], *low)
    replay(driver, falling["loads"], falling["weights"])
    initial = request["stimulus"]["initial_state"]
    if initial == "z" and driver["model"]["model_type"].lower() not in {"3-state", "i/o"}:
        raise UnsupportedIBIS("Static z requires a 3-state or I/O driver.")
    weights = [(0.0, *((0.0, 0.0) if initial == "z" else low if initial == "low" else high))]
    end = 0.0
    for transition in request["stimulus"]["transitions"]:
        kind = "rising waveform" if transition["state"] == "high" else "falling waveform"
        calibration = calibrations[kind]
        if set(transition["waveform_indices"]) != set(calibration["indices"]):
            raise UnsupportedIBIS("Transition must select its two matching edge waveform indices.")
        start = transition["time_s"]
        edge_end = start + calibration["weights"][-1][0]
        if start < end or edge_end > stop:
            raise UnsupportedIBIS("Edges cannot overlap or extend beyond stop_time_s.")
        shifted = [(start + point[0], *point[1:]) for point in calibration["weights"]]
        if shifted[0][0] == weights[-1][0]:
            weights[-1] = shifted[0]
            shifted = shifted[1:]
        weights.extend(shifted)
        end = edge_end
    if weights[-1][0] < stop:
        weights.append((stop, *weights[-1][1:]))
    if len(weights) > 20000:
        raise UnsupportedIBIS("Expanded switching schedule exceeds 20000 samples.")
    lines = ["SPIKE original experimental classic IBIS behavioral circuit", ".option filetype=ascii", ".option plotwinsize=0"]
    for role, endpoint_data in (("driver", driver), ("receiver", receiver)):
        _package(lines, endpoint_data, role)
        for name in TABLES:
            if name not in endpoint_data["tables"]:
                continue
            reference = _format(endpoint_data["references"][name])
            axis = f"({reference}-v({role}_die))" if name in {"pullup", "power clamp"} else f"(v({role}_die)-({reference}))"
            current = expression(endpoint_data["tables"][name], axis)
            if name in {"pullup", "pulldown"}:
                column = 1 if name == "pullup" else 2
                current = f"v(weight_{column})*({current})"
            lines.append(f"B{role}_{name.replace(' ', '_')} {role}_die 0 I={current}")
    for column in (1, 2):
        pairs = " ".join(f"{_format(point[0])} {_format(point[column])}" for point in weights)
        lines.append(f"Vweight_{column} weight_{column} 0 PWL({pairs})")
    lines.append("Vdriver_probe driver_pad channel_in 0")
    link = request["interconnect"]
    if link["kind"] == "lossless_tline":
        lines.append(f"Tchannel channel_in 0 receiver_pad 0 Z0={_format(link['impedance_ohm'])} TD={_format(link['delay_s'])}")
    else:
        lines.append(f"Rchannel channel_in receiver_pad {_format(link['resistance_ohm'])}")
    lines.extend([".save v(driver_pad) v(receiver_pad) v(driver_die) v(receiver_die) i(vdriver_probe)",
                  f".tran {_format(step)} {_format(stop)} 0 {_format(step)}", ".end", ""])
    netlist = "\n".join(lines)
    if len(netlist) > 2_000_000:
        raise UnsupportedIBIS("Generated netlist exceeds 2 MB.")
    evidence = [{key: value for key, value in calibration.items() if key not in {"loads", "weights"}}
                for calibration in calibrations.values()]
    return netlist, {"edges": evidence, "low_weights": list(low), "high_weights": list(high),
                     "continuation": "constant endpoint continuation for Newton iteration; mandatory die-voltage domain audit",
                     "model_status": "experimental", "external_fixture_replay_executed": False}
