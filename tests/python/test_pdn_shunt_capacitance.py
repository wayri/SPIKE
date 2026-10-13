# SPDX-License-Identifier: Apache-2.0
"""Independent lumped energy and ideal-plate oracles; no board accuracy claim."""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
import unittest

import numpy as np

from python.spike_core.contracts import AnalysisSpec, SpiDeR
from python.spike_core.hybrid_mesh import MeshBranch
from python.spike_core.pdn_shunt_capacitance import (
    estimate_geometry_shunts, normalize_shunt_capacitance, pdn_capacitor_elements,
)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()).hexdigest()


def supplied():
    return {"kind": "supplied_lumped", "model": "synthetic circuit fixture",
            "model_status": "supplied", "provenance": {"source": "independent test circuit"},
            "context_digest": "a" * 64,
            "return_boundary": {"mode": "explicit", "node": "return-42", "net": "AGND"},
            "elements": [{"id": "c", "node_a": "rail", "node_b": "return-42", "capacitance_f": 2e-9}]}


class PdnShuntCapacitanceTests(unittest.TestCase):
    def test_lumped_roundtrip_and_context_binding(self):
        request = supplied()
        result = normalize_shunt_capacitance(request, expected_context_digest="a" * 64)
        self.assertEqual(result["elements"], request["elements"])
        self.assertEqual(result["model_status"], "supplied")
        self.assertEqual(result["source_digest"], digest(request))
        with self.assertRaisesRegex(ValueError, "context"):
            normalize_shunt_capacitance(request, expected_context_digest="b" * 64)

    def test_missing_return_and_malformed_data_fail(self):
        mutations = [lambda r: r.pop("return_boundary"),
                     lambda r: r.update(model_status="unsupported"),
                     lambda r: r.update(provenance={}),
                     lambda r: r.update(provenance={"source": True}),
                     lambda r: r.update(provenance={"unknown": "pretend extractor"}),
                     lambda r: r.update(mesh={"status": "accepted", "defects": ["inverted cell"]}),
                     lambda r: r["elements"][0].update(capacitance_f=True),
                     lambda r: r["elements"][0].update(capacitance_f=float("nan")),
                     lambda r: r["elements"][0].update(capacitance_f=-1e-12),
                     lambda r: r["elements"][0].update(node_b="GND")]
        for mutate in mutations:
            request = supplied()
            mutate(request)
            with self.subTest(request=request), self.assertRaises(ValueError):
                normalize_shunt_capacitance(request)

    def test_backend_adapter_preserves_two_terminal_mutual_edges(self):
        from python.spike_core.pdn_network import evaluate_pdn_network
        request = supplied()
        request.update(kind="supplied_maxwell_matrix", nodes=["rail", "other"],
                       matrix_f=[[5e-9, -3e-9], [-3e-9, 7e-9]])
        request.pop("elements")
        elements = pdn_capacitor_elements(request, expected_context_digest="a" * 64)
        self.assertEqual(len(elements), 3)
        self.assertTrue(all(edge["provenance"]["kind"] == "supplied" for edge in elements))
        result = evaluate_pdn_network({"contract": "spike/pdn-network-request/v1",
            "reference": "return-42", "nodes": ["rail", "other"], "elements": elements,
            "ports": [{"id": "p", "mode": "single", "positive": "rail", "negative": "return-42"}],
            "frequencies_hz": [1e6], "load_transient": None})
        # Floating other conductor: Schur-complement C = 5 - 9/7 nF, not 5 nF.
        expected = -1 / (2 * np.pi * 1e6 * (5 - 9 / 7) * 1e-9)
        self.assertAlmostEqual(result["ac"][0]["impedance_ohm"][0][0]["imag"] / expected, 1.0, places=12)

    def test_maxwell_preserves_mutual_energy_not_diagonal_shunts(self):
        request = supplied()
        request.update(kind="supplied_maxwell_matrix", nodes=["rail", "other"],
                       matrix_f=[[5e-9, -3e-9], [-3e-9, 7e-9]])
        request.pop("elements")
        result = normalize_shunt_capacitance(request)
        shunts = [v for v in result["elements"] if v["node_b"] == "return-42"]
        np.testing.assert_allclose([v["capacitance_f"] for v in shunts], [2e-9, 4e-9], rtol=1e-14)
        voltage = {"rail": 2.0, "other": -3.0, "return-42": 0.0}
        graph_energy = sum(0.5 * edge["capacitance_f"] *
                           (voltage[edge["node_a"]] - voltage[edge["node_b"]]) ** 2
                           for edge in result["elements"])
        self.assertAlmostEqual(graph_energy / 1e-9, 59.5, places=12)
        self.assertAlmostEqual(graph_energy, np.array([2., -3.]) @
                               np.array(request["matrix_f"]) @ np.array([2., -3.]) / 2, places=20)

    def test_matrix_rejects_negative_energy_nonreciprocity_or_bad_ground(self):
        for matrix in ([[1., -2.], [-2., 1.]], [[2., -1.], [0., 2.]],
                       [[1., 0.5], [0.5, 1.]], [[1., -1.], [-1., 1.]],
                       [[1., -2.], [-2., 5.]]):
            request = supplied()
            request.update(kind="supplied_maxwell_matrix", nodes=["a", "b"], matrix_f=matrix)
            request.pop("elements")
            with self.subTest(matrix=matrix), self.assertRaises(ValueError):
                normalize_shunt_capacitance(request)

    def test_unknown_fields_and_control_labels_rejected(self):
        mutations = [lambda r: r.update(ignored_geometry=True),
                     lambda r: r.update(matrix_f=[[1.0]]),
                     lambda r: r["return_boundary"].update(implicit_ground=True),
                     lambda r: r["elements"][0].update(ignored_loss_tangent=0.01),
                     lambda r: r["elements"][0].update(node_a="rail\ncontrol"),
                     lambda r: r["elements"][0].update(id="x" * 81),
                     lambda r: r.update(mesh={"status": "not_applicable", "unrecognized": False}),
                     lambda r: r.update(mesh={"status": "accepted", "digest": "a" * 64, "negative_energy": 0})]
        for mutate in mutations:
            request = supplied()
            mutate(request)
            with self.subTest(request=request), self.assertRaises(ValueError):
                normalize_shunt_capacitance(request)

    def test_json_resource_limit_and_attachment_context_required(self):
        request = supplied()
        request["mesh"] = {"status": "accepted", "digest": "a" * 64,
                           "defects": ["x" * (8 * 1024 * 1024)]}
        with self.assertRaisesRegex(ValueError, "8 MiB"):
            normalize_shunt_capacitance(request)
        with self.assertRaises(ValueError):
            pdn_capacitor_elements(supplied(), expected_context_digest=None)

    def test_normalization_snapshots_do_not_alias_input_metadata(self):
        request = supplied()
        result = normalize_shunt_capacitance(request)
        request["return_boundary"]["node"] = "different"
        request["provenance"]["source"] = "changed"
        self.assertEqual(result["return_boundary"]["node"], "return-42")
        self.assertEqual(result["provenance"]["source"], "independent test circuit")

    def plate(self):
        design = SpiDeR(zones=[
            {"id": "signal", "layer": "F.Cu", "net_name": "VCC",
             "points": [(0, 0), (2, 0), (2, 2), (0, 2)], "filled_copper_state": "source_filled"},
            {"id": "return", "layer": "B.Cu", "net_name": "GND",
             "points": [(-1, -1), (3, -1), (3, 3), (-1, 3)], "filled_copper_state": "source_filled"}],
            stackup=[{"name": "F.Cu", "thickness": 0.035},
                     {"name": "core", "thickness": 0.2, "epsilon_r": 4.0, "loss_tangent": 0.0},
                     {"name": "B.Cu", "thickness": 0.035}])
        spec = AnalysisSpec(mode="ac", net_names=["VCC", "GND"],
                            return_path={"mode": "explicit", "net": "GND"})
        branch = MeshBranch("signal-link", "zone", 0, 1, (0.5, 1, 0), (1.5, 1, 0),
                            0.5, 0.035, 5.8e7, "F.Cu", "VCC", "signal")
        return design, spec, [branch]

    def extract(self, design, spec, branches):
        return estimate_geometry_shunts(design, spec, branches, {"VCC": "load-node"},
                                        "return-node", "a" * 64,
                                        {"status": "accepted", "digest": digest([asdict(v) for v in branches])})

    def test_plate_si_oracle_and_approximate_status(self):
        result = self.extract(*self.plate())
        # 2 mm square, 0.2 mm dielectric, epsilon_r=4. Independent ideal plate.
        expected = 8.8541878128e-12 * 4 * 4e-6 / 0.2e-3
        self.assertAlmostEqual(result["elements"][0]["capacitance_f"] / expected, 1.0, places=12)
        self.assertEqual(result["model_status"], "approximate")
        self.assertEqual(result["elements"][0]["node_b"], "return-node")

    def test_geometry_missing_return_holes_duplicates_and_stale_mesh_rejected(self):
        for defect in ("missing", "hole", "duplicate", "implicit", "stale"):
            design, spec, branches = self.plate()
            if defect == "missing":
                design.zones.pop()
            elif defect == "hole":
                design.zones[0]["holes"] = [[(0.1, 0.1), (0.2, 0.1), (0.1, 0.2)]]
            elif defect == "duplicate":
                design.zones.append(deepcopy(design.zones[0]))
            elif defect == "implicit":
                spec.return_path = {"mode": "implicit"}
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                if defect == "stale":
                    estimate_geometry_shunts(design, spec, branches, {"VCC": "x"}, "y", "a" * 64,
                                             {"status": "accepted", "digest": "b" * 64})
                else:
                    self.extract(design, spec, branches)


if __name__ == "__main__":
    unittest.main()
