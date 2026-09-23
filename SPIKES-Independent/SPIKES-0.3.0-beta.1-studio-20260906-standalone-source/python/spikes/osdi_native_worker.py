"""Minimal out-of-process OSDI 0.3 callback host used by SPIKES.

This file deliberately has no SPIKES imports.  It is copied into a temporary
directory and launched with ``python -I -S`` by :mod:`osdi_runtime`.  Loading an
OSDI DLL runs native initialization code, so this module must never be imported
by the main solver process.
"""

from __future__ import annotations

import ctypes
import json
import math
from pathlib import Path


CALC_RESIST_RESIDUAL = 1
CALC_RESIST_JACOBIAN = 4
CALC_OP = 32
ANALYSIS_DC = 2048
EVAL_FATAL_MASK = 2 | 4 | 8


class OsdiSimParas(ctypes.Structure):
    _fields_ = [
        ("names", ctypes.POINTER(ctypes.c_char_p)),
        ("vals", ctypes.POINTER(ctypes.c_double)),
        ("names_str", ctypes.POINTER(ctypes.c_char_p)),
        ("vals_str", ctypes.POINTER(ctypes.c_char_p)),
    ]


class OsdiSimInfo(ctypes.Structure):
    _fields_ = [
        ("paras", OsdiSimParas),
        ("abstime", ctypes.c_double),
        ("prev_solve", ctypes.POINTER(ctypes.c_double)),
        ("prev_state", ctypes.POINTER(ctypes.c_double)),
        ("next_state", ctypes.POINTER(ctypes.c_double)),
        ("flags", ctypes.c_uint32),
    ]


class OsdiInitErrorPayload(ctypes.Union):
    _fields_ = [("parameter_id", ctypes.c_uint32)]


class OsdiInitError(ctypes.Structure):
    _fields_ = [("code", ctypes.c_uint32), ("payload", OsdiInitErrorPayload)]


class OsdiInitInfo(ctypes.Structure):
    _fields_ = [
        ("flags", ctypes.c_uint32),
        ("num_errors", ctypes.c_uint32),
        ("errors", ctypes.POINTER(OsdiInitError)),
    ]


class OsdiNodePair(ctypes.Structure):
    _fields_ = [("node_1", ctypes.c_uint32), ("node_2", ctypes.c_uint32)]


class OsdiJacobianEntry(ctypes.Structure):
    _fields_ = [
        ("nodes", OsdiNodePair),
        ("react_ptr_off", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
    ]


class OsdiNode(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p),
        ("units", ctypes.c_char_p),
        ("residual_units", ctypes.c_char_p),
        ("resist_residual_off", ctypes.c_uint32),
        ("react_residual_off", ctypes.c_uint32),
        ("resist_limit_rhs_off", ctypes.c_uint32),
        ("react_limit_rhs_off", ctypes.c_uint32),
        ("is_flow", ctypes.c_bool),
    ]


class OsdiNoiseSource(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char_p), ("nodes", OsdiNodePair)]


# OSDI 0.3 descriptor.  OSDI 0.4 preserves this prefix, but the release host
# intentionally accepts exactly 0.3 until its appended descriptor-size symbol
# and additional callback semantics are qualified.
class OsdiDescriptor03(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p),
        ("num_nodes", ctypes.c_uint32),
        ("num_terminals", ctypes.c_uint32),
        ("nodes", ctypes.POINTER(OsdiNode)),
        ("num_jacobian_entries", ctypes.c_uint32),
        ("jacobian_entries", ctypes.POINTER(OsdiJacobianEntry)),
        ("num_collapsible", ctypes.c_uint32),
        ("collapsible", ctypes.POINTER(OsdiNodePair)),
        ("collapsed_offset", ctypes.c_uint32),
        ("noise_sources", ctypes.POINTER(OsdiNoiseSource)),
        ("num_noise_src", ctypes.c_uint32),
        ("num_params", ctypes.c_uint32),
        ("num_instance_params", ctypes.c_uint32),
        ("num_opvars", ctypes.c_uint32),
        ("param_opvar", ctypes.c_void_p),
        ("node_mapping_offset", ctypes.c_uint32),
        ("jacobian_ptr_resist_offset", ctypes.c_uint32),
        ("num_states", ctypes.c_uint32),
        ("state_idx_off", ctypes.c_uint32),
        ("bound_step_offset", ctypes.c_uint32),
        ("instance_size", ctypes.c_uint32),
        ("model_size", ctypes.c_uint32),
        ("access", ctypes.c_void_p),
        ("setup_model", ctypes.c_void_p),
        ("setup_instance", ctypes.c_void_p),
        ("eval", ctypes.c_void_p),
        ("load_noise", ctypes.c_void_p),
        ("load_residual_resist", ctypes.c_void_p),
        ("load_residual_react", ctypes.c_void_p),
        ("load_limit_rhs_resist", ctypes.c_void_p),
        ("load_limit_rhs_react", ctypes.c_void_p),
        ("load_spice_rhs_dc", ctypes.c_void_p),
        ("load_spice_rhs_tran", ctypes.c_void_p),
        ("load_jacobian_resist", ctypes.c_void_p),
        ("load_jacobian_react", ctypes.c_void_p),
        ("load_jacobian_tran", ctypes.c_void_p),
    ]


SetupModel = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p, ctypes.c_void_p,
    ctypes.POINTER(OsdiSimParas), ctypes.POINTER(OsdiInitInfo),
)
SetupInstance = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double,
    ctypes.c_uint32, ctypes.POINTER(OsdiSimParas), ctypes.POINTER(OsdiInitInfo),
)
Eval = ctypes.CFUNCTYPE(
    ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
    ctypes.POINTER(OsdiSimInfo),
)
LoadResidual = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_double),
)
LoadJacobian = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)
LogCallback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32)


def _decoded(value: bytes | None) -> str:
    return value.decode("utf-8", errors="replace") if value else ""


def _check_descriptor(desc: OsdiDescriptor03) -> None:
    if not 1 <= desc.num_nodes <= 4096 or not 1 <= desc.num_terminals <= desc.num_nodes:
        raise ValueError("OSDI descriptor node counts are outside release bounds")
    if desc.num_jacobian_entries > 1_000_000:
        raise ValueError("OSDI descriptor Jacobian count exceeds release bound")
    if not 1 <= desc.instance_size <= 256 * 1024 * 1024:
        raise ValueError("OSDI instance size is outside release bounds")
    if not 1 <= desc.model_size <= 256 * 1024 * 1024:
        raise ValueError("OSDI model size is outside release bounds")
    required = (
        desc.setup_model, desc.setup_instance, desc.eval,
        desc.load_residual_resist, desc.load_jacobian_resist,
    )
    if not all(required):
        raise ValueError("OSDI descriptor omits a required DC callback")


def evaluate(request: dict[str, object]) -> dict[str, object]:
    artifact = Path(str(request["artifact"])).resolve(strict=True)
    module_name = str(request["module_name"])
    terminal_voltages = [float(value) for value in request["terminal_voltages"]]  # type: ignore[index]
    temperature = float(request.get("temperature_kelvin", 300.15))
    if not math.isfinite(temperature) or not 1.0 <= temperature <= 2000.0:
        raise ValueError("temperature is outside release bounds")

    library = ctypes.WinDLL(str(artifact)) if hasattr(ctypes, "WinDLL") else ctypes.CDLL(str(artifact))
    major = ctypes.c_uint32.in_dll(library, "OSDI_VERSION_MAJOR").value
    minor = ctypes.c_uint32.in_dll(library, "OSDI_VERSION_MINOR").value
    count = ctypes.c_uint32.in_dll(library, "OSDI_NUM_DESCRIPTORS").value
    if (major, minor) != (0, 3):
        raise ValueError(f"unsupported OSDI ABI {major}.{minor}; release host requires 0.3")
    if not 1 <= count <= 4096:
        raise ValueError("OSDI descriptor count is outside release bounds")

    logs: list[dict[str, object]] = []
    def log_callback(_handle: int, message: bytes, level: int) -> None:
        if len(logs) < 128:
            logs.append({"level": int(level), "message": _decoded(message)[:4096]})
    logger = LogCallback(log_callback)
    try:
        callback_slot = ctypes.c_void_p.in_dll(library, "osdi_log")
        callback_slot.value = ctypes.cast(logger, ctypes.c_void_p).value
    except ValueError:
        pass

    descriptor_array = (OsdiDescriptor03 * count).in_dll(library, "OSDI_DESCRIPTORS")
    selected = next((item for item in descriptor_array if _decoded(item.name) == module_name), None)
    if selected is None:
        names = [_decoded(item.name) for item in descriptor_array]
        raise ValueError(f"OSDI module {module_name!r} is absent; available={names!r}")
    desc = selected
    _check_descriptor(desc)
    if len(terminal_voltages) != desc.num_terminals:
        raise ValueError("terminal voltage count does not match OSDI descriptor")
    if not all(math.isfinite(value) for value in terminal_voltages):
        raise ValueError("terminal voltages must be finite")

    model = ctypes.create_string_buffer(desc.model_size)
    instance = ctypes.create_string_buffer(desc.instance_size)
    model_ptr = ctypes.cast(model, ctypes.c_void_p)
    instance_ptr = ctypes.cast(instance, ctypes.c_void_p)
    sim_params = OsdiSimParas()
    init = OsdiInitInfo()
    SetupModel(desc.setup_model)(None, model_ptr, ctypes.byref(sim_params), ctypes.byref(init))
    if init.num_errors:
        raise ValueError(f"OSDI model setup returned {init.num_errors} initialization errors")
    SetupInstance(desc.setup_instance)(
        None, instance_ptr, model_ptr, temperature, desc.num_terminals,
        ctypes.byref(sim_params), ctypes.byref(init),
    )
    if init.num_errors:
        raise ValueError(f"OSDI instance setup returned {init.num_errors} initialization errors")

    mapping = ctypes.cast(
        ctypes.addressof(instance) + desc.node_mapping_offset,
        ctypes.POINTER(ctypes.c_uint32),
    )
    for index in range(desc.num_nodes):
        mapping[index] = index

    jacobian_values = (ctypes.c_double * max(1, desc.num_jacobian_entries))()
    jacobian_pointers = ctypes.cast(
        ctypes.addressof(instance) + desc.jacobian_ptr_resist_offset,
        ctypes.POINTER(ctypes.c_void_p),
    )
    for index in range(desc.num_jacobian_entries):
        jacobian_pointers[index] = ctypes.addressof(jacobian_values) + index * ctypes.sizeof(ctypes.c_double)

    solve = (ctypes.c_double * desc.num_nodes)()
    for index, value in enumerate(terminal_voltages):
        solve[index] = value
    state_count = max(1, desc.num_states)
    previous_state = (ctypes.c_double * state_count)()
    next_state = (ctypes.c_double * state_count)()
    info = OsdiSimInfo(
        sim_params, 0.0, solve, previous_state, next_state,
        CALC_RESIST_RESIDUAL | CALC_RESIST_JACOBIAN | CALC_OP | ANALYSIS_DC,
    )
    eval_flags = Eval(desc.eval)(None, instance_ptr, model_ptr, ctypes.byref(info))
    if eval_flags & EVAL_FATAL_MASK:
        raise ValueError(f"OSDI evaluation stopped with flags 0x{eval_flags:x}")

    residual = (ctypes.c_double * desc.num_nodes)()
    LoadResidual(desc.load_residual_resist)(instance_ptr, model_ptr, residual)
    LoadJacobian(desc.load_jacobian_resist)(instance_ptr, model_ptr)
    jacobian = []
    for index in range(desc.num_jacobian_entries):
        entry = desc.jacobian_entries[index]
        value = float(jacobian_values[index])
        if not math.isfinite(value):
            raise ValueError("OSDI callback produced a non-finite Jacobian value")
        jacobian.append({
            "row": int(entry.nodes.node_1), "column": int(entry.nodes.node_2),
            "value": value, "flags": int(entry.flags),
        })
    residual_values = [float(residual[index]) for index in range(desc.num_nodes)]
    if not all(math.isfinite(value) for value in residual_values):
        raise ValueError("OSDI callback produced a non-finite residual")
    return {
        "status": "completed", "osdi_abi": "0.3", "module_name": module_name,
        "num_nodes": int(desc.num_nodes), "num_terminals": int(desc.num_terminals),
        "residual": residual_values, "jacobian": jacobian,
        "eval_flags": int(eval_flags), "logs": logs,
    }


def main() -> int:
    try:
        request = json.loads(Path("request.json").read_text(encoding="utf-8"))
        result = evaluate(request)
        Path("result.json").write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
        return 0
    except BaseException as exc:  # The parent treats any worker failure as fail-closed.
        Path("error.json").write_text(
            json.dumps({"error_type": type(exc).__name__, "detail": str(exc)[:4096]}, sort_keys=True),
            encoding="utf-8",
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
