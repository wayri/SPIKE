# SPDX-License-Identifier: Apache-2.0
"""Capacity admission for prescribed-voltage DC boundaries, using solved KCL."""
from collections import Counter, defaultdict
from math import fsum, isfinite

from .contracts import AnalysisResult, ValidationIssue

CAPABILITY = "source_current_feasibility"


def source_boundary_record(source, index, terminals, node_nets, anchor_id):
    return {
        "id": str(source.get("id", index + 1)), "geometry_anchor_id": anchor_id,
        "node": next(iter(terminals)), "boundary_nodes": list(terminals),
        "boundary_weights": list(terminals.values()), "net": node_nets[next(iter(terminals))],
        "voltage_v": float(source.get("voltage_v", source.get("voltage", 0))),
        "role": str(source.get("terminal_role", "source_positive")),
        "domain_id": str(source.get("domain_id", "default")),
    }


def has_current_limits(spec):
    return any("current_limit_a" in source for source in spec.sources)


def current_limit_issues(spec, supported=True):
    issues = []
    for index, source in enumerate(spec.sources):
        if "current_limit_a" not in source:
            continue
        value = source["current_limit_a"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
            issues.append(ValidationIssue("SPIKE-BE-PI-E-0110", "error",
                "Source current_limit_a must be a finite positive number in amperes.",
                path=f"analysis.sources[{index}].current_limit_a",
                suggestion="Enter a positive current capacity or omit the limit for an ideal unlimited source."))
    if has_current_limits(spec) and (not supported or spec.mode != "dc"):
        issues.append(ValidationIssue("SPIKE-BE-PI-E-0111", "error",
            "The selected solver does not support source current-capacity feasibility for this mode.",
            path="analysis.sources", suggestion="Select the DC resistive-network solver or explicitly remove the capacity requirement.", status="unsupported"))
    return issues


def capacity_failure(spec, issues, records=None, status="unsupported"):
    return AnalysisResult(analysis_id=spec.analysis_id, mode=spec.mode, status="failed",
        model_status="unsupported" if status == "unsupported" else "approximate",
        summary={"source_capacity_status": status},
        fields={"source_current_results": records or []}, issues=issues)


def source_capacity(spec, sources, edges, rhs):
    """I_source = sum(outgoing branch I) - external nodal injection, in A.

    Shared ideal boundary nodes do not determine individual source currents.
    A limit is a forward sourcing rating, not a reverse absorption rating.
    """
    owners = Counter(node for source in sources for node in source["boundary_nodes"])
    incident = defaultdict(list)
    for edge in edges:
        incident[edge["a"]].append(float(edge["current_a"]))
        incident[edge["b"]].append(-float(edge["current_a"]))
    records, issues = [], []
    for index, source in enumerate(sources):
        limit = spec.sources[index].get("current_limit_a")
        ambiguous = any(owners[node] > 1 for node in source["boundary_nodes"])
        current = None if ambiguous else fsum(
            fsum(incident[node]) - float(rhs[node]) for node in source["boundary_nodes"])
        # Return boundaries use inward current as the paired forward direction.
        forward = None if current is None else (-current if source["role"] == "source_return" else current)
        tolerance = 1e-9 * max(1.0, abs(forward or 0), limit or 0)
        state = "unlimited"
        if limit is not None:
            state = "indeterminate" if ambiguous else "reverse_flow_unsupported" if forward < -tolerance else "exceeded" if forward > limit + tolerance else "within_limit"
            if state != "within_limit":
                code = "SPIKE-BE-PI-E-0112" if state == "exceeded" else "SPIKE-BE-PI-E-0113"
                issues.append(ValidationIssue(code, "error",
                    f"Source {source['id']} current capacity: {state}.",
                    path=f"analysis.sources[{index}].current_limit_a",
                    suggestion="Reduce demand or increase reviewed source capacity; provide distinct resistive source contacts for sharing and a qualified model for reverse flow.",
                    status="violated" if state == "exceeded" else "unsupported"))
        records.append({"id": source["id"], "domain_id": source["domain_id"], "role": source["role"],
            "required_current_a": current, "forward_current_a": forward, "current_limit_a": limit,
            "headroom_a": None if limit is None or forward is None else limit - forward,
            "status": state, "current_allocation": "indeterminate" if ambiguous else "solved_kcl"})
    status = "unsupported" if any(record["status"] in {"indeterminate", "reverse_flow_unsupported"} for record in records) else "infeasible" if issues else "feasible" if has_current_limits(spec) else "not_requested"
    return records, issues, status
