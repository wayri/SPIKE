# SPDX-License-Identifier: Apache-2.0
"""Logical solver blocks and inert dependency planning; no package execution.

This metadata describes workflow composition, not independently shipped archives,
runtime availability, or numerical qualification. Optional edges never expand plans.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from . import __version__

SOLVER_BLOCK_CONTRACT = "spike/solver-blocks/v1"
GROUPS = [
    {"id": identifier, "name": name} for identifier, name in (
        ("core", "Base and shared services"), ("pcb", "PCB"),
        ("harness", "Harness"), ("mcad", "MCAD collaboration"),
        ("circuits", "Circuits and SPIKES Studio"), ("pi", "Power integrity"),
        ("si", "Signal integrity"), ("cfd", "CFD"), ("cht", "CHT"),
        ("thermal", "Thermal"), ("electromagnetics", "Electromagnetics"),
        ("mechanics", "Structural mechanics"), ("execution", "Execution and coupling"),
    )
]


def _block(identifier: str, name: str, groups: list[str], requires: list[str],
           *, capability: bool = False, optional: tuple[str, ...] = (),
           delivery: str = "bundled", description: str = "",
           external_requirements: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "id": identifier, "name": name, "groups": groups, "requires": requires,
        "optional": list(optional), "capability_ids": [identifier] if capability else [],
        "delivery": delivery, "description": description or (
            "Bundled workflow code; existing numerical status and runtime admission still apply."
        ), **({"external_requirements": list(external_requirements)} if external_requirements else {}),
    }


BLOCKS = [
    _block("core", "Base contracts and worker", ["core"], [],
           description="Mandatory contracts, worker transport, diagnostics and project services."),
    _block("geometry", "Shared geometry and identity", ["core", "mcad", "pcb"], ["core"]),
    _block("materials", "Shared material evidence", ["core", "thermal", "mechanics"], ["core"]),
    _block("mesh", "Shared mesh contracts and admission", ["core", "mcad"], ["geometry"],
           description="Mesh data/admission; a mesh generator remains optional."),
    _block("pcb-adapter", "PCB geometry adapters", ["pcb"], ["geometry"]),
    _block("harness-adapter", "Harness conductor and network workflows", ["harness"],
           ["geometry", "materials", "si-networks"], optional=("pi-dc",),
           description="Explicit wire DC and supplied conductor SI; no arbitrary shield or radiation qualification."),
    _block("mcad-adapter", "MCAD collaboration and retained-solid handoff", ["mcad"], ["geometry"],
           optional=("mesh", "mcad-freecad"), description="Occurrence-bound geometry exchange, not general MCAD authoring."),
    _block("mcad-freecad", "FreeCAD export and collaboration adapter", ["mcad"],
           ["geometry", "external-freecad"],
           description="Bundled explicit export adapter; FreeCAD is a separately licensed application/runtime."),
    _block("thermal-calculix", "CalculiX solid thermal adapter", ["thermal", "mechanics"],
           ["mesh", "materials", "external-calculix"],
           description="Bundled bounded solid thermal adapter; separately admitted CalculiX runtime required."),
    _block("thermal-openfoam", "OpenFOAM cooling and CHT adapter", ["cfd", "cht", "thermal"],
           ["mesh", "materials", "external-openfoam"],
           description="Bundled cooling adapter; separately admitted OpenFOAM runtime and case required."),
    _block("cht-assembly", "Assembly solid/fluid CHT adapter", ["cht", "cfd", "thermal", "mcad"],
           ["thermal-solids", "mesh", "materials", "thermal-openfoam"],
           description="Bounded assembly case preparation and admitted external execution; no general CHT qualification."),
    _block('pi-solid-dc', 'Retained-volume 3D DC conduction', ['pi', 'pcb'], ['mesh', 'materials'],
           capability=True, delivery='bundled', optional=()),
    _block('pi-transient', 'Geometry PEEC RLC transient', ['pi', 'pcb'], ['pi-peec', 'circuit-native'],
           capability=True, delivery='bundled', optional=()),
    _block('mechanics-static', 'Static tetrahedral structural mechanics', ['mechanics', 'mcad'], ['mesh', 'materials'],
           capability=True, delivery='bundled', optional=()),
    _block('mechanics-thermoelastic', 'Same-mesh thermal-to-mechanical coupling', ['mechanics', 'mcad'], ['mechanics-static', 'thermal-solids'],
           capability=True, delivery='bundled', optional=()),
    _block('planned-mom', 'Surface method of moments', ['electromagnetics'], ['core'],
           capability=True, delivery='planned', optional=()),
    _block('circuit-native', 'Native circuit OP, AC and transient', ['circuits'], ['core'],
           capability=True, delivery='bundled', optional=()),
    _block('circuit-adaptive', 'Adaptive BDF2 and trapezoidal transient', ['circuits'], ['circuit-native'],
           capability=True, delivery='bundled', optional=()),
    _block('circuit-equations', 'Electrical I/Q equations and package parasitics', ['circuits'], ['circuit-native'],
           capability=True, delivery='bundled', optional=()),
    _block('circuit-physics-parts', 'Supplied multi-terminal physics parts', ['circuits'], ['circuit-equations'],
           capability=True, delivery='bundled', optional=()),
    _block('circuit-smps', 'Ideal CCM SMPS and control-loop stability', ['circuits'], ['core'],
           capability=True, delivery='bundled', optional=()),
    _block('circuit-battery', 'One-RC battery reference study', ['circuits'], ['core'],
           capability=True, delivery='bundled', optional=()),
    _block('circuit-libraries', 'Passive, digital and compiled controller models', ['circuits'], ['circuit-native'],
           capability=True, delivery='bundled', optional=()),
    _block('circuit-pdk', 'Open-PDK inventory and ngspice circuit studies', ['circuits'], ['core', 'external-ngspice'],
           capability=True, delivery='bundled', optional=(), description="Bundled adapter; requires separately licensed runtime and workflow-specific admission."),
    _block('circuit-asic', 'IC/ASIC preflight and KLayout inspection', ['circuits'], ['core', 'external-klayout'],
           capability=True, delivery='bundled', optional=(), description="Bundled adapter; requires separately licensed runtime and workflow-specific admission."),
    _block('circuit-tcad', 'Native 1D equilibrium semiconductor field', ['circuits'], ['core'],
           capability=True, delivery='bundled', optional=()),
    _block('pi-dc', 'Board DC resistance and source-capacity screening', ['pi', 'pcb'], ['pcb-adapter', 'materials'],
           capability=True, delivery='bundled', optional=()),
    _block('pi-peec', 'PEEC R/L and approximate RLCG extraction', ['pi', 'pcb'], ['pi-dc'],
           capability=True, delivery='bundled', optional=()),
    _block('pi-pdn', 'Explicit PDN/filter and simultaneous load transients', ['pi', 'pcb'], ['core'],
           capability=True, delivery='bundled', optional=()),
    _block('pi-capacitance', 'Finite-dielectric electrostatic capacitance', ['pi', 'pcb'], ['mesh', 'materials'],
           capability=True, delivery='bundled', optional=()),
    _block('pi-dielectric-ac', 'Finite-dielectric AC admittance', ['pi', 'pcb'], ['pi-capacitance'],
           capability=True, delivery='bundled', optional=()),
    _block('pi-reduction', 'Passive sampled port reduction', ['pi', 'pcb'], ['pi-dielectric-ac'],
           capability=True, delivery='bundled', optional=()),
    _block('pi-engineering', 'Converter, copper and capacitor screening', ['pi', 'pcb'], ['core'],
           capability=True, delivery='bundled', optional=()),
    _block('si-networks', 'Touchstone and sampled network processing', ['si', 'pcb'], ['core'],
           capability=True, delivery='bundled', optional=()),
    _block('si-channels', 'Single and coupled quasi-TEM channel extraction', ['si', 'pcb'], ['pcb-adapter', 'si-networks', 'materials'],
           capability=True, delivery='bundled', optional=('thermal-board',)),
    _block('si-eye', 'Eye masks and protocol suite input review', ['si', 'pcb'], ['si-networks'],
           capability=True, delivery='bundled', optional=()),
    _block('thermal-board', 'Object networks and layered board thermal', ['thermal'], ['pcb-adapter', 'materials'],
           capability=True, delivery='bundled', optional=()),
    _block('thermal-solids', 'Retained tetrahedral solid thermal', ['thermal'], ['mesh', 'materials'],
           capability=True, delivery='bundled', optional=()),
    _block('thermal-electrothermal', 'Assembly and multiboard electrothermal feedback', ['thermal'], ['thermal-solids', 'pi-solid-dc', 'pi-pdn'],
           capability=True, delivery='bundled', optional=()),
    _block('thermal-pwm', 'Native PWM and retained-volume electrothermal', ['thermal'], ['thermal-solids', 'circuit-native'],
           capability=True, delivery='bundled', optional=()),
    _block('thermal-channel', 'Laminar channel and fan-system screening', ['thermal'], ['materials'],
           capability=True, delivery='bundled', optional=()),
    _block('cfd-native', 'Native laminar 2D CFD cavity', ['cfd'], ['core'],
           capability=True, delivery='bundled', optional=()),
    _block('cfd-su2', 'SU2 cavity and three-zone CHT references', ['cfd', 'cht', 'thermal'], ['core', 'external-su2', 'mesh', 'materials'],
           capability=True, delivery='bundled', optional=(), description="Bundled adapter; requires separately licensed runtime and workflow-specific admission."),
    _block('thermal-external', 'CalculiX solid thermal and OpenFOAM cooling', ['thermal', 'cht', 'cfd', 'mcad'], ['core'],
           capability=True, delivery='bundled', optional=('thermal-calculix', 'thermal-openfoam'),
           description="External thermal workflow index; select one concrete backend adapter. Each backend has separate runtime admission."),
    _block('em-magnetic', 'Planar nonlinear magnetic FEM machines', ['electromagnetics'], ['mesh', 'materials'],
           capability=True, delivery='bundled', optional=()),
    _block('em-lumped', 'Lumped PM DC motor and electromagnet', ['electromagnetics'], ['materials'],
           capability=True, delivery='bundled', optional=()),
    _block('em-openems', 'openEMS board and retained-volume fields', ['electromagnetics'], ['core', 'external-openems', 'mesh', 'materials'],
           capability=True, delivery='bundled', optional=(), description="Bundled adapter; requires separately licensed runtime and workflow-specific admission."),
    _block('em-palace', 'PALACE native configuration and field inspection', ['electromagnetics'], ['core', 'external-palace', 'mesh', 'materials'],
           capability=True, delivery='bundled', optional=(), description="Bundled adapter; requires separately licensed runtime and workflow-specific admission."),
    _block('circuit-xyce', 'Xyce bounded circuit workbench', ['circuits'], ['core', 'external-xyce'],
           capability=True, delivery='bundled', optional=(), description="Bundled adapter; requires separately licensed runtime and workflow-specific admission."),
    _block('execution-cosim', 'Scalar co-simulation and recorded digital twins', ['execution'], ['core'],
           capability=True, delivery='bundled', optional=('circuit-native', 'thermal-solids', 'cfd-native')),
    _block('execution-workers', 'Parallel jobs and enrolled remote workers', ['execution'], ['core'],
           capability=True, delivery='bundled', optional=()),
    _block('execution-extensions', 'Meshing, optional engines and acceleration', ['execution'], ['core'],
           capability=True, delivery='bundled', optional=()),
    _block('em-emerge', 'EMerge multilayer SI and radiation FEM', ['electromagnetics'], ['core', 'external-emerge', 'mesh', 'materials'],
           capability=True, delivery='bundled', optional=(), description="Bundled adapter; requires separately licensed runtime and workflow-specific admission."),
    _block('execution-gmsh', 'Gmsh PCB and retained assembly volume meshes', ['execution'], ['core', 'external-gmsh', 'mesh', 'materials'],
           capability=True, delivery='bundled', optional=(), description="Bundled adapter; requires separately licensed runtime and workflow-specific admission."),
    _block('execution-sparselizard', 'sparseLizard case preparation and qualification gates', ['execution'], ['core', 'external-sparselizard', 'mesh', 'materials'],
           capability=True, delivery='bundled', optional=(), description="Bundled adapter; requires separately licensed runtime and workflow-specific admission."),
    _block('planned-elmer', 'Elmer FEM solver integration', ['execution'], ['core'],
           capability=True, delivery='planned', optional=()),
    _block('planned-fullwave', 'Owned arbitrary-PCB full-wave solver', ['electromagnetics'], ['core'],
           capability=True, delivery='planned', optional=()),
    _block('planned-tcad', 'Full TCAD and ASIC physical closure', ['circuits'], ['core'],
           capability=True, delivery='planned', optional=()),
    _block("external-calculix", "External calculix runtime", ['thermal', 'mechanics'], ["core"],
           delivery="external", external_requirements=("Separately licensed calculix runtime; platform/runtime and case admission required.",),
           description="Not bundled or automatically installed; this preview does not probe local availability."),
    _block("external-emerge", "External emerge runtime", ['electromagnetics'], ["core"],
           delivery="external", external_requirements=("Separately licensed emerge runtime; platform/runtime and case admission required.",),
           description="Not bundled or automatically installed; this preview does not probe local availability."),
    _block("external-freecad", "External FreeCAD application/runtime", ["mcad"], ["core"],
           delivery="external", external_requirements=("Separately licensed FreeCAD runtime; platform and export admission required.",),
           description="Not bundled or automatically installed; this preview does not probe local availability."),
    _block("external-gmsh", "External gmsh runtime", ['execution'], ["core"],
           delivery="external", external_requirements=("Separately licensed gmsh runtime; platform/runtime and case admission required.",),
           description="Not bundled or automatically installed; this preview does not probe local availability."),
    _block("external-klayout", "External klayout runtime", ['circuits'], ["core"],
           delivery="external", external_requirements=("Separately licensed klayout runtime; platform/runtime and case admission required.",),
           description="Not bundled or automatically installed; this preview does not probe local availability."),
    _block("external-ngspice", "External ngspice runtime", ['circuits'], ["core"],
           delivery="external", external_requirements=("Separately licensed ngspice runtime; platform/runtime and case admission required.",),
           description="Not bundled or automatically installed; this preview does not probe local availability."),
    _block("external-openems", "External openems runtime", ['electromagnetics'], ["core"],
           delivery="external", external_requirements=("Separately licensed openems runtime; platform/runtime and case admission required.",),
           description="Not bundled or automatically installed; this preview does not probe local availability."),
    _block("external-openfoam", "External openfoam runtime", ['cfd', 'cht', 'thermal'], ["core"],
           delivery="external", external_requirements=("Separately licensed openfoam runtime; platform/runtime and case admission required.",),
           description="Not bundled or automatically installed; this preview does not probe local availability."),
    _block("external-palace", "External palace runtime", ['electromagnetics'], ["core"],
           delivery="external", external_requirements=("Separately licensed palace runtime; platform/runtime and case admission required.",),
           description="Not bundled or automatically installed; this preview does not probe local availability."),
    _block("external-sparselizard", "External sparselizard runtime", ['execution'], ["core"],
           delivery="external", external_requirements=("Separately licensed sparselizard runtime; platform/runtime and case admission required.",),
           description="Not bundled or automatically installed; this preview does not probe local availability."),
    _block("external-su2", "External su2 runtime", ['cfd', 'cht'], ["core"],
           delivery="external", external_requirements=("Separately licensed su2 runtime; platform/runtime and case admission required.",),
           description="Not bundled or automatically installed; this preview does not probe local availability."),
    _block("external-xyce", "External xyce runtime", ['circuits'], ["core"],
           delivery="external", external_requirements=("Separately licensed xyce runtime; platform/runtime and case admission required.",),
           description="Not bundled or automatically installed; this preview does not probe local availability."),
]


def validate_graph(blocks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Fail closed for inconsistent descriptors and required or optional cycles."""
    index = {block["id"]: block for block in blocks}
    if len(index) != len(blocks):
        raise ValueError("Duplicate solver block ID")
    group_ids = {group["id"] for group in GROUPS}
    for block in blocks:
        if not block["groups"] or set(block["groups"]) - group_ids:
            raise ValueError(f"Unknown or missing groups for {block['id']}")
        for dependency in block["requires"] + block["optional"]:
            if dependency not in index:
                raise ValueError(f"Unknown dependency {dependency} for {block['id']}")
    active: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in active:
            raise ValueError(f"Solver block dependency cycle at {identifier}")
        if identifier in visited:
            return
        active.add(identifier)
        for dependency in index[identifier]["requires"] + index[identifier]["optional"]:
            visit(dependency)
        active.remove(identifier)
        visited.add(identifier)

    for identifier in index:
        visit(identifier)
    return index


def _selection(params: dict[str, Any], key: str, valid: set[str]) -> list[str]:
    values = params.get(key, [])
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ValueError(f"{key} must be an array of string IDs")
    unknown = set(values) - valid
    if unknown:
        raise ValueError(f"Unknown {key}: {', '.join(sorted(unknown))}")
    return list(dict.fromkeys(values))


def solver_blocks_catalog(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a deterministic, side-effect-free bulk selection preview.

    Omitted selection includes all bundled code. Explicit empty arrays request
    only mandatory base. External prerequisites are unresolved, never installed.
    """
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError("solver_blocks params must be an object")
    if set(params) - {"selected_blocks", "selected_groups"}:
        raise ValueError("Unknown solver_blocks parameter")
    index = validate_graph(BLOCKS)
    selected = _selection(params, "selected_blocks", set(index))
    groups = _selection(params, "selected_groups", {group["id"] for group in GROUPS})
    if not params:
        selected = [block["id"] for block in BLOCKS if block["delivery"] == "bundled"]
    requested = set(selected)
    requested.update(block["id"] for block in BLOCKS if set(groups) & set(block["groups"]))
    requested_order = [identifier for identifier in index if identifier in requested]
    ordered: list[str] = []
    seen: set[str] = set()

    def include(identifier: str) -> None:
        if identifier in seen:
            return
        seen.add(identifier)
        for dependency in index[identifier]["requires"]:
            include(dependency)
        ordered.append(identifier)

    include("core")
    for identifier in requested_order:
        include(identifier)
    blocked: list[str] = []
    for identifier in ordered:
        block = index[identifier]
        if block["delivery"] != "bundled" or any(dep in blocked for dep in block["requires"]):
            blocked.append(identifier)
    warnings = [
        "Logical blocks share the current monolithic payload; selection does not change installed files.",
        "Bundled code does not establish runtime readiness or numerical qualification.",
    ]
    if blocked:
        warnings.append("External runtimes and planned blocks are unresolved; dependent workflows remain gated. No availability probe or installation was performed.")
    return {
        "contract": SOLVER_BLOCK_CONTRACT, "catalog_version": __version__,
        "packaging_mode": "bundled_all",
        "managed_downloads": False, "groups": deepcopy(GROUPS), "blocks": deepcopy(BLOCKS),
        "plan": {
            "requested_blocks": requested_order,
            "required_blocks": [identifier for identifier in ordered if identifier not in requested],
            "ordered_blocks": ordered, "blocked_blocks": blocked,
            "warnings": warnings, "action": "preview_only",
        },
    }


def handle_solver_blocks(params: dict[str, Any]) -> dict[str, Any]:
    """Translate validation failures into the existing canonical worker envelope."""
    from .service_helpers import error_response
    try:
        if not isinstance(params, dict):
            raise ValueError("solver_blocks params must be an object")
        return {"ok": True, "result": solver_blocks_catalog(params)}
    except ValueError as exc:
        return error_response(
            "SPIKE-BE-IPC-E-0001", str(exc), context={"method": "solver_blocks"},
        )


if __name__ == "__main__":
    import json
    print(json.dumps(solver_blocks_catalog(), indent=2, ensure_ascii=True))
