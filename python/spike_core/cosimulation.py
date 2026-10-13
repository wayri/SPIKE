# SPDX-License-Identifier: Apache-2.0
"""Experimental fixed-grid, explicit-lag scalar co-simulation master.

All participants read the previous accepted output snapshot. There is no
same-tick feedthrough, algebraic-loop iteration, interpolation or unit conversion.
Adapters are trusted Python objects; JSON cannot select arbitrary code or paths.
"""
from copy import deepcopy
import hashlib
import json
import math
import time
from types import MappingProxyType

REQUEST = "spike/cosimulation-request/v1"
RESULT = "spike/cosimulation-result/v1"
MAX_BYTES = 8 * 1024 * 1024
MAX_STEPS = 10000
MAX_PORT_VALUES = 200000


def bounded_digest(value):
    digest = hashlib.sha256()
    size = 0
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False)
    for chunk in encoder.iterencode(value):
        encoded = chunk.encode()
        size += len(encoded)
        if size > MAX_BYTES:
            raise ValueError("JSON payload exceeds 8 MiB")
        digest.update(encoded)
    return digest.hexdigest()


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Expected a finite scalar number")
    return float(value)


def identity(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError("Expected a nonempty identity of at most 256 characters")
    return value


class ReplayAdapter:
    """Replay supplied output values at each communication tick."""
    version = "1"

    def validate(self, participant, steps):
        if participant["inputs"]:
            raise ValueError("Replay has no inputs")
        if set(participant["config"]) != {"values"}:
            raise ValueError("Replay configuration requires only values")
        values = participant["config"].get("values")
        if not isinstance(values, list) or len(values) != steps:
            raise ValueError("Replay requires one output object per step")
        for item in values:
            _outputs(item, participant["outputs"])

    def step(self, participant, inputs, state, tick, time_s, step_s):
        return dict(participant["config"]["values"][tick - 1]), state


class GainAdapter:
    """y[k] = gain * u[k-1]; dimensionless gain, identical scalar units."""
    version = "1"

    def validate(self, participant, steps):
        if set(participant["config"]) != {"gain"}:
            raise ValueError("Gain configuration requires only gain")
        if set(participant["inputs"]) != {"u"} or set(participant["outputs"]) != {"y"}:
            raise ValueError("Gain requires input u and output y")
        if participant["inputs"]["u"] != participant["outputs"]["y"]:
            raise ValueError("Gain input and output units must match")
        number(participant["config"].get("gain"))

    def step(self, participant, inputs, state, tick, time_s, step_s):
        return {"y": number(participant["config"]["gain"]) * inputs["u"]}, state


def default_adapters():
    return {"replay": ReplayAdapter(), "gain": GainAdapter()}


def _outputs(values, ports):
    if not isinstance(values, dict) or set(values) != set(ports):
        raise ValueError("Output values must exactly match declared ports")
    return {key: number(value) for key, value in values.items()}


def _readonly(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _readonly(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_readonly(item) for item in value)
    return value


def _admit(request, adapters):
    if not isinstance(request, dict) or request.get("contract") != REQUEST:
        raise ValueError("Expected " + REQUEST)
    if set(request) != {"contract", "model_id", "model_revision", "step_s", "steps", "participants", "connections"}:
        raise ValueError("Unexpected or missing co-simulation request fields")
    identity(request.get("model_id"))
    identity(request.get("model_revision"))
    step_s = number(request.get("step_s"))
    steps = request.get("steps")
    if step_s <= 0 or not isinstance(steps, int) or isinstance(steps, bool) or not 1 <= steps <= MAX_STEPS:
        raise ValueError("Positive step_s and 1..10000 integer steps required")
    number(step_s * steps)
    participants = request.get("participants")
    if not isinstance(participants, list) or not 1 <= len(participants) <= 64:
        raise ValueError("Expected 1..64 participants")
    by_id = {}
    for p in participants:
        if not isinstance(p, dict):
            raise ValueError("Participant must be an object")
        if set(p) != {"id", "model_revision", "model_status", "adapter", "inputs", "outputs", "initial_outputs", "config"}:
            raise ValueError("Unexpected or missing participant fields")
        pid = identity(p.get("id"))
        if pid in by_id:
            raise ValueError("Duplicate participant identity")
        identity(p.get("model_revision"))
        if p.get("model_status") not in {"experimental", "approximate", "validated", "unsupported"}:
            raise ValueError("Explicit participant model_status required")
        if p["model_status"] == "unsupported":
            raise ValueError("Unsupported participant cannot run")
        adapter_id = p.get("adapter")
        if not isinstance(adapter_id, str) or adapter_id not in adapters:
            raise ValueError("Unregistered participant adapter")
        for direction in ("inputs", "outputs"):
            ports = p.get(direction)
            if not isinstance(ports, dict) or len(ports) > 32:
                raise ValueError("Expected at most 32 scalar ports per direction")
            for name, unit in ports.items():
                identity(name)
                identity(unit)
        if not p["outputs"] or not isinstance(p.get("config"), dict):
            raise ValueError("Participant requires outputs and configuration")
        _outputs(p.get("initial_outputs"), p["outputs"])
        adapters[adapter_id].validate(deepcopy(p), steps)
        by_id[pid] = p
    if (steps + 1) * sum(len(p["outputs"]) for p in participants) > MAX_PORT_VALUES:
        raise ValueError("Retained output exceeds 200000 scalar values")
    # A conservative per-frame size using the longest finite float spelling.
    # Reserve metadata/error space so a permitted run can fit the worker reply.
    output_shape = {pid: {key: -1.7976931348623157e308 for key in p["outputs"]} for pid, p in by_id.items()}
    frame_bytes = len(json.dumps({"time_s": -1.7976931348623157e308, "outputs": output_shape},
                                ensure_ascii=True).encode()) + 2
    if frame_bytes * (steps + 1) > MAX_BYTES - 256 * 1024:
        raise ValueError("Retained frames exceed the worker JSON byte budget")
    connections = request.get("connections")
    if not isinstance(connections, list) or len(connections) > 2048:
        raise ValueError("Expected at most 2048 connections")
    drivers = {}
    for connection in connections:
        if not isinstance(connection, dict):
            raise ValueError("Connection must be an object")
        if set(connection) != {"source", "target"}:
            raise ValueError("Connection requires only source and target")
        source, target = connection.get("source"), connection.get("target")
        if not all(isinstance(e, list) and len(e) == 2 and all(isinstance(v, str) for v in e) for e in (source, target)):
            raise ValueError("Endpoint must be [participant_id, port_id]")
        if source[0] not in by_id or target[0] not in by_id:
            raise ValueError("Unknown participant endpoint")
        output, input_ = by_id[source[0]]["outputs"], by_id[target[0]]["inputs"]
        if source[1] not in output or target[1] not in input_:
            raise ValueError("Endpoint direction or port is invalid")
        if output[source[1]] != input_[target[1]]:
            raise ValueError("Connection units must match exactly; conversion is unsupported")
        if tuple(target) in drivers:
            raise ValueError("Multiple drivers for one input")
        drivers[tuple(target)] = tuple(source)
    if set(drivers) != {(p["id"], key) for p in participants for key in p["inputs"]}:
        raise ValueError("Every participant input requires exactly one driver")
    return by_id, drivers, steps, step_s


def run_cosimulation(request, *, adapters=None, cancelled=None, timeout_s=60.0):
    """Run a fresh session. Adapter.step returns (outputs, JSON state).

    Timeout/cancellation are cooperative between callbacks. Adapters must bound
    their own calls; the enclosing worker host supplies hard process termination.
    Only fully accepted ticks appear in frames on failure or cancellation.
    """
    result = {"contract": RESULT, "status": "rejected", "model_status": "experimental",
              "issues": [], "frames": [], "completed_steps": 0,
              "limitations": ["Explicit one-step lag; no implicit coupling or error control.",
                              "Participant status is a supplied claim, not physics qualification."]}
    try:
        result["request_sha256"] = bounded_digest(request)
        request = deepcopy(request)
        adapters = default_adapters() if adapters is None else adapters
        by_id, drivers, steps, step_s = _admit(request, adapters)
        timeout_s = number(timeout_s)
        if not 0 < timeout_s <= 3600:
            raise ValueError("timeout_s must be in (0, 3600]")
        result.update(model_id=request["model_id"], model_revision=request["model_revision"],
                      participant_provenance=[{"id": p["id"], "model_revision": p["model_revision"],
                                               "model_status": p["model_status"], "adapter": p["adapter"],
                                               "inputs": deepcopy(p["inputs"]), "outputs": deepcopy(p["outputs"]),
                                               "adapter_version": identity(adapters[p["adapter"]].version)}
                                              for p in sorted(by_id.values(), key=lambda p: p["id"])])
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        result["issues"] = [{"code": "COSIM_ADMISSION", "severity": "error", "message": str(exc)}]
        return result
    outputs = {pid: _outputs(p["initial_outputs"], p["outputs"]) for pid, p in by_id.items()}
    states = {pid: None for pid in by_id}
    participant_views = {pid: _readonly(p) for pid, p in by_id.items()}
    result["frames"] = [{"time_s": 0.0, "outputs": deepcopy(outputs)}]
    started = time.monotonic()

    def check_control():
        if cancelled is not None and cancelled():
            return "cancelled"
        return "timed_out" if time.monotonic() - started >= timeout_s else None

    for tick in range(1, steps + 1):
        staged_outputs, staged_states = {}, {}
        try:
            for pid in sorted(by_id):
                control = check_control()
                if control:
                    result["status"] = control
                    return result
                p = by_id[pid]
                inputs = {key: outputs[drivers[(pid, key)][0]][drivers[(pid, key)][1]] for key in p["inputs"]}
                values, state = adapters[p["adapter"]].step(
                    participant_views[pid], inputs, deepcopy(states[pid]), tick, tick * step_s, step_s)
                staged_outputs[pid] = _outputs(values, p["outputs"])
                bounded_digest(state)
                staged_states[pid] = deepcopy(state)
            control = check_control()
            if control:
                result["status"] = control
                return result
        except Exception as exc:
            result["status"] = "failed"
            result["issues"] = [{"code": "COSIM_ADAPTER_FAILED", "severity": "error",
                                 "participant_id": pid, "message": str(exc)}]
            return result
        outputs, states = staged_outputs, staged_states
        result["frames"].append({"time_s": tick * step_s, "outputs": deepcopy(outputs)})
        result["completed_steps"] = tick
    result["status"] = "completed"
    return result
