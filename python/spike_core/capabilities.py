"""Capabilities are data, so clients can disable unsupported workflows honestly."""

from __future__ import annotations

from typing import Any, Dict

from .owned_spice_process import capability_manifest as owned_spice_process_capability
from .layout_scoring_process import capability_manifest as layout_scoring_process_capability


def capabilities() -> Dict[str, Any]:
    owned_spice = owned_spice_process_capability()
    layout_scoring = layout_scoring_process_capability()
    owned_engine = owned_spice["owned_engine"]
    owned_features = owned_engine.get("features", {})
    owned_analyses = ["dc"] if owned_engine.get("available") else []
    if owned_engine.get("available") and owned_features.get("transient"):
        owned_analyses.append("transient")
    return {
        "contract": "spike/v1",
        "version": "0.2.10",
        "analyses": {
            "dc": {"state": "available", "model_status": "approximate"},
            "ac": {
                "state": "experimental",
                "model_status": "approximate",
                "validity": (
                    "The native quasi-static PEEC plugin extracts conductor R and partial L, with optional "
                    "approximate single-reference stackup capacitance/dielectric conductance and Hammerstad "
                    "RMS roughness where their required inputs are present. Result-level parameter_availability "
                    "and blocked_uses are authoritative. Proximity effect, via/antipad capacitance, arbitrary "
                    "multiconductor electrostatics, and measured-board correlation remain unavailable."
                ),
            },
            "broadband_hf": {
                "state": "experimental",
                "model_status": "approximate",
                "validity": (
                    "Executable frequency-dependent R/L and optional approximate C/G sweeps inherit the AC "
                    "PEEC parameter availability and limits. A network Z(f) sweep is not a spatial impedance "
                    "field, and validated field-solver plus measured correlation is required before release."
                ),
            },
            "transient": {
                "state": "experimental",
                "model_status": "approximate",
                "validity": "Geometry-derived conductor R, full mutual partial L, and optional stackup-derived single-reference capacitance are integrated with backward Euler. Via capacitance, dielectric loss, radiation, nonlinear devices, and closed-loop source behavior are not inferred.",
            },
            "spice_export": {"state": "integration_pending", "model_status": "unsupported"},
            "closed_loop_spice": {
                "state": "planned",
                "model_status": "unsupported",
                "validity": "Requires validated geometry-derived RLC networks, model assignment, and ngspice co-simulation.",
            },
            "behavioral_blocks": {
                "state": "schema_planned",
                "model_status": "unsupported",
                "validity": "C/C++ and Verilog stand-ins must declare timing, state, and numerical limits.",
            },
            "geometry_uniform_channel": {
                "state": "experimental",
                "model_status": "bounded_geometry_approximate",
                "request_contract": "spike/si-uniform-channel-request/v1",
                "result_contract": "spike/si-channel-result/v1",
                "validity": (
                    "One straight path or two parallel coextensive paths over one proven reference polygon can produce "
                    "a quasi-TEM RLGC model, two/four-port S sweep, explicit unwindowed Hermitian TDR/TDT, bounded "
                    "NEXT/FEXT, and normalized ideal-source NRZ eye. The coupled path uses a sparse cross-section "
                    "reference solve with convergence evidence. Bends, vias, launches, connectors, skin/proximity/roughness, "
                    "protocol limits, independent correlation, and measured "
                    "qualification remain unavailable."
                ),
            },
            "loaded_si_workflow": {
                "state": "experimental",
                "model_status": "linear_network_and_endpoint_approximation",
                "request_contract": "spike/si-workflow-request/v1",
                "result_contract": "spike/si-workflow-result/v1",
                "validity": "Source/receiver and passive loading, deterministic aggressors, PRBS7 eyes, Touchstone import/export and recorded edits are executable. Capacitor and resistor grades carry editable assumptions. IBIS is inventory and selected DC-slope/ramp reduction only; nonlinear switching, AMI, general PCB extraction and compliance remain unavailable.",
            },
            "next_fext": {
                "state": "experimental",
                "model_status": "bounded_parallel_pair_only",
                "validity": "Geometry-derived NEXT/FEXT is executable only for the bounded straight parallel coextensive pair. General PCB coupling and signoff remain unsupported.",
            },
            "sparameter_network": {
                "state": "available",
                "model_status": "imported_or_solver_dependent",
                "validity": (
                    "Touchstone import, network conversion, renormalization, "
                    "mixed-mode traces, passivity, reciprocity, group delay, "
                    "and matched-port impedance are available. The separate bounded uniform-channel path can "
                    "generate experimental two-port S-parameters from a restricted DesignIR geometry envelope; "
                    "general PCB and multiconductor geometry remain unsupported."
                ),
            },
            "eye_diagram": {
                "state": "experimental",
                "model_status": "normalized_linear_channel_only",
                "validity": "Deterministic ideal-source NRZ convolution is available only for the bounded uniform channel. IBIS, equalization, CDR, jitter/noise decomposition, rare-event BER, PAM4, and protocol compliance remain unsupported.",
            },
            "pam4_eye": {"state": "planned", "model_status": "unsupported"},
            "protocol_presets": {
                "state": "configuration_available",
                "model_status": "solver_gated",
                "contract": "spike/si-protocol-suite/v1",
                "families": ["DDR", "GDDR", "SERDES", "LVDS", "PCI", "PCIE", "PXI", "DISPLAYPORT", "HDMI", "USB", "ETHERNET", "MIPI", "SATA", "CXL", "JESD204", "HBM", "CUSTOM"],
                "validity": "Suites configure topology, required inputs, analysis stages, limits, and provenance. They do not establish solver accuracy or protocol compliance.",
            },
            "emi_emc": {
                "state": "research",
                "model_status": "unsupported",
                "validity": "No compliance claim is available without validated fixtures and calibrated limits.",
            },
            "pcb_antenna_full_wave": {
                "state": "research",
                "model_status": "unsupported",
                "validity": "Candidate open-source engines require license and accuracy review before integration.",
            },
            "multi_board": {"state": "schema_ready", "model_status": "unsupported"},
            "thermal": {
                "state": "case_preparation",
                "model_status": "solver_dependent",
                "validity": "Guided scenario and OpenFOAM case preparation are available; CFD results require a validated OpenFOAM setup.",
            },
        },
        "imports": {
            "kicad": {"state": "available", "quality": "native_parser"},
            "ipc2581": {
                "state": "topology_preview",
                "quality": "metadata_only",
                "validity": (
                    "Layer, stackup, net, and component metadata are normalized with an import report. "
                    "Conductor feature geometry is not yet normalized and all geometry solvers remain blocked."
                ),
            },
            "odb_plus_plus": {"state": "planned", "quality": "not_implemented"},
            "gerber": {"state": "planned", "quality": "fallback_only"},
            "altium_native": {"state": "planned", "quality": "not_implemented"},
        },
        "geometry": {
            "complete_net_extraction": {"state": "available", "contract": "spike/net-geometry/v1"},
            "stackup_materials": {"state": "available", "source": "kicad"},
            "rigid_flex_design_ir": {"state": "available", "scope": "planar regions and bend metadata"},
            "regional_stackup": {"state": "integration_pending", "model_status": "unsupported"},
            "deformed_rigid_flex": {"state": "planned", "model_status": "unsupported"},
        },
        "network_data": {
            "touchstone_import": {
                "state": "available",
                "parameters": ["S", "Z", "Y"],
                "formats": ["RI", "MA", "DB"],
            },
            "touchstone_export": {"state": "available", "formats": ["RI", "MA", "DB"]},
            "reference_renormalization": {"state": "available", "reference": "real_positive"},
            "mixed_mode": {"state": "available", "pairing": "adjacent_pairs"},
            "passivity_check": {"state": "available", "method": "maximum_singular_value"},
            "reciprocity_check": {"state": "available"},
            "causality_check": {
                "state": "planned",
                "model_status": "not_evaluated",
                "validity": "Requires explicit DC, resampling, window, and delay policy.",
            },
        },
        "models": {
            "global_library": {"state": "available", "offline": True, "formats": ["step", "stp", "wrl", "vrml", "glb", "gltf"]},
            "footprint_assignment": {"state": "schema_ready", "model_status": "not_wired_to_ui"},
        },
        "solver_runtime": {
            "state": "available",
            "contract": "spike/solver-plugin/v1",
            "execution_modes": ["builtin", "isolated_process"],
            "selection": ["analysis", "formulation", "required_capabilities", "priority"],
            "owned_spice_process": {
                "state": "experimental" if owned_engine.get("available") else "unavailable",
                "model_status": "experimental",
                "product_qualified": False,
                "contract": owned_spice["contract"],
                "input_contract": owned_spice["input_contract"],
                "result_contract": owned_spice["result_contract"],
                "analyses": owned_analyses,
                "structured_workspace_only": True,
                "raw_netlist_accepted": False,
                "caller_selected_library": False,
                "shell_invoked": False,
                "maximum_control_bytes": owned_spice["maximum_control_bytes"],
                "maximum_circuit_result_bytes": owned_spice["maximum_circuit_result_bytes"],
                "trusted_host_supervision_required": owned_spice[
                    "trusted_host_supervision_required"
                ],
                "supported_supervision": owned_spice["supported_supervision"],
                "binary_and_library_sha256_admission": owned_spice[
                    "binary_and_library_sha256_admission"
                ],
                "packaging_state": "dedicated_build_recipe_available",
                "packaged_artifact_qualified": False,
                "validity": (
                    "The dedicated circuit process exposes only the release-owned structured-workspace "
                    "bridge. Availability and DC/transient modes reflect the owned engine probe. It is "
                    "experimental and is not product-qualified."
                ),
            },
        },
        "layout_automation": {
            "state": "orchestration_available",
            "contracts": ["spike/layout-evaluation/v1", "spike/layout-metric-registry/v1"],
            "consumers": ["autorouter", "autoplacer", "joint"],
            "features": [
                "canonical_candidate_preflight",
                "evidence_backed_metric_negotiation",
                "deterministic_native_job_derivation",
                "fail_closed_result_correlation",
                "fixed_process_prepare_and_score",
            ],
            "process": {
                "state": "experimental",
                "contract": layout_scoring["contract"],
                "input_contract": layout_scoring["input_contract"],
                "result_contract": layout_scoring["result_contract"],
                "actions": layout_scoring["actions"],
                "maximum_control_bytes": layout_scoring["maximum_control_bytes"],
                "routes_or_places": False,
                "meshes_or_solves": False,
                "packaged_artifact_qualified": False,
            },
            "metric_registry": "provider_supplied",
            "pcb_physics": "integration_pending",
            "validity": (
                "The orchestration, capability negotiation, and candidate identity boundary are available. "
                "No private PCB layout metric is qualified by this declaration."
            ),
        },
        "extension_runtime": {
            "state": "available",
            "contract": "spike/extension/v1",
            "execution_modes": ["isolated_process"],
            "extension_points": ["applications", "commands", "analyses", "importers", "exporters", "reports", "panels", "validators"],
            "ui_model": "schema_driven",
            "third_party_javascript": "not_loaded",
            "trust": "explicit_for_unbundled_extensions",
        },
    }
