"""Resource admission for CAD-neutral board assemblies.

The estimator is intentionally separate from solver validity.  It answers
whether an assembly is small enough to enter a workload under the configured
machine policy; it does not claim that the selected formulation is accurate or
even implemented for every retained entity.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Mapping

from .design_ir_v2 import AssemblyIRV1
from .assembly_scale import (
    MAX_ASSEMBLY_PARTS,
    MAX_BOARD_AREA_MM2,
    MAX_BOARD_EXTENT_MM,
    MAX_BOARDS,
    MAX_COMPONENTS_PER_BOARD,
    MAX_COPPER_LAYERS,
    MAX_NETS_PER_BOARD,
    design_scale,
)


GIB = 1024 ** 3
MIN_MEMORY_GB = 2.0
DEFAULT_MACHINE_FRACTION = 0.75


_WORKLOADS: Dict[str, Dict[str, Any]] = {
    "visualization": {
        "fixed": 256 * 1024 ** 2,
        "board": 24 * 1024 ** 2,
        "layer": 2 * 1024 ** 2,
        "primitive": 512,
        "component": 2 * 1024,
        "net": 1024,
        "board_area_mm2": 8,
        "part": 4 * 1024 ** 2,
        "harness_pin": 16 * 1024,
        "model": "bounded scene geometry and GPU staging estimate",
    },
    "pi_dc": {
        "fixed": 512 * 1024 ** 2,
        "board": 48 * 1024 ** 2,
        "layer": 8 * 1024 ** 2,
        "primitive": 24 * 1024,
        "component": 12 * 1024,
        "net": 2 * 1024,
        "board_area_mm2": 24,
        "part": 2 * 1024 ** 2,
        "harness_pin": 128 * 1024,
        "model": "sparse conductor graph plus result and mesh workspace estimate",
    },
    "pi_ac": {
        "fixed": 1024 * 1024 ** 2,
        "board": 64 * 1024 ** 2,
        "layer": 12 * 1024 ** 2,
        "primitive": 12 * 1024,
        "component": 16 * 1024,
        "net": 4 * 1024,
        "board_area_mm2": 48,
        "part": 2 * 1024 ** 2,
        "harness_pin": 256 * 1024,
        "dense_bytes_per_unknown_squared": 96,
        "model": "dense PEEC/RLCG upper-bound workspace estimate",
    },
    "thermal": {
        "fixed": 1024 * 1024 ** 2,
        "board": 80 * 1024 ** 2,
        "layer": 16 * 1024 ** 2,
        "primitive": 32 * 1024,
        "component": 24 * 1024,
        "net": 2 * 1024,
        "board_area_mm2": 96,
        "part": 12 * 1024 ** 2,
        "harness_pin": 128 * 1024,
        "model": "solid thermal mesh, contacts, fields, and result workspace estimate",
    },
    "full_wave": {
        "fixed": 2 * GIB,
        "board": 128 * 1024 ** 2,
        "layer": 24 * 1024 ** 2,
        "primitive": 64 * 1024,
        "component": 8 * 1024,
        "net": 8 * 1024,
        "board_area_mm2": 192,
        "part": 16 * 1024 ** 2,
        "harness_pin": 512 * 1024,
        "model": "pre-mesh full-wave geometry and field-state admission estimate",
    },
}


def _physical_memory_bytes() -> int | None:
    """Return total physical memory without adding a production dependency."""

    try:
        if os.name == "nt":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_phys", ctypes.c_ulonglong),
                    ("avail_phys", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("avail_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("avail_virtual", ctypes.c_ulonglong),
                    ("avail_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.total_phys)
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        page_count = int(os.sysconf("SC_PHYS_PAGES"))
        total = page_size * page_count
        return total if total > 0 else None
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def estimate_assembly_resources(
    assembly: AssemblyIRV1 | Mapping[str, Any],
    designs: Mapping[str, Any],
    *,
    workload: str,
    memory_limit_gb: float,
    cpu_limit: int | None = None,
    physical_memory_bytes: int | None = None,
    machine_fraction: float = DEFAULT_MACHINE_FRACTION,
) -> Dict[str, Any]:
    """Return a deterministic, fail-closed assembly admission decision."""

    assembly_value = assembly if isinstance(assembly, AssemblyIRV1) else AssemblyIRV1.from_dict(assembly)
    if workload not in _WORKLOADS:
        raise ValueError(f"Unsupported assembly workload: {workload}")
    try:
        configured_gb = float(memory_limit_gb)
    except (TypeError, ValueError) as exc:
        raise ValueError("Assembly memory limit must be a number in GB.") from exc
    if not 0.1 <= float(machine_fraction) <= 0.9:
        raise ValueError("Assembly machine memory fraction must be between 0.1 and 0.9.")

    detected_cpu = max(os.cpu_count() or 1, 1)
    requested_cpu = detected_cpu if cpu_limit is None else int(cpu_limit)
    effective_cpu = min(max(requested_cpu, 1), detected_cpu)
    detected_memory = physical_memory_bytes if physical_memory_bytes is not None else _physical_memory_bytes()
    configured_bytes = max(int(configured_gb * GIB), 0)
    machine_ceiling = (
        int(detected_memory * machine_fraction)
        if detected_memory is not None and detected_memory > 0
        else configured_bytes
    )
    effective_limit = min(configured_bytes, machine_ceiling)

    issues = []
    if configured_gb < MIN_MEMORY_GB:
        issues.append({
            "code": "ASSEMBLY_MEMORY_LIMIT_INVALID",
            "severity": "error",
            "message": "Assembly solver memory limit must be at least 2 GB.",
        })
    if len(assembly_value.boards) > MAX_BOARDS:
        issues.append({"code": "ASSEMBLY_BOARD_LIMIT_EXCEEDED", "severity": "error", "message": f"Assembly exceeds the {MAX_BOARDS}-board product limit."})
    if len(assembly_value.parts) > MAX_ASSEMBLY_PARTS:
        issues.append({"code": "ASSEMBLY_PART_LIMIT_EXCEEDED", "severity": "error", "message": "Assembly exceeds the 100-part MCAD limit."})

    totals = {
        "boards": len(assembly_value.boards), "copper_layers": 0,
        "primitives": 0, "components": 0, "nets": 0,
        "declared_board_area_mm2": 0.0, "boards_with_declared_dimensions": 0,
    }
    board_summaries = []
    for board in assembly_value.boards:
        design = designs.get(board.design_id)
        if design is None:
            issues.append({
                "code": "ASSEMBLY_DESIGN_UNRESOLVED",
                "severity": "error",
                "message": f"Board {board.id} references unavailable design {board.design_id}.",
                "entity_id": board.id,
            })
            continue
        try:
            counts = design_scale(design)
        except ValueError as exc:
            issues.append({
                "code": "ASSEMBLY_BOARD_DIMENSIONS_INVALID",
                "severity": "error",
                "message": f"Board {board.id} has invalid declared dimensions: {exc}",
                "entity_id": board.id,
            })
            continue
        if counts["copper_layers"] > MAX_COPPER_LAYERS:
            issues.append({
                "code": "ASSEMBLY_LAYER_LIMIT_EXCEEDED",
                "severity": "error",
                "message": f"Board {board.id} has {counts['copper_layers']} copper layers; the supported maximum is 32.",
                "entity_id": board.id,
            })
        if counts["components"] > MAX_COMPONENTS_PER_BOARD:
            issues.append({
                "code": "ASSEMBLY_COMPONENT_LIMIT_EXCEEDED",
                "severity": "error",
                "message": f"Board {board.id} has {counts['components']} components; the supported maximum is {MAX_COMPONENTS_PER_BOARD}.",
                "entity_id": board.id,
            })
        if counts["nets"] > MAX_NETS_PER_BOARD:
            issues.append({
                "code": "ASSEMBLY_NET_LIMIT_EXCEEDED",
                "severity": "error",
                "message": f"Board {board.id} has {counts['nets']} nets; the supported maximum is {MAX_NETS_PER_BOARD}.",
                "entity_id": board.id,
            })
        size = counts["board_size_mm"]
        if size is not None and (size[0] > MAX_BOARD_EXTENT_MM or size[1] > MAX_BOARD_EXTENT_MM):
            issues.append({
                "code": "ASSEMBLY_BOARD_SIZE_LIMIT_EXCEEDED",
                "severity": "error",
                "message": (
                    f"Board {board.id} is {size[0]:g} mm by {size[1]:g} mm; the supported maximum is "
                    f"{MAX_BOARD_EXTENT_MM:g} mm by {MAX_BOARD_EXTENT_MM:g} mm."
                ),
                "entity_id": board.id,
            })
        totals["copper_layers"] += counts["copper_layers"]
        totals["primitives"] += counts["primitives"]
        totals["components"] += counts["components"]
        totals["nets"] += counts["nets"]
        if counts["board_area_mm2"] is not None:
            totals["declared_board_area_mm2"] += counts["board_area_mm2"]
            totals["boards_with_declared_dimensions"] += 1
        board_summaries.append({"board_id": board.id, "design_id": board.design_id, **counts})

    harness_pins = sum(len(item.pin_map) for item in assembly_value.harnesses)
    profile = _WORKLOADS[workload]
    estimated_bytes = (
        profile["fixed"]
        + totals["boards"] * profile["board"]
        + totals["copper_layers"] * profile["layer"]
        + totals["primitives"] * profile["primitive"]
        + totals["components"] * profile["component"]
        + totals["nets"] * profile["net"]
        + totals["declared_board_area_mm2"] * profile["board_area_mm2"]
        + len(assembly_value.parts) * profile["part"]
        + harness_pins * profile["harness_pin"]
    )
    dense_unknowns = 0
    if "dense_bytes_per_unknown_squared" in profile:
        # Admission uses one lower-bounded unknown per retained primitive or
        # net. The native mesher will replace this with its exact count.
        dense_unknowns = max(totals["primitives"], totals["nets"], harness_pins, 1)
        estimated_bytes += profile["dense_bytes_per_unknown_squared"] * dense_unknowns ** 2

    if estimated_bytes > effective_limit:
        issues.append({
            "code": "ASSEMBLY_MEMORY_BUDGET_EXCEEDED",
            "severity": "error",
            "message": (
                f"Estimated {workload} workspace is {estimated_bytes / GIB:.2f} GB, "
                f"above the effective {effective_limit / GIB:.2f} GB limit."
            ),
        })

    can_admit = not any(issue["severity"] == "error" for issue in issues)
    return {
        "contract": "spike/assembly-resource-admission/v1",
        "workload": workload,
        "state": "admitted" if can_admit else "blocked",
        "can_admit": can_admit,
        "configured_memory_gb": configured_gb,
        "configured_memory_bytes": configured_bytes,
        "detected_physical_memory_bytes": detected_memory,
        "machine_memory_fraction": machine_fraction,
        "effective_memory_limit_bytes": effective_limit,
        "requested_cpu_threads": requested_cpu,
        "detected_cpu_threads": detected_cpu,
        "effective_cpu_threads": effective_cpu,
        "estimated_workspace_bytes": int(estimated_bytes),
        "estimated_workspace_gb": estimated_bytes / GIB,
        "estimation_model": profile["model"],
        "dense_unknown_upper_bound": dense_unknowns,
        "totals": {**totals, "assembly_parts": len(assembly_value.parts), "harness_pins": harness_pins},
        "boards": board_summaries,
        "per_board_limits": {
            "maximum_boards": MAX_BOARDS,
            "maximum_copper_layers": MAX_COPPER_LAYERS,
            "maximum_extent_mm": MAX_BOARD_EXTENT_MM,
            "maximum_area_mm2": MAX_BOARD_AREA_MM2,
            "maximum_components": MAX_COMPONENTS_PER_BOARD,
            "maximum_nets": MAX_NETS_PER_BOARD,
        },
        "issues": issues,
        "meaning": "Resource admission only; solver capability, convergence, and physical validity are separate release gates.",
    }
