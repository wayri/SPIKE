# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SPIKE contributors
"""Independent analytical/continuum oracles; no solver helpers or imported data."""
import copy
import itertools
import math
import unittest

import numpy as np

from python.spike_core.solvers.power_integrity.dc.dc_tetra_rt0 import DCTetraRT0Error, solve_tetra_dc
from python.spike_core.solvers.power_integrity.dc.dc_tetra_rt0_evidence import validate_tetra_dc


def slab(n=1, size=(1., 1., 1.), origin=(0., 0., 0.), owner="body"):
    """Original Cartesian subdivision; each ordered axis walk defines a simplex."""
    points = [(np.array(origin) + np.array(size) * np.array(p) / n).tolist()
              for p in itertools.product(range(n + 1), repeat=3)]
    lookup = {p: i for i, p in enumerate(itertools.product(range(n + 1), repeat=3))}
    cells = []
    for lower in itertools.product(range(n), repeat=3):
        for axes in itertools.permutations(range(3)):
            p = list(lower)
            ids = [lookup[tuple(p)]]
            for axis in axes:
                p[axis] += 1
                ids.append(lookup[tuple(p)])
            xyz = np.array([points[i] for i in ids])
            if np.linalg.det(xyz[1:] - xyz[0]) < 0:
                ids[1], ids[2] = ids[2], ids[1]
            cells.append({"id": f"{owner}-{len(cells)}", "kind": "tetrahedron",
                          "vertices": ids, "material_id": "metal", "source_object_ids": [owner]})
    return {"contract": "spike/solver-mesh/v1", "units": "m",
            "coordinate_system": "right_handed_xyz", "vertices": points, "cells": cells,
            "counts": {"vertices": len(points), "cells": len(cells)},
            "object_map": {owner: {"kind": "solid"}}}


def exterior(mesh):
    occurrences = {}
    for cell in mesh["cells"]:
        for nodes in itertools.combinations(cell["vertices"], 3):
            key = tuple(sorted(nodes))
            occurrences.setdefault(key, []).append(cell["vertices"])
    return [(list(face), owners[0]) for face, owners in occurrences.items() if len(owners) == 1]


def faces_at(mesh, axis, coordinate):
    return [f for f, _ in exterior(mesh)
            if all(mesh["vertices"][i][axis] == coordinate for i in f)]


def face_geometry(mesh, face, cell):
    xyz = np.array([mesh["vertices"][i] for i in face])
    centroid = xyz.mean(axis=0)
    area_vector = np.cross(xyz[1] - xyz[0], xyz[2] - xyz[0]) / 2
    opposite = next(i for i in cell if i not in face)
    if np.dot(area_vector, np.array(mesh["vertices"][opposite]) - centroid) > 0:
        area_vector = -area_vector
    return centroid, area_vector


def request(mesh=None, sigma=2., current=3.):
    mesh = mesh or slab()
    xx = [p[0] for p in mesh["vertices"]]
    return {"contract": "spike/tetra-dc-rt0-request/v1", "mesh": mesh,
            "conductivity_s_m": {c["id"]: sigma for c in mesh["cells"]},
            "contacts": [{"id": "source", "faces": faces_at(mesh, 0, min(xx)), "current_a": current},
                         {"id": "sink", "faces": faces_at(mesh, 0, max(xx)), "current_a": -current}]}


def merge_meshes(first, second):
    mesh = copy.deepcopy(first)
    offset = len(first["vertices"])
    mesh["vertices"] += second["vertices"]
    mesh["cells"] += [{**c, "vertices": [v + offset for v in c["vertices"]]} for c in second["cells"]]
    mesh["object_map"].update(second["object_map"])
    mesh["counts"] = {"vertices": len(mesh["vertices"]), "cells": len(mesh["cells"])}
    return mesh


def quadrature():
    # Equal weights: enforce E[lambda_i]=1/4, E[lambda_i^2]=1/10,
    # E[lambda_i lambda_j]=1/20. These moments determine a,b independently.
    a, b = (5 + 3 * math.sqrt(5)) / 20, (5 - math.sqrt(5)) / 20
    return np.array([[a if i == j else b for i in range(4)] for j in range(4)])


def continuum_request(n):
    raw = request(slab(n), sigma=1.)
    raw["contacts"] = []
    for face, cell in exterior(raw["mesh"]):
        p, area_vector = face_geometry(raw["mesh"], face, cell)
        # phi=x*y => J=(-y,-x,0), exactly linear on each triangle.
        current = -float(np.dot([-p[1], -p[0], 0.], area_vector))
        if current:
            raw["contacts"].append({"id": f"f{len(raw['contacts'])}", "faces": [face],
                                    "current_a": current})
    return raw


def radial_cube_quantile(probability):
    # Volume fraction is the area of a first-quadrant disk within the unit
    # square, since the field magnitude sqrt(x*x+y*y) is independent of z.
    def fraction(radius):
        if radius <= 1:
            return math.pi * radius * radius / 4
        return math.sqrt(radius * radius - 1) + radius * radius * (math.asin(1 / radius) - math.pi / 4)
    low, high = 0., math.sqrt(2)
    for _ in range(60):
        mid = (low + high) / 2
        if fraction(mid) < probability:
            low = mid
        else:
            high = mid
    return (low + high) / 2


class DCTetraRT0Tests(unittest.TestCase):
    def assert_physical_ledgers(self, raw, out):
        barycentric = quadrature()
        points = np.array(raw["mesh"]["vertices"])
        scale = 1e-3 if raw["mesh"]["units"] == "mm" else 1.
        points *= scale
        incidence, power = {}, 0.
        for cell in out["cells"]:
            xyz = points[cell["vertices"]]
            volume = abs(np.linalg.det(xyz[1:] - xyz[0])) / 6
            self.assertAlmostEqual(cell["volume_m3"], volume, delta=volume * 1e-10)
            values = np.array(cell["vertex_density_a_m2"])
            samples = barycentric @ values
            integrated = volume * np.mean(np.sum(samples * samples, axis=1)) / raw["conductivity_s_m"][cell["id"]]
            self.assertAlmostEqual(cell["joule_heat_w"], integrated, delta=max(1e-13, integrated * 1e-9))
            power += integrated
            self.assertAlmostEqual(sum(cell["outward_face_current_a"]), 0., delta=1e-9)
            for i, flux in enumerate(cell["outward_face_current_a"]):
                face = [v for j, v in enumerate(cell["vertices"]) if j != i]
                _, area_vector = face_geometry(raw["mesh"], face, cell["vertices"])
                area_vector *= scale ** 2
                recovered = float(np.dot(np.delete(values, i, axis=0).mean(axis=0), area_vector))
                self.assertAlmostEqual(flux, recovered, delta=1e-9)
                incidence.setdefault(tuple(sorted(face)), []).append(flux)
        for face, fluxes in incidence.items():
            if len(fluxes) == 2:
                self.assertAlmostEqual(sum(fluxes), 0., delta=1e-9)
        self.assertAlmostEqual(out["joule_heat_w"], power, delta=max(1e-11, power * 1e-9))
        work = sum(c["mean_potential_v"] * c["current_a"]
                   for c in ({**source, **result} for source, result in zip(raw["contacts"], out["contacts"])))
        self.assertAlmostEqual(work, power, delta=max(1e-10, power * 1e-8))
        self.assertAlmostEqual(out["signed_terminal_work_w"], power, delta=max(1e-10, power * 1e-8))
        for source, contact in zip(raw["contacts"], out["contacts"]):
            recovered = -sum(sum(incidence[tuple(sorted(face))]) for face in source["faces"])
            self.assertAlmostEqual(recovered, source["current_a"], delta=1e-9)
            self.assertAlmostEqual(contact["recovered_inward_current_a"], recovered, delta=1e-9)

    def test_uniform_slab_field_voltage_energy_and_si_units(self):
        raw = request(slab(2, size=(2., 3., 4.)), sigma=5., current=6.)
        original = copy.deepcopy(raw)
        out = solve_tetra_dc(raw)
        self.assertEqual(raw, original)
        self.assertEqual(out["source_request"], raw)
        self.assertFalse(out["production_qualified"])
        self.assert_physical_ledgers(raw, out)
        for c in out["cells"]:
            np.testing.assert_allclose(c["vertex_density_a_m2"], np.tile([.5, 0., 0.], (4, 1)), atol=1e-9)
        self.assertAlmostEqual(out["contacts"][0]["mean_potential_v"] - out["contacts"][1]["mean_potential_v"], .2, places=9)
        self.assertAlmostEqual(out["joule_heat_w"], 1.2, places=9)
        raw["mesh"]["units"] = "mm"
        raw["mesh"]["vertices"] = (np.array(raw["mesh"]["vertices"]) * 1000).tolist()
        converted = solve_tetra_dc(raw)
        self.assert_physical_ledgers(raw, converted)
        self.assertAlmostEqual(converted["joule_heat_w"], 1.2, places=9)
        self.assertNotEqual(out["input_digest"], converted["input_digest"])

    def test_rotated_translated_slab(self):
        raw = request(slab(2))
        axis = np.array([1., 2., 3.]) / math.sqrt(14)
        x, y, z = axis
        cross = np.array([[0., -z, y], [z, 0., -x], [-y, x, 0.]])
        rotation = np.eye(3) + math.sin(.713) * cross + (1 - math.cos(.713)) * cross @ cross
        raw["mesh"]["vertices"] = (np.array(raw["mesh"]["vertices"]) @ rotation.T + [7., -3., 5.]).tolist()
        out = solve_tetra_dc(raw)
        self.assert_physical_ledgers(raw, out)
        for cell in out["cells"]:
            np.testing.assert_allclose(cell["vertex_density_a_m2"], np.tile(rotation @ [3., 0., 0.], (4, 1)), atol=2e-8)
        self.assertAlmostEqual(out["joule_heat_w"], 4.5, places=8)

    def test_series_conductivity_exact_interface_current(self):
        raw = request(slab(2), current=2.)
        points = np.array(raw["mesh"]["vertices"])
        raw["conductivity_s_m"] = {c["id"]: (2. if points[c["vertices"], 0].mean() < .5 else 8.)
                                   for c in raw["mesh"]["cells"]}
        out = solve_tetra_dc(raw)
        self.assert_physical_ledgers(raw, out)
        # R=(L1/sigma1+L2/sigma2)/A=5/16 ohm.
        self.assertAlmostEqual(out["joule_heat_w"], 1.25, places=9)
        self.assertAlmostEqual(out["contacts"][0]["mean_potential_v"] - out["contacts"][1]["mean_potential_v"], .625, places=9)
        for c in out["cells"]:
            np.testing.assert_allclose(c["vertex_density_a_m2"], np.tile([2., 0., 0.], (4, 1)), atol=2e-9)

    def test_six_terminal_three_dimensional_superposition(self):
        raw = request(slab(2), sigma=4.)
        raw["contacts"] = [{"id": f"{axis}-{side}", "faces": faces_at(raw["mesh"], axis, side),
                            "current_a": float((1 - 2 * side) * current)}
                           for axis, current in enumerate([2., -3., 5.]) for side in (0, 1)]
        out = solve_tetra_dc(raw)
        self.assert_physical_ledgers(raw, out)
        for c in out["cells"]:
            np.testing.assert_allclose(c["vertex_density_a_m2"], np.tile([2., -3., 5.], (4, 1)), atol=2e-9)
        self.assertAlmostEqual(out["joule_heat_w"], 9.5, places=8)

    def test_harmonic_nonuniform_field_refinement(self):
        field_errors, heat_errors = [], []
        for n in (1, 2, 4):
            raw = continuum_request(n)
            out = solve_tetra_dc(raw)
            self.assert_physical_ledgers(raw, out)
            error_squared = 0.
            for c in out["cells"]:
                xyz = np.array(raw["mesh"]["vertices"])[c["vertices"]]
                samples = quadrature() @ xyz
                exact = np.column_stack([-samples[:, 1], -samples[:, 0], np.zeros(4)])
                field = quadrature() @ np.array(c["vertex_density_a_m2"])
                error_squared += c["volume_m3"] * np.mean(np.sum((field - exact) ** 2, axis=1))
            field_errors.append(math.sqrt(error_squared))
            heat_errors.append(abs(out["joule_heat_w"] - 2 / 3))
            if n == 4:
                for name, quantile in (("p95", .95), ("p99", .99)):
                    expected = radial_cube_quantile(quantile)
                    observed = out["current_density_observable"][name]
                    self.assertLess(abs(observed["lower_a_m2"] / expected - 1), .1)
                    self.assertLess(abs(observed["upper_a_m2"] / expected - 1), .1)
        self.assertTrue(all(b < .65 * a for a, b in zip(field_errors, field_errors[1:])), field_errors)
        self.assertLess(field_errors[-1], .12, field_errors)
        self.assertTrue(all(b < .4 * a for a, b in zip(heat_errors, heat_errors[1:])), heat_errors)
        self.assertLess(heat_errors[-1], .02, heat_errors)

    def test_disconnected_undriven_volume_retained_and_local_balance(self):
        active = slab(owner="active")
        inactive = slab(size=(2., 2., 2.), origin=(3., 0., 0.), owner="inactive")
        raw = request(active)
        raw["mesh"] = merge_meshes(active, inactive)
        raw["conductivity_s_m"] = {c["id"]: 2. for c in raw["mesh"]["cells"]}
        out = solve_tetra_dc(raw)
        self.assert_physical_ledgers(raw, out)
        self.assertEqual(len(out["cells"]), 12)
        obs = out["current_density_observable"]
        self.assertAlmostEqual(obs["physical_volume_m3"], 9., places=10)
        self.assertAlmostEqual(obs["undriven_volume_m3"], 8., places=10)
        self.assertTrue(obs["complete_supplied_volume"])
        self.assertFalse(obs["complete_board_physical_volume"])
        for cell in out["cells"]:
            if cell["id"].startswith("inactive-"):
                np.testing.assert_array_equal(cell["vertex_density_a_m2"], np.zeros((4, 3)))
        # Globally balanced, individually impossible disconnected components.
        raw["contacts"][1]["faces"] = faces_at(raw["mesh"], 0, 5.)
        with self.assertRaises(DCTetraRT0Error):
            solve_tetra_dc(raw)

    def test_zero_current_complete_volume(self):
        raw = request(current=0.)
        out = solve_tetra_dc(raw)
        self.assert_physical_ledgers(raw, out)
        self.assertEqual(out["joule_heat_w"], 0.)
        for cell in out["cells"]:
            np.testing.assert_array_equal(cell["vertex_density_a_m2"], np.zeros((4, 3)))
        self.assertAlmostEqual(out["current_density_observable"]["undriven_volume_m3"], 1.)

    def test_two_balanced_components_have_independent_gauges(self):
        first, second = slab(owner="a"), slab(origin=(3., 0., 0.), owner="b")
        raw = request(merge_meshes(first, second))
        raw["contacts"] = [{"id": f"p{i}", "faces": faces_at(raw["mesh"], 0, x), "current_a": current}
                           for i, (x, current) in enumerate([(0., 2.), (1., -2.), (3., 5.), (4., -5.)])]
        out = solve_tetra_dc(raw)
        self.assert_physical_ledgers(raw, out)
        self.assertEqual(len(out["gauge_face_ids"]), 2)
        self.assertAlmostEqual(out["joule_heat_w"], 14.5, places=8)
        for c in out["cells"]:
            expected = 2. if c["id"].startswith("a-") else 5.
            np.testing.assert_allclose(c["vertex_density_a_m2"], np.tile([expected, 0., 0.], (4, 1)), atol=1e-9)

    def test_reciprocity_finite_patches_and_current_reversal(self):
        mesh = slab(2)
        faces = [faces_at(mesh, 0, 0.)[:2], faces_at(mesh, 0, 1.)[-2:],
                 faces_at(mesh, 1, 0.)[:2]]
        raw = request(mesh)
        raw["contacts"] = [{"id": f"p{i}", "faces": face, "current_a": current}
                           for i, (face, current) in enumerate(zip(faces, [1., -1., 0.]))]
        first = solve_tetra_dc(raw)
        self.assert_physical_ledgers(raw, first)
        for c, current in zip(raw["contacts"], [0., -1., 1.]):
            c["current_a"] = current
        second = solve_tetra_dc(raw)
        self.assert_physical_ledgers(raw, second)
        first_voltage = [p["mean_potential_v"] for p in first["contacts"]]
        second_voltage = [p["mean_potential_v"] for p in second["contacts"]]
        self.assertAlmostEqual(first_voltage[2] - first_voltage[1],
                               second_voltage[0] - second_voltage[1], places=10)
        for contact in raw["contacts"]:
            contact["current_a"] *= -1
        reversed_out = solve_tetra_dc(raw)
        for a, b in zip(second["cells"], reversed_out["cells"]):
            np.testing.assert_allclose(a["vertex_density_a_m2"], -np.array(b["vertex_density_a_m2"]), atol=1e-10)
        self.assertAlmostEqual(second["joule_heat_w"], reversed_out["joule_heat_w"], places=10)

    def test_overlap_internal_contact_and_resource_budgets(self):
        mesh = merge_meshes(slab(owner="a"), slab(origin=(.2, .2, .2), owner="b"))
        with self.assertRaises(DCTetraRT0Error):
            solve_tetra_dc(request(mesh))
        raw = request()
        faces = {}
        for cell in raw["mesh"]["cells"]:
            for face in itertools.combinations(cell["vertices"], 3):
                key = tuple(sorted(face))
                faces[key] = faces.get(key, 0) + 1
        raw["contacts"][0]["faces"] = [list(next(f for f, count in faces.items() if count == 2))]
        with self.assertRaises(DCTetraRT0Error):
            solve_tetra_dc(raw)
        raw = request()
        raw["mesh"]["cells"] *= 834
        with self.assertRaises(DCTetraRT0Error):
            solve_tetra_dc(raw)
        raw = request()
        raw["contacts"] *= 2049
        with self.assertRaises(DCTetraRT0Error):
            solve_tetra_dc(raw)

    def test_tiny_nonzero_current_cannot_be_silently_zeroed(self):
        for current in (1e-160, 1e-200, 5e-324):
            with self.subTest(current=current), self.assertRaises(DCTetraRT0Error):
                solve_tetra_dc(request(current=current))
        raw = request(current=1e-100)
        out = solve_tetra_dc(raw)
        self.assertGreater(out["joule_heat_w"], 0.)
        self.assertAlmostEqual(out["joule_heat_w"] / 5e-201, 1., places=8)

    def test_source_net_ownership_cannot_create_a_weld(self):
        raw = request()
        raw["mesh"]["object_map"] = {"a": {"kind": "solid", "net": "VDD"},
                                     "b": {"kind": "solid", "net": "GND"}}
        for i, cell in enumerate(raw["mesh"]["cells"]):
            cell["source_object_ids"] = ["a" if i == 0 else "b"]
        with self.assertRaises(DCTetraRT0Error):
            solve_tetra_dc(raw)
        for cell in raw["mesh"]["cells"]:
            cell["source_object_ids"] = ["a", "b"]
        with self.assertRaises(DCTetraRT0Error):
            solve_tetra_dc(raw)

    def test_retained_witness_rejects_field_heat_trace_and_scope_forgeries(self):
        raw = request(slab(2))
        result = solve_tetra_dc(raw)
        validate_tetra_dc(result)
        mutations = [lambda r: r["cells"][0]["vertex_density_a_m2"][0].__setitem__(1, 1.),
                     lambda r: r["cells"][0].__setitem__("mean_potential_v", 100.),
                     lambda r: r["cells"][0].__setitem__("joule_heat_w", 1.),
                     lambda r: r["cells"][0]["outward_face_current_a"].__setitem__(0, 100.),
                     lambda r: r["contacts"][0].__setitem__("recovered_inward_current_a", 100.),
                     lambda r: r["current_density_observable"]["p95"].__setitem__("upper_a_m2", 100.),
                     lambda r: r["current_density_observable"].__setitem__("complete_board_physical_volume", True),
                     lambda r: r.__setitem__("production_qualified", True)]
        for mutate in mutations:
            forged = copy.deepcopy(result)
            mutate(forged)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                validate_tetra_dc(forged)

    def test_invalid_material_contact_topology_and_nonfinite_fail_closed(self):
        mutations = [lambda r: r["conductivity_s_m"].pop(next(iter(r["conductivity_s_m"]))),
                     lambda r: r["conductivity_s_m"].__setitem__("unknown", 1.),
                     lambda r: r["conductivity_s_m"].__setitem__("body-0", 0.),
                     lambda r: r["conductivity_s_m"].__setitem__("body-0", True),
                     lambda r: r["contacts"][0].__setitem__("current_a", float("nan")),
                     lambda r: r["contacts"][0].__setitem__("current_a", True),
                     lambda r: r["contacts"][0].__setitem__("faces", [[0, 0, 1]]),
                     lambda r: r["contacts"][0].__setitem__("faces", [[0, 1, 999]]),
                     lambda r: r["contacts"].append(copy.deepcopy(r["contacts"][0])),
                     lambda r: r["contacts"][0]["faces"].append(r["contacts"][0]["faces"][0]),
                     lambda r: r["contacts"][0].__setitem__("current_a", 2.),
                     lambda r: r["mesh"]["vertices"][0].__setitem__(0, float("inf")),
                     lambda r: r["mesh"]["cells"][0].__setitem__("vertices", [0, 0, 1, 2])]
        for mutate in mutations:
            raw = request()
            mutate(raw)
            with self.subTest(mutation=mutate), self.assertRaises(DCTetraRT0Error):
                solve_tetra_dc(raw)


if __name__ == "__main__":
    unittest.main()
