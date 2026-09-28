# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Fail-closed deployability program for the requested solver suite.

This module does not accept user-authored evidence or promote workflows.  It
derives readiness only from the reviewed native capability ledger, whose
validated states require immutable release-qualification bindings.
"""

from __future__ import annotations

from typing import Any, Mapping

from .capability_ledger import native_capability_ledger, release_ready_workflows, validate_capability_ledger


CONTRACT = "spike/solver-suite-deployability/v1"

_PROFILES = (
    {
        "id": "pi.ac_broadband",
        "title": "PI AC and broadband",
        "workflows": ("pi.ac_rlcg", "pi.pdn_target_and_capacitor_optimization"),
        "depends_on": (),
        "next_gate": "Independent field/circuit comparison and measured impedance correlation for the complete admitted geometry envelope.",
    },
    {
        "id": "pi.transient",
        "title": "PI transient",
        "workflows": ("pi.geometry_transient", "circuit.spice_compatible_mna", "circuit.field_circuit_cosimulation"),
        "depends_on": ("pi.ac_broadband",),
        "next_gate": "Time-step convergence, switching-device binding, ngspice correlation, cancellation/restart and energy audits.",
    },
    {
        "id": "thermal.solid",
        "title": "Full solid thermal",
        "workflows": ("thermal.structured_solid_reference", "thermal.solid_steady"),
        "depends_on": (),
        "next_gate": "Compile conforming assembly geometry, add scalable native field execution, and correlate contacts, spreading and radiation.",
    },
    {
        "id": "thermal.full",
        "title": "Full thermal and conjugate heat transfer",
        "workflows": ("thermal.solid_steady", "thermal.conjugate_heat_transfer"),
        "depends_on": ("thermal.solid",),
        "next_gate": "Qualify solid/fluid interfaces, turbulence/fan models, conservation, mesh independence and chamber measurements.",
    },
    {
        "id": "si.deployable",
        "title": "Deployable signal integrity",
        "workflows": ("si.uniform_single_reference_channel", "si.uniform_coupled_pair_channel", "si.quasi_tem_extraction", "si.sparameters_and_tdr", "si.crosstalk_and_eye"),
        "depends_on": ("pi.ac_broadband",),
        "next_gate": "General geometry extraction, launches/vias/packages, causal/passive macromodels, IBIS endpoints and VNA/TDR correlation.",
    },
    {
        "id": "rf.basic",
        "title": "Deployable basic RF",
        "workflows": ("si.sparameters_and_tdr", "emi.near_and_far_field"),
        "depends_on": ("si.deployable",),
        "next_gate": "General wave ports, PML/radiation qualification, adaptive full-wave sweeps and antenna/waveguide references.",
    },
    {
        "id": "emi_emc.fullwave",
        "title": "EMI/EMC field solving",
        "workflows": ("emi.conducted_screening", "emi.near_and_far_field"),
        "depends_on": ("pi.transient", "rf.basic"),
        "next_gate": "Near/far-field, shielding and LISN/chamber fixtures with calibrated uncertainty and limits provenance.",
    },
    {
        "id": "multiphysics.electrothermal",
        "title": "Full electrothermal coupling",
        "workflows": ("pi.ac_rlcg", "pi.geometry_transient", "thermal.solid_steady", "thermal.electrothermal"),
        "depends_on": ("pi.transient", "thermal.solid"),
        "next_gate": "Conservative loss mapping, temperature-dependent materials/devices, relaxed nonlinear iteration and transient energy closure.",
    },
    {
        "id": "multiphysics.platform",
        "title": "General multiphysics platform",
        "workflows": ("thermal.electrothermal", "magnetics.em_thermal", "assembly.multiboard_pi", "assembly.multiboard_thermal"),
        "depends_on": ("thermal.full", "si.deployable", "emi_emc.fullwave", "multiphysics.electrothermal"),
        "next_gate": "Typed conservative coupling operators, partitioned convergence control, checkpoint/restart and coupled V&V matrices.",
    },
)


def _state(workflows: list[Mapping[str, Any]], ready_ids: set[str]) -> tuple[str, list[str]]:
    missing = [str(item["id"]) for item in workflows if item["release_state"] in {"planned", "implementation_pending"}]
    unqualified = [str(item["id"]) for item in workflows if item["id"] not in ready_ids]
    if missing:
        return "implementation_blocked", missing
    if unqualified:
        return "qualification_blocked", unqualified
    return "deployable", []


def build_solver_suite_deployability(ledger: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build the authoritative dependency-ordered deployability report."""
    reviewed = native_capability_ledger() if ledger is None else validate_capability_ledger(ledger)
    by_id = {item["id"]: item for item in reviewed["workflows"]}
    ready = {item["id"] for item in release_ready_workflows(reviewed["workflows"])}
    results: list[dict[str, Any]] = []
    for profile in _PROFILES:
        unknown = [identifier for identifier in profile["workflows"] if identifier not in by_id]
        if unknown:
            state, blockers, workflows = "ledger_incomplete", unknown, []
        else:
            workflows = [by_id[identifier] for identifier in profile["workflows"]]
            state, blockers = _state(workflows, ready)
        dependency_blockers = [identifier for identifier in profile["depends_on"] if next((item for item in results if item["id"] == identifier and item["state"] == "deployable"), None) is None]
        if dependency_blockers and state == "deployable":
            state = "dependency_blocked"
        results.append({
            "id": profile["id"], "title": profile["title"], "state": state, "deployable": state == "deployable" and not dependency_blockers,
            "workflow_states": [{"id": item["id"], "release_state": item["release_state"], "validation_state": item["validation_state"],
                                 "immutable_qualification_bound": bool(item.get("release_qualification"))} for item in workflows],
            "workflow_blockers": blockers, "dependency_blockers": dependency_blockers,
            "next_gate": profile["next_gate"],
        })
    deployable_count = sum(bool(item["deployable"]) for item in results)
    return {
        "contract": CONTRACT,
        "status": "deployable" if deployable_count == len(results) else "blocked",
        "deployable": deployable_count == len(results),
        "policy": {
            "native_ownership_required": True,
            "immutable_release_qualification_required": True,
            "external_solver_is_comparison_not_product_owner": True,
            "dependency_order_enforced": True,
            "capability_labels_cannot_self_promote": True,
        },
        "summary": {"total": len(results), "deployable": deployable_count, "blocked": len(results) - deployable_count},
        "capabilities": results,
        "execution_order": [item["id"] for item in results],
    }


__all__ = ["CONTRACT", "build_solver_suite_deployability"]
