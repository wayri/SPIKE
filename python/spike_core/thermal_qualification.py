"""Machine-checkable release qualification for field-thermal solver adapters.

Runtime discovery and a solver's self-declared model status are deliberately
insufficient.  A production field job must be bound to immutable fixture
results covering its requested physics, conservation/convergence, independent
and measured correlation, and the supported release platforms.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, Mapping


QUALIFICATION_CONTRACT = "spike/thermal-solver-qualification-evidence/v1"
REQUIRED_RELEASE_PLATFORMS = frozenset({"windows-x64", "linux-x64"})
_SHA256 = re.compile(r"^[a-f0-9]{64}$")

_PHYSICS_GATES = {
    "solid_conduction": "pcb_solid",
    "transient_conduction": "transient",
    "thermal_contacts": "contact",
    "material_properties": "materials",
    "coatings": "coatings",
    "component_heat_source_table": "heat_sources",
    "package_shapes": "package_shapes",
    "mcad_parts": "mcad_parts",
    "enclosure": "enclosure",
    "heatsinks": "heatsink",
    "fans": "fan",
    "potting": "potting",
    "vacuum_radiation": "vacuum_radiation",
    "radiation": "radiation",
    "airflow": "airflow",
    "conjugate_heat_transfer": "cht",
    "electrothermal_iteration": "electrothermal",
}
_UNIVERSAL_GATES = frozenset({
    "energy_conservation",
    "mesh_convergence",
    "independent_correlation",
    "measured_correlation",
})


def required_qualification_gates(requested_physics: Iterable[str]) -> list[str]:
    """Return the deterministic release gate set for requested physics."""
    return sorted(_UNIVERSAL_GATES | {_PHYSICS_GATES[item] for item in requested_physics if item in _PHYSICS_GATES})


def validate_thermal_qualification(
    evidence: Any,
    *,
    solver_id: str,
    solver_version: str,
    requested_physics: Iterable[str],
) -> Dict[str, Any]:
    """Validate and normalize one qualification-evidence record.

    The function never opens a path or executes a probe.  Fixture/result
    digests are the immutable handoff from a separate trusted validation run.
    """
    issues: list[str] = []
    if not isinstance(evidence, Mapping) or evidence.get("contract") != QUALIFICATION_CONTRACT:
        return {"valid": False, "issues": [f"Qualification evidence must use {QUALIFICATION_CONTRACT}."], "covered_gates": [], "required_gates": required_qualification_gates(requested_physics)}

    solver = evidence.get("solver")
    if not isinstance(solver, Mapping) or solver.get("id") != solver_id:
        issues.append("Qualification evidence solver identity does not match the selected adapter.")
    if not isinstance(solver, Mapping) or str(solver.get("version") or "") != str(solver_version or ""):
        issues.append("Qualification evidence solver version does not match the selected adapter.")

    platforms = {str(item) for item in evidence.get("platforms", [])} if isinstance(evidence.get("platforms"), list) else set()
    missing_platforms = sorted(REQUIRED_RELEASE_PLATFORMS - platforms)
    if missing_platforms:
        issues.append(f"Release qualification is missing platforms: {', '.join(missing_platforms)}.")

    requested = {str(item) for item in requested_physics}
    capabilities = {str(item) for item in evidence.get("capabilities", [])} if isinstance(evidence.get("capabilities"), list) else set()
    missing_capabilities = sorted(requested - capabilities)
    if missing_capabilities:
        issues.append(f"Qualification evidence does not cover: {', '.join(missing_capabilities)}.")

    fixtures = evidence.get("fixtures")
    covered: set[str] = set()
    reference_types: set[str] = set()
    if not isinstance(fixtures, list) or not fixtures:
        issues.append("Qualification evidence requires passed validation fixtures.")
        fixtures = []
    for index, fixture in enumerate(fixtures):
        label = f"fixtures[{index}]"
        if not isinstance(fixture, Mapping):
            issues.append(f"{label} must be an object.")
            continue
        gate = str(fixture.get("gate") or "")
        status = str(fixture.get("status") or "")
        fixture_digest = str(fixture.get("fixture_sha256") or "")
        result_digest = str(fixture.get("result_sha256") or "")
        reference_type = str(fixture.get("reference_type") or "")
        if not gate or status != "passed":
            issues.append(f"{label} must name a passed gate.")
            continue
        if not _SHA256.fullmatch(fixture_digest) or not _SHA256.fullmatch(result_digest):
            issues.append(f"{label} must bind its fixture and result with SHA-256 digests.")
            continue
        if any(type(fixture.get(key)) not in (int, float) for key in ("tolerance", "observed")):
            issues.append(f"{label} tolerance and observed values must be JSON numbers.")
            continue
        try:
            tolerance = float(fixture.get("tolerance"))
            observed = float(fixture.get("observed"))
        except (TypeError, ValueError, OverflowError):
            issues.append(f"{label} tolerance and observed values must be numeric.")
            continue
        if not math.isfinite(tolerance) or tolerance < 0 or not math.isfinite(observed) or observed < 0 or observed > tolerance:
            issues.append(f"{label} did not satisfy its finite non-negative tolerance.")
            continue
        if reference_type not in {"analytic", "independent_solver", "measured"} or not str(fixture.get("reference_id") or ""):
            issues.append(f"{label} requires an identified analytic, independent-solver, or measured reference.")
            continue
        expected_reference = {
            "independent_correlation": "independent_solver",
            "measured_correlation": "measured",
        }.get(gate)
        if expected_reference is not None and reference_type != expected_reference:
            issues.append(f"{label} gate {gate} requires a {expected_reference} reference.")
            continue
        covered.add(gate)
        reference_types.add(reference_type)

    required = set(required_qualification_gates(requested))
    missing_gates = sorted(required - covered)
    if missing_gates:
        issues.append(f"Qualification fixtures are missing gates: {', '.join(missing_gates)}.")
    if "independent_solver" not in reference_types:
        issues.append("Qualification requires correlation against an identified independent solver.")
    if "measured" not in reference_types:
        issues.append("Qualification requires correlation against identified measured data.")

    return {
        "valid": not issues,
        "evidence_id": str(evidence.get("evidence_id") or ""),
        "covered_gates": sorted(covered),
        "required_gates": sorted(required),
        "platforms": sorted(platforms),
        "issues": issues,
    }


__all__ = [
    "QUALIFICATION_CONTRACT",
    "REQUIRED_RELEASE_PLATFORMS",
    "required_qualification_gates",
    "validate_thermal_qualification",
]
