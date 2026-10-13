# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Capture one bounded, actual openEMS E/H volume for the two-board box fixture.

This example records native frequency-domain E and H phasors. It is a
visualization/probe data capture, not Ethernet, LVDS, SerDes, or product
qualification. The output directory must not already exist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from python.spike_core.external_engines import _run_isolated_python
from python.spike_core.openems_assembly_geometry import compile_assembly_geometry
from python.spike_core.runtime_locations import openems_install_root, openems_python
from python.spike_core.crossboard_mesh import plan_crossboard_mesh
from scripts.run_crossboard_openems import fixture

FREQUENCIES_HZ = [0.5e9, 1.5e9, 2.5e9]

WORKER = r'''
import hashlib
import json
import math
from pathlib import Path

import h5py
import numpy as np
from CSXCAD import ContinuousStructure
from importlib.metadata import version
from openEMS import openEMS

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def decode(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray):
        return [decode(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return decode(value.item())
    return value

def hdf5_inventory(path):
    datasets = []
    with h5py.File(path, "r") as handle:
        def visit(name, obj):
            if isinstance(obj, h5py.Dataset):
                datasets.append({"path": "/" + name, "shape": list(obj.shape),
                    "dtype": str(obj.dtype),
                    "attributes": {str(key): decode(value) for key, value in obj.attrs.items()}})
        handle.visititems(visit)
        attributes = {str(key): decode(value) for key, value in handle.attrs.items()}
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": digest(path),
            "attributes": attributes, "datasets": datasets}

def read_frequency_dump(path, expected_frequencies):
    with h5py.File(path, "r") as handle:
        axes = [np.asarray(handle["/Mesh/" + name], dtype=float) for name in ("x", "y", "z")]
        group = handle["/FieldData/FD"]
        stored = np.asarray(group.attrs.get("frequency", expected_frequencies), dtype=float).reshape(-1)
        frames = []
        for index, requested in enumerate(expected_frequencies):
            base = "f" + str(index)
            if base in group:
                raw = np.asarray(group[base])
                if raw.dtype.fields:
                    names = raw.dtype.names or ()
                    real_name = "r" if "r" in names else names[0]
                    imag_name = "i" if "i" in names else names[1]
                    field = np.asarray(raw[real_name], dtype=float) + 1j * np.asarray(raw[imag_name], dtype=float)
                else:
                    field = raw.astype(complex)
                attrs = group[base].attrs
            else:
                real_ds = group[base + "_real"]
                imag_ds = group[base + "_imag"]
                field = np.asarray(real_ds, dtype=float) + 1j * np.asarray(imag_ds, dtype=float)
                attrs = real_ds.attrs
            order = decode(attrs.get("d_order", "NZYX"))
            if isinstance(order, list):
                order = "".join(str(item) for item in order)
            order = str(order).upper()
            if order == "NZYX":
                field = field.transpose(0, 3, 2, 1)
            elif order != "NXYZ":
                expected = tuple(len(axis) for axis in axes)
                if tuple(field.shape[1:]) == expected[::-1]:
                    field = field.transpose(0, 3, 2, 1)
                elif tuple(field.shape[1:]) != expected:
                    raise ValueError("Unsupported field axis order " + order + " with shape " + str(field.shape))
            expected_shape = (3, *(len(axis) for axis in axes))
            if tuple(field.shape) != expected_shape:
                raise ValueError("Field shape " + str(field.shape) + " does not match mesh " + str(expected_shape))
            vectors = np.moveaxis(field, 0, -1).reshape(-1, 3)
            frequency = float(attrs.get("frequency", stored[index] if index < len(stored) else requested))
            frames.append({"frequency_hz": frequency,
                           "real": vectors.real.tolist(), "imag": vectors.imag.tolist()})
        return {"axes_m": {name: axis.tolist() for name, axis in zip(("x", "y", "z"), axes)},
                "shape": [len(axis) for axis in axes],
                "storage_order": "Cartesian product [ix,iy,iz], flattened in NumPy C order; component x,y,z",
                "frames": frames}

root = Path(OUTPUT)
raw = RAW
compiled = compile_assembly_geometry(raw)
gap = GAP
frequencies = np.asarray(FIELD_FREQUENCIES_HZ, dtype=float)
csx = ContinuousStructure()
fdtd = openEMS(NrTS=MAX_STEPS, EndCriteria=END_CRITERIA)
fdtd.SetCSX(csx)
fdtd.SetGaussExcite(1.5e9, 1.5e9)
fdtd.SetBoundaryCond(["PML_8"] * 6)
emit_csxcad_geometry(csx, raw)
grid = csx.GetGrid()
grid.SetDeltaUnit(1e-3)
definitions = [([-15, -1, -1], [-15, 1, 0]), ([15, -1, -1], [15, 1, 0]),
               ([-15, -1, gap], [-15, 1, gap + 1]), ([15, -1, gap], [15, 1, gap + 1])]
plan = plan_crossboard_mesh(compiled, definitions, base_spacing_mm=MESH, level=MESH_LEVEL)
for axis in range(3):
    grid.AddLine(axis, plan["lines_mm"][axis])
ports = []
for index, (start, stop) in enumerate(definitions):
    for axis in range(3):
        grid.AddLine(axis, [(start[axis] + stop[axis]) / 2])
    ports.append(fdtd.AddLumpedPort(index + 1, 50.0, start, stop, "z",
                 1.0 if index == 0 else 0.0, priority=50, edges2grid="all"))

inner = []
for axis in range(3):
    lines = grid.GetLines(axis, do_sort=True)
    low = min(box["start_mm"][axis] for box in compiled["boxes"])
    high = max(box["stop_mm"][axis] for box in compiled["boxes"])
    if len(lines) < 19 or not lines[8] < low or not lines[-9] > high:
        raise ValueError("Eight-cell PML overlaps or touches assembly material")
    inner.append([float(lines[8]), float(lines[-9])])
dimensions = [len(grid.GetLines(axis, do_sort=True)) - 1 for axis in range(3)]
cells = math.prod(dimensions)
if cells > 1500000:
    raise ValueError("Cross-board field fixture exceeds 1.5 million cells")

# Cell interpolation gives co-located E/H vectors. All materials in this
# fixture use relative permeability 1. Raw HDF5 remains the solver authority.
capture_start = [-20.0, -10.0, -1.1]
capture_stop = [20.0, 10.0, gap + 1.1]
e_dump = csx.AddDump("interboard_Ef", dump_type=10, dump_mode=2, file_type=1)
h_dump = csx.AddDump("interboard_Hf", dump_type=11, dump_mode=2, file_type=1)
e_dump.SetFrequency(frequencies)
h_dump.SetFrequency(frequencies)
e_dump.AddBox(capture_start, capture_stop)
h_dump.AddBox(capture_start, capture_stop)

simulation = root / "simulation"
csx.Write2XML(str(root / "geometry.xml"))
fdtd.Run(str(simulation), cleanup=True, verbose=0, numThreads=1)
for port in ports:
    port.CalcPort(str(simulation), frequencies, ref_impedance=50.0)
incident = np.asarray(ports[0].uf_inc)
if not np.isfinite(incident).all() or np.any(np.abs(incident) < 1e-10 * max(np.max(np.abs(incident)), 1e-30)):
    raise ValueError("Insufficient incident spectrum at requested field frequencies")
e_path = simulation / "interboard_Ef.h5"
h_path = simulation / "interboard_Hf.h5"
if not e_path.is_file() or not h_path.is_file():
    raise FileNotFoundError("openEMS did not write both requested E/H HDF5 dumps")
e_field = read_frequency_dump(e_path, frequencies)
h_field = read_frequency_dump(h_path, frequencies)
if e_field["axes_m"] != h_field["axes_m"] or e_field["shape"] != h_field["shape"]:
    raise ValueError("E and H field dumps are not co-located")

result = {
    "contract": "spike/openems-spatial-eh-field/v1", "status": "executed",
    "model_status": "unvalidated", "solver": "openEMS", "solver_version": version("openEMS"),
    "coordinate_system": "Cartesian", "coordinate_unit": "m", "vector_components": ["x", "y", "z"],
    "electric_field_unit": "V/m", "magnetic_field_unit": "A/m",
    "positions": e_field["axes_m"], "shape": e_field["shape"], "storage_order": e_field["storage_order"],
    "excitation": {"port": "A.near", "openems_lumped_port_number": 1, "direction": "z",
        "reference_impedance_ohm": 50.0, "excitation_amplitude": 1.0,
        "excitation_amplitude_semantics": "openEMS AddLumpedPort excitation argument with Gaussian pulse",
        "gaussian_center_hz": 1.5e9, "gaussian_width_hz": 1.5e9,
        "other_ports_excitation_amplitude": 0.0,
        "incident_voltage_real_v": incident.real.tolist(), "incident_voltage_imag_v": incident.imag.tolist(),
        "reflected_voltage_real_v": np.asarray(ports[0].uf_ref).real.tolist(),
        "reflected_voltage_imag_v": np.asarray(ports[0].uf_ref).imag.tolist()},
    "frequencies_hz": frequencies.tolist(), "electric_field": e_field["frames"],
    "magnetic_field": h_field["frames"],
    "geometry": {"gap_mm": gap, "capture_bounds_mm": {"start": capture_start, "stop": capture_stop},
                 "ports": ["A.near", "A.far", "B.near", "B.far"]},
    "mesh": {"dimensions": dimensions, "cells": cells, "inner_pml_bounds_mm": inner,
             "policy": plan["policy"], "level": MESH_LEVEL, "base_spacing_mm": MESH,
             "dump_mode": 2, "dump_mode_name": "cell interpolation"},
    "solver_controls": {"end_criteria": END_CRITERIA, "max_timesteps": MAX_STEPS, "threads": 1},
    "native_artifacts": [hdf5_inventory(e_path), hdf5_inventory(h_path)], "production_qualified": False,
    "limitations": [
        "Original box geometry only; not imported complete PCB, connector, cable, or harness geometry.",
        "One broadband lumped-port excitation and three frequencies from 0.2 to 3 GHz scope; no 10/100G qualification.",
        "Coarse Cartesian copper cells do not resolve RF skin depth; mesh and duration convergence are not established.",
        "Fields are raw complex openEMS frequency-domain samples for the recorded Gaussian-pulse excitation, not normalized to 1 W accepted power."]}
for quantity in ("electric_field", "magnetic_field"):
    for frame in result[quantity]:
        values = np.asarray(frame["real"], dtype=float) + 1j * np.asarray(frame["imag"], dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("Non-finite " + quantity + " samples")
(root / "field-samples.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
(root / "dump-schema.json").write_text(json.dumps(result["native_artifacts"], indent=2, allow_nan=False), encoding="utf-8")
print(json.dumps({"status": result["status"], "shape": result["shape"],
                  "frequencies_hz": result["frequencies_hz"],
                  "field_samples_per_quantity": math.prod(result["shape"]) * len(frequencies)}))
'''

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("actual_capture"))
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    if not 30 <= args.timeout <= 600:
        parser.error("timeout must be 30..600 seconds")
    raw = fixture(4.0)
    compiled = compile_assembly_geometry(raw)
    definitions = [([-15, -1, -1], [-15, 1, 0]), ([15, -1, -1], [15, 1, 0]),
                   ([-15, -1, 4], [-15, 1, 5]), ([15, -1, 4], [15, 1, 5])]
    plan = plan_crossboard_mesh(compiled, definitions, base_spacing_mm=2.0, level=0)
    if args.plan_only:
        print(json.dumps({"geometry": raw, "mesh": plan, "frequencies_hz": FREQUENCIES_HZ}, indent=2))
        return 0
    output = args.output.resolve()
    owned_root = Path(__file__).resolve().parent
    if owned_root not in output.parents:
        parser.error("output must be below examples/high_speed_si/field")
    output.mkdir(parents=True, exist_ok=False)
    modules = [ROOT / "extensions/openems_suite/openems_assembly_geometry.py",
               ROOT / "python/spike_core/crossboard_mesh.py"]
    source = "\n".join(path.read_text(encoding="utf-8") for path in modules)
    tracked = [*modules, ROOT / "scripts/run_crossboard_openems.py", Path(__file__)]
    source_hashes = {str(path.relative_to(ROOT)): digest(path) for path in tracked}
    payload = (source + "\nOUTPUT=" + repr(str(output)) + "\nRAW=" + repr(raw) +
               "\nGAP=4.0\nMESH=2.0\nMESH_LEVEL=0\nEND_CRITERIA=1e-7\nMAX_STEPS=120000" +
               "\nFIELD_FREQUENCIES_HZ=" + repr(FREQUENCIES_HZ) + "\n" + WORKER).encode()
    (output / "input.json").write_text(json.dumps({
        "contract": "spike/openems-spatial-eh-field-input/v1", "geometry": raw,
        "compiled_geometry": compiled, "frequencies_hz": FREQUENCIES_HZ, "excited_port": "A.near",
        "mesh": {"base_spacing_mm": 2.0, "level": 0, "policy": plan["policy"]},
        "solver_controls": {"end_criteria": 1e-7, "max_timesteps": 120000, "threads": 1},
        "production_qualified": False}, indent=2, allow_nan=False), encoding="utf-8")
    environment = {key: os.environ[key] for key in
                   ("PATH", "SYSTEMROOT", "WINDIR", "USERPROFILE", "LD_LIBRARY_PATH") if key in os.environ}
    environment.update(OPENEMS_INSTALL_PATH=openems_install_root(), TEMP=str(output), TMP=str(output))
    started = time.perf_counter()
    execution = _run_isolated_python(openems_python(), payload, [], cwd=output, environment=environment,
        log_path=output / "solver.log", output_root=output, timeout_seconds=args.timeout,
        output_limit_bytes=512 * 1024**2)
    unchanged = all(digest(ROOT / path) == value for path, value in source_hashes.items())
    success = execution["returncode"] == 0 and unchanged and (output / "field-samples.json").is_file()
    runtime_executable = Path(openems_install_root()) / "openEMS.exe"
    report = {"contract": "spike/openems-spatial-eh-field-execution/v1",
        "status": "executed" if success else "failed", "execution": execution,
        "elapsed_s": time.perf_counter() - started, "machine": platform.platform(),
        "runtime_python": openems_python(), "runtime_root": openems_install_root(),
        "runtime_openems_sha256": digest(runtime_executable) if runtime_executable.is_file() else None,
        "source_sha256": source_hashes, "sources_unchanged": unchanged,
        "worker_sha256": hashlib.sha256(payload).hexdigest(),
        "artifact_sha256": {str(path.relative_to(output)): digest(path) for path in output.rglob("*") if path.is_file()},
        "production_qualified": False}
    (output / "execution.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if success else 1

if __name__ == "__main__":
    raise SystemExit(main())
