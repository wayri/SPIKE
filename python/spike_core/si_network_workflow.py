"""Network acquisition, lossless-safe wave transforms and recorded edits."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

import numpy as np
from scipy.linalg import expm

from .si_passives import number
from .sparameters import NetworkData, parse_touchstone_text


def checked(raw: Mapping[str, Any], allowed: set[str], label: str) -> None:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label} must be an object.")
    if set(raw) - allowed:
        raise ValueError(f"Unknown {label} fields: {sorted(set(raw) - allowed)}.")


def line_network(raw: Mapping[str, Any]) -> NetworkData:
    checked(raw, {"kind", "length_m", "resistance_ohm_per_m", "inductance_h_per_m", "capacitance_f_per_m",
                  "loss_tangent", "inductive_coupling", "capacitive_coupling", "coupled",
                  "frequency_stop_hz", "frequency_points", "reference_impedance_ohm"}, "line")
    length = number(raw.get("length_m", 0.05), "length_m", 1e-9, 100)
    r = number(raw.get("resistance_ohm_per_m", 5), "resistance_ohm_per_m", 0, 1e6)
    l = number(raw.get("inductance_h_per_m", 250e-9), "inductance_h_per_m", 1e-15, 1)
    c = number(raw.get("capacitance_f_per_m", 100e-12), "capacitance_f_per_m", 1e-18, 1)
    loss = number(raw.get("loss_tangent", 0.015), "loss_tangent", 0, 1)
    kl = number(raw.get("inductive_coupling", 0.08), "inductive_coupling", 0, 0.95)
    kc = number(raw.get("capacitive_coupling", 0.08), "capacitive_coupling", 0, 0.95)
    z0 = number(raw.get("reference_impedance_ohm", 50), "reference_impedance_ohm", 0.01, 1e6)
    stop = number(raw.get("frequency_stop_hz", 8e9), "frequency_stop_hz", 1, 1e14)
    count = number(raw.get("frequency_points", 1025), "frequency_points", 3, 8193)
    if int(count) != count or not isinstance(raw.get("coupled", True), bool):
        raise ValueError("frequency_points must be integral and coupled must be boolean.")
    n = 2 if raw.get("coupled", True) else 1
    lm = np.array([[l, kl * l], [kl * l, l]]) if n == 2 else np.array([[l]])
    cm = np.array([[c, -kc * c], [-kc * c, c]]) if n == 2 else np.array([[c]])
    f = np.linspace(0, stop, int(count))
    matrices = []
    root, invroot = np.eye(n) * np.sqrt(z0), np.eye(n) / np.sqrt(z0)
    for frequency in f:
        w = 2 * np.pi * frequency
        state = np.block([[np.zeros((n, n)), -(r * np.eye(n) + 1j * w * lm)],
                          [-(1j * w + w * loss) * cm, np.zeros((n, n))]])
        t = expm(state * length)
        t11, t12, t21, t22 = t[:n, :n], t[:n, n:], t[n:, :n], t[n:, n:]
        # Direct wave boundary solve admits ideal through networks at DC.
        a = np.block([[-t11 @ root - t12 @ invroot, root], [-t21 @ root - t22 @ invroot, -invroot]])
        b = np.block([[-t11 @ root + t12 @ invroot, root], [-t21 @ root + t22 @ invroot, invroot]])
        matrices.append(np.linalg.solve(b, -a))
    return NetworkData(f, np.asarray(matrices), np.repeat(z0, 2 * n), source="User-defined uniform RLGC line")


def acquire_network(raw: Mapping[str, Any], design=None) -> tuple[NetworkData, dict[str, Any]]:
    if not isinstance(raw, Mapping):
        raise ValueError("channel must be an object.")
    kind = raw.get("kind", "rlgc")
    evidence = {}
    if kind == "rlgc":
        network = line_network(raw)
    elif kind == "touchstone":
        checked(raw, {"kind", "name", "text"}, "Touchstone channel")
        network = parse_touchstone_text(raw["text"], raw.get("name", "channel.s2p"))
    elif kind == "multiboard":
        from .si_multiboard import build_multiboard_network

        network, evidence = build_multiboard_network(raw)
    elif kind == "network_graph":
        from .si_network_graph import build_network_graph
        network, evidence = build_network_graph(raw)
    elif kind == "geometry":
        checked(raw, {"kind", "request"}, "geometry channel")
        if design is None:
            raise ValueError("Geometry channel requires the active canonical DesignIR v2.")
        from .design_ir_v2 import DesignIRV2
        from .si_channel import _validate_channel_request, extract_uniform_path_rlgc, uniform_rlgc_network
        from .si_coupled_channel import extract_coupled_path_rlgc, multiconductor_rlgc_network
        request = raw["request"]
        _validate_channel_request(request)
        design = DesignIRV2.from_dict(design)
        coupled = bool(request.get("victim_net"))
        evidence = (extract_coupled_path_rlgc if coupled else extract_uniform_path_rlgc)(design, request)
        network = (multiconductor_rlgc_network if coupled else uniform_rlgc_network)(
            evidence, request["frequencies_hz"], request.get("reference_impedance_ohm", 50))
    else:
        raise ValueError("channel.kind must be rlgc, touchstone, geometry, multiboard or network_graph.")
    if not 2 <= network.port_count <= 16 or len(network.frequencies_hz) > 8193:
        raise ValueError("Loaded SI admits 2..16 ports and at most 8193 frequency points.")
    if not np.all(np.isfinite(network.s_parameters())):
        raise ValueError("Network contains non-finite values.")
    return network, evidence


def renormalize_waves(s: np.ndarray, old: np.ndarray, new: float) -> np.ndarray:
    """Change real reference impedances without singular intermediate Z data."""
    ratio = np.sqrt(old / new)
    a, b = np.diag((ratio + 1 / ratio) / 2), np.diag((ratio - 1 / ratio) / 2)
    return np.asarray([np.linalg.solve((a + b @ matrix).T, (b + a @ matrix).T).T for matrix in s])


def cascade_networks(network: NetworkData, other: NetworkData) -> NetworkData:
    """Cascade two two-ports directly in wave coordinates without reacquisition."""
    f,s,z0=network.frequencies_hz,network.s_parameters(),network.reference_impedance_ohm
    if network.port_count != 2 or other.port_count != 2 or not np.array_equal(f,other.frequencies_hz):
        raise ValueError("Cascade needs two 2-port networks on identical frequency grids.")
    if not np.allclose(z0,z0[0]):
        raise ValueError("Renormalize to a shared reference before cascading.")
    t=renormalize_waves(other.s_parameters(),other.reference_impedance_ohm,z0[0])
    d=1-s[:,1,1]*t[:,0,0]
    if np.any(np.abs(d)<1e-12):raise ValueError("Cascade feedback is singular.")
    result=np.empty_like(s)
    result[:,0,0]=s[:,0,0]+s[:,0,1]*t[:,0,0]*s[:,1,0]/d
    result[:,1,1]=t[:,1,1]+t[:,1,0]*s[:,1,1]*t[:,0,1]/d
    result[:,1,0]=t[:,1,0]*s[:,1,0]/d
    result[:,0,1]=s[:,0,1]*t[:,0,1]/d
    if not np.all(np.isfinite(result)):raise ValueError("Cascade produced non-finite values.")
    return NetworkData(f.copy(),result,z0.copy(),source=network.source,warnings=network.warnings)


def edit_network(network: NetworkData, edits: list[Mapping[str, Any]]) -> tuple[NetworkData, list[dict[str, Any]]]:
    if not isinstance(edits, list) or len(edits) > 32:
        raise ValueError("Network edits must be an array of at most 32 operations.")
    f, s, z0 = network.frequencies_hz.copy(), network.s_parameters().copy(), network.reference_impedance_ohm.copy()
    history = []
    for edit in edits:
        kind = edit.get("kind")
        if kind == "renormalize":
            checked(edit, {"kind", "reference_impedance_ohm"}, "renormalization")
            new = number(edit["reference_impedance_ohm"], "reference_impedance_ohm", 0.01, 1e6)
            s = renormalize_waves(s, z0, new)
            z0 = np.repeat(new, len(z0))
        elif kind == "reorder":
            checked(edit, {"kind", "ports"}, "port reorder")
            ports = edit["ports"]
            if not isinstance(ports, list) or any(type(p) is not int for p in ports) or sorted(ports) != list(range(len(z0))):
                raise ValueError("Port reorder requires each zero-based port index exactly once.")
            s, z0 = s[:, ports, :][:, :, ports], z0[ports]
        elif kind == "port_extension":
            checked(edit, {"kind", "delay_s"}, "port extension")
            delays = edit["delay_s"]
            if not isinstance(delays, list) or len(delays) != len(z0):
                raise ValueError("port_extension.delay_s needs one non-negative delay per port.")
            delays = np.array([number(v, "delay_s", 0, 1e-3) for v in delays])
            phase = np.exp(-2j * np.pi * f[:, None] * delays[None, :])
            s *= phase[:, :, None] * phase[:, None, :]
        elif kind == "cascade":
            checked(edit, {"kind", "channel"}, "cascade")
            other, _ = acquire_network(edit["channel"])
            s = cascade_networks(NetworkData(f,s,z0,source=network.source,warnings=network.warnings),other).s_parameters()
        else:
            raise ValueError(f"Unsupported network edit {kind!r}.")
        history.append(dict(edit))
    if not np.all(np.isfinite(s)):
        raise ValueError("Network edits produced non-finite values.")
    return NetworkData(f, s, z0, source=network.source, warnings=network.warnings), history


def digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
