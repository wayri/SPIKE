# SPDX-License-Identifier: Apache-2.0
"""Original circuit, nonreciprocal power and strict sampled-reduction oracles."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core import pdn_admittance_reduction as reduction
from python.spike_core.pdn_dielectric_ac import extract_pdn_dielectric_ac
from tests.python.test_pdn_dielectric_ac import plate


def pairs(matrix):
    return [[{"real": float(complex(value).real), "imag": float(complex(value).imag)} for value in row] for row in matrix]


def complex_matrix(matrix):
    return np.array([[complex(value["real"], value["imag"]) for value in row] for row in matrix])


def request(matrices=None, nodes=None, retained=None, eliminated=None, loads=None):
    matrices = matrices if matrices is not None else [np.array([[.75, -.5], [-.5, .625]])]
    nodes = nodes or ["P", "Q"]
    eliminated = eliminated or ["Q"]
    return {"contract": reduction.REQUEST_CONTRACT,
            "source": {"nodes": nodes, "reference_node": "GND", "frequencies_hz": [float(i + 1) for i in range(len(matrices))],
                       "admittance_s": [pairs(matrix) for matrix in matrices], "model_status": "approximate",
                       "source_id": "independent-circuit-equations", "context_digest": "a" * 64},
            "retained_nodes": retained or ["P"], "eliminated_nodes": eliminated,
            "termination_admittance_s": [pairs(matrix) for matrix in (loads if loads is not None else
                                                                      [np.zeros((len(eliminated), len(eliminated)))] * len(matrices))]}


def stamp(matrix, a, b, admittance):
    if a is not None:
        matrix[a, a] += admittance
    if b is not None:
        matrix[b, b] += admittance
    if a is not None and b is not None:
        matrix[a, b] -= admittance
        matrix[b, a] -= admittance


class PdnAdmittanceReductionTests(unittest.TestCase):
    def test_resistor_ladder_floating_and_terminated_auxiliary(self):
        # P-to-ground 4 ohm, P-Q 2 ohm, Q-ground 8 ohm.
        # Floating Q gives 1/4+1/(2+8), not the clamped-port .75 S.
        for termination in (0., .2, 10.):
            with self.subTest(termination=termination):
                req = request(loads=[[[termination]]])
                before = deepcopy(req)
                result = reduction.reduce_pdn_admittance(req)
                self.assertEqual(req, before)
                expected = .25 + 1 / (2 + 1 / (.125 + termination))
                self.assertAlmostEqual(complex_matrix(result["admittance_s"][0])[0, 0].real, expected, delta=2e-14)
                self.assertAlmostEqual(complex_matrix(result["auxiliary_voltage_basis"][0])[0, 0].real,
                                       .5 / (.625 + termination), delta=2e-14)
                np.testing.assert_allclose(complex_matrix(result["power_identity_matrix_s"][0]), [[expected]], atol=2e-14)
                self.assertEqual(result["model_status"], "approximate")
                self.assertFalse(result["production_qualified"])
                self.assertEqual(result["reference_node"], "GND")
                self.assertEqual(result["context_digest"], "a" * 64)
                self.assertEqual(result["termination_admittance_s"], req["termination_admittance_s"])
                req["termination_admittance_s"][0][0][0]["real"] += 1.
                self.assertEqual(result["termination_admittance_s"][0][0][0]["real"], termination)

    def test_complete_circuit_reference_with_crosscoupled_complex_termination(self):
        source_matrices, terminations, complete = [], [], []
        for omega in (1., 2., 3.):
            source = np.zeros((4, 4), dtype=complex)
            for a, b, conductance, capacitance in ((0, None, .5, .1), (1, None, .2, .02),
                    (2, None, .3, .04), (3, None, .1, .07), (0, 1, .4, .03),
                    (1, 2, .8, .02), (2, 3, .7, .01), (0, 3, .2, .08)):
                stamp(source, a, b, conductance + 1j * omega * capacitance)
            # Elimination order is C,B. Termination adds a bridge plus two
            # ground shunts; reconstruct the complete circuit independently.
            load = np.zeros((2, 2), dtype=complex)
            stamp(load, 0, None, .4 + .02j * omega)
            stamp(load, 1, None, .6 + .05j * omega)
            stamp(load, 0, 1, .9 + .03j * omega)
            full = source.copy()
            stamp(full, 2, None, .4 + .02j * omega)
            stamp(full, 1, None, .6 + .05j * omega)
            stamp(full, 2, 1, .9 + .03j * omega)
            source_matrices.append(source); terminations.append(load); complete.append(full)
        req = request(source_matrices, ["A", "B", "C", "D"], ["D", "A"], ["C", "B"], terminations)
        result = reduction.reduce_pdn_admittance(req)
        self.assertEqual(result["nodes"], ["D", "A"])
        self.assertEqual(result["eliminated_nodes"], ["C", "B"])
        excitation = np.array([1 + .2j, -.4 + .8j])
        for index, matrix in enumerate(complete):
            injections = np.zeros(4, dtype=complex); injections[[3, 0]] = excitation
            reference = np.linalg.solve(matrix, injections)
            retained = np.linalg.solve(complex_matrix(result["admittance_s"][index]), excitation)
            auxiliary = complex_matrix(result["auxiliary_voltage_basis"][index]) @ retained
            np.testing.assert_allclose(retained, reference[[3, 0]], rtol=2e-13, atol=2e-13)
            np.testing.assert_allclose(auxiliary, reference[[2, 1]], rtol=2e-13, atol=2e-13)
            supplied_power = reference.conj() @ matrix @ reference
            reduced_power = retained.conj() @ excitation
            self.assertLess(abs(supplied_power - reduced_power), 2e-13)

    def test_complex_nonreciprocal_passive_source_without_symmetry_repair(self):
        source = (np.diag([3., 2., 4.]) + np.array([[0., .7, .2], [-.7, 0., .5], [-.2, -.5, 0.]])
                  + 1j * np.array([[2., -.3, -.1], [-.3, 1., -.2], [-.1, -.2, .5]]))
        load = np.array([[.25 - .8j]])
        req = request([source], ["A", "B", "C"], ["B", "A"], ["C"], [load])
        req["source"]["model_status"] = "experimental"
        result = reduction.reduce_pdn_admittance(req)
        reduced = complex_matrix(result["admittance_s"][0])
        auxiliary = complex_matrix(result["auxiliary_voltage_basis"][0])
        self.assertGreater(abs(reduced[0, 1] - reduced[1, 0]), 1.)
        self.assertGreater(np.linalg.eigvalsh((reduced + reduced.conj().T) / 2)[0], 0.)
        voltage = np.array([1. + 2j, -.7 + .3j])
        full_voltage = np.array([voltage[1], voltage[0], (auxiliary @ voltage)[0]])
        power = full_voltage.conj() @ source @ full_voltage + (auxiliary @ voltage).conj() @ load @ (auxiliary @ voltage)
        self.assertLess(abs(voltage.conj() @ reduced @ voltage - power), 2e-13)
        self.assertEqual(result["model_status"], "experimental")

    def test_dielectric_projection_binding_and_copies(self):
        req = plate(2)
        req["electrodes"].insert(1, {"id": "middle", "node": "middle-node",
            "vertices": [i for i, point in enumerate(req["mesh"]["vertices"]) if point[0] == .5]})
        original = extract_pdn_dielectric_ac(req)
        projected = reduction.dielectric_admittance_source(original)
        self.assertEqual(projected["source_id"], original["input_digest"])
        self.assertEqual(projected["reference_node"], "return-terminal")
        self.assertEqual(projected["context_digest"], original["context_digest"])
        projected["admittance_s"][0][0][0]["real"] += 1.
        self.assertNotEqual(projected["admittance_s"][0][0][0]["real"], original["ac"][0]["admittance_s"][0][0]["real"])
        for key, value in (("production_qualified", True), ("production_qualified", 0), ("model_status", "validated"),
                           ("contract", "other"), ("input_digest", "bad")):
            bad = deepcopy(original); bad[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(reduction.PdnAdmittanceReductionError):
                reduction.dielectric_admittance_source(bad)
        result = reduction.reduce_pdn_admittance(request())
        changed = request(); changed["termination_admittance_s"] = [pairs([[1.]])]
        second = reduction.reduce_pdn_admittance(changed)
        self.assertEqual(result["source_digest"], second["source_digest"])
        self.assertNotEqual(result["input_digest"], second["input_digest"])

    def test_singular_conditioning_active_and_corrupted_solve_rejections(self):
        cases = [(request([np.diag([1., 0.])]), "CONDITIONING_FAILURE"),
                 (request([np.diag([-1., 1.])]), "NONPASSIVE_RESPONSE"),
                 (request(loads=[[[-.1]]]), "NONPASSIVE_RESPONSE")]
        ill = np.array([[1., 0., 0.], [0., 1., 1 - 1e-14], [0., 1 - 1e-14, 1.]])
        cases.append((request([ill], ["P", "Q", "R"], ["P"], ["Q", "R"]), "CONDITIONING_FAILURE"))
        for req, code in cases:
            with self.subTest(code=code), self.assertRaises(reduction.PdnAdmittanceReductionError) as caught:
                reduction.reduce_pdn_admittance(req)
            self.assertEqual(caught.exception.code, "PDN_ADMITTANCE_REDUCTION_" + code)
        with patch.object(reduction, "_solve_linear", side_effect=lambda system, rhs, where: (np.zeros_like(rhs), 0., 1.)):
            with self.assertRaisesRegex(reduction.PdnAdmittanceReductionError, "equation residual"):
                reduction.reduce_pdn_admittance(request())

    def test_malformed_partition_complex_values_frequency_and_status(self):
        mutations = [lambda r: r.update(retained_nodes=[]), lambda r: r.update(eliminated_nodes=["P"]),
            lambda r: r.update(retained_nodes=["missing"]), lambda r: r.update(extra=1),
            lambda r: r["source"].update(reference_node="P"), lambda r: r["source"].update(nodes=["P", "P"]),
            lambda r: r["source"].update(frequencies_hz=[0.]), lambda r: r["source"].update(frequencies_hz=[True]),
            lambda r: r["source"].update(frequencies_hz=[2., 1.]), lambda r: r["source"].update(model_status="validated"),
            lambda r: r["source"].update(context_digest="A" * 64), lambda r: r["source"].update(extra=True),
            lambda r: r["source"]["admittance_s"][0][0][0].update(real=True),
            lambda r: r["source"]["admittance_s"][0][0][0].update(imag=float("nan")),
            lambda r: r["source"]["admittance_s"][0].append([]),
            lambda r: r.update(termination_admittance_s=[])]
        for index, mutate in enumerate(mutations):
            req = request(); mutate(req)
            with self.subTest(case=index), self.assertRaises(reduction.PdnAdmittanceReductionError) as caught:
                reduction.reduce_pdn_admittance(req)
            self.assertEqual(caught.exception.code, "PDN_ADMITTANCE_REDUCTION_INVALID_REQUEST")

    def test_resource_bounds_before_solve_and_atomic_cancellation(self):
        for attribute, limit in (("_MAX_NODES", 1), ("_MAX_FREQUENCIES", 0), ("_MAX_MATRIX_ENTRIES", 1),
                                 ("_MAX_DENSE_WORK", 1), ("_MAX_RESULT_BYTES", 1), ("_MAX_REQUEST_BYTES", 1)):
            with self.subTest(bound=attribute), patch.object(reduction, attribute, limit), \
                    patch.object(reduction, "_solve_linear") as solve:
                with self.assertRaises(reduction.PdnAdmittanceReductionError) as caught:
                    reduction.reduce_pdn_admittance(request())
                self.assertEqual(caught.exception.code, "PDN_ADMITTANCE_REDUCTION_RESOURCE_LIMIT")
                solve.assert_not_called()
        calls = 0

        def cancel():
            nonlocal calls
            calls += 1
            return calls == 3

        req = request([np.array([[.75, -.5], [-.5, .625]])] * 2)
        with self.assertRaises(reduction.PdnAdmittanceReductionError) as caught:
            reduction.reduce_pdn_admittance(req, cancel_check=cancel)
        self.assertEqual(caught.exception.code, "PDN_ADMITTANCE_REDUCTION_CANCELLED")
        self.assertEqual(calls, 3)


if __name__ == "__main__":
    unittest.main()
