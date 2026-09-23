"""Deterministic analytical and convergence benchmarks for copper solvers."""

from __future__ import annotations

from dataclasses import dataclass
from math import log, pi
from typing import Any, Dict, Iterable, List, Sequence

import numpy as np

from .contracts import AnalysisSpec, DesignIR
from .field_circuit_cosim import (
    FIELD_RESULT_CONTRACT,
    REQUEST_CONTRACT as FIELD_CIRCUIT_REQUEST_CONTRACT,
    run_iterative_field_circuit_cosimulation,
)
from .hybrid_mesh import (
    COPPER_CONDUCTIVITY_S_M,
    HybridMesh,
    MeshBranch,
    MeshNode,
    build_hybrid_mesh,
    nearest_mesh_node,
)
from .peec_plugin import (
    _solve_shared_reference_port_matrix,
    native_available,
    solve_peec_2_5d,
)
from .benchmark_native_mna import run_native_mna_reference_benchmarks
from .benchmark_pdn import run_pdn_two_port_loading_benchmark
from .quasistatic_capacitance import EPSILON_0_F_M, estimate_line_capacitance_per_m
from .spice_workspace import SPICE_WORKSPACE_CONTRACT
from .transient_peec import solve_peec_rl_transient


@dataclass
class Benchmark:
    name: str
    status: str
    measured: float | None
    expected: float | None
    relative_error: float | None
    tolerance: float | None
    units: str
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


def _relative_error(measured: float, expected: float) -> float:
    return abs(measured - expected) / max(abs(expected), 1e-30)


def _result(
    name: str,
    measured: float,
    expected: float,
    tolerance: float,
    units: str,
    detail: str,
) -> Benchmark:
    error = _relative_error(measured, expected)
    return Benchmark(
        name,
        "passed" if error <= tolerance else "failed",
        measured,
        expected,
        error,
        tolerance,
        units,
        detail,
    )


def _stackup() -> List[Dict[str, Any]]:
    return [
        {"name": "F.Cu", "type": "copper", "thickness": 0.035},
        {"name": "dielectric 1", "type": "core", "thickness": 1.53, "epsilon_r": 4.2},
        {"name": "B.Cu", "type": "copper", "thickness": 0.035},
    ]


def _equivalent_resistance(
    mesh: HybridMesh,
    source_nodes: Sequence[int],
    sink_nodes: Sequence[int],
) -> float:
    size = len(mesh.nodes)
    conductance = np.zeros((size, size), dtype=float)
    for branch in mesh.branches:
        value = 1.0 / branch.resistance_ohm
        a, b = branch.node_p, branch.node_n
        conductance[a, a] += value
        conductance[b, b] += value
        conductance[a, b] -= value
        conductance[b, a] -= value
    source, sink = set(source_nodes), set(sink_nodes)
    known = sorted(source | sink)
    unknown = [node for node in range(size) if node not in source and node not in sink]
    voltage = np.zeros(size, dtype=float)
    voltage[list(source)] = 1.0
    if unknown:
        rhs = -conductance[np.ix_(unknown, known)] @ voltage[known]
        voltage[unknown] = np.linalg.solve(conductance[np.ix_(unknown, unknown)], rhs)
    current = 0.0
    for branch in mesh.branches:
        if branch.node_p in source and branch.node_n not in source:
            current += (voltage[branch.node_p] - voltage[branch.node_n]) / branch.resistance_ohm
        elif branch.node_n in source and branch.node_p not in source:
            current += (voltage[branch.node_n] - voltage[branch.node_p]) / branch.resistance_ohm
    if current <= 0:
        raise ValueError("benchmark mesh has no conductive source-to-sink path")
    return 1.0 / current


def _port_resistance(mesh: HybridMesh, source: Dict[str, Any], sink: Dict[str, Any], net: str) -> float:
    source_node = nearest_mesh_node(mesh, source, net)
    sink_node = nearest_mesh_node(mesh, sink, net)
    if source_node is None or sink_node is None:
        raise ValueError("benchmark terminals did not map to the hybrid mesh")
    return _equivalent_resistance(mesh, [source_node], [sink_node])


def _trace_benchmark() -> Benchmark:
    design = DesignIR(
        name="analytical straight trace",
        layers=[{"name": "F.Cu"}],
        stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        tracks=[{
            "id": "trace",
            "start": [0, 0],
            "end": [20, 0],
            "width": 1.0,
            "layer": "F.Cu",
            "net_name": "VCC",
        }],
    )
    mesh = build_hybrid_mesh(
        design,
        AnalysisSpec(mode="dc", net_names=["VCC"], mesh={"target_size_mm": 1.25}),
    )
    measured = sum(branch.resistance_ohm for branch in mesh.branches)
    expected = 20e-3 / (COPPER_CONDUCTIVITY_S_M * 1e-3 * 0.035e-3)
    return _result(
        "straight_trace_dc_resistance",
        measured,
        expected,
        1e-10,
        "ohm",
        "R = length / (conductivity * width * thickness); segmentation must be invariant.",
    )


def _via_benchmark() -> Benchmark:
    design = DesignIR(
        name="analytical plated via",
        layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
        stackup=_stackup(),
        vias=[{
            "id": "via",
            "at": [0, 0],
            "drill": 0.3,
            "size": 0.6,
            "plating_thickness_mm": 0.025,
            "layers": ["F.Cu", "B.Cu"],
            "net_name": "VCC",
        }],
    )
    mesh = build_hybrid_mesh(design, AnalysisSpec(mode="dc", net_names=["VCC"]))
    measured = sum(branch.resistance_ohm for branch in mesh.branches)
    length_m = abs(mesh.branches[0].end_mm[2] - mesh.branches[0].start_mm[2]) * 1e-3
    inner_radius_m = 0.3e-3 / 2
    outer_radius_m = inner_radius_m + 0.025e-3
    expected = length_m / (
        COPPER_CONDUCTIVITY_S_M * pi * (outer_radius_m**2 - inner_radius_m**2)
    )
    return _result(
        "plated_via_dc_resistance",
        measured,
        expected,
        1e-10,
        "ohm",
        "The rectangular PEEC surrogate preserves the exact annular barrel area.",
    )


def _zone_mesh(cell_mm: float) -> HybridMesh:
    design = DesignIR(
        name="square sheet",
        layers=[{"name": "F.Cu"}],
        stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        zones=[{
            "id": "sheet",
            "points": [[0, 0], [10, 0], [10, 10], [0, 10]],
            "layer": "F.Cu",
            "net_name": "VCC",
        }],
    )
    return build_hybrid_mesh(
        design,
        AnalysisSpec(
            mode="dc",
            net_names=["VCC"],
            mesh={"target_size_mm": cell_mm, "zone_cell_mm": cell_mm, "max_zone_cells": 10000},
        ),
    )


def _zone_resistance(mesh: HybridMesh) -> float:
    nodes = [node for node in mesh.nodes if node.net == "VCC"]
    min_x, max_x = min(node.x_mm for node in nodes), max(node.x_mm for node in nodes)
    tolerance = mesh.target_size_mm * 0.1
    source = [node.id for node in nodes if abs(node.x_mm - min_x) <= tolerance]
    sink = [node.id for node in nodes if abs(node.x_mm - max_x) <= tolerance]
    return _equivalent_resistance(mesh, source, sink)


def _zone_convergence_benchmark() -> Benchmark:
    sizes = [2.0, 1.0, 0.5, 0.25]
    values = [_zone_resistance(_zone_mesh(size)) for size in sizes]
    sheet_resistance = 1.0 / (COPPER_CONDUCTIVITY_S_M * 0.035e-3)
    errors = [_relative_error(value, sheet_resistance) for value in values]
    monotonic = all(next_error < error for error, next_error in zip(errors, errors[1:]))
    tolerance = 0.03
    status = "passed" if monotonic and errors[-1] <= tolerance else "failed"
    return Benchmark(
        "square_zone_sheet_resistance_convergence",
        status,
        values[-1],
        sheet_resistance,
        errors[-1],
        tolerance,
        "ohm/square",
        f"cells_mm={sizes}; relative_errors={[round(float(value), 6) for value in errors]}",
    )


def hybrid_fixture() -> tuple[DesignIR, AnalysisSpec]:
    design = DesignIR(
        name="trace-zone-pad-via fixture",
        layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
        stackup=_stackup(),
        tracks=[
            # Meet the pad at its outer edge instead of running through the
            # pad and plane.  Large coincident copper volumes double-count the
            # same conductor in the filament model and make the raw partial-L
            # matrix non-passive, which is an invalid MNA benchmark fixture.
            {"id": "top", "start": [0, 5], "end": [2.0, 5], "width": 0.5, "layer": "F.Cu", "net_name": "VCC"},
            {"id": "bottom", "start": [7, 5], "end": [10, 5], "width": 0.5, "layer": "B.Cu", "net_name": "VCC"},
        ],
        zones=[{
            "id": "plane",
            "points": [[3, 4], [7, 4], [7, 6], [3, 6]],
            "layer": "F.Cu",
            "net_name": "VCC",
        }],
        vias=[{
            "id": "via",
            "at": [7, 5],
            "size": 0.6,
            "drill": 0.3,
            "plating_thickness_mm": 0.025,
            "layers": ["F.Cu", "B.Cu"],
            "net_name": "VCC",
        }],
        pads=[{
            "id": "pad",
            # Retain only the small attachment overlap needed by the hybrid
            # topology builder (the circular pad spans x=1.9..3.1 mm).
            "at": [2.5, 5],
            "size": [1.2, 1.2],
            "shape": "circle",
            "layers": ["F.Cu"],
            "layer": "F.Cu",
            "net_name": "VCC",
        }],
    )
    spec = AnalysisSpec(
        mode="ac",
        solver_id="spike.peec_2_5d",
        formulation="peec_2_5d",
        net_names=["VCC"],
        sources=[{"id": "source", "position_mm": [0, 5], "layer": "F.Cu", "net": "VCC"}],
        loads=[{"id": "load", "position_mm": [10, 5], "layer": "B.Cu", "net": "VCC"}],
        frequency_start_hz=1e3,
        frequency_stop_hz=1e4,
        frequency_points=2,
        mesh={"target_size_mm": 1.0, "zone_cell_mm": 0.5, "max_conductors": 1000},
    )
    return design, spec


def _hybrid_connectivity_benchmark() -> Benchmark:
    design, spec = hybrid_fixture()
    mesh = build_hybrid_mesh(design, spec)
    measured = _port_resistance(mesh, spec.sources[0], spec.loads[0], "VCC")
    required = {"track": 2, "zone": 1, "via": 1, "pad": 1}
    correct_counts = all(mesh.geometry_counts.get(kind) == count for kind, count in required.items())
    status = "passed" if correct_counts and measured > 0 and not mesh.truncated else "failed"
    return Benchmark(
        "hybrid_trace_zone_pad_via_connectivity",
        status,
        measured,
        None,
        None,
        None,
        "ohm",
        f"geometry_counts={mesh.geometry_counts}; nodes={len(mesh.nodes)}; branches={len(mesh.branches)}",
    )


def _native_trace_inductance_benchmark() -> Benchmark:
    if not native_available():
        return Benchmark(
            "native_straight_trace_self_inductance",
            "skipped",
            None,
            None,
            None,
            None,
            "henry",
            "Native PEEC extension is not installed.",
        )
    length_mm, width_mm, thickness_mm = 20.0, 1.0, 0.035
    design = DesignIR(
        name="native straight trace",
        layers=[{"name": "F.Cu"}],
        stackup=[{"name": "F.Cu", "type": "copper", "thickness": thickness_mm}],
        tracks=[{
            "id": "trace",
            "start": [0, 0],
            "end": [length_mm, 0],
            "width": width_mm,
            "layer": "F.Cu",
            "net_name": "VCC",
        }],
    )
    spec = AnalysisSpec(
        mode="ac",
        solver_id="spike.peec_2_5d",
        formulation="peec_2_5d",
        net_names=["VCC"],
        sources=[{"position_mm": [0, 0], "layer": "F.Cu", "net": "VCC"}],
        loads=[{"position_mm": [length_mm, 0], "layer": "F.Cu", "net": "VCC"}],
        frequency_start_hz=1e3,
        frequency_stop_hz=2e3,
        frequency_points=2,
        # This fixture validates the native rectangular-conductor self term,
        # so preserve one filament instead of applying production width-aware
        # longitudinal refinement and accumulating mutual terms.
        mesh={"target_size_mm": length_mm, "feature_aware": False},
    )
    result = solve_peec_2_5d(design, spec)
    measured = float(result.summary.get("partial_inductance_h", 0))
    length_m, width_m, thickness_m = length_mm * 1e-3, width_mm * 1e-3, thickness_mm * 1e-3
    gmd = width_m + thickness_m
    expected = 2e-7 * length_m * (
        log(2 * length_m / gmd) + 0.5 + 0.2235 * gmd / length_m
    )
    return _result(
        "native_straight_trace_self_inductance",
        measured,
        expected,
        1e-8,
        "henry",
        "Independent Python evaluation of the rectangular-conductor Rosa/Grover expression.",
    )


def _native_hybrid_smoke_benchmark() -> Benchmark:
    if not native_available():
        return Benchmark(
            "native_hybrid_peec_mna",
            "skipped",
            None,
            None,
            None,
            None,
            "ohm",
            "Native PEEC extension is not installed.",
        )
    design, spec = hybrid_fixture()
    result = solve_peec_2_5d(design, spec)
    counts = result.summary.get("geometry_counts", {})
    measured = float(result.summary.get("resistance_start_ohm", 0))
    complete = result.status == "completed" and all(counts.get(kind, 0) for kind in ("track", "zone", "via", "pad"))
    return Benchmark(
        "native_hybrid_peec_mna",
        "passed" if complete and measured > 0 else "failed",
        measured,
        None,
        None,
        None,
        "ohm",
        f"status={result.status}; geometry_counts={counts}; ports={result.summary.get('port_count', 0)}",
    )


def _capacitance_asymptote_benchmark() -> Benchmark:
    width_mm, height_mm, epsilon_r = 100.0, 1.0, 4.0
    measured = estimate_line_capacitance_per_m(width_mm, height_mm, epsilon_r)
    expected = EPSILON_0_F_M * epsilon_r * width_mm / height_mm
    return _result(
        "wide_microstrip_parallel_plate_capacitance_limit",
        measured,
        expected,
        0.05,
        "farad/meter",
        "A wide microstrip must approach the independent parallel-plate electrostatic limit.",
    )


def _native_ac_loss_benchmark() -> Benchmark:
    if not native_available():
        return Benchmark(
            "native_ac_resistance_monotonicity",
            "skipped",
            None,
            None,
            None,
            None,
            "ohm",
            "Native PEEC extension is not installed.",
        )
    design = DesignIR(
        name="AC loss fixture",
        layers=[{"name": "F.Cu"}],
        stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
        tracks=[{"id": "trace", "start": [0, 0], "end": [100, 0], "width": 1.0, "layer": "F.Cu", "net_name": "VCC"}],
    )
    spec = AnalysisSpec(
        mode="ac",
        net_names=["VCC"],
        sources=[{"position_mm": [0, 0], "layer": "F.Cu", "net": "VCC"}],
        loads=[{"position_mm": [100, 0], "layer": "F.Cu", "net": "VCC"}],
        frequency_start_hz=1e3,
        frequency_stop_hz=1e8,
        frequency_points=5,
        mesh={"target_size_mm": 100.0},
        options={"include_dielectric": False, "conductor_models": {"skin_effect": True}},
    )
    result = solve_peec_2_5d(design, spec)
    values = [float(item["resistance_ohm"]) for item in result.networks["parasitics"][0]["impedance"]]
    monotonic = all(right >= left for left, right in zip(values, values[1:]))
    return Benchmark(
        "native_ac_resistance_monotonicity",
        "passed" if monotonic and values[-1] > values[0] else "failed",
        values[-1],
        values[0],
        None,
        None,
        "ohm",
        f"frequency_sweep_resistance_ohm={values}",
    )


def _shared_reference_multiport_benchmark() -> Benchmark:
    """Compare the PEEC multi-RHS port solve with a closed-form resistor chain."""

    mesh = HybridMesh(
        nodes=[
            MeshNode(10, 0.0, 0.0, 0.0, "F.Cu", "VCC"),
            MeshNode(20, 1.0, 0.0, 0.0, "F.Cu", "VCC"),
            MeshNode(30, 2.0, 0.0, 0.0, "F.Cu", "VCC"),
        ],
        branches=[
            MeshBranch(
                "r1", "track", 10, 20,
                (0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                1.0, 0.035, COPPER_CONDUCTIVITY_S_M, "F.Cu", "VCC", "r1",
            ),
            MeshBranch(
                "r2", "track", 20, 30,
                (1.0, 0.0, 0.0), (2.0, 0.0, 0.0),
                1.0, 0.035, COPPER_CONDUCTIVITY_S_M, "F.Cu", "VCC", "r2",
            ),
        ],
    )
    expected = np.asarray([[2.0, 2.0], [2.0, 5.0]], dtype=complex)
    measured, quality = _solve_shared_reference_port_matrix(
        mesh,
        node_ids=[10, 20, 30],
        branch_indices=[0, 1],
        port_nodes=[20, 30],
        reference_node=10,
        branch_impedance=np.diag([2.0, 3.0]).astype(complex),
        diagnostics=True,
    )
    relative_error = float(
        np.linalg.norm(measured - expected)
        / max(np.linalg.norm(expected), np.finfo(float).eps)
    )
    tolerance = 1e-12
    return Benchmark(
        "peec_shared_reference_multiport_resistor_matrix",
        "passed" if relative_error <= tolerance else "failed",
        relative_error,
        0.0,
        relative_error,
        tolerance,
        "relative_frobenius",
        (
            "Two-port closed-form Z=[[R1,R1],[R1,R1+R2]] with non-contiguous "
            f"mesh node IDs; method={quality['method']}; residual={quality['relative_residual']:.6g}. "
            "This verifies MNA assembly and the multi-right-hand-side solve, not PCB field extraction."
        ),
    )


def _geometry_peec_transient_benchmark() -> Benchmark:
    if not native_available():
        return Benchmark(
            "geometry_peec_transient_constant_current_reference", "skipped",
            None, None, None, None, "volt", "Native PEEC extension is not installed.",
        )
    design = DesignIR(
        name="geometry transient constant-current fixture",
        layers=[{"name": "F.Cu"}],
        nets=[{"id": 1, "name": "VCC"}],
        tracks=[{
            "id": "trace", "start": [0.0, 0.0], "end": [10.0, 0.0],
            "width": 1.0, "layer": "F.Cu", "net_name": "VCC",
        }],
        stackup=[{"name": "F.Cu", "type": "copper", "thickness": 0.035}],
    )
    spec = AnalysisSpec(
        analysis_id="benchmark-geometry-transient",
        mode="transient",
        solver_id="spike.peec_rl_transient",
        formulation="peec_rl_transient",
        net_names=["VCC"],
        sources=[{
            "id": "source", "position_mm": [0.0, 0.0], "layer": "F.Cu", "net": "VCC",
            "voltage_v": 5.0, "profile": {"kind": "constant"},
        }],
        loads=[{
            "id": "load", "position_mm": [10.0, 0.0], "layer": "F.Cu", "net": "VCC",
            "current_a": 1.0, "profile": {"kind": "constant"},
        }],
        transient={
            "stop_time_s": 2e-6, "time_step_s": 2e-7, "output_decimation": 1,
            "initial_condition": "operating_point", "max_output_frames": 64,
        },
        mesh={"target_size_mm": 2.0, "zone_cell_mm": 2.0, "max_preview_cells": 1000},
    )
    mesh = build_hybrid_mesh(design, spec)
    expected = _port_resistance(mesh, spec.sources[0], spec.loads[0], "VCC")
    solved = solve_peec_rl_transient(design, spec)
    measured = float(solved.summary.get("max_voltage_drop_v", float("nan")))
    benchmark = _result(
        "geometry_peec_transient_constant_current_reference",
        measured,
        expected,
        1e-8,
        "volt",
        "A constant 1 A geometry-derived transient must reproduce the independently assembled DC mesh drop.",
    )
    if solved.status != "completed":
        benchmark.status = "failed"
        benchmark.detail += f" Solver status was {solved.status}."
    return benchmark


def _field_circuit_cosimulation_benchmark() -> Benchmark:
    design = DesignIR(
        design_id="field-circuit-reference",
        components=[{"id": "v1", "reference": "V1"}, {"id": "r1", "reference": "R1"}],
        pads=[
            {"id": "v1p", "ref": "V1", "name": "1", "net_name": "VIN"},
            {"id": "v1n", "ref": "V1", "name": "2", "net_name": "GND"},
            {"id": "r1p", "ref": "R1", "name": "1", "net_name": "LOAD"},
            {"id": "r1n", "ref": "R1", "name": "2", "net_name": "GND"},
        ],
    )
    workspace = {
        "contract": SPICE_WORKSPACE_CONTRACT,
        "name": "Field/circuit analytical reference",
        "domain": "pi",
        "ground_node": "GND",
        "models": [
            {
                "id": "source", "kind": "primitive", "primitive": "voltage_source",
                "pins": ["p", "n"], "value": "5", "origin": "built_in",
                "parameters": {"dc_value": 5.0},
            },
            {
                "id": "load", "kind": "primitive", "primitive": "resistor",
                "pins": ["p", "n"], "value": "1000", "origin": "built_in",
                "parameters": {"resistance_ohm": 1000.0},
            },
        ],
        "assignments": [
            {
                "id": "source-binding", "component_ref": "V1", "model_id": "source", "enabled": True,
                "pin_bindings": [
                    {"model_pin": "p", "pad_id": "v1p", "circuit_node": "VIN"},
                    {"model_pin": "n", "pad_id": "v1n", "circuit_node": "GND"},
                ],
            },
            {
                "id": "load-binding", "component_ref": "R1", "model_id": "load", "enabled": True,
                "pin_bindings": [
                    {"model_pin": "p", "pad_id": "r1p", "circuit_node": "LOAD"},
                    {"model_pin": "n", "pad_id": "r1n", "circuit_node": "GND"},
                ],
            },
        ],
        "parasitics": [{
            "id": "path", "enabled": True, "endpoint_reviewed": True,
            "from_node": "VIN", "to_node": "LOAD", "reference_node": "GND",
            "resistance_ohm": 0.1, "inductance_h": 0.0,
            "capacitance_f": 0.0, "conductance_s": 0.0,
        }],
        "analysis": {"mode": "operating_point"},
    }

    def provider(item: Dict[str, Any]) -> Dict[str, Any]:
        parasitic = item["parasitics"][0]
        return {
            "contract": FIELD_RESULT_CONTRACT,
            "status": "completed",
            "provider": "analytical.fixed_resistance_reference",
            "parasitics": [{
                "id": parasitic["id"],
                "resistance_ohm": 0.2,
                "inductance_h": 0.0,
                "capacitance_f": 0.0,
                "conductance_s": 0.0,
            }],
            "diagnostics": {"analytical_reference": True},
        }

    result = run_iterative_field_circuit_cosimulation(
        design,
        workspace,
        {
            "contract": FIELD_CIRCUIT_REQUEST_CONTRACT,
            "request_id": "benchmark-field-circuit",
            "maximum_iterations": 6,
            "minimum_iterations": 2,
            "relaxation": 1.0,
            "parameter_relative_tolerance": 1e-12,
            "circuit_relative_tolerance": 1e-12,
            "absolute_floor": 1e-18,
            "time_limit_s": 10.0,
            "resource_limits": {"memory_limit_gb": 2.0},
        },
        provider,
    )
    measured = float(
        (((result.get("circuit") or {}).get("result") or {}).get("data") or {})
        .get("node_voltage_v", {}).get("LOAD", float("nan"))
    )
    expected = 5.0 * 1000.0 / 1000.2
    benchmark = _result(
        "field_circuit_fixed_point_resistive_reference",
        measured,
        expected,
        1e-12,
        "volt",
        "Fixed-point field reduction to 0.2 ohm compared with an independent source-path-load divider.",
    )
    if result.get("status") != "completed" or result.get("converged") is not True:
        benchmark.status = "failed"
        benchmark.detail += f" Coupler status was {result.get('status')}."
    return benchmark


def run_solver_benchmarks() -> Dict[str, Any]:
    benchmarks = [
        _trace_benchmark(),
        _via_benchmark(),
        _zone_convergence_benchmark(),
        _hybrid_connectivity_benchmark(),
        _native_trace_inductance_benchmark(),
        _native_hybrid_smoke_benchmark(),
        _capacitance_asymptote_benchmark(),
        _native_ac_loss_benchmark(),
        _shared_reference_multiport_benchmark(),
        run_pdn_two_port_loading_benchmark(_result, Benchmark),
        *run_native_mna_reference_benchmarks(_result),
        _geometry_peec_transient_benchmark(),
        _field_circuit_cosimulation_benchmark(),
    ]
    failed = sum(item.status == "failed" for item in benchmarks)
    skipped = sum(item.status == "skipped" for item in benchmarks)
    return {
        "contract": "spike/solver-benchmark-report/v1",
        "status": "passed" if failed == 0 else "failed",
        "summary": {
            "total": len(benchmarks),
            "passed": sum(item.status == "passed" for item in benchmarks),
            "failed": failed,
            "skipped": skipped,
        },
        "benchmarks": [item.to_dict() for item in benchmarks],
        "limitations": [
            "These fixtures validate extraction, units, topology, convergence, passivity metadata, AC-loss monotonicity, one capacitance asymptote, a closed-form shared-reference multiport matrix, the PDN two-port loading identity, native linear MNA, geometry transient execution, and fixed-point field/circuit orchestration; they do not replace arbitrary-geometry electrostatic or full-wave validation.",
            "Measured fixture and trusted-tool correlation remain required before sign-off claims.",
        ],
    }
