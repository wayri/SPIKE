# SPDX-License-Identifier: Apache-2.0
"""Bounded, explicit passive PDN AC and finite-rise transient network.

The same descriptor MNA equations are used in both analyses:
    E x' + A x = b,  x = [node voltages, inductor currents].
Capacitors stamp E_vv, inductances (including signed mutual L) stamp E_ii,
resistors stamp A_vv, and branch incidence stamps A_vi = -A_iv.T.
The real-power identity is d(x.T E x/2)/dt + v.T G v + i.T R i = x.T b.
This is a lumped supplied/measurement/extraction model, not PCB extraction.
"""

from __future__ import annotations

import math
import json
from typing import Any, Callable

import numpy as np
from scipy.linalg import LinAlgWarning, lu_factor, lu_solve
import warnings

REQUEST_CONTRACT = "spike/pdn-network-request/v1"
RESULT_CONTRACT = "spike/pdn-network-result/v1"
_MAX_NODES = 64
_MAX_ELEMENTS = 128
_MAX_PORTS = 16
_MAX_FREQUENCIES = 512
_MAX_STEPS = 20000
_MAX_REQUEST_BYTES = 8 * 1024 * 1024
_MAX_RESULT_BYTES = 16 * 1024 * 1024
_MAX_DENSE_WORK = 100_000_000


class PdnNetworkError(ValueError):
    """Invalid or unsupported explicit network, with a stable diagnostic code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = "PDN_" + code.upper()


def _fail(code: str, message: str) -> None:
    raise PdnNetworkError(code, message)


def _record(value: Any, keys: set[str], where: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        _fail("invalid_request", f"{where} requires exactly {sorted(keys)}")
    return value


def _number(value: Any, where: str, *, positive: bool = False, signed: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        _fail("invalid_request", f"{where} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError):
        _fail("invalid_request", f"{where} must be a finite number")
    if not math.isfinite(result):
        _fail("invalid_request", f"{where} must be a finite number")
    if (not signed and result < 0) or (positive and result == 0):
        _fail("invalid_request", f"{where} must be {'positive' if positive else 'nonnegative'}")
    return result


def _name(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 80 or not value.strip():
        _fail("invalid_request", f"{where} must be a nonempty bounded string")
    return value


def _array(value: Any, where: str, minimum: int, maximum: int) -> list:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        _fail("resource_limit", f"{where} must contain {minimum}..{maximum} entries")
    return value


def _provenance(value: Any, where: str) -> dict:
    item = _record(value, {"kind", "source_id"}, where)
    if item["kind"] not in ("supplied", "measured", "extracted"):
        _fail("invalid_request", f"{where}.kind must be supplied, measured, or extracted")
    _name(item["source_id"], where + ".source_id")
    return item


def _complex_pair(value: complex) -> dict[str, float]:
    return {"real": float(value.real), "imag": float(value.imag)}


def _compensated_add(total: float, correction: float, value: float) -> tuple[float, float]:
    """Kahan accumulator for signed source work and passive dissipation."""
    increment = value - correction
    updated = total + increment
    return updated, (updated - total) - increment


def _solve_linear(system: np.ndarray, rhs: np.ndarray, where: str) -> tuple[np.ndarray, float, float]:
    """Equilibrate mixed SI units before conditioning and solving.

    Report the 2-norm condition of the equilibrated system. The residual is
    an unscaled normwise backward error of the original physical equations.
    """
    if not np.all(np.isfinite(system)) or not np.all(np.isfinite(rhs)):
        _fail("numerical_failure", f"Nonfinite coefficients at {where}")
    row_norm = np.max(np.abs(system), axis=1)
    if np.any(row_norm == 0):
        _fail("singular_network", f"Zero matrix row at {where}")
    row_scale = 1 / row_norm
    row_scaled = row_scale[:, None] * system
    column_norm = np.max(np.abs(row_scaled), axis=0)
    if np.any(column_norm == 0):
        _fail("singular_network", f"Zero matrix column at {where}")
    column_scale = 1 / column_norm
    balanced = row_scaled * column_scale[None, :]
    if not np.all(np.isfinite(balanced)):
        _fail("numerical_failure", f"Nonfinite equilibrated matrix at {where}")
    try:
        condition = float(np.linalg.cond(balanced))
    except np.linalg.LinAlgError as exc:
        _fail("numerical_failure", f"Condition estimate failed at {where}: {exc}")
    if not math.isfinite(condition) or condition > 1e12:
        _fail("singular_network", f"Equilibrated matrix ill-conditioned at {where}")
    with warnings.catch_warnings():
        warnings.simplefilter("error", LinAlgWarning)
        try:
            solution = column_scale[:, None] * lu_solve(lu_factor(balanced), row_scale[:, None] * rhs)
        except (LinAlgWarning, ValueError, np.linalg.LinAlgError) as exc:
            _fail("numerical_failure", f"Linear factorization failed at {where}: {exc}")
    denominator = np.linalg.norm(system) * np.linalg.norm(solution) + np.linalg.norm(rhs)
    residual = float(np.linalg.norm(system @ solution - rhs) / max(float(denominator), np.finfo(float).tiny))
    if not np.all(np.isfinite(solution)) or not math.isfinite(residual) or residual > 1e-10:
        _fail("numerical_failure", f"Excessive backward error at {where}")
    return solution, residual, condition


def _transient_setup(raw: Any, port_ids: list[str]) -> dict | None:
    if raw is None:
        return None
    legacy = not isinstance(raw, dict) or "loads" not in raw
    fields = {"port_id", "points", "output_times_s", "max_step_s"} if legacy else {
        "loads", "output_times_s", "max_step_s"}
    _record(raw, fields, "load_transient")
    raw_loads = [{"port_id": raw["port_id"], "points": raw["points"]}] if legacy else _array(
        raw["loads"], "load_transient.loads", 1, _MAX_PORTS)
    loads = []
    seen = set()
    for item in raw_loads:
        _record(item, {"port_id", "points"}, "transient load")
        port_id = _name(item["port_id"], "transient load port_id")
        if port_id not in port_ids or port_id in seen:
            _fail("invalid_request", "Transient load ports must be known and unique")
        seen.add(port_id)
        points = _array(item["points"], "load_transient.points", 2, 1024)
        for point in points:
            _record(point, {"time_s", "current_a"}, "PWL point")
        times = [_number(p["time_s"], "PWL time_s") for p in points]
        currents = [_number(p["current_a"], "PWL current_a", signed=True) for p in points]
        if times[0] != 0 or currents[0] != 0 or any(b <= a for a, b in zip(times, times[1:])):
            _fail("invalid_request", "PWL must start at (0,0) and have strictly increasing time")
        slopes = [(b - a) / (stop - start) for a, b, start, stop in
                  zip(currents, currents[1:], times, times[1:])]
        if not all(math.isfinite(slope) for slope in slopes):
            _fail("invalid_request", "PWL current slopes must be finite")
        if loads and times[-1] != loads[0]["times"][-1]:
            _fail("invalid_request", "All transient waveforms must have the same final time")
        loads.append({"port_id": port_id, "port_col": port_ids.index(port_id),
                      "times": times, "currents": currents, "slopes": slopes})
    output_times = _array(raw["output_times_s"], "output_times_s", 2, 2048)
    output_times = [_number(t, "output time_s") for t in output_times]
    if output_times[0] != 0 or output_times[-1] > loads[0]["times"][-1] or any(b <= a for a, b in zip(output_times, output_times[1:])):
        _fail("invalid_request", "Output times must start at zero, increase, and end within PWL")
    max_step = _number(raw["max_step_s"], "max_step_s", positive=True)
    events = sorted(set(output_times).union(*(load["times"] for load in loads)))
    steps = 0
    for start, stop in zip(events, events[1:]):
        ratio = (stop - start) / max_step
        if not math.isfinite(ratio) or ratio > _MAX_STEPS:
            _fail("resource_limit", "Transient exceeds 20000 integration steps")
        steps += math.ceil(ratio)
        if steps > _MAX_STEPS:
            _fail("resource_limit", "Transient exceeds 20000 integration steps")
    return {"legacy": legacy, "loads": loads, "output_times": output_times,
            "max_step": max_step, "events": events, "steps": steps}


def _inductive_slope_response(A: np.ndarray, E: np.ndarray, load: np.ndarray,
                             voltage_count: int, conductances: list,
                             capacitances: list) -> np.ndarray:
    """Return the algebraic state jump per A/s change of sink-current slope.

    K contains constant voltage shifts on each R/C-connected island without
    an R/C path to reference. These are exactly the common nullspace of the
    nodal C and G matrices, found from topology without an SI-dependent rank
    tolerance. Let F be coil incidence and L the positive-definite coil block.
    Differentiating island KCL, K.T F i = -K.T B u, gives
    K.T F L^-1 F.T K dv = -K.T B du/dt. Thus a slope change alters only
    island voltages: capacitor voltages, coil currents, energy and resistor
    dissipation are continuous. No pseudoinverse or artificial loss is added.
    """
    parent = list(range(voltage_count + 1))
    reference = voltage_count

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for a, b, _ in conductances + capacitances:
        parent[root(reference if a is None else a)] = root(reference if b is None else b)
    groups: dict[int, list[int]] = {}
    reference_root = root(reference)
    for index in range(voltage_count):
        component = root(index)
        if component != reference_root:
            groups.setdefault(component, []).append(index)
    response = np.zeros_like(load)
    if not groups:
        return response
    K = np.zeros((voltage_count, len(groups)))
    for column, indices in enumerate(groups.values()):
        K[indices, column] = 1 / math.sqrt(len(indices))
    if voltage_count == len(load):
        _fail("singular_network", "Transient has an unreferenced R/C island without inductors")
    incidence = A[:voltage_count, voltage_count:]
    island_incidence = K.T @ incidence
    derivative, _, _ = _solve_linear(E[voltage_count:, voltage_count:],
                                     island_incidence.T, "transient coil consistency")
    shifts, _, _ = _solve_linear(island_incidence @ derivative,
                                 -(K.T @ load[:voltage_count]),
                                 "transient island consistency")
    response[:voltage_count] = K @ shifts
    return response


def evaluate_pdn_network(request: dict, *, cancel_check: Callable[[], bool] | None = None,
                         _admission_only: bool = False) -> dict:
    """Analyze a strict JSON-shaped, explicit passive network.

    Required top-level keys: contract, reference, nodes, elements, ports,
    frequencies_hz, load_transient. ``load_transient`` may be null. A load
    transient has ``port_id``, ``points`` (time_s/current_a), ``output_times_s``,
    and ``max_step_s``. Alternatively ``loads`` supplies unique port_id/points
    records sharing one final time. Positive current_a sinks at each port.
    All values are SI; all supplied elements require explicit provenance.
    """
    if cancel_check is not None and not callable(cancel_check):
        _fail("invalid_request", "cancel_check must be callable")

    def poll_cancel() -> None:
        if cancel_check is None:
            return
        try:
            cancelled = cancel_check()
        except Exception as exc:
            _fail("cancel_check_failed", f"Cancellation check failed: {exc}")
        if cancelled:
            _fail("cancelled", "PDN execution cancelled")

    poll_cancel()
    try:
        encoded = json.dumps(request, ensure_ascii=False, allow_nan=False,
                             sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        _fail("invalid_request", f"Request is not finite JSON: {exc}")
    if len(encoded) > _MAX_REQUEST_BYTES:
        _fail("resource_limit", "PDN request exceeds 8 MiB")
    _record(request, {"contract", "reference", "nodes", "elements", "ports",
                      "frequencies_hz", "load_transient"}, "request")
    if request["contract"] != REQUEST_CONTRACT:
        _fail("invalid_contract", "Unsupported PDN network contract")
    reference = _name(request["reference"], "reference")
    nodes = _array(request["nodes"], "nodes", 1, _MAX_NODES)
    if any(not isinstance(n, str) or not n or n == reference for n in nodes) or len(set(nodes)) != len(nodes):
        _fail("invalid_request", "nodes must be unique named non-reference nodes")
    node_index = {name: index for index, name in enumerate(nodes)}
    n = len(nodes)
    poll_cancel()
    conductances: list[tuple[int | None, int | None, float]] = []
    capacitances: list[tuple[int | None, int | None, float]] = []
    coils: list[tuple[int | None, int | None, float, float]] = []
    mutuals: list[tuple[int, int, float]] = []
    provenance_counts = {"supplied": 0, "measured": 0, "extracted": 0}
    internal = 0

    def node(name: Any) -> int | None:
        if not isinstance(name, str):
            _fail("invalid_topology", "Node reference must be a string")
        if name == reference:
            return None
        if name not in node_index:
            _fail("invalid_topology", f"Unknown node {name!r}")
        return node_index[name]

    def endpoints(item: dict) -> tuple[int | None, int | None]:
        a, b = node(item["positive"]), node(item["negative"])
        if a == b:
            _fail("invalid_topology", "Element endpoints must differ")
        return a, b

    def intermediate() -> int:
        nonlocal internal
        result = n + internal
        internal += 1
        return result

    def add_series(a: int | None, b: int | None, r: float, l: float, c: float | None = None) -> None:
        if r == 0 and l == 0 and c is None:
            _fail("invalid_topology", "Zero-impedance element is not admitted")
        start = a
        if r > 0:
            end = intermediate() if l > 0 or c is not None else b
            conductances.append((start, end, 1 / r))
            start = end
        if l > 0:
            end = intermediate() if c is not None else b
            coils.append((start, end, l, 0.0))
            start = end
        if c is not None:
            capacitances.append((start, b, c))

    elements = _array(request["elements"], "elements", 1, _MAX_ELEMENTS)
    element_ids: set[str] = set()
    for raw in elements:
        poll_cancel()
        if not isinstance(raw, dict) or "type" not in raw:
            _fail("invalid_request", "Each element requires a type")
        kind = raw["type"]
        common = {"id", "type", "provenance"}
        terminal = {"positive", "negative"}
        fields = {
            "resistor": common | terminal | {"resistance_ohm"},
            "inductor": common | terminal | {"inductance_h", "resistance_ohm"},
            "capacitor": common | terminal | {"capacitance_f"},
            "decap": common | terminal | {"capacitance_f", "esr_ohm", "esl_h"},
            "dm_choke": common | terminal | {"inductance_h", "resistance_ohm"},
            "source_output_impedance": common | terminal | {"resistance_ohm", "inductance_h"},
            "net_ground_capacitance": common | {"node", "capacitance_f"},
            "cm_choke": common | {"winding_a", "winding_b", "coupling_coefficient", "polarity"},
        }
        if not isinstance(kind, str) or kind not in fields:
            _fail("unsupported_element", f"Unsupported element type {kind!r}")
        _record(raw, fields[kind], f"{kind} element")
        element_id = _name(raw["id"], "element.id")
        if element_id in element_ids:
            _fail("invalid_request", "Duplicate element ID")
        element_ids.add(element_id)
        prov = _provenance(raw["provenance"], f"{element_id}.provenance")
        provenance_counts[prov["kind"]] += 1
        if kind == "net_ground_capacitance":
            a = node(raw["node"])
            if a is None:
                _fail("invalid_topology", "Ground capacitance requires a non-reference node")
            capacitances.append((a, None, _number(raw["capacitance_f"], "capacitance_f", positive=True)))
        elif kind == "cm_choke":
            windings = []
            for key in ("winding_a", "winding_b"):
                winding = _record(raw[key], terminal | {"inductance_h", "resistance_ohm"}, key)
                a, b = endpoints(winding)
                windings.append((a, b, _number(winding["inductance_h"], key + ".inductance_h", positive=True),
                                 _number(winding["resistance_ohm"], key + ".resistance_ohm")))
            k = _number(raw["coupling_coefficient"], "coupling_coefficient")
            if k >= 1:
                _fail("invalid_request", "Coupling must be less than one for nonsingular magnetic energy")
            if raw["polarity"] not in ("a_positive_to_b_positive", "opposing"):
                _fail("invalid_request", "Invalid choke polarity")
            first = len(coils)
            coils.extend(windings)
            sign = 1 if raw["polarity"] == "a_positive_to_b_positive" else -1
            mutuals.append((first, first + 1, sign * k * math.sqrt(windings[0][2] * windings[1][2])))
        else:
            a, b = endpoints(raw)
            if kind == "resistor":
                conductances.append((a, b, 1 / _number(raw["resistance_ohm"], "resistance_ohm", positive=True)))
            elif kind == "capacitor":
                capacitances.append((a, b, _number(raw["capacitance_f"], "capacitance_f", positive=True)))
            elif kind == "decap":
                add_series(a, b, _number(raw["esr_ohm"], "esr_ohm"),
                           _number(raw["esl_h"], "esl_h"),
                           _number(raw["capacitance_f"], "capacitance_f", positive=True))
            else:
                add_series(a, b, _number(raw["resistance_ohm"], "resistance_ohm"),
                           _number(raw["inductance_h"], "inductance_h", positive=kind in ("inductor", "dm_choke")))

    size = n + internal + len(coils)
    if size > 256:
        _fail("resource_limit", "Expanded MNA system exceeds 256 unknowns")
    A = np.zeros((size, size))
    E = np.zeros((size, size))

    def stamp(matrix: np.ndarray, a: int | None, b: int | None, value: float) -> None:
        if a is not None:
            matrix[a, a] += value
        if b is not None:
            matrix[b, b] += value
        if a is not None and b is not None:
            matrix[a, b] -= value
            matrix[b, a] -= value

    for a, b, g in conductances:
        stamp(A, a, b, g)
    for a, b, c in capacitances:
        stamp(E, a, b, c)
    for j, (a, b, l, r) in enumerate(coils):
        col = n + internal + j
        E[col, col] = l
        A[col, col] = r
        for endpoint, direction in ((a, 1), (b, -1)):
            if endpoint is not None:
                A[endpoint, col] += direction
                A[col, endpoint] -= direction
    for i, j, m in mutuals:
        ii, jj = n + internal + i, n + internal + j
        E[ii, jj] = E[jj, ii] = m

    ports_raw = _array(request["ports"], "ports", 1, _MAX_PORTS)
    port_ids: list[str] = []
    port_vectors: list[np.ndarray] = []
    for raw in ports_raw:
        if not isinstance(raw, dict) or raw.get("mode") not in ("single", "differential", "common"):
            _fail("invalid_request", "Port mode must be single, differential, or common")
        mode = raw["mode"]
        fields = {"id", "mode", "positive", "negative"} if mode != "common" else {
            "id", "mode", "positive_nodes", "negative_nodes"}
        _record(raw, fields, "port")
        port_id = _name(raw["id"], "port.id")
        if port_id in port_ids:
            _fail("invalid_request", "Duplicate port ID")
        port_ids.append(port_id)
        vector = np.zeros(size)
        if mode == "common":
            positives = _array(raw["positive_nodes"], "positive_nodes", 2, 2)
            negatives = _array(raw["negative_nodes"], "negative_nodes", 2, 2)
            if any(not isinstance(name, str) for name in positives + negatives) or len(set(positives)) != 2:
                _fail("invalid_topology", "Common-mode positive conductors must differ")
            pairs = [(name, .5) for name in positives] + [(name, -.5) for name in negatives]
        else:
            if raw["positive"] == raw["negative"]:
                _fail("invalid_topology", "Port endpoints must differ")
            pairs = [(raw["positive"], 1.), (raw["negative"], -1.)]
        for name, coefficient in pairs:
            index = node(name)
            if index is not None:
                vector[index] += coefficient
        if not np.any(vector):
            _fail("invalid_topology", "Port has no non-reference terminal")
        port_vectors.append(vector)
    B = np.column_stack(port_vectors)

    frequencies = _array(request["frequencies_hz"], "frequencies_hz", 1, _MAX_FREQUENCIES)
    frequencies = [_number(f, "frequency_hz", positive=True) for f in frequencies]
    if any(b <= a for a, b in zip(frequencies, frequencies[1:])):
        _fail("invalid_request", "Frequencies must increase strictly")
    if any(not math.isfinite(2 * math.pi * f) for f in frequencies):
        _fail("invalid_request", "Frequency produces nonfinite angular frequency")
    transient_setup = _transient_setup(request["load_transient"], port_ids)
    transient_steps = transient_setup["steps"] if transient_setup is not None else 0
    if (len(frequencies) + transient_steps + (2 if transient_setup else 0)) * size**3 > _MAX_DENSE_WORK:
        _fail("resource_limit", "Estimated dense factorization work exceeds 100 million unknown-cubed units")
    # Conservative JSON-envelope estimate, before allocating every response.
    output_count = len(transient_setup["output_times"]) if transient_setup is not None else 0
    response_bytes = (len(frequencies) * (len(port_ids)**2 + n * len(port_ids)) * 96
                      + output_count * (n + len(port_ids)) * 64
                      + (len(frequencies) + output_count) * 256)
    if transient_setup is not None and not transient_setup["legacy"]:
        response_bytes += (output_count + 1) * len(transient_setup["loads"]) * 384
    if response_bytes > _MAX_RESULT_BYTES:
        _fail("resource_limit", "Estimated PDN response exceeds 16 MiB")
    # The native SPIKES public ABI has PWL and L/C but no coupled-inductor
    # constructor plus AC multiport solve. This bounded SciPy MNA is explicit.
    ac = []
    worst_residual = 0.
    worst_condition = 0.
    for frequency in ([] if _admission_only else frequencies):
        poll_cancel()
        system = A.astype(complex) + (2j * math.pi * frequency) * E
        response, residual, condition = _solve_linear(system, B, f"AC {frequency} Hz")
        z = B.T @ response
        if np.min(np.linalg.eigvalsh((z.real + z.real.T) / 2)) < -1e-8 * max(1., np.linalg.norm(z)):
            _fail("nonpassive_response", "AC multiport real impedance is not passive")
        worst_residual = max(worst_residual, residual)
        worst_condition = max(worst_condition, condition)
        ac.append({"frequency_hz": frequency,
                   "impedance_ohm": [[_complex_pair(value) for value in row] for row in z],
                   "node_transfer_impedance_ohm": {
                       name: [_complex_pair(value) for value in response[index, :]]
                       for name, index in node_index.items()},
                   "relative_residual": residual, "condition_number": condition})

    transient = None
    if transient_setup is not None:
        legacy, loads = transient_setup["legacy"], transient_setup["loads"]
        output_times, max_step = transient_setup["output_times"], transient_setup["max_step"]
        events, steps = transient_setup["events"], transient_setup["steps"]
        load_ids = [load["port_id"] for load in loads]
        load_matrix = B[:, [load["port_col"] for load in loads]]
        if _admission_only:
            poll_cancel()
            return {"contract": RESULT_CONTRACT, "status": "structurally_admitted",
                    "model_status": "approximate", "unknowns": size,
                    "frequency_count": len(frequencies), "transient_steps": steps,
                    "provenance_counts": provenance_counts}
        slope_response = _inductive_slope_response(A, E, load_matrix, n + internal,
                                                   conductances, capacitances)
        slope_indices = [0] * len(loads)
        state = slope_response @ np.array([load["slopes"][0] for load in loads])
        if not np.all(np.isfinite(state)):
            _fail("numerical_failure", "Nonfinite consistent initial transient voltage")
        previous_time = 0.
        previous_input = np.zeros(len(loads))
        work_sum = work_correction = 0.
        dissipation_sum = dissipation_correction = 0.
        absolute_energy_flow = 0.
        max_stored_energy = 0.
        worst_step_residual = 0.
        worst_step_condition = 0.
        def current_observation(values: np.ndarray) -> dict:
            return {"load_current_a": float(values[0])} if legacy else {
                "load_current_a_by_port": {pid: float(value) for pid, value in zip(load_ids, values)}}

        observations = [{"time_s": 0., **current_observation(previous_input),
                         "port_voltage_v": {pid: float(B[:, j] @ state) for j, pid in enumerate(port_ids)},
                         "node_voltage_v": {name: float(state[index]) for name, index in node_index.items()},
                         "stored_energy_j": 0.}]
        output_set = set(output_times[1:])
        for start, stop in zip(events, events[1:]):
            count = math.ceil((stop - start) / max_step)
            for step in range(count):
                poll_cancel()
                next_time = stop if step == count - 1 else start + (step + 1) * (stop-start) / count
                dt = next_time - previous_time
                next_input = np.array([float(np.interp(next_time, load["times"], load["currents"]))
                                       for load in loads])
                left = E + .5 * dt * A
                summed_input = previous_input + next_input
                forcing = (.5 * dt * float(summed_input[0]) * load_matrix[:, 0] if legacy else
                           .5 * dt * (load_matrix @ summed_input))
                right = (E - .5 * dt * A) @ state - forcing
                next_state, residual, condition = _solve_linear(left, right[:, None], f"transient {next_time} s")
                next_state = next_state[:, 0]
                midpoint = .5 * (state + next_state)
                dissipation = dt * float(midpoint @ ((A + A.T) * .5) @ midpoint)
                source_work = -.5 * dt * summed_input * (load_matrix.T @ midpoint)
                if not np.all(np.isfinite(source_work)):
                    _fail("numerical_failure", f"Nonfinite source work at {next_time} s")
                try:
                    work = float(source_work[0]) if legacy else math.fsum(source_work)
                except OverflowError:
                    _fail("numerical_failure", f"Nonfinite total source work at {next_time} s")
                source_flow = float(np.sum(np.abs(source_work)))
                energy_before = .5 * float(state @ E @ state)
                energy_after = .5 * float(next_state @ E @ next_state)
                if not all(math.isfinite(value) for value in
                           (work, dissipation, energy_before, energy_after)):
                    _fail("numerical_failure", f"Nonfinite energy terms at {next_time} s")
                balance_scale = max(abs(energy_before), abs(energy_after), source_flow, abs(dissipation),
                                    np.finfo(float).tiny)
                if energy_after < -1e-10 * balance_scale or abs((energy_after - energy_before) -
                                                                (work - dissipation)) > 1e-7 * balance_scale:
                    _fail("energy_failure", f"Passive energy balance failed at {next_time} s")
                work_sum, work_correction = _compensated_add(work_sum, work_correction, work)
                dissipation_sum, dissipation_correction = _compensated_add(
                    dissipation_sum, dissipation_correction, dissipation)
                absolute_energy_flow += source_flow + abs(dissipation)
                max_stored_energy = max(max_stored_energy, abs(energy_after))
                if not all(math.isfinite(value) for value in
                           (work_sum, dissipation_sum, absolute_energy_flow)):
                    _fail("numerical_failure", f"Nonfinite accumulated energy at {next_time} s")
                state = next_state
                previous_time, previous_input = next_time, next_input
                worst_step_residual = max(worst_step_residual, residual)
                worst_step_condition = max(worst_step_condition, condition)
            # PWL samples use the right derivative at interior corners and
            # the left derivative at the final endpoint (no extrapolation).
            changes = np.zeros(len(loads))
            for index, load in enumerate(loads):
                slope_index = slope_indices[index]
                if slope_index + 1 < len(load["slopes"]) and stop == load["times"][slope_index + 1]:
                    changes[index] = load["slopes"][slope_index + 1] - load["slopes"][slope_index]
                    slope_indices[index] += 1
            if not np.all(np.isfinite(changes)):
                _fail("numerical_failure", "Nonfinite PWL slope change")
            if np.any(changes):
                state = state + slope_response @ changes
                if not np.all(np.isfinite(state)):
                    _fail("numerical_failure", "Nonfinite algebraic voltage at PWL corner")
            if stop in output_set:
                stored_energy = .5 * float(state @ E @ state)
                energy_scale = max(absolute_energy_flow, max_stored_energy, np.finfo(float).tiny)
                balance_error = abs(stored_energy - (work_sum - dissipation_sum))
                roundoff = 64 * np.finfo(float).eps * max(1, steps) * energy_scale
                if stored_energy < -1e-10 * energy_scale or balance_error > 1e-10 * energy_scale + roundoff:
                    _fail("energy_failure", "Transient passive energy balance failed")
                observations.append({"time_s": stop, **current_observation(previous_input),
                                     "port_voltage_v": {pid: float(B[:, j] @ state) for j, pid in enumerate(port_ids)},
                                     "node_voltage_v": {name: float(state[index]) for name, index in node_index.items()},
                                     "stored_energy_j": stored_energy})
        final_stored_energy = .5 * float(state @ E @ state)
        final_energy_error = abs(final_stored_energy - (work_sum - dissipation_sum))
        energy_scale = max(absolute_energy_flow, max_stored_energy, np.finfo(float).tiny)
        final_roundoff = 64 * np.finfo(float).eps * max(1, steps) * energy_scale
        if not math.isfinite(final_energy_error) or final_energy_error > 1e-10 * energy_scale + final_roundoff:
            _fail("energy_failure", "Final transient passive energy balance failed")
        load_identity = {"load_port_id": load_ids[0]} if legacy else {"load_port_ids": load_ids}
        transient = {**load_identity, "points": observations,
                     "steps": steps, "max_relative_residual": worst_step_residual,
                     "max_condition_number": worst_step_condition,
                     "energy_balance_error_j": final_energy_error,
                     "energy_balance_relative_error": float(final_energy_error / energy_scale),
                     "energy_balance_scale_j": energy_scale}

    if _admission_only:
        poll_cancel()
        return {"contract": RESULT_CONTRACT, "status": "structurally_admitted",
                "model_status": "approximate", "unknowns": size,
                "frequency_count": len(frequencies), "transient_steps": transient_steps,
                "provenance_counts": provenance_counts}
    poll_cancel()
    result = {"contract": RESULT_CONTRACT, "model_status": "approximate", "solver": "scipy_dense_descriptor_mna",
            "reference": reference, "port_ids": port_ids, "ac": ac, "load_transient": transient,
            "diagnostics": {"unknowns": size, "max_ac_relative_residual": worst_residual,
                            "max_ac_condition_number": worst_condition,
                            "provenance_counts": provenance_counts,
                            "limitations": ["Explicit lumped linear passive network only; no PCB geometry extraction or regulator control.",
                                            "R, L, C, coupling, ESR and ESL are frequency-invariant; no ferrite dispersion, tolerance, temperature, or nonlinear bias model.",
                                            "Only requested positive frequencies are solved; no interpolation or validity outside the supplied component/model band is established.",
                                            "No parasitics are inferred; supplied, measured, and extracted inputs retain their declared provenance.",
                                            "Finite-rise PWL trapezoidal transient; timestep convergence and measured-board validation remain required."]}}
    try:
        actual_bytes = len(json.dumps(result, ensure_ascii=False, allow_nan=False,
                                      separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError, OverflowError) as exc:
        _fail("numerical_failure", f"Result is not finite JSON: {exc}")
    if actual_bytes > _MAX_RESULT_BYTES:
        _fail("resource_limit", "PDN response exceeds 16 MiB")
    return result


def validate_pdn_network(request: dict) -> dict:
    """Validate syntax, topology references, and resource bounds without solving.

    This is not numerical solvability or physical-model validation; execution
    can still reject an ill-conditioned frequency or timestep matrix.
    """
    return evaluate_pdn_network(request, _admission_only=True)
