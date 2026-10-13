# SPDX-License-Identifier: Apache-2.0
"""Declarative workspace routes; these never grant solver qualification."""
from __future__ import annotations


def validate_workspace_routes(contributes: dict, permissions: list[str]) -> None:
    if not isinstance(contributes, dict) or any(not isinstance(group, list) for group in contributes.values()):
        raise ValueError("Workspace contributions require lists of contribution objects.")
    entries = [entry for group in contributes.values() for entry in group]
    if any(not isinstance(entry, dict) or not isinstance(entry.get("id"), str) for entry in entries):
        raise ValueError("Workspace contributions require string identities.")
    identities = {entry["id"] for entry in entries}
    routes = set()
    allowed = {"id", "workspace", "operation", "label", "setup_contribution_id",
               "preview_contribution_id", "mesh_kind", "model_status", "compatible_solver_ids", "requires_board"}
    for entry in entries:
        values = entry.get("workspace_routes", [])
        if not isinstance(values, list) or len(values) > 20:
            raise ValueError("workspace_routes must be a bounded list.")
        for route in values:
            if not isinstance(route, dict) or set(route) - allowed:
                raise ValueError("Unsupported workspace route fields.")
            for key in ("id", "label", "model_status"):
                if not isinstance(route.get(key), str) or not 1 <= len(route[key]) <= 256:
                    raise ValueError(f"Workspace route requires bounded {key}.")
            if route["id"] in routes:
                raise ValueError("Duplicate workspace route ID.")
            routes.add(route["id"])
            if (not isinstance(route.get("workspace"), str) or route["workspace"] not in {"mesh", "pi", "si", "em", "thermal"}
                    or not isinstance(route.get("operation"), str) or route["operation"] not in {"mesh", "solve"}):
                raise ValueError("Unsupported workspace route domain or operation.")
            if route["model_status"] not in {"unvalidated", "experimental", "approximate", "unsupported"}:
                raise ValueError("Workspace metadata cannot grant physics validation.")
            for key in ("setup_contribution_id", "preview_contribution_id"):
                if key in route and (not isinstance(route[key], str) or route[key] not in identities):
                    raise ValueError("Workspace route references an undeclared contribution.")
            if 'requires_board' in route and type(route['requires_board']) is not bool:
                raise ValueError('requires_board must be boolean.')
            if route.get('requires_board', True) and "design.read" not in permissions:
                raise ValueError("Board workspace routes require design.read.")
            compatible = route.get("compatible_solver_ids", [])
            if not isinstance(compatible, list) or len(compatible) > 32 or any(not isinstance(v, str) or not 1 <= len(v) <= 256 for v in compatible):
                raise ValueError("Invalid compatible solver IDs.")
            if "mesh_kind" in route and (not isinstance(route["mesh_kind"], str) or route["mesh_kind"] not in {"tetrahedral", "cartesian_fdtd", "surface", "conductor_network"}):
                raise ValueError("Unsupported declared mesh kind.")
