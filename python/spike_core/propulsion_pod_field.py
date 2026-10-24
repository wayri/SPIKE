# SPDX-License-Identifier: Apache-2.0
"""Experimental reciprocal two-port planar PM reference, not a BLDC product.

Four existing P1 kernel solves span the exact admitted linear finite-element
solution. Current excitation and flux extraction share one normalized winding
basis; torque is the angle derivative of the same reduced field functional.
See docs/validation/PROPULSION_POD_FIELD_DERIVATION_20261023.md.
"""
from __future__ import annotations

import hashlib
import json
import math
from numbers import Real
import numpy as np

from .magnetic_fem import MU0, PlanarMagneticOperator, solve_magnetostatic


DEFAULT_SPEC = {
    "mesh_edge_m": .004, "outer_radius_m": .035, "rotor_radius_m": .009,
    "winding_inner_radius_m": .014, "winding_outer_radius_m": .022,
    "stack_depth_m": .02, "turns": 40, "remanence_t": .6,
    "rotor_relative_permeability": 1.05, "max_current_a": 200.,
}


def _number(value, name, low, high):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be finite in [{low}, {high}]")
    return float(value)


def _mesh_layout(spec):
    h, outer = spec["mesh_edge_m"], spec["outer_radius_m"]
    count = max(32, 16 * math.ceil(2 * math.pi * outer / (16 * h)))
    radii = []
    bounds = [0., spec["rotor_radius_m"], spec["winding_inner_radius_m"],
              spec["winding_outer_radius_m"], outer]
    for a, b in zip(bounds, bounds[1:]):
        radii.extend(np.linspace(a, b, math.ceil((b-a)/h)+1)[1:].tolist())
    if 1 + count*len(radii) > 12000:
        raise ValueError("Field reference exceeds 12000 nodes; coarsen the mesh")
    return count, radii


def validate_field_spec(spec=None):
    """Return a fresh normalized specification without meshing or solving."""
    if spec is None:
        spec = {}
    if not isinstance(spec, dict) or set(spec)-set(DEFAULT_SPEC):
        raise ValueError("Unknown field-motor specification fields")
    clean = {**DEFAULT_SPEC, **spec}
    for key in ("mesh_edge_m", "outer_radius_m", "rotor_radius_m",
                "winding_inner_radius_m", "winding_outer_radius_m", "stack_depth_m"):
        clean[key] = _number(clean[key], key, .0005, .2)
    if not (clean["rotor_radius_m"] < clean["winding_inner_radius_m"]
            < clean["winding_outer_radius_m"] < clean["outer_radius_m"]):
        raise ValueError("Need rotor < winding inner < winding outer < exterior radius")
    if type(clean["turns"]) is not int or not 1 <= clean["turns"] <= 500:
        raise ValueError("turns must be an integer in 1..500")
    clean["remanence_t"] = _number(clean["remanence_t"], "remanence_t", 0., 1.5)
    clean["rotor_relative_permeability"] = _number(clean["rotor_relative_permeability"], "rotor_relative_permeability", 1., 5.)
    clean["max_current_a"] = _number(clean["max_current_a"], "max_current_a", .001, 1000.)
    _mesh_layout(clean)
    return clean


def _mesh(spec):
    """Concentric P1 mesh; circular interfaces are inscribed polygons."""
    count, radii = _mesh_layout(spec)
    angles = np.arange(count) * (2 * math.pi / count)
    nodes = [[0., 0.]]
    nodes.extend([[r*math.cos(t), r*math.sin(t)] for r in radii for t in angles])
    triangles = [[0, 1+j, 1+(j+1) % count] for j in range(count)]
    for ring in range(1, len(radii)):
        inner, outer_start = 1+(ring-1)*count, 1+ring*count
        for j in range(count):
            nxt = (j+1) % count
            triangles.extend([[inner+j, outer_start+j, outer_start+nxt],
                              [inner+j, outer_start+nxt, inner+nxt]])
    nodes, triangles = np.asarray(nodes), np.asarray(triangles, dtype=int)
    # Radial/angular sector classification uses the known ring topology rather
    # than centroid radius, which would misclassify interface triangles.
    regions = ["rotor"]*count
    for ring in range(1, len(radii)):
        mid_r = (radii[ring-1]+radii[ring])/2
        for j in range(count):
            region = "rotor" if mid_r < spec["rotor_radius_m"] else "air"
            if spec["winding_inner_radius_m"] < mid_r < spec["winding_outer_radius_m"]:
                theta = ((j+.5)*2*math.pi/count) % (2*math.pi)
                sector = round(theta/(math.pi/2)) % 4
                offset = ((theta-sector*math.pi/2+math.pi) % (2*math.pi))-math.pi
                if abs(offset) < math.pi/8:
                    region = ("a_pos", "b_pos", "a_neg", "b_neg")[sector]
            regions.extend([region, region])
    boundary = list(range(1+(len(radii)-1)*count, 1+len(radii)*count))
    return nodes, triangles, regions, boundary


class FieldMotor:
    """Synthetic two-phase reference; winding currents [A] and rotor angle [rad].

    No winding resistance/end turns/inverter/controller/mechanics/propeller or
    loss is inferred. The caller owns v=Ri+d(lambda)/dt and shaft integration.
    """
    def __init__(self, spec=None):
        clean = validate_field_spec(spec)
        self._spec = clean
        self.spec_sha256 = hashlib.sha256(json.dumps(clean, sort_keys=True).encode()).hexdigest()
        self.nodes_m, self.triangles, self.region_ids, self.boundary = _mesh(clean)
        self.materials = {key: {"mu_r": clean["rotor_relative_permeability"] if key=="rotor" else 1.}
                          for key in set(self.region_ids)}
        self._op = PlanarMagneticOperator(self.nodes_m.tolist(), self.triangles.tolist(),
                                         self.region_ids, self.materials)
        self.winding_chi_per_m2 = np.zeros((len(self.triangles), 2))
        for phase, positive, negative in ((0, "a_pos", "a_neg"), (1, "b_pos", "b_neg")):
            for region, sign in ((positive, 1), (negative, -1)):
                mask = np.asarray(self.region_ids)==region
                area = float(self._op.areas[mask].sum())
                if area <= 0:
                    raise ValueError("Mesh lacks a winding region; refine the geometry")
                self.winding_chi_per_m2[mask, phase] = sign*clean["turns"]/area
        self._C = np.zeros((len(self.nodes_m), 2))
        for phase in range(2):
            np.add.at(self._C[:, phase], self.triangles.ravel(),
                      np.repeat(self._op.areas*self.winding_chi_per_m2[:, phase]/3, 3))
        if np.max(np.abs(self._C.sum(axis=0))) > 1e-11*clean["turns"]:
            raise ValueError("Unbalanced winding basis; linkage is not gauge invariant")
        self._F = np.zeros_like(self._C)
        basis = []
        residuals = []
        for index in range(4):
            materials = {key: dict(value) for key, value in self.materials.items()}
            j = self.winding_chi_per_m2[:, index].tolist() if index<2 else [0.]*len(self.triangles)
            if index >= 2:
                br = [0., 0.];br[index-2] = clean["remanence_t"]
                materials["rotor"]["remanence_t"] = br
                op = PlanarMagneticOperator(self.nodes_m.tolist(), self.triangles.tolist(), self.region_ids, materials)
                self._F[:, index-2] = -op.evaluate(np.zeros(len(self.nodes_m)))[0]
            result = solve_magnetostatic(nodes_m=self.nodes_m.tolist(), triangles=self.triangles.tolist(),
                region_ids=self.region_ids, materials=materials, stack_depth_m=clean["stack_depth_m"],
                dirichlet_a_wb_per_m={i: 0. for i in self.boundary}, current_density_a_per_m2=j,
                absolute_tolerance_a=1e-10, relative_tolerance=1e-10)
            basis.append(result["potential_a_wb_per_m"])
            residuals.append(result["convergence"]["residual_norm_a"])
        self._basis = np.asarray(basis).T
        depth = clean["stack_depth_m"]
        self.inductance_h = depth*self._C.T@self._basis[:, :2]
        self.pm_flux_cos_sin_wb_turn = depth*self._C.T@self._basis[:, 2:]
        self._S = depth*self._F.T@self._basis[:, 2:]
        self.pm_flux_basis_wb_turn = self.pm_flux_cos_sin_wb_turn
        self.pm_self_matrix_j = self._S
        if (np.max(np.abs(self.inductance_h-self.inductance_h.T)) > 1e-10
                or np.min(np.linalg.eigvalsh(self.inductance_h)) <= 0
                or np.max(np.abs(self._S-self._S.T)) > 1e-10):
            raise ValueError("Field basis violates reciprocal positive inductance")
        # The positive recoil reference adds |Br|^2/(2 mu) in the PM. Its
        # integral is angle-independent because this rotor is isotropic/rigid.
        rotor = np.asarray(self.region_ids)=="rotor"
        self._pm_reference_j = (depth*float(self._op.areas[rotor].sum())
                               *clean["remanence_t"]**2/(2*MU0*clean["rotor_relative_permeability"]))
        self.diagnostics = {"basis_field_solves": 4, "nodes": len(self.nodes_m),
                            "triangles": len(self.triangles), "basis_residual_norm_a": residuals,
                            "winding_signed_turn_integrals": (self._op.areas@self.winding_chi_per_m2).tolist()}
        self.region_ids = tuple(self.region_ids)
        for array in (self.nodes_m, self.triangles, self.winding_chi_per_m2,
                      self._C, self._F, self._basis, self.inductance_h,
                      self.pm_flux_cos_sin_wb_turn, self._S):
            array.setflags(write=False)

    @property
    def spec(self):
        return dict(self._spec)

    def coupling_terms(self, angle_rad):
        """Return exact harmonic coefficients for a discrete-gradient coupler.

        C below is .5*f^T*K^-1*f, without the fixed recoil-reference constant.
        That constant is separate and cancels in every time-step difference.
        """
        theta = _number(angle_rad, "angle_rad", -1e12, 1e12)
        r = np.array([math.cos(theta), math.sin(theta)])
        dr = np.array([-r[1], r[0]])
        return {"psi_wb_turn": (self.pm_flux_basis_wb_turn@r).tolist(),
                "dpsi_dangle_wb_turn_per_rad": (self.pm_flux_basis_wb_turn@dr).tolist(),
                "pm_source_potential_j": float(.5*r@self._S@r),
                "dpm_source_potential_dangle_j_per_rad": float(dr@self._S@r),
                "pm_reference_constant_j": self._pm_reference_j}

    def evaluate(self, currents, angle_rad, include_field=False):
        if not isinstance(currents, (list, tuple, np.ndarray)) or len(currents)!=2:
            raise ValueError("currents must contain exactly two phase currents in amperes")
        i = np.array([_number(v, "phase current", -self.spec["max_current_a"], self.spec["max_current_a"]) for v in currents])
        theta = _number(angle_rad, "angle_rad", -1e12, 1e12)
        if type(include_field) is not bool:
            raise ValueError("include_field must be boolean")
        r = np.array([math.cos(theta), math.sin(theta)])
        dr = np.array([-r[1], r[0]])
        L, M, S = self.inductance_h, self.pm_flux_cos_sin_wb_turn, self._S
        flux = L@i+M@r
        torque = float(i@M@dr + dr@S@r)
        coenergy = float(.5*i@L@i + i@M@r + .5*r@S@r - self._pm_reference_j)
        energy = float(i@flux-coenergy)
        derivative = M@dr
        result = {"contract": "spike/propulsion-pod-field-state/v1", "model_status": "experimental",
                  "production_qualified": False, "spec_sha256": self.spec_sha256,
                  "currents_a": i.tolist(), "angle_rad": theta,
                  "flux_linkage_wb_turn": flux.tolist(), "incremental_inductance_h": L.tolist(),
                  "torque_n_m": torque, "magnetic_energy_j": energy, "magnetic_coenergy_j": coenergy,
                  "pm_flux_linkage_wb_turn": (M@r).tolist(),
                  "pm_source_potential_j": float(.5*r@S@r),
                  "pm_reference_constant_j": self._pm_reference_j,
                  "angular_derivatives": {"dflux_dangle_wb_turn_per_rad": derivative.tolist(),
                    "dtorque_dcurrent_nm_per_a": derivative.tolist(),
                    "dtorque_dangle_nm_per_rad": float(-i@M@r-r@S@r+dr@S@dr)},
                  "energy_reference": "integral of |B-Br|^2/(2mu); rigid recoil PM reference included",
                  "solution_method": "exact linear P1 basis superposition on fixed polygonal circular geometry",
                  "scope": "synthetic two-phase planar PM reference; no actual pod identity or loss/end-turn inference"}
        if include_field:
            a = self._basis@np.r_[i, r]
            b = np.einsum("eik,ei->ek", self._op.curl, a[self.triangles])
            remanence = np.zeros_like(b)
            remanence[np.asarray(self.region_ids)=="rotor"] = self.spec["remanence_t"]*r
            mu = np.array([self._op.materials[key].mu for key in self.region_ids])
            result["field"] = {"nodes_m": self.nodes_m.tolist(), "triangles": self.triangles.tolist(),
                "region_ids": list(self.region_ids), "potential_a_wb_per_m": a.tolist(), "element_b_t": b.tolist(),
                "element_h_a_per_m": ((b-remanence)/mu[:, None]).tolist(),
                "current_density_a_per_m2": (self.winding_chi_per_m2@i).tolist(),
                "element_area_m2": self._op.areas.tolist(), "remanence_t": remanence.tolist(),
                "winding_chi_per_m2": self.winding_chi_per_m2.tolist()}
        return result


__all__ = ["DEFAULT_SPEC", "FieldMotor", "validate_field_spec"]

