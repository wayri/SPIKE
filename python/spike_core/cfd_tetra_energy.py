# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Research steady tetra RT0/P0 conduction and shared-face upwind enthalpy.

Prescribed coefficients and mass flux only; not turbulent CHT qualification.
See docs/validation/CFD_TETRA_ENERGY_20261021.md.
"""
import json
import math
import numbers
import time

import numpy as np
from scipy.sparse import bmat, coo_matrix, diags
from scipy.sparse.linalg import LinearOperator, onenormest, splu

from .cfd_tetra_mesh import admit_cfd_tetra_mesh
from .enclosure_sa_transport import _matvec

CONTRACT = "spike/cfd-tetra-energy/v1"
RESULT_CONTRACT = "spike/cfd-tetra-energy-result/v1"
MAX_FIELD_BYTES = 4 * 1024**2
MAX_FACTOR_NONZEROS = 4_000_000
MAX_SECONDS = 60.


def _array(raw, count, name, positive=False):
    if isinstance(raw, (list, tuple)) and (
            len(raw) != count or not all(isinstance(v, numbers.Real) and not isinstance(v, (bool, np.bool_))
                                        for v in raw)):
        raise ValueError(f"{name} must be a flat real array of length {count}")
    a = np.asarray(raw)
    if a.shape != (count,) or a.dtype.kind not in "iuf":
        raise ValueError(f"{name} must be a real array of length {count}")
    a = a.astype(float)
    if not np.isfinite(a).all() or (positive and np.any(a <= 0.)):
        raise ValueError(f"{name} must be finite" + (" and positive" if positive else ""))
    return a


def _values(raw, count, name, positive=False):
    if type(raw) in (int, float):
        raw = [raw]*count
    return _array(raw, count, name, positive)


def _max(a):
    return float(np.max(np.abs(a), initial=0.))


def _relative(error, scale):
    return error/scale if scale else (0. if error == 0. else math.inf)


def _temperature_lift(mesh, boundaries, anchor):
    """Area-weighted prescribed temperature, formed without large sums."""
    temperatures, areas = [], []
    for patch, faces in mesh["boundary_patches"].items():
        bc = boundaries[patch]
        if not isinstance(bc, dict):
            raise ValueError("Boundary condition must be a mapping")
        name = {"temperature": "temperature_k", "convection": "ambient_temperature_k"}.get(bc.get("type"))
        if name is not None:
            temperatures.extend(_values(bc[name], len(faces), name, True))
            areas.extend(mesh["face_areas"][faces])
    if not temperatures:
        return anchor
    temperatures, areas = np.asarray(temperatures), np.asarray(areas)
    reference = temperatures[0]
    return float(reference+np.sum((areas/np.sum(areas))*(temperatures-reference)))


def _inputs(request, cancel_check):
    if not isinstance(request, dict) or set(request) != {
            "contract", "mesh", "cell_material_ids", "materials", "face_mass_flow_kg_s",
            "source_w_m3", "reference_temperature_k", "boundaries"} or request["contract"] != CONTRACT:
        raise ValueError("Invalid tetra energy contract or fields")
    mesh = admit_cfd_tetra_mesh(request["mesh"], cancel_check=cancel_check)
    count, faces = len(mesh["cells"]), len(mesh["face_areas"])
    ids, materials = request["cell_material_ids"], request["materials"]
    if (not isinstance(ids, list) or len(ids) != count
            or not all(isinstance(s, str) and 0 < len(s) <= 128 for s in ids)
            or not isinstance(materials, dict) or set(materials) != set(ids)):
        raise ValueError("Explicit material IDs must cover cells and materials exactly")
    conductivity, cp, fluid = np.empty(count), np.empty(count), np.zeros(count, bool)
    for key, material in materials.items():
        if not isinstance(material, dict) or set(material) != {
                "phase", "conductivity_w_mk", "specific_heat_j_kgk"}:
            raise ValueError("Invalid material fields")
        phase = material["phase"]
        k, c = material["conductivity_w_mk"], material["specific_heat_j_kgk"]
        if (phase not in ("solid", "fluid") or type(k) not in (int, float)
                or type(c) not in (int, float) or not math.isfinite(k) or k <= 0.
                or not math.isfinite(c) or (c <= 0. if phase == "fluid" else c < 0.)):
            raise ValueError("Materials require k>0, fluid cp>0, and unused solid cp>=0")
        selected = np.array([s == key for s in ids])
        conductivity[selected], cp[selected], fluid[selected] = k, c, phase == "fluid"
    mass = _array(request["face_mass_flow_kg_s"], faces, "face mass flow")
    source = _array(request["source_w_m3"], count, "source")
    anchor = request["reference_temperature_k"]
    if type(anchor) not in (int, float) or not math.isfinite(anchor) or anchor <= 0.:
        raise ValueError("Reference temperature must be finite and positive")
    signs, cf = mesh["cell_face_signs"], mesh["cell_faces"]
    if np.any(mass[cf[~fluid]] != 0.):
        raise ValueError("Every solid and fluid-solid face requires exactly zero mass flux")
    balance = np.array([math.fsum(float(s*m) for s, m in zip(ss, mm))
                        for ss, mm in zip(signs, mass[cf])])
    throughput = np.sum(abs(mass[cf]), axis=1)
    rel_mass = max((_relative(abs(v), s) for v, s in zip(balance, throughput)), default=0.)
    if not math.isfinite(rel_mass) or rel_mass > 1e-10:
        raise ValueError("Cell mass balance exceeds 1e-10 relative tolerance")
    for left, right in mesh["face_owners"]:
        if right >= 0 and fluid[left] and fluid[right] and cp[left] != cp[right]:
            raise ValueError("Fluid heat capacity must be identical in each connected fluid component")
    boundaries = request["boundaries"]
    if not isinstance(boundaries, dict) or set(boundaries) != set(mesh["boundary_patches"]):
        raise ValueError("Thermal boundaries must cover every patch exactly")
    return mesh, conductivity, cp, fluid, mass, source, float(anchor), boundaries, balance, rel_mass


def _assemble(mesh, conductivity, cp, mass, source, anchor, boundaries, mass_balance, cancel_check):
    nc, nf = len(mesh["cells"]), len(mesh["face_areas"])
    rows, cols, values = [], [], []
    drow, dcol, dval = [], [], []
    for cell, vertices in enumerate(mesh["cells"]):
        if cancel_check and cancel_check():
            raise InterruptedError()
        points = mesh["vertices"][vertices]
        local = points-points[0]
        offsets = local-local.mean(axis=0)
        covariance_trace = float(np.sum(offsets*offsets))/20.
        gram = np.sum(offsets[:, None, :]*offsets[None, :, :], axis=2) + covariance_trace
        s = mesh["cell_face_signs"][cell]
        local_mass = (gram/(9.*mesh["cell_volumes"][cell])/conductivity[cell]) * (s[:, None]*s[None, :])
        if not np.isfinite(local_mass).all() or np.linalg.eigvalsh(local_mass)[0] <= 0.:
            raise ValueError("Invalid or unrepresentable RT0 cell mass")
        f = mesh["cell_faces"][cell]
        for i in range(4):
            drow.append(cell); dcol.append(int(f[i])); dval.append(int(s[i]))
            for j in range(4):
                rows.append(int(f[i])); cols.append(int(f[j])); values.append(local_mass[i, j])
    mixed = coo_matrix((values, (rows, cols)), shape=(nf, nf)).tocsr()
    divergence = coo_matrix((dval, (drow, dcol)), shape=(nc, nf)).tocsr()
    rhs_flux, robin = np.zeros(nf), np.zeros(nf)
    fixed, fixed_values, inflow = [], [], {}
    anchored = set()
    for patch, faces in mesh["boundary_patches"].items():
        bc = boundaries[patch]
        if not isinstance(bc, dict):
            raise ValueError("Boundary condition must be a mapping")
        kind = bc.get("type")
        fields = {"temperature": {"temperature_k"}, "heat_flux": {"outward_heat_flux_w_m2"},
                  "convection": {"ambient_temperature_k", "heat_transfer_coefficient_w_m2k"}}
        if kind not in fields or set(bc)-{"inflow_temperature_k"} != {"type"} | fields[kind]:
            raise ValueError("Invalid thermal boundary fields")
        if kind in ("temperature", "convection"):
            name = "temperature_k" if kind == "temperature" else "ambient_temperature_k"
            temp = _values(bc[name], len(faces), name, True)
            rhs_flux[faces] = -(temp-anchor)
            anchored.update(int(mesh["face_owners"][f, 0]) for f in faces)
            if kind == "convection":
                h = _values(bc["heat_transfer_coefficient_w_m2k"], len(faces), "heat transfer", True)
                robin[faces] = 1./(h*mesh["face_areas"][faces])
        else:
            value = _values(bc["outward_heat_flux_w_m2"], len(faces), "outward heat flux")
            fixed.extend(int(f) for f in faces)
            fixed_values.extend(value*mesh["face_areas"][faces])
        if "inflow_temperature_k" in bc:
            incoming = _values(bc["inflow_temperature_k"], len(faces), "inflow temperature", True)
        elif kind == "temperature":
            incoming = temp
        else:
            incoming = None
        for i, f in enumerate(faces):
            if mass[f] < 0.:
                if incoming is None:
                    raise ValueError("Incoming mass flux requires explicit inflow temperature")
                inflow[int(f)] = incoming[i]-anchor
    if any(not anchored.intersection(int(c) for c in component) for component in mesh["components"]):
        raise ValueError("Every thermal component requires a temperature or convection anchor")
    mixed += diags(robin)
    hr, hc, hv = [], [], []
    # Include the accepted, nonzero roundoff mass defect without subtracting
    # large baseline enthalpy face sums. This preserves the original T equation.
    load = source*mesh["cell_volumes"] - (anchor*cp)*mass_balance
    incoming_heat = np.zeros(nf)
    for f, (left, right) in enumerate(mesh["face_owners"]):
        transport = mass[f]*cp[left]
        if right >= 0:
            donor = left if transport >= 0. else right
            hr.extend((left, right)); hc.extend((donor, donor)); hv.extend((transport, -transport))
        elif transport >= 0.:
            hr.append(left); hc.append(left); hv.append(transport)
        else:
            incoming_heat[f] = transport*inflow[f]
            load[left] -= incoming_heat[f]
    advection = coo_matrix((hv, (hr, hc)), shape=(nc, nc)).tocsr()
    fixed = np.array(fixed, dtype=int)
    prescribed = np.array(fixed_values)
    free = np.setdiff1d(np.arange(nf), fixed)
    if len(fixed):
        rhs_flux -= _matvec(mixed[:, fixed], prescribed)
        load -= _matvec(divergence[:, fixed], prescribed)
    return mixed, divergence, advection, rhs_flux, load, free, fixed, prescribed, incoming_heat


def solve_cfd_tetra_energy(request, *, cancel_check=None):
    result = {"contract": RESULT_CONTRACT, "research_only": True, "production_qualified": False,
              "scope": "steady_prescribed_coefficient_tetra_conjugate_sensible_energy"}
    started = time.monotonic()
    external_cancel = cancel_check
    def poll():
        if time.monotonic()-started > MAX_SECONDS:
            raise ValueError("Tetra energy exceeded cooperative 60-second budget")
        return external_cancel is not None and external_cancel()
    cancel_check = poll
    try:
        if cancel_check and cancel_check():
            raise InterruptedError()
        with np.errstate(all="raise"):
            mesh, k, cp, fluid, mass, source, anchor, boundaries, mass_balance, rel_mass = _inputs(request, cancel_check)
            lift = _temperature_lift(mesh, boundaries, anchor)
            m, d, h, r1, r2, free, fixed, prescribed, incoming = _assemble(
                mesh, k, cp, mass, source, lift, boundaries, mass_balance, cancel_check)
            mf, df = m[free][:, free], d[:, free]
            fs = 1./np.sqrt(mf.diagonal())
            ds = df @ diags(fs)
            ts = 1./np.sqrt(np.asarray(ds.multiply(ds).sum(axis=1)).ravel())
            scale = np.r_[fs, ts]
            matrix = bmat([[mf, -df.T], [-df, -h]], format="csc")
            rhs = np.r_[r1[free], -r2]
            scaled = (diags(scale) @ matrix @ diags(scale)).tocsc()
            if not np.isfinite(scaled.data).all() or not np.isfinite(rhs).all():
                raise ValueError("Unrepresentable scaled energy system")
            if cancel_check and cancel_check():
                raise InterruptedError()
            factor = splu(scaled)
            if cancel_check():
                raise InterruptedError()
            factor_nonzeros = int(factor.L.nnz+factor.U.nnz)
            if factor_nonzeros > MAX_FACTOR_NONZEROS:
                raise ValueError("Tetra energy sparse factors exceed 4000000 nonzeros")
            inverse = LinearOperator(scaled.shape, matvec=factor.solve,
                                     rmatvec=lambda x: factor.solve(x, trans="T"),
                                     matmat=factor.solve, dtype=float)
            condition = float(np.max(np.asarray(abs(scaled).sum(axis=0))))*float(onenormest(inverse, t=1))
            if cancel_check():
                raise InterruptedError()
            if not math.isfinite(condition) or condition > 1e10:
                raise ValueError("Scaled energy condition estimate exceeds 1e10")
            scaled_rhs = scale*rhs
            solution = scale*factor.solve(scaled_rhs)
            residual = _matvec(matrix, solution)-rhs
            relative = _relative(_max(scale*residual), _max(scaled_rhs))
            if not math.isfinite(relative) or relative > 1e-10:
                raise ValueError("Actual mixed energy residual exceeds 1e-10")
            flux = np.zeros(len(mesh["face_areas"]))
            flux[free], flux[fixed] = solution[:len(free)], prescribed
            lifted_rise = solution[len(free):]
            rise = lifted_rise+(lift-anchor)
            temperature = lifted_rise+lift
            if not np.isfinite(temperature).all() or np.any(temperature <= 0.):
                raise ValueError("Nonpositive or nonfinite absolute temperature")
            lifted_advective = incoming.copy()
            for f, (left, right) in enumerate(mesh["face_owners"]):
                if right >= 0 or mass[f] >= 0.:
                    donor = left if mass[f] >= 0. or right < 0 else right
                    lifted_advective[f] = mass[f]*cp[left]*lifted_rise[donor]
            transport = mass*cp[mesh["face_owners"][:, 0]]
            advective = lifted_advective+transport*(lift-anchor)
            # Certify the ORIGINAL absolute-T equation without summing a
            # constant advective field. Keep the caller's original scales.
            cell_heat = _matvec(d, flux+lifted_advective) + lift*cp*mass_balance
            source_heat = source*mesh["cell_volumes"]
            defect = cell_heat-source_heat
            cf = mesh["cell_faces"]
            cell_scale = np.maximum.reduce([
                abs(source_heat), np.sum(abs(flux[cf])+abs(advective[cf]), axis=1),
                abs(anchor*cp*mass_balance)])
            cell_relative = max(_relative(abs(v), s) for v, s in zip(defect, cell_scale))
            exterior = np.flatnonzero(mesh["face_owners"][:, 1] < 0)
            boundary_heat = math.fsum(float(v) for v in flux[exterior]+lifted_advective[exterior])
            boundary_heat += math.fsum(float(v) for v in lift*cp*mass_balance)
            generated = math.fsum(float(v) for v in source_heat)
            global_scale = max(math.fsum(abs(float(v)) for v in source_heat),
                               math.fsum(abs(float(v)) for v in flux[exterior]+advective[exterior]),
                               math.fsum(abs(float(v)) for v in anchor*cp*mass_balance))
            global_relative = _relative(abs(boundary_heat-generated), global_scale)
            if (not all(math.isfinite(v) for v in (cell_relative, global_relative))
                    or max(cell_relative, global_relative) > 1e-9):
                raise ValueError("Cell or global energy balance exceeds 1e-9")
            fields = {"temperature_k": temperature.tolist(), "temperature_rise_k": rise.tolist(),
                      "face_conductive_heat_flow_w": flux.tolist(),
                      "face_advective_heat_flow_relative_w": advective.tolist(),
                      "face_advective_heat_flow_w": (lifted_advective+transport*lift).tolist(),
                      "cell_heat_balance_defect_w": defect.tolist()}
            field_bytes = len(json.dumps(fields, allow_nan=False, separators=(",", ":")).encode())
            if field_bytes > MAX_FIELD_BYTES:
                raise ValueError("Tetra energy fields exceed 4 MiB budget")
            if cancel_check and cancel_check():
                raise InterruptedError()
            result.update(status="completed", fields=fields, diagnostics={
                "mixed_relative_residual": relative, "cell_energy_relative_defect": cell_relative,
                "global_energy_relative_defect": global_relative, "mass_relative_defect": rel_mass,
                "generated_heat_w": generated, "outward_boundary_heat_w": boundary_heat,
                "scaled_condition_estimate": condition, "field_payload_bytes": field_bytes,
                "factor_nonzeros": factor_nonzeros, "elapsed_seconds": time.monotonic()-started,
                "fluid_cells": int(np.count_nonzero(fluid)), "solid_cells": int(np.count_nonzero(~fluid)),
                "flux_orientation": "outward_from_first_face_owner", "reference_temperature_k": anchor,
                "internal_temperature_lift_k": lift,
                "global_intersections_checked": False})
    except InterruptedError:
        result.update(status="cancelled", issues=[{"code": "CANCELLED", "message": "Tetra energy cancelled"}])
    except (ValueError, TypeError, ArithmeticError, RuntimeError, KeyError, np.linalg.LinAlgError) as exc:
        result.update(status="blocked", issues=[{"code": "TETRA_ENERGY_REJECTED", "message": str(exc)}])
    return result
