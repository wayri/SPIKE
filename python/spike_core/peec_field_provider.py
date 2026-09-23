"""Native PEEC reduction provider for reviewed field/circuit iteration.

The adapter reruns SPIKE's native quasi-static PEEC extraction and maps the
result back to existing workspace parasitics by explicit provenance. It never
infers endpoints, changes topology, or substitutes a different extracted net.

This provider is an experimental orchestration path. The current PEEC model is
geometry/material driven, so circuit state does not yet feed nonlinear material
or temperature changes back into the extraction.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from .contracts import AnalysisSpec, DesignIR
from .field_circuit_cosim import FIELD_REQUEST_CONTRACT, FIELD_RESULT_CONTRACT
from .peec_plugin import solve_peec_2_5d


PROVIDER_ID = "spike.native.peec_rlcg"
PROVIDER_VERSION = "0.1.0"
_PARAMETERS = (
    "resistance_ohm",
    "inductance_h",
    "capacitance_f",
    "conductance_s",
)


class NativePeecFieldReductionProvider:
    """Map native PEEC RLCG networks to reviewed circuit parasitics."""

    def __init__(self, design: DesignIR, analysis_spec: AnalysisSpec) -> None:
        if analysis_spec.mode not in {"ac", "broadband_hf"}:
            raise ValueError("The native PEEC field provider requires AC extraction mode.")
        if not str(analysis_spec.analysis_id or "").strip():
            raise ValueError("The native PEEC field provider requires a stable analysis_id.")
        self._design = design
        self._analysis_spec = analysis_spec

    @staticmethod
    def _mapped_network(
        networks: List[Dict[str, Any]],
        parasitic: Dict[str, Any],
        analysis_id: str,
    ) -> Dict[str, Any]:
        identifier = str(parasitic.get("id", "")).strip()
        source_result_id = str(parasitic.get("source_result_id", "")).strip()
        if source_result_id != analysis_id:
            raise ValueError(
                f"Parasitic {identifier} references extraction {source_result_id or 'missing'}, "
                f"not {analysis_id}."
            )
        try:
            index = int(parasitic["source_network_index"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Parasitic {identifier} requires an explicit source_network_index."
            ) from exc
        if index < 0 or index >= len(networks):
            raise ValueError(f"Parasitic {identifier} references unavailable PEEC network {index}.")
        network = networks[index]
        if network.get("contract") != "spike/rlgc-network/v1":
            raise ValueError(f"PEEC network {index} does not use spike/rlgc-network/v1.")
        expected_net = str(parasitic.get("net", "")).strip()
        actual_net = str(network.get("net", "")).strip()
        if expected_net != actual_net:
            raise ValueError(
                f"Parasitic {identifier} net identity changed from {expected_net or 'missing'} "
                f"to {actual_net or 'missing'}."
            )
        source_nodes = parasitic.get("source_mesh_nodes")
        actual_nodes = [network.get("source_node"), network.get("sink_node")]
        if isinstance(source_nodes, list) and len(source_nodes) == 2 and source_nodes != actual_nodes:
            raise ValueError(
                f"Parasitic {identifier} PEEC endpoint identity changed from {source_nodes} "
                f"to {actual_nodes}."
            )
        return network

    def __call__(self, request: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(request, dict) or request.get("contract") != FIELD_REQUEST_CONTRACT:
            raise ValueError(f"The PEEC provider requires {FIELD_REQUEST_CONTRACT}.")
        parasitics = request.get("parasitics")
        if not isinstance(parasitics, list) or not parasitics:
            raise ValueError("The PEEC provider requires reviewed parasitic mappings.")

        result = solve_peec_2_5d(self._design, self._analysis_spec)
        if result.status != "completed":
            messages = "; ".join(issue.message for issue in result.issues)
            raise RuntimeError(f"Native PEEC extraction did not complete: {messages or result.status}.")
        networks = result.networks.get("parasitics", [])
        if not isinstance(networks, list) or not networks:
            raise RuntimeError("Native PEEC extraction returned no RLCG networks.")

        updates = []
        for parasitic in parasitics:
            if not isinstance(parasitic, dict):
                raise ValueError("Every reviewed parasitic mapping must be an object.")
            identifier = str(parasitic.get("id", "")).strip()
            network = self._mapped_network(networks, parasitic, result.analysis_id)
            update = {"id": identifier}
            for parameter in _PARAMETERS:
                value = network.get(parameter)
                update[parameter] = 0.0 if value is None else float(value)
            updates.append(update)

        return {
            "contract": FIELD_RESULT_CONTRACT,
            "status": "completed",
            "provider": PROVIDER_ID,
            "provider_version": PROVIDER_VERSION,
            "model_status": "experimental",
            "parasitics": updates,
            "diagnostics": {
                "analysis_id": result.analysis_id,
                "solver": result.provenance.get("solver", ""),
                "formulation": result.provenance.get("formulation", ""),
                "mapped_network_count": len(updates),
                "circuit_state_feedback": False,
                "limits": deepcopy(result.provenance.get("limits", [])),
            },
        }


__all__ = [
    "NativePeecFieldReductionProvider",
    "PROVIDER_ID",
    "PROVIDER_VERSION",
]
