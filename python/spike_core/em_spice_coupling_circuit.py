# SPDX-License-Identifier: Apache-2.0
"""Strict linear AC circuit admission and exact frequency-domain MNA assembly.

This is a bounded co-simulation adapter, not a new general SPICE parser.
Numerical solution belongs to the release-owned SPICE operating-point engine.
"""
import math
import re

import numpy as np

from .em_network_ac import _pair

MAX_ELEMENTS = 128
MAX_NODES = 64
_NAME = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_PASSIVE = {"resistor", "capacitor", "inductor"}
_SOURCES = {"voltage_source", "current_source"}


def require(condition, message):
    if not condition:
        raise ValueError("EM_SPICE_COUPLING: " + message)


def admit_circuit(circuit, bindings, ports):
    require(isinstance(circuit, dict) and set(circuit) == {"ground_node", "elements"},
            "Circuit requires only ground_node and elements")
    ground = circuit["ground_node"]
    require(isinstance(ground, str) and _NAME.fullmatch(ground), "Invalid ground node")
    elements = circuit["elements"]
    require(isinstance(elements, list) and 1 <= len(elements) <= MAX_ELEMENTS,
            "Provide 1..128 typed linear circuit elements")
    names, nodes = set(), {ground}
    for element in elements:
        require(isinstance(element, dict), "Circuit elements must be objects")
        kind = element.get("type")
        require(kind in _PASSIVE | _SOURCES, "Only linear RLC and independent sources are supported")
        required = {"id", "type", "positive_node", "negative_node",
                    "value" if kind in _PASSIVE else "phasor"}
        require(set(element) == required, "Exact typed element fields required; no raw source/model text")
        for key in ("id", "positive_node", "negative_node"):
            require(isinstance(element[key], str) and _NAME.fullmatch(element[key]),
                    "Element and node IDs must be bounded safe identifiers")
        require(element["id"].casefold() not in names, "Duplicate element ID")
        names.add(element["id"].casefold())
        p, n = element["positive_node"], element["negative_node"]
        require(p != n, "An element requires distinct terminals")
        nodes.update((p, n))
        if kind in _PASSIVE:
            value = element["value"]
            require(type(value) in (int, float) and math.isfinite(value) and 1e-18 <= value <= 1e18,
                    "RLC SI values must be finite and within 1e-18..1e18")
        else:
            _pair(element["phasor"])
    require(len(nodes) <= MAX_NODES + 1, "Circuit exceeds 64 non-ground nodes")
    require(len({node.casefold() for node in nodes}) == len(nodes),
            "Node names must not differ only by case")
    require(any(ground in (e["positive_node"], e["negative_node"]) for e in elements),
            "Ground must be present in the supplied circuit")
    require(isinstance(bindings, dict) and set(bindings) == set(ports),
            "Every EM port requires an explicit circuit binding")
    terminal_pairs = set()
    for port in ports:
        item = bindings[port]
        require(isinstance(item, dict) and set(item) == {"positive_node", "negative_node", "reference_plane"},
                "Port requires exactly positive_node, negative_node and reference_plane")
        require(item["positive_node"] in nodes and item["negative_node"] in nodes
                and item["positive_node"] != item["negative_node"],
                "Port terminals must be distinct existing circuit nodes")
        label = item["reference_plane"]
        require(isinstance(label, str) and label.strip() and len(label) <= 128
                and not any(c in label for c in "\r\n\0"), "Explicit bounded reference plane required")
        pair = frozenset((item["positive_node"], item["negative_node"]))
        require(pair not in terminal_pairs, "Duplicate or reversed duplicate EM terminal pair")
        terminal_pairs.add(pair)
    return sorted(nodes - {ground})


def incidence(nodes, ground, positive, negative):
    result = np.zeros(len(nodes))
    if positive != ground:
        result[nodes.index(positive)] += 1
    if negative != ground:
        result[nodes.index(negative)] -= 1
    return result


def admittance(element, frequency):
    kind, value = element["type"], element["value"]
    if kind == "resistor":
        return 1 / value
    omega = 2 * math.pi * frequency
    return 1j * omega * value if kind == "capacitor" else 1 / (1j * omega * value)


def assemble(circuit, nodes, bindings, ports, frequency, s, z0):
    """Unknowns: node V, independent-voltage-source A, q=sqrt(Z0)*a in V.

    KCL includes EM current B*(I-S)*q/Z0. The EM terminal relation is
    B.T*v=(I+S)*q. No S-to-Y/Z inversion or fictitious termination occurs.
    """
    elements, ground = circuit["elements"], circuit["ground_node"]
    voltage_sources = [e for e in elements if e["type"] == "voltage_source"]
    n, m, p = len(nodes), len(voltage_sources), len(ports)
    size = n + m + p
    matrix, rhs = np.zeros((size, size), complex), np.zeros(size, complex)
    for element in elements:
        branch = incidence(nodes, ground, element["positive_node"], element["negative_node"])
        kind = element["type"]
        if kind in _PASSIVE:
            matrix[:n, :n] += admittance(element, frequency) * np.outer(branch, branch)
        elif kind == "current_source":
            rhs[:n] -= branch * _pair(element["phasor"])
        else:
            index = n + voltage_sources.index(element)
            matrix[:n, index] = branch
            matrix[index, :n] = branch
            rhs[index] = _pair(element["phasor"])
    port_incidence = np.column_stack([
        incidence(nodes, ground, bindings[port]["positive_node"], bindings[port]["negative_node"])
        for port in ports])
    matrix[:n, n+m:] = port_incidence @ (np.eye(p) - s) / z0
    matrix[n+m:, :n] = port_incidence.T
    matrix[n+m:, n+m:] = -(np.eye(p) + s)
    require(np.all(np.isfinite(matrix)) and np.all(np.isfinite(rhs)), "Nonfinite AC assembly")
    return matrix, rhs, voltage_sources, port_incidence


def lower_real_block(matrix, rhs):
    """Encode the dimensionless SI-number real block as controlled-source KCL.

    Each row is divided by its maximum coefficient magnitude, preserving its
    solution. Node xk represents a numerical unknown, NOT a physical circuit
    terminal; operating-point artificial powers are never physical outputs.
    """
    real = np.block([[matrix.real, -matrix.imag], [matrix.imag, matrix.real]])
    vector = np.concatenate((rhs.real, rhs.imag))
    scales = np.max(np.abs(real), axis=1)
    require(np.all(scales > 0), "Singular empty equation")
    real = real / scales[:, None]
    vector = vector / scales
    require(np.all(np.isfinite(real)) and np.all(np.isfinite(vector)), "Nonfinite real-block scaling")
    require(len(real) <= 416 and np.count_nonzero(real) <= 16384,
            "Real block exceeds 416 equations or 16384 nonzero coefficients")
    condition = float(np.linalg.cond(real))
    require(math.isfinite(condition) and condition <= 1e10,
            "Singular/ill-conditioned real-block circuit connection")
    lines = ["SPIKE exact linear AC real-block coupling"]
    count = 0
    for row in range(len(real)):
        for col in np.flatnonzero(real[row]):
            count += 1
            lines.append(f"G{count} x{row} 0 x{col} 0 {real[row, col]:.17g}")
        lines.append(f"I{row} 0 x{row} {vector[row]:.17g}")
    lines.extend((".op", ".end"))
    netlist = "\n".join(lines) + "\n"
    require(len(netlist.encode()) <= 2 * 1024**2, "Lowered netlist exceeds 2 MiB")
    return netlist, real, vector, condition
