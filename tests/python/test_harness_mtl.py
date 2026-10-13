# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Yawar B and SPIKE contributors.
"""Independent scalar, modal and resistor-network oracles, not round trips."""
import copy
import math
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.harness_mtl import run_harness_mtl


def fixture(count=1, frequencies=None):
    frequencies = frequencies or [0, 1e6, 10e6]
    identities = np.eye(count)
    wires = [f"wire-{i}" for i in range(count)]
    model = {"wire_ids": wires, "frequency_hz": frequencies,
             "r_ohm_per_m": [np.zeros((count, count)).tolist()]*len(frequencies),
             "g_s_per_m": [np.zeros((count, count)).tolist()]*len(frequencies),
             "l_h_per_m": [(identities*250e-9).tolist()]*len(frequencies),
             "c_f_per_m": [(identities*100e-12).tolist()]*len(frequencies),
             "provenance": {"source": "original matched analytical line"}}
    return {"contract": "spike/harness-mtl-request/v1", "reference_node": "gnd",
            "frequency_hz": frequencies, "nodes": [{"id": f"{end}{i}", "occurrence_id": f"board-{end}", "wire_id": wires[i]} for end in ("a", "b") for i in range(count)],
            "segments": [{"id": "line", "wire_ids": wires, "from_nodes": [f"a{i}" for i in range(count)],
                          "to_nodes": [f"b{i}" for i in range(count)], "length_m": 1, "model": model}],
            "contacts": [], "terminations": [], "ports": [{"id": f"{end}{i}", "positive_node": f"{end}{i}",
              "negative_node": "gnd", "reference_impedance_ohm": 50, "occurrence_id": f"board-{end}", "wire_id": wires[i]}
             for end in ("a", "b") for i in range(count)], "provenance": {"source": "independent synthetic harness"}}


def complex_s(result):
    return np.array(result["s_real"])+1j*np.array(result["s_imag"])


class HarnessMtlTests(unittest.TestCase):
    def test_matched_line_dc_phase_identity_and_terminal_kcl(self):
        raw = fixture()
        before = copy.deepcopy(raw)
        out = run_harness_mtl(raw)
        s = complex_s(out)
        phase = np.exp(-2j*math.pi*np.array(raw["frequency_hz"])*5e-9)
        np.testing.assert_allclose(s[:, 0, 1], phase, atol=1e-12)
        np.testing.assert_allclose(s[:, 1, 0], phase, atol=1e-12)
        np.testing.assert_allclose(s[:, [0, 1], [0, 1]], 0, atol=1e-12)
        self.assertEqual(raw, before)
        self.assertEqual(out["nodes"], raw["nodes"])
        branch = out["segments"][0]
        i_from = np.array(branch["from_current_a"]["real"])+1j*np.array(branch["from_current_a"]["imag"])
        np.testing.assert_allclose(i_from[:, 0, 0], 1/math.sqrt(50), atol=1e-12)
        self.assertFalse(out["field_coupling_executed"])

    def test_coupled_matrices_against_modal_oracle(self):
        raw = fixture(2)
        # Same orthogonal eigenvectors for exact uncoupled modal oracle.
        q = np.array([[1, 1], [1, -1]])/math.sqrt(2)
        model = raw["segments"][0]["model"]
        model["l_h_per_m"] = [(q @ np.diag([300e-9, 200e-9]) @ q.T).tolist()]*3
        model["c_f_per_m"] = [(q @ np.diag([120e-12, 80e-12]) @ q.T).tolist()]*3
        out = run_harness_mtl(raw)
        s = complex_s(out)
        for k, f in enumerate(raw["frequency_hz"]):
            expected = q @ np.diag(np.exp(-2j*math.pi*f*np.array([6e-9, 4e-9]))) @ q.T
            np.testing.assert_allclose(s[k, 2:, :2], expected, atol=2e-12)
        self.assertGreater(abs(s[-1, 3, 0]), .01)  # physical interconductor transfer
        raw["mixed_mode_pairs"] = [["a0", "a1"], ["b0", "b1"]]
        mixed = run_harness_mtl(raw)["mixed_mode"]
        sm = np.array(mixed["s_real"])+1j*np.array(mixed["s_imag"])
        np.testing.assert_allclose(sm[:, :2, 2:], 0, atol=2e-12)
        self.assertEqual(mixed["reference_impedance_ohm"], [100, 100, 25, 25])

    def test_noncommuting_matrices_against_refining_ladder(self):
        from scipy.sparse import lil_matrix
        from scipy.sparse.linalg import spsolve
        raw = fixture(2, [30e6])
        l = np.array([[300, 70], [70, 200]])*1e-9
        c = np.array([[120, -20], [-20, 80]])*1e-12
        self.assertGreater(np.linalg.norm(l @ c-c @ l), 1e-18)
        model = raw["segments"][0]["model"]
        model["l_h_per_m"], model["c_f_per_m"] = [l.tolist()], [c.tolist()]
        model["r_ohm_per_m"] = [(np.eye(2)*5).tolist()]
        model["g_s_per_m"] = [(np.eye(2)*1e-4).tolist()]
        exact = complex_s(run_harness_mtl(raw))[0]
        omega = 2*math.pi*30e6
        errors = []
        for subdivisions in (32, 64, 128):
            # Independent reciprocal lumped pi ladder, no transfer/expm use.
            dimension = 2*(subdivisions+1)
            y = lil_matrix((dimension, dimension), dtype=complex)
            series = np.linalg.inv((np.eye(2)*5+1j*omega*l)/subdivisions)
            shunt = (np.eye(2)*1e-4+1j*omega*c)/subdivisions
            for section in range(subdivisions):
                a, b = slice(2*section, 2*section+2), slice(2*section+2, 2*section+4)
                y[a, a] += series+shunt/2
                y[b, b] += series+shunt/2
                y[a, b] -= series
                y[b, a] -= series
            ports = [0, 1, dimension-2, dimension-1]
            rhs = np.zeros((dimension, 4), complex)
            for i, p in enumerate(ports):
                y[p, p] += .02
                rhs[p, i] = 2/math.sqrt(50)
            v = spsolve(y.tocsc(), rhs)
            s = v[ports]/math.sqrt(50)-np.eye(4)
            errors.append(float(np.linalg.norm(s-exact)))
        self.assertLess(errors[-1], 2e-5)
        self.assertGreater(errors[0]/errors[1], 3.9)
        self.assertGreater(errors[1]/errors[2], 3.9)

    def test_branched_three_port_star_against_kcl(self):
        raw = fixture()
        raw["segments"] = []
        raw["nodes"] = [{"id": x} for x in ("a0", "b0", "c0", "star")]
        raw["ports"].append(dict(raw["ports"][0], id="c0", positive_node="c0"))
        raw["contacts"] = [{"id": f"contact-{x}", "positive_node": x, "negative_node": "star",
                            "resistance_ohm": 0, "inductance_h": 0, "provenance": {"source": "ideal junction"}}
                           for x in ("a0", "b0", "c0")]
        expected = 2/3*np.ones((3, 3))-np.eye(3)
        np.testing.assert_allclose(complex_s(run_harness_mtl(raw)), np.broadcast_to(expected, (3, 3, 3)), atol=1e-12)

    def test_parallel_contacts_and_explicit_termination(self):
        raw = fixture(frequencies=[0])
        raw["segments"] = []
        raw["contacts"] = [{"id": str(i), "positive_node": "a0", "negative_node": "b0",
                            "resistance_ohm": 100, "inductance_h": 0, "provenance": {"source": "original R"}}
                           for i in (1, 2)]
        np.testing.assert_allclose(complex_s(run_harness_mtl(raw))[0], [[1/3, 2/3], [2/3, 1/3]], atol=1e-12)
        raw["terminations"] = [{"id": "load", "positive_node": "b0", "negative_node": "gnd",
                                 "conductance_s": .02, "capacitance_f": 0, "provenance": {"source": "50 ohm"}}]
        np.testing.assert_allclose(complex_s(run_harness_mtl(raw))[0], [[.2, .4], [.4, -.2]], atol=1e-12)

    def test_rejects_negative_energy_unknown_fields_and_stale_order(self):
        for defect, code in (("energy", "ENERGY"), ("boolean", "MODEL"), ("unknown", "CONTRACT"), ("order", "MODEL"), ("frequency", "FREQUENCY")):
            raw = fixture()
            if defect == "energy": raw["segments"][0]["model"]["r_ohm_per_m"][0][0][0] = -1
            if defect == "boolean": raw["segments"][0]["model"]["l_h_per_m"][0][0][0] = True
            if defect == "unknown": raw["assume_shield"] = True
            if defect == "order": raw["segments"][0]["model"]["wire_ids"] = ["other"]
            if defect == "frequency": raw["frequency_hz"] = [1, 0]
            with self.subTest(defect=defect), self.assertRaisesRegex(ValueError, code): run_harness_mtl(raw)

    def test_cancel_singular_floating_and_resource_bounds(self):
        with self.assertRaisesRegex(ValueError, "CANCELLED"): run_harness_mtl(fixture(), cancel_check=lambda: True)
        raw = fixture()
        raw["nodes"].append({"id": "floating"})
        with self.assertRaisesRegex(ValueError, "CONDITION"): run_harness_mtl(raw)
        raw = fixture()
        raw["segments"][0]["length_m"] = 1e10
        with self.assertRaisesRegex(ValueError, "CONDITION"): run_harness_mtl(raw)
        raw = fixture(16, list(range(257)))
        with self.assertRaisesRegex(ValueError, "RESOURCE"): run_harness_mtl(raw)

    def test_schema_and_mixed_mode_reference_rejection(self):
        import json
        from pathlib import Path
        from jsonschema import Draft202012Validator
        path = Path(__file__).resolve().parents[2]/"schemas/harness-mtl-request-v1.schema.json"
        validator = Draft202012Validator(json.loads(path.read_text()))
        validator.validate(fixture(2))
        bad = fixture()
        bad["segments"][0]["model"]["l_h_per_m"][0][0][0] = True
        self.assertTrue(list(validator.iter_errors(bad)))
        raw = fixture(2)
        raw["mixed_mode_pairs"] = [["a0", "a1"], ["b0", "b1"]]
        raw["ports"][0]["reference_impedance_ohm"] = 75
        with self.assertRaisesRegex(ValueError, "MODES"): run_harness_mtl(raw)

    def test_late_cancellation_and_boolean_model_sweep(self):
        raw = fixture(frequencies=[0])
        cancelled = False
        solve = np.linalg.solve
        def late_cancel(*args, **kwargs):
            nonlocal cancelled
            result = solve(*args, **kwargs)
            cancelled = True
            return result
        with patch("python.spike_core.harness_mtl.np.linalg.solve", side_effect=late_cancel):
            with self.assertRaisesRegex(ValueError, "CANCELLED"):
                run_harness_mtl(raw, cancel_check=lambda: cancelled)
        raw["segments"][0]["model"]["frequency_hz"] = [False]
        with self.assertRaisesRegex(ValueError, "NUMBER"): run_harness_mtl(raw)

    def test_unequal_port_power_normalization_and_reactive_lumped_phase(self):
        raw = fixture(frequencies=[0, 1e6])
        raw["segments"] = []
        raw["ports"][1]["reference_impedance_ohm"] = 75
        raw["contacts"] = [{"id": "contact", "positive_node": "a0", "negative_node": "b0",
                            "resistance_ohm": 0, "inductance_h": 0, "provenance": {"source": "ideal through"}}]
        expected = np.array([[.2, 2*math.sqrt(50*75)/125], [2*math.sqrt(50*75)/125, -.2]])
        np.testing.assert_allclose(complex_s(run_harness_mtl(raw)), np.broadcast_to(expected, (2, 2, 2)), atol=1e-12)
        raw["ports"][1]["reference_impedance_ohm"] = 50
        raw["contacts"][0]["inductance_h"] = 1e-6
        raw["terminations"] = [{"id": "load", "positive_node": "b0", "negative_node": "gnd",
                                 "conductance_s": 0, "capacitance_f": 1e-9, "provenance": {"source": "original reactive load"}}]
        s = complex_s(run_harness_mtl(raw))[1]
        # Independent series-Z then shunt-Y ABCD scalar algebra.
        z, y = 2j*math.pi*1e6*1e-6, 2j*math.pi*1e6*1e-9
        a, b, c, d = 1+z*y, z, y, 1
        denominator = a+b/50+c*50+d
        expected = np.array([[(a+b/50-c*50-d)/denominator, 2/denominator],
                             [2/denominator, (-a+b/50-c*50+d)/denominator]])
        np.testing.assert_allclose(s, expected, atol=1e-12)

    def test_unrepresentable_inputs_are_coded(self):
        raw = fixture()
        raw["ports"][0]["reference_impedance_ohm"] = 10**400
        with self.assertRaisesRegex(ValueError, "NUMBER"): run_harness_mtl(raw)
        raw = fixture()
        raw["segments"][0]["model"]["r_ohm_per_m"][0][0][0] = 10**400
        with self.assertRaisesRegex(ValueError, "MODEL"): run_harness_mtl(raw)
        raw = fixture(frequencies=[1e308])
        raw["segments"] = []
        raw["contacts"] = [{"id": "contact", "positive_node": "a0", "negative_node": "b0",
                            "resistance_ohm": 100, "inductance_h": 0, "provenance": {"source": "R"}}]
        with self.assertRaisesRegex(ValueError, "CONDITION"): run_harness_mtl(raw)

    def test_finite_return_conductor_with_one_grounded_endpoint(self):
        raw = fixture(2, [0])
        raw["nodes"] = [{"id": x} for x in ("a0", "b0", "b1")]
        segment = raw["segments"][0]
        segment["from_nodes"] = ["a0", "gnd"]
        segment["model"]["r_ohm_per_m"] = [[[2., 0.], [0., 3.]]]
        raw["ports"] = [raw["ports"][0], dict(raw["ports"][2], negative_node="b1")]
        out = run_harness_mtl(raw)
        # The physical return's 3 ohms is not dropped into an ideal return.
        np.testing.assert_allclose(complex_s(out)[0], [[1/21, 20/21], [20/21, 1/21]], atol=1e-12)
        currents = np.array(out["segments"][0]["from_current_a"]["real"])[0]
        np.testing.assert_allclose(currents[0], -currents[1], atol=1e-12)


if __name__ == "__main__":
    unittest.main()
