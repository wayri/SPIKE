"""Reviewed PEEC RLCG import and staged ngspice co-simulation.

The compiler deliberately accepts only explicit extraction-network to circuit-
node mappings.  It does not infer circuit topology from coordinates or fit a
frequency-dependent impedance sweep to an unreviewed equivalent circuit.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List

from .contracts import AnalysisSpec, DesignIR, ValidationIssue
from .ngspice_plugin import NgspicePlugin
from .spice_workspace import SPICE_WORKSPACE_CONTRACT, compose_spice_workspace


PEEC_SPICE_IMPORT_CONTRACT = "spike/peec-spice-import/v1"
HYBRID_COSIMULATION_CONTRACT = "spike/hybrid-cosimulation/v1"
MAX_IMPORTED_NETWORKS = 10_000

_STATUS_RANK = {
    "validated": 0,
    "solver_dependent": 1,
    "approximate": 2,
    "experimental": 3,
    "unvalidated": 4,
    "unsupported": 5,
    "failed": 6,
}


def _model_status(*values: Any) -> str:
    normalized = [str(value or "unvalidated").strip().lower() for value in values]
    return max(normalized, key=lambda value: _STATUS_RANK.get(value, 4))


def _node(value: Any, field: str) -> str:
    node = str(value or "").strip()
    if not node or len(node) > 128 or any(character in node for character in "\r\n\t"):
        raise ValueError(f"{field} must be a non-empty bounded circuit-node name.")
    return node


def _finite_nonnegative(value: Any, field: str) -> float:
    try:
        number = float(value or 0.0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite non-negative number.") from exc
    if number < 0 or number != number or number in {float("inf"), float("-inf")}:
        raise ValueError(f"{field} must be a finite non-negative number.")
    return number


def _networks(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(result, dict):
        raise ValueError("The extraction result must be an object.")
    networks = result.get("networks", {}).get("parasitics", [])
    if not isinstance(networks, list) or not networks:
        raise ValueError("The extraction result contains no PEEC RLCG networks.")
    if len(networks) > MAX_IMPORTED_NETWORKS:
        raise ValueError(f"The extraction result exceeds {MAX_IMPORTED_NETWORKS} RLCG networks.")
    return networks


def list_peec_spice_networks(result: Dict[str, Any]) -> Dict[str, Any]:
    """Return the bounded network catalog that the UI can map explicitly."""

    catalog = []
    for index, network in enumerate(_networks(result)):
        catalog.append({
            "network_index": index,
            "contract": network.get("contract", ""),
            "net": str(network.get("net", "")),
            "load": str(network.get("load", "")),
            "source_mesh_node": network.get("source_node"),
            "sink_mesh_node": network.get("sink_node"),
            "model_status": str(network.get("model_status", result.get("model_status", "unvalidated"))),
            "parameters": {
                "resistance_ohm": network.get("resistance_ohm"),
                "inductance_h": network.get("inductance_h"),
                "capacitance_f": network.get("capacitance_f"),
                "conductance_s": network.get("conductance_s"),
            },
            "frequency_samples": len(network.get("impedance", [])) if isinstance(network.get("impedance"), list) else 0,
        })
    return {
        "contract": PEEC_SPICE_IMPORT_CONTRACT,
        "status": "mapping_required",
        "analysis_id": str(result.get("analysis_id", "")),
        "networks": catalog,
        "limits": {
            "topology": "series_rl_with_sink_shunt_cg",
            "frequency_dependent_fitting": "unsupported",
            "endpoint_inference": "forbidden",
        },
    }


def import_peec_rlcg(
    result: Dict[str, Any],
    workspace: Dict[str, Any],
    mappings: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    """Append reviewed lumped RLCG sections to a SPICE workspace.

    Each mapping identifies one extracted network by its stable array index and
    supplies explicit circuit endpoints.  The returned workspace is a deep copy;
    the caller's project state is never mutated implicitly.
    """

    if not isinstance(workspace, dict) or workspace.get("contract") != SPICE_WORKSPACE_CONTRACT:
        raise ValueError("A spike/spice-workspace/v1 workspace is required.")
    source_networks = _networks(result)
    mapping_list = list(mappings)
    if not mapping_list:
        raise ValueError("At least one reviewed PEEC network mapping is required.")
    if len(mapping_list) > len(source_networks):
        raise ValueError("The mapping count exceeds the available extracted networks.")

    imported: List[Dict[str, Any]] = []
    seen_indices: set[int] = set()
    source_id = str(result.get("analysis_id") or result.get("provenance", {}).get("run_id") or "peec-result")
    source_status = str(result.get("model_status", "unvalidated"))

    for mapping_position, mapping in enumerate(mapping_list):
        if not isinstance(mapping, dict):
            raise ValueError(f"Mapping {mapping_position} must be an object.")
        try:
            network_index = int(mapping.get("network_index"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Mapping {mapping_position} requires an integer network_index.") from exc
        if network_index < 0 or network_index >= len(source_networks):
            raise ValueError(f"Mapping {mapping_position} references an unavailable RLCG network.")
        if network_index in seen_indices:
            raise ValueError(f"RLCG network {network_index} is mapped more than once.")
        seen_indices.add(network_index)
        if mapping.get("endpoint_reviewed") is not True:
            raise ValueError(f"Mapping {mapping_position} must be explicitly endpoint_reviewed.")

        network = source_networks[network_index]
        if network.get("contract") != "spike/rlgc-network/v1":
            raise ValueError(f"Network {network_index} does not use spike/rlgc-network/v1.")
        start = _node(mapping.get("from_node"), f"mappings[{mapping_position}].from_node")
        stop = _node(mapping.get("to_node"), f"mappings[{mapping_position}].to_node")
        if start == stop:
            raise ValueError(f"Mapping {mapping_position} requires distinct circuit endpoints.")
        resistance = _finite_nonnegative(network.get("resistance_ohm"), "resistance_ohm")
        inductance = _finite_nonnegative(network.get("inductance_h"), "inductance_h")
        capacitance = _finite_nonnegative(network.get("capacitance_f"), "capacitance_f")
        conductance = _finite_nonnegative(network.get("conductance_s"), "conductance_s")
        if not any(value > 0 for value in (resistance, inductance, capacitance, conductance)):
            raise ValueError(f"Network {network_index} contains no positive RLCG parameter.")
        reference = ""
        if capacitance > 0 or conductance > 0:
            reference = _node(mapping.get("reference_node"), f"mappings[{mapping_position}].reference_node")

        imported.append({
            "id": f"peec_{network_index + 1}",
            "enabled": True,
            "net": str(network.get("net", "")),
            "from_node": start,
            "to_node": stop,
            "reference_node": reference,
            "resistance_ohm": resistance,
            "inductance_h": inductance,
            "capacitance_f": capacitance,
            "conductance_s": conductance,
            "source_result_id": source_id,
            "source_network_index": network_index,
            "source_mesh_nodes": [network.get("source_node"), network.get("sink_node")],
            "model_status": _model_status(source_status, network.get("model_status")),
            "endpoint_reviewed": True,
            "topology": "series_rl_with_sink_shunt_cg",
        })

    updated = deepcopy(workspace)
    existing = updated.setdefault("parasitics", [])
    if not isinstance(existing, list):
        raise ValueError("workspace.parasitics must be an array.")
    existing_ids = {str(item.get("id", "")) for item in existing if isinstance(item, dict)}
    for item in imported:
        base = item["id"]
        suffix = 2
        while item["id"] in existing_ids:
            item["id"] = f"{base}_{suffix}"
            suffix += 1
        existing_ids.add(item["id"])
        existing.append(item)

    return {
        "contract": PEEC_SPICE_IMPORT_CONTRACT,
        "status": "imported_reviewed_lumped_model",
        "workspace": updated,
        "imported_parasitics": imported,
        "source": {
            "analysis_id": source_id,
            "solver": result.get("provenance", {}).get("solver", ""),
            "model_status": source_status,
        },
        "validity": {
            "topology": "series_rl_with_sink_shunt_cg",
            "preserves_frequency_sweep": False,
            "frequency_dependent_fitting": "not_performed",
            "iterative_field_circuit_feedback": False,
            "statement": "The imported section uses the extracted equivalent R/L/C/G scalars. The source impedance sweep remains attached to the PEEC result and is not silently fitted.",
        },
    }


def run_staged_hybrid_cosimulation(
    design: DesignIR,
    extraction_result: Dict[str, Any],
    workspace: Dict[str, Any],
    mappings: Iterable[Dict[str, Any]],
    *,
    timeout_seconds: int = 120,
) -> Dict[str, Any]:
    """Run extract/compose/ngspice as a bounded, non-iterative hybrid stage."""

    imported = import_peec_rlcg(extraction_result, workspace, mappings)
    preview = compose_spice_workspace(imported["workspace"], design)
    if preview.get("status") != "ready":
        return {
            "contract": HYBRID_COSIMULATION_CONTRACT,
            "status": "blocked",
            "import": imported,
            "netlist_preview": preview,
            "result": None,
        }

    spice_spec = AnalysisSpec(
        analysis_id=f"{extraction_result.get('analysis_id', 'extraction')}-ngspice",
        mode="spice",
        solver_id="spike.ngspice",
        formulation="explicit_geometry_parasitic_netlist",
        options={
            "spice_netlist": preview["netlist"],
            "timeout_seconds": max(1, min(int(timeout_seconds), 3600)),
            "spice_overlay_bindings": imported["workspace"].get("overlay_bindings", []),
            "component_stress_bindings": imported["workspace"].get("component_stress_bindings", []),
        },
    )
    analysis = NgspicePlugin().run(design, spice_spec)
    analysis.issues = [issue for issue in analysis.issues if issue.code != "EXPLICIT_NETLIST_ONLY"]
    analysis.issues.append(ValidationIssue(
        code="HYBRID_COSIMULATION_NON_ITERATIVE",
        severity="warning",
        message="PEEC extraction and ngspice circuit execution completed as staged one-way coupling; field/circuit iteration was not performed.",
        suggestion="Use a validated iterative adapter before treating geometry/device feedback as converged.",
        status="approximate",
    ))
    analysis.model_status = _model_status(analysis.model_status, extraction_result.get("model_status"))
    analysis.provenance.update({
        "hybrid_contract": HYBRID_COSIMULATION_CONTRACT,
        "geometry_parasitics_included": True,
        "extraction_analysis_id": extraction_result.get("analysis_id", ""),
        "extraction_solver": extraction_result.get("provenance", {}).get("solver", ""),
        "coupling": "one_way_staged",
    })
    return {
        "contract": HYBRID_COSIMULATION_CONTRACT,
        "status": analysis.status,
        "model_status": analysis.model_status,
        "import": imported,
        "netlist_preview": preview,
        "result": analysis.to_dict(),
    }


__all__ = [
    "HYBRID_COSIMULATION_CONTRACT",
    "PEEC_SPICE_IMPORT_CONTRACT",
    "import_peec_rlcg",
    "list_peec_spice_networks",
    "run_staged_hybrid_cosimulation",
]
