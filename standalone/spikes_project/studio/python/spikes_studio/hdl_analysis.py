# SPDX-License-Identifier: Apache-2.0
"""Headless admission and measurements for HDL reports and VCD timing data."""
from __future__ import annotations

import csv
import io
import json


MAX_DISPLAY_TRANSITIONS = 5000


def capability_inventory(tool_paths):
    """Describe only workflows actually connected to the current IDE backend."""
    present = lambda name: bool(tool_paths.get(name))
    return [
        {"language": "Verilog/SystemVerilog", "operation": "syntax/check",
         "available": present("iverilog"), "tool": "iverilog",
         "detail": "Icarus Verilog -g2012 frontend"},
        {"language": "Verilog/SystemVerilog", "operation": "testbench/VCD",
         "available": present("iverilog") and present("vvp"), "tool": "iverilog + vvp",
         "detail": "Bounded local testbench execution; VCD only when the testbench writes one"},
        {"language": "Verilog", "operation": "synthesis metrics",
         "available": present("yosys"), "tool": "yosys",
         "detail": "Actual Yosys JSON hierarchy, ports, and cell counts"},
        {"language": "VHDL", "operation": "syntax/check",
         "available": present("ghdl"), "tool": "ghdl",
         "detail": "GHDL VHDL-2008 analysis"},
        {"language": "VHDL", "operation": "testbench/VCD",
         "available": present("ghdl"), "tool": "ghdl",
         "detail": "GHDL VHDL-2008 elaborate/run; 1 ms model-time and 15 s wall-time limits"},
        {"language": "HDL", "operation": "static timing analysis",
         "available": False, "tool": "sta" if present("sta") else None,
         "detail": "Requires an explicit clock constraint and Liberty library; not implemented"},
    ]


def _port_width(bits):
    return len(bits) if isinstance(bits, list) else 0


def summarize_netlist(netlist):
    """Return hierarchy, port and cell totals from an actual Yosys JSON netlist."""
    if not isinstance(netlist, dict) or not isinstance(netlist.get("modules"), dict):
        raise ValueError("Synthesis report does not contain a Yosys modules object")
    modules = {}
    totals = {}
    for name, raw in sorted(netlist["modules"].items()):
        if not isinstance(raw, dict):
            continue
        ports = []
        for port_name, port in sorted(raw.get("ports", {}).items()):
            ports.append({"name": port_name, "direction": port.get("direction", "unknown"),
                          "width": _port_width(port.get("bits"))})
        cells = {}
        children = []
        for cell_name, cell in sorted(raw.get("cells", {}).items()):
            cell_type = str(cell.get("type", "<unknown>"))
            cells[cell_type] = cells.get(cell_type, 0) + 1
            totals[cell_type] = totals.get(cell_type, 0) + 1
            if cell_type in netlist["modules"]:
                children.append({"instance": cell_name, "module": cell_type})
        modules[name] = {"ports": ports, "cell_types": cells, "children": children,
                         "cell_count": sum(cells.values())}
    return {"modules": modules, "cell_type_totals": dict(sorted(totals.items())),
            "module_count": len(modules), "cell_count": sum(totals.values())}


def value_at(transitions, time_s):
    value = None
    for transition_time, transition_value in transitions:
        if transition_time > time_s:
            break
        value = transition_value
    return value


def bounded_transitions(transitions, limit=MAX_DISPLAY_TRANSITIONS):
    """Bound rendering cost while retaining endpoints; measurements use originals."""
    count = len(transitions)
    if count <= limit:
        return list(transitions)
    if limit < 2:
        raise ValueError("Transition display limit must be at least two")
    indexes = [round(i * (count - 1) / (limit - 1)) for i in range(limit)]
    return [transitions[index] for index in indexes]


def signal_metrics(signal, end_time_s):
    """Compute edge, complete-cycle and duty metrics from original transitions."""
    transitions = signal.get("transitions", [])
    width = int(signal.get("width", 1))
    metrics = {"transition_count": len(transitions), "rising_edges": 0,
               "falling_edges": 0, "cycles": 0, "period_s": None,
               "frequency_hz": None, "duty_cycle": None}
    if width != 1:
        return metrics
    rising, falling = [], []
    previous = None
    normalized = [(float(t), v) for t, v in transitions]
    for time_s, value in normalized:
        if previous == "0" and value == "1": rising.append(time_s)
        elif previous == "1" and value == "0": falling.append(time_s)
        previous = value if value in ("0", "1") else None
    metrics["rising_edges"], metrics["falling_edges"] = len(rising), len(falling)
    periods = [b - a for a, b in zip(rising, rising[1:]) if b > a]
    if periods:
        period = sum(periods) / len(periods)
        metrics.update(cycles=len(periods), period_s=period,
                       frequency_hz=(1.0 / period if period else None))
    high, known_duration = 0.0, 0.0
    for (start, value), (stop, _) in zip(normalized, normalized[1:]):
        duration = max(0.0, stop - start)
        if value in ("0", "1"):
            known_duration += duration
            if value == "1": high += duration
    if normalized and normalized[-1][0] < end_time_s and normalized[-1][1] in ("0", "1"):
        duration = end_time_s - normalized[-1][0]
        known_duration += duration
        if normalized[-1][1] == "1": high += duration
    if known_duration:
        metrics["duty_cycle"] = high / known_duration
    return metrics


def timing_measurements(data, names, cursor_a_s=0.0, cursor_b_s=None):
    signals = data.get("signals", {})
    cursor_b_s = data.get("end_time_s", 0.0) if cursor_b_s is None else cursor_b_s
    rows = []
    for name in names:
        signal = signals.get(name)
        if signal is None:
            continue
        row = {"signal": name, "width": signal.get("width", 1),
               "cursor_a_s": cursor_a_s, "value_a": value_at(signal.get("transitions", []), cursor_a_s),
               "cursor_b_s": cursor_b_s, "value_b": value_at(signal.get("transitions", []), cursor_b_s),
               "delta_s": abs(cursor_b_s - cursor_a_s)}
        row.update(signal_metrics(signal, data.get("end_time_s", 0.0)))
        rows.append(row)
    return rows


def serialize_measurements(rows, format_name):
    if format_name.lower() == "json":
        return json.dumps(rows, indent=2, allow_nan=False) + "\n"
    if format_name.lower() != "csv":
        raise ValueError("Measurement export format must be JSON or CSV")
    output = io.StringIO(newline="")
    fields = list(rows[0]) if rows else ["signal", "width", "cursor_a_s", "value_a",
                                        "cursor_b_s", "value_b", "delta_s"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader(); writer.writerows(rows)
    return output.getvalue()
