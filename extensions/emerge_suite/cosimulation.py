# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Prepare bound EMerge networks for owned AC/rational/channel consumers.

No EMerge implementation is copied and no EM field-power calibration inferred.
This is an explicit in-process adapter, not a new advertised GUI capability.
"""
from copy import deepcopy
import hashlib
import json
import re

from python.spike_core.solvers.execution.coupling.em_network_ac import WAVE_CONVENTION
from python.spike_core.extension_analysis_results import admit_analysis_result
from .normalize import network


def prepare_cosimulation_source(result, binding, *, expected_case_sha256,
                               expected_script_sha256, port_bindings, wave_convention):
    """Preserve source status/identity and require explicit circuit/reference planes."""
    if wave_convention != WAVE_CONVENTION:
        raise ValueError("EMERGE_COSIM: Explicit common-real RMS power-wave convention required")
    if len(json.dumps(result, allow_nan=False).encode()) > 8*1024**2:
        raise ValueError("EMERGE_COSIM: Source exceeds 8 MiB")
    admitted = admit_analysis_result(result, binding, extension_id="spike.emerge-suite")
    if any(issue.get("severity") == "error" for issue in admitted["issues"]):
        raise ValueError("EMERGE_COSIM: Source contains blocking error issues")
    provenance = admitted["provenance"]
    if not str(provenance.get("solver", "")).startswith("EMerge/"):
        raise ValueError("EMERGE_COSIM: Expected EMerge solver provenance")
    for name, expected in (("board_case_sha256", expected_case_sha256),
                           ("generated_script_sha256", expected_script_sha256)):
        if not isinstance(expected, str) or not re.fullmatch("[0-9a-f]{64}", expected) or provenance.get(name) != expected:
            raise ValueError("EMERGE_COSIM: Stale or missing " + name)
    normalized, _ = network(admitted["networks"].get("s_parameters"))
    ports = normalized["ports"]
    if len(ports) > 16 or not isinstance(port_bindings, dict) or set(port_bindings) != set(ports):
        raise ValueError("EMERGE_COSIM: Exact 1..16 named circuit port bindings required")
    for item in port_bindings.values():
        if not isinstance(item, dict) or set(item) != {"positive_node", "negative_node", "reference_plane"}:
            raise ValueError("EMERGE_COSIM: Explicit terminal pair and reference plane required")
        if any(not isinstance(v, str) or not v.strip() or len(v) > 128 or any(c in v for c in "\r\n\0")
               for v in item.values()) or item["positive_node"] == item["negative_node"]:
            raise ValueError("EMERGE_COSIM: Invalid circuit binding")
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    source = {"id": "emerge-"+digest[:24], "port_names": list(ports),
              "reference_impedance_ohm": normalized["reference_impedance_ohm"],
              "frequencies_hz": normalized["frequencies_hz"],
              "s_parameters": [[[{"real": pair[0], "imag": pair[1]} for pair in row]
                                  for row in matrix] for matrix in normalized["values"]]}
    return deepcopy({"contract": "spike/emerge-cosimulation-source/v1",
        "model_status": admitted["model_status"], "production_qualified": False,
        "source_status": admitted["status"], "source_issues": admitted["issues"],
        "source_result_sha256": digest, "source_provenance": provenance,
        "network_source": source, "port_bindings": port_bindings, "wave_convention": wave_convention,
        "normalization_evidence": "explicit_caller_declaration_not_field_calibration",
        "limitations": ["Compatible with owned sampled AC and rational-fit source contracts",
                        "Port mapping is explicit; no arbitrary SPICE netlist execution is performed",
                        "Relative radiation/E-H samples and network deficit are not volumetric thermal losses",
                        "No interpolation, renormalization, deembedding or qualification promotion"]})
