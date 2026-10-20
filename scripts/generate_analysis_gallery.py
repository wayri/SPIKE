# SPDX-License-Identifier: Apache-2.0
"""Generate the reproducible SPIKE numerical analysis gallery.

The plots in this gallery are derived from executed first-party solvers and
postprocessors. They are documentation artifacts, not application screenshots
or qualification evidence.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from examples.assembly_field.run_electrothermal import setup_coupled
from examples.assembly_field.run_examples import setup as thermal_setup
from examples.pdn_dielectric_thermal.run_slab import setup as dielectric_setup
from examples.rlgc_line_fields.run_line import request as rlgc_request
from python.spike_core.assembly_electrothermal import run_assembly_electrothermal
from python.spike_core.assembly_field_thermal import run_assembly_field_thermal
from python.spike_core.huygens_far_field import huygens_far_field
from python.spike_core.laminar_channel_cht import solve_laminar_channel_cht
from python.spike_core.multiboard_circuit import run_multiboard_circuit
from python.spike_core.multiboard_thermal import run_multiboard_thermal
from python.spike_core.native_airflow import detect_native_airflow, run_native_cavity
from python.spike_core.pdn_dielectric_ac import extract_pdn_dielectric_ac
from python.spike_core.rlgc_line_fields import run_rlgc_line_fields
from tests.python.test_multiboard_circuit import fixture as multiboard_circuit_fixture
from tests.python.test_multiboard_thermal import request as multiboard_thermal_fixture


OUT = ROOT / "examples" / "analysis_gallery"
DATA = OUT / "data"
FIGURES = OUT / "figures"
PUBLIC = ROOT / "app" / "public" / "help" / "analytics"
GRAPHITE = "#263238"
TEAL = "#008C95"
TEAL_LIGHT = "#64C2C8"
ORANGE = "#D97706"
PURPLE = "#7057A3"
GRID = "#D8E0E3"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def sources(*relative: str) -> list[dict[str, str]]:
    return [{"path": item.replace("\\", "/"), "sha256": sha256(ROOT / item)} for item in relative]


def provenance(command: str, source_paths: tuple[str, ...], request: object, result: object) -> dict[str, object]:
    return {
        "generator": {"path": "scripts/generate_analysis_gallery.py", "sha256": sha256(Path(__file__))},
        "sources": sources(*source_paths),
        "executed_command": command,
        "request_sha256": digest(request),
        "result_sha256": digest(result),
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "matplotlib": matplotlib.__version__,
            "platform": platform.platform(),
        },
    }


def style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.titlesize": 11,
        "axes.labelsize": 9,
        "axes.edgecolor": GRAPHITE,
        "axes.labelcolor": GRAPHITE,
        "axes.titlecolor": GRAPHITE,
        "xtick.color": GRAPHITE,
        "ytick.color": GRAPHITE,
        "text.color": GRAPHITE,
        "grid.color": GRID,
        "grid.linewidth": 0.7,
        "legend.frameon": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    })


def footer(fig: plt.Figure, text: str = "Executed SPIKE result | experimental | not production qualified") -> None:
    fig.text(0.01, -0.055, text, color="#66767D", fontsize=7.5)


def save(fig: plt.Figure, stem: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{stem}.png", dpi=160, bbox_inches="tight",
                metadata={"Software": "SPIKE analysis gallery"})
    plt.close(fig)


def base_record(domain: str, title: str, model_status: str, limitations: list[str],
                source_paths: tuple[str, ...], request: object, result: object) -> dict[str, object]:
    command = ".\\.venv\\Scripts\\python.exe scripts\\generate_analysis_gallery.py"
    return {
        "schema": "spike/analysis-gallery-series/v1",
        "domain": domain,
        "title": title,
        "model_status": model_status,
        "production_qualified": False,
        "limitations": limitations,
        "provenance": provenance(command, source_paths, request, result),
    }


def generate_pi() -> dict[str, object]:
    request = dielectric_setup(3)["electrical_request"]
    request["frequencies_hz"] = np.logspace(2, 6, 13).tolist()
    result = extract_pdn_dielectric_ac(request)
    rows = []
    for sample in result["ac"]:
        f = sample["frequency_hz"]
        y = sample["admittance_s"][0][0]
        value = complex(y["real"], y["imag"])
        rows.append({"frequency_hz": f, "conductance_s": value.real, "susceptance_s": value.imag,
                     "impedance_magnitude_ohm": 1 / abs(value),
                     "equivalent_capacitance_f": value.imag / (2 * math.pi * f),
                     "relative_power_identity_error": sample["diagnostics"]["relative_power_identity_error"]})
    fig, (left, right) = plt.subplots(1, 2, figsize=(8.2, 3.7), layout="constrained")
    f = [row["frequency_hz"] for row in rows]
    left.loglog(f, [row["impedance_magnitude_ohm"] for row in rows], color=TEAL, marker="o", ms=3)
    left.set(xlabel="Frequency (Hz)", ylabel="|Z| (ohm)", title="Terminal impedance")
    right.semilogx(f, [row["equivalent_capacitance_f"] * 1e9 for row in rows], color=ORANGE, marker="o", ms=3)
    right.set(xlabel="Frequency (Hz)", ylabel="B / omega (nF)", title="Equivalent capacitance", ylim=(990, 1010))
    right.text(.03, .08, "constant supplied permittivity", transform=right.transAxes, color="#66767D", fontsize=8)
    for axis in (left, right): axis.grid(True, which="both")
    fig.suptitle("PI | retained dielectric electroquasistatic sweep", fontweight="bold")
    footer(fig)
    save(fig, "pi-dielectric-admittance")
    record = base_record("pi", "Retained dielectric electroquasistatic sweep", result["model_status"],
        result["limitations"], ("examples/pdn_dielectric_thermal/run_slab.py", "python/spike_core/pdn_dielectric_ac.py"), request, result)
    record.update(units={"frequency_hz": "Hz", "conductance_s": "S", "susceptance_s": "S",
                         "impedance_magnitude_ohm": "ohm", "equivalent_capacitance_f": "F"},
                  metrics={"mesh_nodes": result["diagnostics"]["nodes"], "mesh_cells": result["diagnostics"]["cells"],
                           "maximum_relative_power_identity_error": max(row["relative_power_identity_error"] for row in rows)},
                  series=rows)
    write_json(DATA / "pi.json", record)
    return {"id": "pi", "figure": "figures/pi-dielectric-admittance.png", "data": "data/pi.json",
            "status": result["model_status"], "metrics": record["metrics"]}


def generate_si() -> dict[str, object]:
    request = rlgc_request()
    result = run_rlgc_line_fields(request)
    rows = []
    length = request["line_request"]["length_m"]
    for point in result["points"]:
        s21 = result["network"]["s_parameters"][result["network"]["frequencies_hz"].index(point["frequency_hz"])][1][0]
        for probe in point["probe_values"]:
            rows.append({"frequency_hz": point["frequency_hz"], "position_m": probe["fractional_position"] * length,
                         "probe_id": probe["id"], "transported_power_w": probe["transported_power_w"],
                         "total_loss_w_per_m": probe["total_loss_w_per_m"],
                         "s21_db": 20 * math.log10(abs(complex(s21["real"], s21["imag"])))})
    fig, (left, right) = plt.subplots(1, 2, figsize=(8.2, 3.7), layout="constrained")
    colors = [TEAL, ORANGE, PURPLE]
    for color, point in zip(colors, result["points"]):
        values = [row for row in rows if row["frequency_hz"] == point["frequency_hz"]]
        left.plot([row["position_m"] for row in values], [row["transported_power_w"] for row in values],
                  marker="o", color=color, label=f"{point['frequency_hz']/1e6:g} MHz")
    right.semilogx(result["network"]["frequencies_hz"],
                   [next(row["s21_db"] for row in rows if row["frequency_hz"] == f) for f in result["network"]["frequencies_hz"]],
                   marker="o", color=TEAL)
    left.set(xlabel="Position along line (m)", ylabel="Transported power (W)", title="Power along supplied 5 m line")
    right.set(xlabel="Frequency (Hz)", ylabel="|S21| (dB)", title="Two-port transmission")
    left.legend(); left.grid(True); right.grid(True, which="both")
    fig.suptitle("SI | coherent two-end RLGC line fields", fontweight="bold")
    footer(fig)
    save(fig, "si-rlgc-line-fields")
    balances = [abs(point["power_balance"]["residual_w"]) for point in result["points"]]
    record = base_record("si", "Coherent two-end supplied RLGC line", result["model_status"],
        ["Supplied uniform RLGC only; no geometry extraction or broadband causal material law.",
         "No DC fields, thermal deposition, or measured qualification."],
        ("examples/rlgc_line_fields/run_line.py", "examples/rlgc_line_network/run_line.py", "python/spike_core/rlgc_line_fields.py"), request, result)
    record.update(units={"frequency_hz": "Hz", "position_m": "m", "transported_power_w": "W",
                         "total_loss_w_per_m": "W/m", "s21_db": "dB"},
                  metrics={"maximum_absolute_power_balance_residual_w": max(balances), "line_length_m": length}, series=rows)
    write_json(DATA / "si.json", record)
    return {"id": "si", "figure": "figures/si-rlgc-line-fields.png", "data": "data/si.json",
            "status": result["model_status"], "metrics": record["metrics"]}


def generate_em() -> dict[str, object]:
    source_path = ROOT / "examples" / "em" / "huygens_dipole_request.json"
    request = json.loads(source_path.read_text(encoding="utf-8"))
    angles = np.linspace(0, 2 * math.pi, 181, endpoint=False)
    request["directions"] = [[float(math.sin(a)), 0.0, float(math.cos(a))] for a in angles]
    args = {key: value for key, value in request.items() if key != "contract"}
    for name in ("electric_fields", "magnetic_fields"):
        args[name] = {face: np.asarray(value)[..., 0] + 1j * np.asarray(value)[..., 1]
                      for face, value in args[name].items()}
    result = huygens_far_field(**args)
    intensity = np.asarray(result["radiation_intensity_w_per_sr"])
    relative_db = np.maximum(10 * np.log10(intensity / intensity.max()), -40)
    rows = [{"angle_deg": float(math.degrees(angle)), "radiation_intensity_w_per_sr": float(value),
             "relative_intensity_db": float(level)} for angle, value, level in zip(angles, intensity, relative_db)]
    fig = plt.figure(figsize=(5.6, 4.7), layout="constrained")
    axis = fig.add_subplot(111, projection="polar")
    axis.plot(angles, relative_db, color=TEAL, lw=2)
    axis.fill_between(angles, -40, relative_db, color=TEAL_LIGHT, alpha=.25)
    axis.set_rlim(-40, 0); axis.set_rticks([-40, -30, -20, -10, 0]); axis.set_rlabel_position(135)
    axis.set_title("EM | closed-box Huygens far field cut\nrelative intensity (dB), x-z plane", fontweight="bold", pad=18)
    footer(fig, "Executed postprocessor result | synthetic dipole boundary fixture | not a Maxwell solve")
    save(fig, "em-huygens-far-field")
    result_summary = {"surface_samples": result["surface_samples"], "scope": result["scope"],
                      "production_qualified": result["production_qualified"], "intensity": intensity.tolist()}
    limits = ["Closed-box Huygens postprocessor only; it does not solve Maxwell fields.",
              "The original dipole boundary fixture is synthetic and analytically generated.",
              "No total radiated power, directivity, geometry extraction, or compliance verdict is inferred."]
    record = base_record("em", "Closed-box Huygens far field cut", "postprocessor_only", limits,
        ("examples/em/huygens_dipole_request.json", "scripts/run_huygens_far_field.py", "python/spike_core/huygens_far_field.py"),
        request, result_summary)
    record.update(units={"angle_deg": "degree", "radiation_intensity_w_per_sr": "W/sr", "relative_intensity_db": "dB"},
                  metrics={"surface_samples": result["surface_samples"], "direction_count": len(rows),
                           "peak_intensity_w_per_sr": float(intensity.max())}, series=rows)
    write_json(DATA / "em.json", record)
    return {"id": "em", "figure": "figures/em-huygens-far-field.png", "data": "data/em.json",
            "status": "postprocessor_only", "metrics": record["metrics"]}


def generate_thermal() -> dict[str, object]:
    request, problem = thermal_setup(True)
    result = run_assembly_field_thermal(request, problem)
    temperatures = result["field_result"]["node_temperatures_k"]
    rows = []
    for trace in result["source_traceability"]:
        body = next(item for item in request["bodies"] if item["occurrence_id"] == trace["occurrence_id"])
        offset = trace["world_transform_mm"][3] / 1000
        start, stop = trace["vertex_range"]
        for vertex, temperature in zip(body["mesh"]["vertices"], temperatures[start:stop]):
            rows.append({"occurrence_id": trace["occurrence_id"], "x_m": vertex[0] + offset,
                         "temperature_k": temperature})
    fig, axis = plt.subplots(figsize=(7.2, 3.8), layout="constrained")
    for occurrence, color, marker in (("board", TEAL, "o"), ("case", ORANGE, "s")):
        subset = [row for row in rows if row["occurrence_id"] == occurrence]
        axis.scatter([row["x_m"] for row in subset], [row["temperature_k"] for row in subset],
                     color=color, marker=marker, label=occurrence, s=35, alpha=.85)
    axis.axvspan(.97, 1.03, color=PURPLE, alpha=.15, label="matched contact")
    axis.set(xlabel="Assembly x coordinate (m)", ylabel="Node temperature (K)",
             title="Thermal | two-solid steady P1 conduction")
    axis.grid(True); axis.legend(ncol=3)
    footer(fig)
    save(fig, "thermal-two-solid-conduction")
    heat = result["field_result"]["heat_balance"]
    record = base_record("thermal", "Two-solid steady P1 conduction", result["model_status"], result["limitations"],
        ("examples/assembly_field/run_examples.py", "python/spike_core/assembly_field_thermal.py", "python/spike_core/assembly_tetra_thermal.py"),
        {"handoff": request, "problem": problem}, result)
    record.update(units={"x_m": "m", "temperature_k": "K"},
                  metrics={"minimum_temperature_k": min(temperatures), "maximum_temperature_k": max(temperatures),
                           "heat_balance_imbalance_w": heat["imbalance_w"],
                           "heat_balance_acceptance_tolerance_w": heat["acceptance_tolerance_w"]}, series=rows)
    write_json(DATA / "thermal.json", record)
    return {"id": "thermal", "figure": "figures/thermal-two-solid-conduction.png", "data": "data/thermal.json",
            "status": result["model_status"], "metrics": record["metrics"]}


def generate_hybrid() -> dict[str, object]:
    request = setup_coupled()
    request["electrical"]["materials"][0]["temperature_coefficient_per_k"] = .004
    result = run_assembly_electrothermal(request)
    rows = copy.deepcopy(result["history"])
    fig, (left, right) = plt.subplots(1, 2, figsize=(8.2, 3.7), layout="constrained")
    iterations = [row["iteration"] for row in rows]
    left.semilogy(iterations, [row["unrelaxed_temperature_defect_k"] for row in rows], color=TEAL, marker="o", ms=3)
    left.axhline(request["iteration"]["temperature_tolerance_k"], color=GRAPHITE, ls="--", label="acceptance")
    right.semilogy(iterations, [row["power_relative_defect"] for row in rows], color=ORANGE, marker="o", ms=3)
    right.axhline(request["iteration"]["power_relative_tolerance"], color=GRAPHITE, ls="--", label="acceptance")
    left.set(xlabel="Fixed point iteration", ylabel="Temperature defect (K)", title="Thermal feedback closure")
    right.set(xlabel="Fixed point iteration", ylabel="Relative power defect", title="Electrical loss closure")
    for axis in (left, right): axis.grid(True, which="both"); axis.legend()
    fig.suptitle("Hybrid multisolve | DC conduction + steady thermal feedback", fontweight="bold")
    footer(fig)
    save(fig, "hybrid-electrothermal-convergence")
    record = base_record("hybrid_multisolve", "DC conduction and steady thermal feedback", result["model_status"], result["limitations"],
        ("examples/assembly_field/run_electrothermal.py", "python/spike_core/assembly_electrothermal.py"), request, result)
    record.update(units={"unrelaxed_temperature_defect_k": "K", "deposited_heat_w": "W",
                         "power_relative_defect": "dimensionless"},
                  metrics={"iterations": len(rows), "final_temperature_defect_k": rows[-1]["unrelaxed_temperature_defect_k"],
                           "final_power_relative_defect": rows[-1]["power_relative_defect"],
                           "coupled_power_defect_w": result["coupled_power_defect_w"],
                           "thermal_imbalance_w": result["conservation"]["thermal_imbalance_w"]}, series=rows)
    write_json(DATA / "hybrid-multisolve.json", record)
    return {"id": "hybrid_multisolve", "figure": "figures/hybrid-electrothermal-convergence.png",
            "data": "data/hybrid-multisolve.json", "status": result["model_status"], "metrics": record["metrics"]}


def generate_cfd() -> dict[str, object]:
    request = {"n": 24, "reynolds": 100.0, "max_steps": 100000, "steady_tolerance": 1e-7,
               "length_m": 1.0, "lid_velocity_m_s": 1.0, "density_kg_m3": 1.0}
    availability = detect_native_airflow()
    if not availability["available"]:
        raise RuntimeError("native CFD executable unavailable; run python scripts/build_native_airflow.py")
    result = run_native_cavity(request, timeout_s=180)
    if result["status"] != "converged":
        raise RuntimeError("native CFD cavity did not converge")
    n = request["n"]
    x = np.asarray(result["fields"]["x_m"]).reshape(n, n)
    y = np.asarray(result["fields"]["y_m"]).reshape(n, n)
    u = np.asarray(result["fields"]["u_m_s"]).reshape(n, n)
    v = np.asarray(result["fields"]["v_m_s"]).reshape(n, n)
    speed = np.hypot(u, v)
    fig, axis = plt.subplots(figsize=(5.5, 4.6), layout="constrained")
    image = axis.contourf(x, y, speed, levels=24, cmap="viridis")
    stride = 2
    axis.quiver(x[::stride, ::stride], y[::stride, ::stride], u[::stride, ::stride], v[::stride, ::stride],
                color="white", alpha=.75, scale=5)
    fig.colorbar(image, ax=axis, label="Speed (m/s)")
    axis.set(xlabel="x (m)", ylabel="y (m)", aspect="equal", title="CFD | Re=100 lid-driven cavity")
    footer(fig, "Executed original native MAC result | isothermal laminar 2D | not production qualified")
    save(fig, "cfd-native-cavity")
    center = result["centerlines"]
    rows = [{"coordinate_fraction": center["coordinates"][index],
             "vertical_u_m_s": center["u_over_lid"][index] * request["lid_velocity_m_s"],
             "horizontal_v_m_s": center["v_over_lid"][index] * request["lid_velocity_m_s"]} for index in range(19)]
    limits = result["limitations"]
    record = base_record("cfd", "Native Re=100 lid-driven cavity", result["model_status"], limits,
        ("scripts/run_cfd.py", "python/spike_core/native_airflow.py", "src/airflow/main.cpp"), request, result)
    record["provenance"]["native_executable"] = {"path": str(Path(availability["executable"]).relative_to(ROOT)).replace("\\", "/"),
                                                    "sha256": result["provenance"]["executable_sha256"]}
    record.update(units={"coordinate_fraction": "dimensionless", "vertical_u_m_s": "m/s", "horizontal_v_m_s": "m/s"},
                  metrics={"grid": n, **result["diagnostics"]}, series=rows)
    write_json(DATA / "cfd.json", record)
    return {"id": "cfd", "figure": "figures/cfd-native-cavity.png", "data": "data/cfd.json",
            "status": result["model_status"], "metrics": record["metrics"]}


def generate_cht() -> dict[str, object]:
    source = ROOT / "examples" / "thermal" / "laminar_channel_cht_request.json"
    request = json.loads(source.read_text(encoding="utf-8"))
    request["grid"].update(nx=32, fluid_cells=12, lower_wall_cells=3, upper_wall_cells=3)
    result = solve_laminar_channel_cht(request)
    if result["status"] != "completed":
        raise RuntimeError(f"laminar CHT did not complete: {result['issues']}")
    nx, ny = result["shape"]
    temperature = np.asarray(result["temperature_k"]).reshape(ny, nx)
    g = request["geometry"]
    y_edges = np.concatenate((np.linspace(-g["lower_wall_thickness_m"], 0, request["grid"]["lower_wall_cells"] + 1),
                              np.linspace(0, g["fluid_height_m"], request["grid"]["fluid_cells"] + 1)[1:],
                              np.linspace(g["fluid_height_m"], g["fluid_height_m"] + g["upper_wall_thickness_m"],
                                          request["grid"]["upper_wall_cells"] + 1)[1:]))
    x_edges = np.linspace(0, g["length_m"], nx + 1)
    fig, (left, right) = plt.subplots(1, 2, figsize=(8.5, 3.8), layout="constrained")
    image = left.pcolormesh(x_edges, y_edges * 1000, temperature, cmap="inferno", shading="flat")
    left.axhline(0, color="white", lw=.7); left.axhline(g["fluid_height_m"] * 1000, color="white", lw=.7)
    fig.colorbar(image, ax=left, label="Temperature (K)")
    left.set(xlabel="Channel x (m)", ylabel="Cross section y (mm)", title="Solid-fluid temperature")
    velocity = result["velocity_nodes_m_s"]
    right.plot(velocity, np.linspace(0, g["fluid_height_m"] * 1000, len(velocity)), color=TEAL, lw=2)
    right.set(xlabel="Axial velocity (m/s)", ylabel="Fluid y (mm)", title="Solved laminar profile")
    right.grid(True)
    fig.suptitle("CHT | bounded conjugate laminar channel", fontweight="bold")
    footer(fig)
    save(fig, "cht-laminar-channel")
    fluid_start = request["grid"]["lower_wall_cells"]
    rows = [{"x_m": float((index + .5) * g["length_m"] / nx),
             "lower_wall_mean_temperature_k": float(temperature[:fluid_start, index].mean()),
             "fluid_mean_temperature_k": float(temperature[fluid_start:fluid_start + request["grid"]["fluid_cells"], index].mean()),
             "upper_wall_mean_temperature_k": float(temperature[fluid_start + request["grid"]["fluid_cells"]:, index].mean())}
            for index in range(nx)]
    qualification = result["qualification"]
    record = base_record("cht", "Bounded conjugate laminar channel", qualification["state"], qualification["limitations"],
        ("examples/thermal/laminar_channel_cht_request.json", "scripts/run_structured_solid_thermal.py", "python/spike_core/laminar_channel_cht.py"),
        request, result)
    record.update(units={"x_m": "m", "temperature": "K", "velocity": "m/s"},
                  metrics={"reynolds": result["reynolds"], "flow_m3_s": result["flow_m3_s"],
                           "energy_residual_w": result["energy"]["residual_w"],
                           "thermal_relative_residual": result["thermal_relative_residual"],
                           "minimum_temperature_k": float(temperature.min()), "maximum_temperature_k": float(temperature.max())},
                  series=rows)
    write_json(DATA / "cht.json", record)
    return {"id": "cht", "figure": "figures/cht-laminar-channel.png", "data": "data/cht.json",
            "status": qualification["state"], "metrics": record["metrics"]}


def generate_multiboard() -> dict[str, object]:
    circuit_request = multiboard_circuit_fixture()
    circuit_request["domain"] = "si"
    circuit_request["analysis"] = {"mode": "ac", "start_hz": 100, "stop_hz": 100000, "points": 25, "scale": "log"}
    circuit_request["link_models"][0]["pins"][0]["inductance_h"] = 1e-4
    circuit = run_multiboard_circuit(circuit_request)
    data = circuit["native_result"]["data"]
    node_map = circuit["node_map"]["b"]
    positive, negative = (data["node_voltage_v"][node_map[key]] for key in ("J:1", "J:2"))
    transfer_rows = []
    for index, frequency in enumerate(data["frequency_hz"]):
        voltage = complex(positive["real"][index], positive["imaginary"][index]) - complex(negative["real"][index], negative["imaginary"][index])
        transfer_rows.append({"frequency_hz": frequency, "board_b_load_voltage_magnitude_v": abs(voltage),
                              "board_b_load_voltage_phase_deg": math.degrees(math.atan2(voltage.imag, voltage.real))})
    thermal_rows = []
    thermal_results = []
    for conductance in (.1, .3, 1., 3., 10.):
        request = multiboard_thermal_fixture(conductance)
        result = run_multiboard_thermal(request)
        thermal_results.append(result)
        thermal_rows.append({"contact_conductance_w_per_k": conductance,
                             "board_a_temperature_c": result["board_temperatures_c"]["A"]["board"],
                             "board_b_temperature_c": result["board_temperatures_c"]["B"]["board"],
                             "contact_heat_flow_w": result["contact_heat_flows"][0]["heat_flow_w"]})
    fig, (left, right) = plt.subplots(1, 2, figsize=(8.4, 3.8), layout="constrained")
    left.semilogx([row["frequency_hz"] for row in transfer_rows],
                  [row["board_b_load_voltage_magnitude_v"] for row in transfer_rows], color=TEAL, lw=2)
    left.set(xlabel="Frequency (Hz)", ylabel="Board B load |V| (V)", title="Shared harness AC solve")
    right.semilogx([row["contact_conductance_w_per_k"] for row in thermal_rows],
                   [row["board_a_temperature_c"] for row in thermal_rows], color=ORANGE, marker="o", label="Board A")
    right.semilogx([row["contact_conductance_w_per_k"] for row in thermal_rows],
                   [row["board_b_temperature_c"] for row in thermal_rows], color=PURPLE, marker="s", label="Board B")
    right.set(xlabel="Contact conductance (W/K)", ylabel="Steady temperature (deg C)", title="Shared thermal contact")
    for axis in (left, right): axis.grid(True, which="both")
    right.legend()
    fig.suptitle("Multiboard | retained board identity across coupled networks", fontweight="bold")
    footer(fig, "Executed reduced two-board results | explicit harness and RC contact models | not production qualified")
    save(fig, "multiboard-coupled-networks")
    result_summary = {"circuit": circuit, "thermal": thermal_results}
    request_summary = {"circuit": circuit_request, "thermal_conductances_w_per_k": [row["contact_conductance_w_per_k"] for row in thermal_rows]}
    limits = ["Circuit result is an explicit reduced R/L harness and load model, not field-extracted interconnect.",
              "Thermal result is a lumped RC network without geometry spreading, radiation, airflow, or CHT.",
              "Board identity and coupling execute, but neither result qualifies hardware."]
    record = base_record("multiboard", "Two-board harness and thermal contact", "mixed_experimental_approximate", limits,
        ("tests/python/test_multiboard_circuit.py", "tests/python/test_multiboard_thermal.py",
         "python/spike_core/multiboard_circuit.py", "python/spike_core/multiboard_thermal.py", "scripts/build_multiboard_acceptance.py"),
        request_summary, result_summary)
    record.update(units={"frequency_hz": "Hz", "board_b_load_voltage_magnitude_v": "V",
                         "board_b_load_voltage_phase_deg": "degree", "contact_conductance_w_per_k": "W/K",
                         "board_temperature_c": "deg C", "contact_heat_flow_w": "W"},
                  metrics={"circuit_relative_residual_max": circuit["native_result"]["diagnostics"]["relative_residual_max"],
                           "maximum_thermal_energy_balance_residual_w": max(abs(item["summary"]["energy_balance_residual_w"]) for item in thermal_results),
                           "board_count": 2},
                  series={"electrical": transfer_rows, "thermal": thermal_rows})
    write_json(DATA / "multiboard.json", record)
    return {"id": "multiboard", "figure": "figures/multiboard-coupled-networks.png", "data": "data/multiboard.json",
            "status": "mixed_experimental_approximate", "metrics": record["metrics"]}


def main() -> int:
    style()
    DATA.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    entries = [generate_pi(), generate_si(), generate_em(), generate_thermal(), generate_hybrid(),
               generate_cfd(), generate_cht(), generate_multiboard()]
    for entry in entries:
        entry["figure_sha256"] = sha256(OUT / entry["figure"])
        entry["data_sha256"] = sha256(OUT / entry["data"])
    manifest = {
        "schema": "spike/analysis-gallery-manifest/v1",
        "generator": {"path": "scripts/generate_analysis_gallery.py", "sha256": sha256(Path(__file__))},
        "rerun_command": ".\\.venv\\Scripts\\python.exe scripts\\generate_analysis_gallery.py",
        "artifact_class": "executed_numerical_analytics_not_application_screenshots",
        "production_qualified": False,
        "entries": entries,
    }
    write_json(OUT / "manifest.json", manifest)
    for path in FIGURES.glob("*.png"):
        shutil.copy2(path, PUBLIC / path.name)
    shutil.copy2(OUT / "manifest.json", PUBLIC / "manifest.json")
    print(json.dumps({"status": "completed", "entries": len(entries), "manifest": str(OUT / "manifest.json")}, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
