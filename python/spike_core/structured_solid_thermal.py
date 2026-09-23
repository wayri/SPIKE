# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Bounded 3-D finite-volume solid thermal reference solver.

The solver is intentionally geometry-regular and inspectable.  It advances the
native thermal validation ladder without pretending that an axis-aligned voxel
grid is a conforming PCB/assembly mesher.  Cell-centred finite volumes use
harmonic face conductance, optional material-interface contact resistance,
implicit Euler time integration, and Picard-linearized surface radiation.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from scipy.sparse import csc_matrix, diags, lil_matrix
from scipy.sparse.linalg import MatrixRankWarning, spsolve


REQUEST_CONTRACT = "spike/structured-solid-thermal-request/v1"
RESULT_CONTRACT = "spike/structured-solid-thermal-result/v1"
MAX_CELLS = 262_144
MAX_STEPS = 10_000
MAX_OUTPUT_VALUES = 2_000_000
# Conservative limits for this in-process sparse-direct reference. Larger
# production cases need a separately supervised iterative/distributed backend.
MAX_DIRECT_CELLS = 16_384
MAX_CELL_STEPS = 2_000_000
SIGMA = 5.670374419e-8
_FACES = ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")


class StructuredThermalError(ValueError):
    """Raised when a request cannot be solved without guessing."""


@dataclass(frozen=True)
class _Material:
    material_id: str
    conductivity: tuple[float, float, float]
    density: float | None
    specific_heat: float | None


@dataclass(frozen=True)
class _Model:
    shape: tuple[int, int, int]
    spacing: tuple[float, float, float]
    materials: tuple[_Material, ...]
    material_index: np.ndarray
    heat: np.ndarray
    boundaries: Mapping[str, Mapping[str, Any]]
    contacts: Mapping[tuple[str, str], float]
    mode: str
    initial_temperature: float
    time_step: float
    steps: int
    output_stride: int
    radiation_tolerance: float
    radiation_iterations: int

    @property
    def cell_count(self) -> int:
        return int(np.prod(self.shape))

    @property
    def volume(self) -> float:
        return float(np.prod(self.spacing))


def _number(value: Any, label: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StructuredThermalError(f"{label} must be a JSON number.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise StructuredThermalError(f"{label} must be numeric.") from exc
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise StructuredThermalError(f"{label} is outside its admitted range.")
    return result


def _positive_int(value: Any, label: str, *, maximum: int) -> int:
    if type(value) is not int or value < 1 or value > maximum:
        raise StructuredThermalError(f"{label} must be an integer in [1, {maximum}].")
    return value


def _strict_keys(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise StructuredThermalError(f"{label} has unknown fields: {sorted(unknown)}.")


def _vector3(value: Any, label: str) -> tuple[float, float, float]:
    raw = [value, value, value] if isinstance(value, (int, float)) else value
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 3:
        raise StructuredThermalError(f"{label} must be a positive scalar or three-vector.")
    return tuple(_number(item, f"{label}[{index}]", minimum=1e-30) for index, item in enumerate(raw))  # type: ignore[return-value]


def _parse_materials(raw: Any) -> tuple[tuple[_Material, ...], dict[str, int]]:
    if not isinstance(raw, list) or not raw or len(raw) > 256:
        raise StructuredThermalError("materials must contain 1..256 records.")
    materials: list[_Material] = []
    lookup: dict[str, int] = {}
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise StructuredThermalError(f"materials[{index}] must be an object.")
        _strict_keys(item, {"id", "thermal_conductivity_w_mk", "density_kg_m3", "specific_heat_j_kgk"}, f"materials[{index}]")
        material_id = item.get("id")
        if not isinstance(material_id, str):
            raise StructuredThermalError("Material IDs must be strings.")
        if not material_id or material_id in lookup or len(material_id) > 128:
            raise StructuredThermalError("Material IDs must be unique, non-empty, and at most 128 characters.")
        density = item.get("density_kg_m3")
        heat_capacity = item.get("specific_heat_j_kgk")
        parsed = _Material(
            material_id,
            _vector3(item.get("thermal_conductivity_w_mk"), f"materials[{index}].thermal_conductivity_w_mk"),
            None if density is None else _number(density, f"materials[{index}].density_kg_m3", minimum=1e-30),
            None if heat_capacity is None else _number(heat_capacity, f"materials[{index}].specific_heat_j_kgk", minimum=1e-30),
        )
        lookup[material_id] = len(materials)
        materials.append(parsed)
    return tuple(materials), lookup


def _parse_boundaries(raw: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(raw, Mapping) or set(raw) != set(_FACES):
        raise StructuredThermalError(f"boundaries must define exactly {list(_FACES)}.")
    result: dict[str, Mapping[str, Any]] = {}
    for face in _FACES:
        value = raw[face]
        if not isinstance(value, Mapping):
            raise StructuredThermalError(f"boundaries.{face} must be an object.")
        kind = str(value.get("type") or "")
        allowed = {
            "adiabatic": {"type"},
            "temperature": {"type", "temperature_k"},
            "convection": {"type", "ambient_temperature_k", "heat_transfer_coefficient_w_m2k"},
            "heat_flux": {"type", "inward_heat_flux_w_m2"},
            "radiation": {"type", "ambient_temperature_k", "emissivity"},
        }
        if kind not in allowed:
            raise StructuredThermalError(f"boundaries.{face}.type is unsupported.")
        _strict_keys(value, allowed[kind], f"boundaries.{face}")
        if kind == "temperature":
            _number(value.get("temperature_k"), f"boundaries.{face}.temperature_k", minimum=0.0)
        elif kind == "convection":
            _number(value.get("ambient_temperature_k"), f"boundaries.{face}.ambient_temperature_k", minimum=0.0)
            _number(value.get("heat_transfer_coefficient_w_m2k"), f"boundaries.{face}.heat_transfer_coefficient_w_m2k", minimum=1e-30)
        elif kind == "heat_flux":
            _number(value.get("inward_heat_flux_w_m2"), f"boundaries.{face}.inward_heat_flux_w_m2")
        elif kind == "radiation":
            _number(value.get("ambient_temperature_k"), f"boundaries.{face}.ambient_temperature_k", minimum=0.0)
            emissivity = _number(value.get("emissivity"), f"boundaries.{face}.emissivity", minimum=0.0)
            if emissivity > 1:
                raise StructuredThermalError(f"boundaries.{face}.emissivity must not exceed one.")
        result[face] = value
    return result


def _parse_contacts(raw: Any, material_ids: set[str]) -> dict[tuple[str, str], float]:
    if raw is None:
        return {}
    if not isinstance(raw, list) or len(raw) > 32_768:
        raise StructuredThermalError("interface_contacts must be a bounded array.")
    result: dict[tuple[str, str], float] = {}
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise StructuredThermalError(f"interface_contacts[{index}] must be an object.")
        _strict_keys(item, {"materials", "resistance_m2k_w"}, f"interface_contacts[{index}]")
        pair = item.get("materials")
        if not isinstance(pair, list) or len(pair) != 2 or any(str(v) not in material_ids for v in pair) or pair[0] == pair[1]:
            raise StructuredThermalError("Every interface contact must name two distinct known materials.")
        key = tuple(sorted((str(pair[0]), str(pair[1]))))
        if key in result:
            raise StructuredThermalError(f"Duplicate interface contact for {key}.")
        result[key] = _number(item.get("resistance_m2k_w"), f"interface_contacts[{index}].resistance_m2k_w", minimum=0.0)
    return result


def _parse_request(request: Any) -> _Model:
    if not isinstance(request, Mapping) or request.get("contract") != REQUEST_CONTRACT:
        raise StructuredThermalError(f"Request must use {REQUEST_CONTRACT}.")
    _strict_keys(request, {"contract", "grid", "materials", "material_ids", "heat_generation_w_m3", "boundaries", "interface_contacts", "study", "solver"}, "request")
    grid = request.get("grid")
    if not isinstance(grid, Mapping):
        raise StructuredThermalError("grid must be an object.")
    _strict_keys(grid, {"shape", "spacing_m"}, "grid")
    shape_raw = grid.get("shape")
    if not isinstance(shape_raw, list) or len(shape_raw) != 3:
        raise StructuredThermalError("grid.shape must contain nx, ny, nz.")
    shape = tuple(_positive_int(value, f"grid.shape[{index}]", maximum=4096) for index, value in enumerate(shape_raw))
    count = int(np.prod(shape))
    if count > MAX_CELLS:
        raise StructuredThermalError(f"The structured thermal solver admits at most {MAX_CELLS} cells.")
    spacing = _vector3(grid.get("spacing_m"), "grid.spacing_m")
    volume = math.prod(spacing)
    if not math.isfinite(volume) or volume <= 0:
        raise StructuredThermalError("Grid cell volume must be finite and positive.")
    if count > MAX_DIRECT_CELLS:
        raise StructuredThermalError("Grid exceeds the sparse-direct reference workspace limit.")
    materials, lookup = _parse_materials(request.get("materials"))
    ids = request.get("material_ids")
    if not isinstance(ids, list) or len(ids) != count or any(not isinstance(value, str) or value not in lookup for value in ids):
        raise StructuredThermalError("material_ids must identify one known material per cell in x-fast order.")
    material_index = np.asarray([lookup[str(value)] for value in ids], dtype=np.int32)
    heat_raw = request.get("heat_generation_w_m3")
    if isinstance(heat_raw, (int, float)):
        heat = np.full(count, _number(heat_raw, "heat_generation_w_m3"), dtype=float)
    elif isinstance(heat_raw, list) and len(heat_raw) == count:
        heat = np.asarray([_number(value, f"heat_generation_w_m3[{index}]") for index, value in enumerate(heat_raw)], dtype=float)
    else:
        raise StructuredThermalError("heat_generation_w_m3 must be a scalar or one value per cell.")
    boundaries = _parse_boundaries(request.get("boundaries"))
    contacts = _parse_contacts(request.get("interface_contacts"), set(lookup))
    study = request.get("study")
    if not isinstance(study, Mapping):
        raise StructuredThermalError("study must be an object.")
    mode = str(study.get("type") or "")
    if mode == "steady":
        _strict_keys(study, {"type"}, "study")
        initial, time_step, steps, stride = 300.0, 1.0, 1, 1
    elif mode == "transient":
        _strict_keys(study, {"type", "initial_temperature_k", "time_step_s", "steps", "output_stride"}, "study")
        initial = _number(study.get("initial_temperature_k"), "study.initial_temperature_k", minimum=0.0)
        time_step = _number(study.get("time_step_s"), "study.time_step_s", minimum=1e-30)
        steps = _positive_int(study.get("steps"), "study.steps", maximum=MAX_STEPS)
        stride = _positive_int(study.get("output_stride", 1), "study.output_stride", maximum=MAX_STEPS)
        for material in materials:
            if material.density is None or material.specific_heat is None:
                raise StructuredThermalError("Transient studies require density_kg_m3 and specific_heat_j_kgk for every material.")
    else:
        raise StructuredThermalError("study.type must be steady or transient.")
    if count * (1 + math.ceil(steps / stride)) > MAX_OUTPUT_VALUES:
        raise StructuredThermalError("Requested field output exceeds the bounded result budget.")
    if count * steps > MAX_CELL_STEPS:
        raise StructuredThermalError("Requested transient exceeds the cell-step work budget.")
    solver = request.get("solver", {})
    if not isinstance(solver, Mapping):
        raise StructuredThermalError("solver must be an object.")
    _strict_keys(solver, {"radiation_tolerance_k", "radiation_max_iterations"}, "solver")
    return _Model(shape, spacing, materials, material_index, heat, boundaries, contacts, mode, initial, time_step, steps, stride,
                  _number(solver.get("radiation_tolerance_k", 1e-8), "solver.radiation_tolerance_k", minimum=1e-14),
                  _positive_int(solver.get("radiation_max_iterations", 50), "solver.radiation_max_iterations", maximum=200))


def _cell(model: _Model, i: int, j: int, k: int) -> int:
    nx, ny, _ = model.shape
    return i + nx * (j + ny * k)


def _face_geometry(model: _Model, axis: int) -> tuple[float, float]:
    dx, dy, dz = model.spacing
    return ((dy * dz, dx), (dx * dz, dy), (dx * dy, dz))[axis]


def _surface_cells(model: _Model, face: str):
    nx, ny, nz = model.shape
    if face[0] == "x":
        i = 0 if face.endswith("min") else nx - 1
        for k in range(nz):
            for j in range(ny):
                yield _cell(model, i, j, k), 0
    elif face[0] == "y":
        j = 0 if face.endswith("min") else ny - 1
        for k in range(nz):
            for i in range(nx):
                yield _cell(model, i, j, k), 1
    else:
        k = 0 if face.endswith("min") else nz - 1
        for j in range(ny):
            for i in range(nx):
                yield _cell(model, i, j, k), 2


def _boundary_conductance(model: _Model, face: str, cell: int, temperature: float) -> tuple[float, float | None, float]:
    boundary = model.boundaries[face]
    kind = str(boundary["type"])
    axis = "xyz".index(face[0])
    area, distance = _face_geometry(model, axis)
    conductivity = model.materials[int(model.material_index[cell])].conductivity[axis]
    half_resistance = 0.5 * distance / conductivity
    if kind == "temperature":
        return area / half_resistance, float(boundary["temperature_k"]), 0.0
    if kind == "convection":
        film = 1.0 / float(boundary["heat_transfer_coefficient_w_m2k"])
        return area / (half_resistance + film), float(boundary["ambient_temperature_k"]), 0.0
    if kind == "radiation":
        ambient = float(boundary["ambient_temperature_k"])
        emissivity = float(boundary["emissivity"])
        # Radiation acts at the surface, not at the cell centre. Eliminate
        # surface temperature from conduction through the half cell and the
        # Stefan-Boltzmann law using their monotone scalar balance.
        low, high = sorted((temperature, ambient))
        for _ in range(64):
            surface = low + 0.5 * (high - low)
            h_surface = emissivity * SIGMA * (surface + ambient) * (surface ** 2 + ambient ** 2)
            balance = surface - temperature + half_resistance * h_surface * (surface - ambient)
            if balance > 0:
                high = surface
            else:
                low = surface
        surface = low + 0.5 * (high - low)
        h_rad = emissivity * SIGMA * (surface + ambient) * (surface ** 2 + ambient ** 2)
        return (0.0 if h_rad == 0 else area / (half_resistance + 1.0 / h_rad)), ambient, 0.0
    if kind == "heat_flux":
        return 0.0, None, float(boundary["inward_heat_flux_w_m2"]) * area
    return 0.0, None, 0.0


def _assemble(model: _Model, temperatures: np.ndarray) -> tuple[csc_matrix, np.ndarray]:
    n = model.cell_count
    matrix = lil_matrix((n, n), dtype=float)
    rhs = model.heat * model.volume
    nx, ny, nz = model.shape
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                left = _cell(model, i, j, k)
                for axis, neighbor_xyz in enumerate(((i + 1, j, k), (i, j + 1, k), (i, j, k + 1))):
                    ni, nj, nk = neighbor_xyz
                    if ni >= nx or nj >= ny or nk >= nz:
                        continue
                    right = _cell(model, ni, nj, nk)
                    area, distance = _face_geometry(model, axis)
                    left_mat = model.materials[int(model.material_index[left])]
                    right_mat = model.materials[int(model.material_index[right])]
                    contact = model.contacts.get(tuple(sorted((left_mat.material_id, right_mat.material_id))), 0.0)
                    resistance = 0.5 * distance / left_mat.conductivity[axis] + contact + 0.5 * distance / right_mat.conductivity[axis]
                    conductance = area / resistance
                    matrix[left, left] += conductance
                    matrix[right, right] += conductance
                    matrix[left, right] -= conductance
                    matrix[right, left] -= conductance
    for face in _FACES:
        for cell, _ in _surface_cells(model, face):
            conductance, reference, inward_power = _boundary_conductance(model, face, cell, float(temperatures[cell]))
            if conductance:
                matrix[cell, cell] += conductance
                rhs[cell] += conductance * float(reference)
            rhs[cell] += inward_power
    return matrix.tocsc(), rhs


def _solve_step(model: _Model, prior: np.ndarray | None, guess: np.ndarray,
                cancel_check: Callable[[], bool] | None = None) -> tuple[np.ndarray, csc_matrix, np.ndarray, int]:
    has_radiation = any(model.boundaries[face]["type"] == "radiation" for face in _FACES)
    iterations = model.radiation_iterations if has_radiation else 1
    current = guess.copy()
    for iteration in range(iterations):
        if cancel_check is not None and cancel_check():
            raise StructuredThermalError("Thermal solve cancelled.")
        matrix, rhs = _assemble(model, current)
        if prior is not None:
            capacity = np.asarray([
                model.materials[int(material)].density * model.materials[int(material)].specific_heat * model.volume
                for material in model.material_index
            ], dtype=float)
            inertia = capacity / model.time_step
            matrix = matrix + diags(inertia, format="csc")
            rhs = rhs + inertia * prior
        try:
            if not np.all(np.isfinite(matrix.data)) or not np.all(np.isfinite(rhs)):
                raise StructuredThermalError("Derived thermal operator contains non-finite coefficients.")
            with warnings.catch_warnings():
                warnings.simplefilter("error", MatrixRankWarning)
                solved = np.asarray(spsolve(matrix, rhs), dtype=float)
        except Exception as exc:
            raise StructuredThermalError(f"Sparse thermal solve failed: {exc}") from exc
        if cancel_check is not None and cancel_check():
            raise StructuredThermalError("Thermal solve cancelled.")
        if solved.shape != (model.cell_count,) or not np.all(np.isfinite(solved)) or np.any(solved < 0):
            raise StructuredThermalError("Thermal solve produced invalid absolute temperatures.")
        # Under-relax the radiation fixed point; the secant iteration can
        # oscillate for a cold radiative environment even with a unique root.
        if has_radiation:
            solved = 0.5 * (solved + current)
        change = float(np.max(np.abs(solved - current)))
        current = solved
        if not has_radiation or change <= model.radiation_tolerance:
            final_matrix, final_rhs = _assemble(model, current)
            if prior is not None:
                capacity = np.asarray([
                    model.materials[int(material)].density * model.materials[int(material)].specific_heat * model.volume
                    for material in model.material_index
                ], dtype=float)
                inertia = capacity / model.time_step
                final_matrix = final_matrix + diags(inertia, format="csc")
                final_rhs = final_rhs + inertia * prior
            relative = float(np.linalg.norm(final_matrix @ current - final_rhs) / max(np.linalg.norm(final_rhs), 1e-30))
            if relative <= 1e-10 and _energy(model, current, prior)["passed"]:
                return current, final_matrix, final_rhs, iteration + 1
    raise StructuredThermalError("Surface-radiation iteration did not converge within its admitted limit.")


def _energy(model: _Model, temperatures: np.ndarray, prior: np.ndarray | None) -> dict[str, float | bool]:
    generated = float(np.sum(model.heat) * model.volume)
    outward = 0.0
    boundary_throughput = 0.0
    roundoff_scale = 0.0
    for face in _FACES:
        for cell, _ in _surface_cells(model, face):
            conductance, reference, inward = _boundary_conductance(model, face, cell, float(temperatures[cell]))
            power = conductance * (float(temperatures[cell]) - float(reference)) if conductance else -inward
            outward += power
            boundary_throughput += abs(power)
            if conductance:
                roundoff_scale += conductance * (abs(float(temperatures[cell])) + abs(float(reference)))
    storage = 0.0
    if prior is not None:
        capacity = np.asarray([
            model.materials[int(material)].density * model.materials[int(material)].specific_heat * model.volume
            for material in model.material_index
        ], dtype=float)
        storage = float(np.dot(capacity, temperatures - prior) / model.time_step)
        roundoff_scale += float(np.dot(capacity, np.abs(temperatures) + np.abs(prior)) / model.time_step)
    residual = generated - outward - storage
    scale = max(float(np.sum(np.abs(model.heat)) * model.volume) + boundary_throughput + abs(storage), 1e-30)
    relative = abs(residual) / scale
    roundoff_allowance = float(64 * np.finfo(float).eps * roundoff_scale)
    return {"generated_power_w": generated, "outward_boundary_power_w": outward, "storage_rate_w": storage,
            "residual_w": residual, "relative_residual": relative,
            "roundoff_allowance_w": roundoff_allowance, "boundary_throughput_w": boundary_throughput,
            "passed": abs(residual) <= 1e-9 * scale + roundoff_allowance}


def solve_structured_solid_thermal(request: Any, *, cancel_check: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Validate and solve a bounded steady or transient 3-D thermal request."""
    try:
        model = _parse_request(request)
        if model.mode == "steady" and not any(
            model.boundaries[face]["type"] in {"temperature", "convection"}
            or (model.boundaries[face]["type"] == "radiation" and model.boundaries[face]["emissivity"] > 0)
            for face in _FACES
        ):
            raise StructuredThermalError("A steady problem needs at least one temperature-referenced boundary.")
        initial_references = [
            float(model.boundaries[face].get("temperature_k", model.boundaries[face].get("ambient_temperature_k")))
            for face in _FACES if model.boundaries[face]["type"] in {"temperature", "convection", "radiation"}
        ]
        current = np.full(model.cell_count, model.initial_temperature if model.mode == "transient" else float(np.mean(initial_references)), dtype=float)
        if model.mode == "steady" and np.all(current == 0) and np.any(model.heat > 0):
            current.fill(300.0)
        frames: list[dict[str, Any]] = []
        final_matrix: csc_matrix | None = None
        final_rhs: np.ndarray | None = None
        nonlinear_iterations = 0
        last_energy: dict[str, Any] = {}
        for step in range(1 if model.mode == "steady" else model.steps):
            if cancel_check is not None and cancel_check():
                raise StructuredThermalError("Thermal solve cancelled.")
            prior = None if model.mode == "steady" else current.copy()
            current, final_matrix, final_rhs, used = _solve_step(model, prior, current, cancel_check)
            nonlinear_iterations += used
            last_energy = _energy(model, current, prior)
            step_residual = np.asarray(final_matrix @ current - final_rhs, dtype=float)
            step_relative = float(np.linalg.norm(step_residual) / max(np.linalg.norm(final_rhs), 1e-30))
            if not math.isfinite(step_relative) or step_relative > 1e-10 or not last_energy["passed"]:
                raise StructuredThermalError("Thermal timestep failed residual or energy-conservation acceptance.")
            if model.mode == "transient" and ((step + 1) % model.output_stride == 0 or step + 1 == model.steps):
                frames.append({"time_s": (step + 1) * model.time_step, "temperature_k": current.tolist(), "energy": last_energy})
        assert final_matrix is not None and final_rhs is not None
        residual = np.asarray(final_matrix @ current - final_rhs, dtype=float)
        relative_linear = float(np.linalg.norm(residual) / max(np.linalg.norm(final_rhs), 1e-30))
        if relative_linear > 1e-10 or not bool(last_energy.get("passed")):
            raise StructuredThermalError("Thermal residual or energy-conservation qualification failed.")
        return {
            "contract": RESULT_CONTRACT, "status": "completed", "model_status": "verification_reference",
            "shape": list(model.shape), "spacing_m": list(model.spacing), "cell_order": "x-fast",
            "temperature_k": current.tolist(), "frames": frames,
            "summary": {"cell_count": model.cell_count, "minimum_temperature_k": float(np.min(current)),
                        "maximum_temperature_k": float(np.max(current)), "mean_temperature_k": float(np.mean(current)),
                        "linear_relative_residual": relative_linear, "radiation_linearization_iterations": nonlinear_iterations},
            "energy": last_energy, "issues": [],
            "qualification": {"state": "bounded_structured_grid_reference", "production_qualified": False,
                              "limitations": ["Axis-aligned Cartesian cells only.", "No geometry-derived airflow or conforming CAD mesh.",
                                              "Independent-solver, measured, Windows/Linux package, and private-CI evidence remain required."]},
        }
    except (StructuredThermalError, OverflowError, FloatingPointError) as exc:
        return {"contract": RESULT_CONTRACT, "status": "cancelled" if "cancelled" in str(exc).lower() else "blocked",
                "model_status": "failed", "temperature_k": [], "frames": [], "issues": [{"code": "STRUCTURED_THERMAL_REJECTED", "severity": "error", "message": str(exc)}],
                "qualification": {"state": "not_executed", "production_qualified": False}}


__all__ = ["MAX_CELLS", "MAX_STEPS", "REQUEST_CONTRACT", "RESULT_CONTRACT", "StructuredThermalError", "solve_structured_solid_thermal"]
