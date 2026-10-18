# SPDX-License-Identifier: Apache-2.0
"""Original independent spatial-chain and per-section quadrature witnesses."""
from copy import deepcopy
from hashlib import sha256
import json
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.integrate import quad
from scipy.linalg import expm

from python.spike_core import rlgc_line_cascade as cascade
from python.spike_core.rlgc_line_fields import run_rlgc_line_fields
from tests.python.test_rlgc_line_fields import pair, value
from tests.python.test_rlgc_line_network import request as line_request


def request(count=3, frequencies=(1e6, 1e8, 4e8), left=1+.2j, right=.3-.4j):
    return {"contract": cascade.REQUEST_CONTRACT,
            "sections": [{"id": f"section-{index}",
                          "line_request": line_request(frequencies, resistance=3+4*index, conductance=.001+.0007*index,
                                                       length_m=.15+.06*index, inductance_h_per_m=(2.5+index)*1e-7,
                                                       capacitance_f_per_m=(1+.3*index)*1e-10),
                          "probes": [{"id": f"probe-{i}", "fractional_position": fraction} for i, fraction in enumerate((0., .25, .5, 1.))]}
                         for index in range(count)],
            "excitations": [{"frequency_hz": frequency, "incident_left": pair(left), "incident_right": pair(right)} for frequency in frequencies]}


def network_values(result):
    return [np.array([[value(item) for item in row] for row in matrix]) for matrix in result["network"]["s_parameters"]]


def spatial_oracle(req, index):
    """Physical V/I state-transition products and independent boundary solve.

    No leaf S matrices, wave connection matrix or overlap integrals are used.
    """
    reference = req["sections"][0]["line_request"]["reference_impedance_ohm"]
    generators, chains, lengths = [], [], []
    total = np.eye(2, dtype=complex)
    for section in req["sections"]:
        line = section["line_request"]
        sample = line["samples"][index]
        omega = 2 * math.pi * sample["frequency_hz"]
        generator = np.array([[0, sample["resistance_ohm_per_m"] + 1j*omega*line["inductance_h_per_m"]],
                              [sample["conductance_s_per_m"] + 1j*omega*line["capacitance_f_per_m"], 0]])
        chain = expm(generator * line["length_m"])
        generators.append(generator)
        chains.append(chain)
        lengths.append(line["length_m"])
        total = total @ chain
    system = np.vstack([np.array([1, reference]) @ total, [1, -reference]])

    def state(excitation):
        return np.linalg.solve(system, 2 * math.sqrt(reference) * np.asarray(excitation))

    columns = []
    for excitation in ([1, 0], [0, 1]):
        right = state(excitation)
        left = total @ right
        columns.append([(left[0] - reference*left[1])/(2*math.sqrt(reference)),
                        (right[0] + reference*right[1])/(2*math.sqrt(reference))])
    incoming = req["excitations"][index]
    right = state([value(incoming["incident_left"]), value(incoming["incident_right"])])
    right_states = [None] * len(chains)
    for position in reversed(range(len(chains))):
        right_states[position] = right
        right = chains[position] @ right

    def fields(position, fraction):
        return expm(generators[position] * lengths[position] * (1-fraction)) @ right_states[position]

    return np.column_stack(columns), fields


class RLGCLineCascadeTests(unittest.TestCase):
    def test_two_and_three_sections_match_independent_spatial_network_and_fields(self):
        for count in (2, 3):
            req = request(count)
            result = cascade.run_rlgc_line_cascade(req)
            for index, matrix in enumerate(network_values(result)):
                expected, oracle = spatial_oracle(req, index)
                np.testing.assert_allclose(matrix, expected, atol=2e-13, rtol=2e-13)
                for position, child in enumerate(result["sections"]):
                    for probe in child["result"]["points"][index]["probe_values"]:
                        voltage, current = oracle(position, probe["fractional_position"])
                        np.testing.assert_allclose(value(probe["voltage_v"]), voltage, atol=3e-12, rtol=1e-12)
                        np.testing.assert_allclose(value(probe["current_left_to_right_a"]), current, atol=3e-14, rtol=1e-12)

    def test_coherent_local_waves_and_heat_match_independent_section_quadrature(self):
        req = request()
        result = cascade.run_rlgc_line_cascade(req)
        for index, point in enumerate(result["points"]):
            _, oracle = spatial_oracle(req, index)
            conductor_sum, dielectric_sum = 0., 0.
            for position, section in enumerate(req["sections"]):
                line, child = section["line_request"], result["sections"][position]["result"]
                sample = line["samples"][index]
                conductor = quad(lambda x: sample["resistance_ohm_per_m"] * abs(oracle(position, x)[1])**2,
                                 0, 1, epsabs=1e-13, epsrel=1e-12)[0] * line["length_m"]
                dielectric = quad(lambda x: sample["conductance_s_per_m"] * abs(oracle(position, x)[0])**2,
                                  0, 1, epsabs=1e-13, epsrel=1e-12)[0] * line["length_m"]
                self.assertAlmostEqual(child["points"][index]["power_balance"]["conductor_loss_w"], conductor, delta=2e-12)
                self.assertAlmostEqual(child["points"][index]["power_balance"]["dielectric_loss_w"], dielectric, delta=2e-12)
                conductor_sum += conductor
                dielectric_sum += dielectric
                reference = line["reference_impedance_ohm"]
                for name, fraction, sign in (("incident_left", 0, 1), ("incident_right", 1, -1)):
                    voltage, current = oracle(position, fraction)
                    expected_wave = (voltage + sign*reference*current)/(2*math.sqrt(reference))
                    actual_wave = value(child["source_request"]["excitations"][index][name])
                    np.testing.assert_allclose(actual_wave, expected_wave, atol=3e-13, rtol=1e-12)
            self.assertAlmostEqual(point["power_balance"]["net_input_w"], conductor_sum + dielectric_sum, delta=3e-12)
            self.assertAlmostEqual(point["power_balance"]["conductor_loss_w"], conductor_sum, delta=3e-12)
            self.assertAlmostEqual(point["power_balance"]["dielectric_loss_w"], dielectric_sum, delta=3e-12)
            for junction in point["junctions"]:
                self.assertLess(abs(value(junction["voltage_residual_v"])), 1e-12)
                self.assertLess(abs(value(junction["current_residual_a"])), 1e-13)
                self.assertLess(abs(junction["power_residual_w"]), 1e-12)

    def test_identical_segmentation_preserves_network_fields_and_total_heat(self):
        req = request()
        prototype = deepcopy(req["sections"][0]["line_request"])
        lengths = (.17, .28, .11)
        whole_probes, offset = [], 0.
        for section, length in zip(req["sections"], lengths):
            section["line_request"] = {**deepcopy(prototype), "length_m": length}
            for probe in section["probes"]:
                whole_probes.append({"id": section["id"] + "/" + probe["id"], "fractional_position": (offset + length*probe["fractional_position"])/sum(lengths)})
            offset += length
        whole = run_rlgc_line_fields({"contract": "spike/rlgc-line-fields-request/v1", "line_request": {**prototype, "length_m": sum(lengths)},
                                      "excitations": req["excitations"], "probes": whole_probes})
        result = cascade.run_rlgc_line_cascade(req)
        for index, (actual, expected) in enumerate(zip(network_values(result), network_values(whole))):
            np.testing.assert_allclose(actual, expected, atol=2e-13, rtol=2e-13)
            self.assertAlmostEqual(result["points"][index]["power_balance"]["total_loss_w"], whole["points"][index]["power_balance"]["total_loss_w"], delta=2e-13)
            probes = [probe for child in result["sections"] for probe in child["result"]["points"][index]["probe_values"]]
            for probe, expected_probe in zip(probes, whole["points"][index]["probe_values"]):
                np.testing.assert_allclose(value(probe["voltage_v"]), value(expected_probe["voltage_v"]), atol=3e-12, rtol=1e-12)
                np.testing.assert_allclose(value(probe["current_left_to_right_a"]), value(expected_probe["current_left_to_right_a"]), atol=3e-14, rtol=1e-12)

    def test_analytic_quarter_wave_impedance_step_and_lossless_power(self):
        req = request(2, (1e8,))
        for section, length, inductance in zip(req["sections"], (.5, .25), (2.5e-7, 1e-6)):
            section["line_request"] = line_request((1e8,), resistance=0., conductance=0., length_m=length,
                                                    inductance_h_per_m=inductance, capacitance_f_per_m=1e-10)
        result = cascade.run_rlgc_line_cascade(req)
        matrix = network_values(result)[0]
        np.testing.assert_allclose(matrix, [[-.6, -.8], [-.8, .6]], atol=3e-15, rtol=0)
        np.testing.assert_allclose(matrix.conj().T @ matrix, np.eye(2), atol=3e-15, rtol=0)
        self.assertEqual(result["points"][0]["power_balance"]["total_loss_w"], 0.)
        self.assertLess(abs(result["points"][0]["power_balance"]["net_input_w"]), 2e-15)
        self.assertLess(result["diagnostics"]["maximum_junction_power_residual_w"], 2e-15)

    def test_one_section_is_actual_s04_and_zero_drive_has_exact_zero_ledger(self):
        req = request(1)
        section = req["sections"][0]
        direct = run_rlgc_line_fields({"contract": "spike/rlgc-line-fields-request/v1", "line_request": section["line_request"],
                                       "probes": section["probes"], "excitations": req["excitations"]})
        result = cascade.run_rlgc_line_cascade(req)
        self.assertEqual(result["sections"][0]["result"], direct)
        self.assertEqual(result["network"]["s_parameters"], direct["network"]["s_parameters"])
        self.assertEqual(result["diagnostics"]["maximum_junction_power_residual_w"], 0.)
        zero = cascade.run_rlgc_line_cascade(request(left=0, right=0))
        for point in zero["points"]:
            self.assertTrue(all(value == 0 for value in point["power_balance"].values()))
            self.assertTrue(all(j["power_residual_w"] == 0 for j in point["junctions"]))

    def test_coherent_scaling_and_reversal_preserve_physical_ownership(self):
        req = request(frequencies=(1e8,))
        result = cascade.run_rlgc_line_cascade(req)
        scaled = deepcopy(req)
        factor = 3-4j
        for excitation in scaled["excitations"]:
            for key in ("incident_left", "incident_right"):
                excitation[key] = pair(factor * value(excitation[key]))
        scaled_result = cascade.run_rlgc_line_cascade(scaled)
        self.assertEqual(result["network"]["s_parameters"], scaled_result["network"]["s_parameters"])
        self.assertAlmostEqual(scaled_result["points"][0]["power_balance"]["total_loss_w"], 25*result["points"][0]["power_balance"]["total_loss_w"], delta=2e-12)
        reverse = deepcopy(req)
        reverse["sections"].reverse()
        excitation = reverse["excitations"][0]
        excitation["incident_left"], excitation["incident_right"] = excitation["incident_right"], excitation["incident_left"]
        reversed_result = cascade.run_rlgc_line_cascade(reverse)
        np.testing.assert_allclose(network_values(reversed_result)[0], network_values(result)[0][::-1, ::-1], atol=2e-13, rtol=2e-13)
        for normal, reversed_child in zip(result["sections"], reversed(reversed_result["sections"])):
            self.assertEqual(normal["id"], reversed_child["id"])
            self.assertAlmostEqual(normal["result"]["points"][0]["power_balance"]["total_loss_w"], reversed_child["result"]["points"][0]["power_balance"]["total_loss_w"], delta=2e-13)

    def test_contract_digest_and_child_input_snapshots(self):
        req = request()
        before = deepcopy(req)
        result = cascade.run_rlgc_line_cascade(req)
        self.assertEqual(set(result), {"contract", "model_status", "production_qualified", "input_digest", "source_request", "network", "sections", "points", "diagnostics", "limitations"})
        self.assertEqual(result["contract"], cascade.RESULT_CONTRACT)
        self.assertEqual(result["model_status"], "experimental")
        self.assertFalse(result["production_qualified"])
        self.assertEqual(result["source_request"], before)
        digest = sha256(json.dumps(req, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(result["input_digest"], digest)
        for original, child in zip(req["sections"], result["sections"]):
            self.assertEqual(child["id"], original["id"])
            self.assertEqual(child["result"]["source_request"]["line_request"], original["line_request"])
            self.assertEqual(child["result"]["source_request"]["probes"], original["probes"])
        self.assertEqual(req, before)
        req["sections"][0]["line_request"]["length_m"] = .9
        self.assertEqual(result["source_request"], before)
        self.assertNotEqual(cascade.run_rlgc_line_cascade(req)["input_digest"], digest)

    def test_exact_grid_reference_ids_and_nested_admission(self):
        invalid = [request(0), request(9), request(frequencies=(0.,)), request(frequencies=(1., 1.))]
        for path, replacement in ((["contract"], "wrong"), (["sections", 1, "id"], "section-0"),
                                  (["sections", 0, "id"], " "), (["sections", 0, "id"], "x"*81),
                                  (["sections", 1, "line_request", "reference_impedance_ohm"], math.nextafter(50., 51.)),
                                  (["sections", 1, "line_request", "samples", 0, "frequency_hz"], 1e6+.1),
                                  (["excitations", 0, "incident_left", "real"], True),
                                  (["excitations", 0, "incident_right", "imag"], math.inf),
                                  (["sections", 0, "probes", 0, "fractional_position"], -1)):
            req = request()
            target = req
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = replacement
            invalid.append(req)
        tuple_sections, extra = request(), request()
        tuple_sections["sections"] = tuple(tuple_sections["sections"])
        extra["sections"][0]["extra"] = 1
        invalid.extend([tuple_sections, extra])
        for req in invalid:
            with self.subTest(req=repr(req)[:90]):
                with self.assertRaises(cascade.RLGCLineCascadeError):
                    cascade.run_rlgc_line_cascade(req)

    def test_combined_output_and_work_preflight_precede_leaf_solvers(self):
        large = request(8, tuple(range(1, 1025)))
        with patch.object(cascade, "build_rlgc_line_network") as build:
            with self.assertRaises(cascade.RLGCLineCascadeError) as caught:
                cascade.run_rlgc_line_cascade(large)
            self.assertEqual(caught.exception.code, "RLGC_LINE_CASCADE_RESOURCE_LIMIT")
            build.assert_not_called()
        with patch.object(cascade, "_MAX_WORK", 1), patch.object(cascade, "build_rlgc_line_network") as build:
            with self.assertRaises(cascade.RLGCLineCascadeError) as caught:
                cascade.run_rlgc_line_cascade(request())
            self.assertEqual(caught.exception.code, "RLGC_LINE_CASCADE_RESOURCE_LIMIT")
            build.assert_not_called()

    def test_cancellation_and_numerical_failure_are_atomic(self):
        calls = 0

        def cancelled():
            nonlocal calls
            calls += 1
            return calls == 24

        with self.assertRaises(cascade.RLGCLineCascadeError) as caught:
            cascade.run_rlgc_line_cascade(request(), cancel_check=cancelled)
        self.assertEqual(caught.exception.code, "RLGC_LINE_CASCADE_CANCELLED")
        with self.assertRaises(cascade.RLGCLineCascadeError) as caught:
            cascade.run_rlgc_line_cascade(request(), cancel_check=lambda: 1/0)
        self.assertEqual(caught.exception.code, "RLGC_LINE_CASCADE_CANCEL_CHECK_FAILED")
        for req in (request(frequencies=(1e308,)), request(left=1e308)):
            with self.assertRaises(cascade.RLGCLineCascadeError):
                cascade.run_rlgc_line_cascade(req)
        with patch.object(cascade.np.linalg, "cond", return_value=1e9):
            with self.assertRaises(cascade.RLGCLineCascadeError) as caught:
                cascade.run_rlgc_line_cascade(request())
            self.assertEqual(caught.exception.code, "RLGC_LINE_CASCADE_ILL_CONDITIONED")

    def test_corrupt_child_junction_and_loss_are_rejected_without_repair(self):
        for corrupt_power in (False, True):
            def damaged(child_request, **kwargs):
                child = run_rlgc_line_fields(child_request, **kwargs)
                if corrupt_power:
                    child["points"][0]["power_balance"]["conductor_loss_w"] += 1
                else:
                    child["points"][0]["boundary_values"]["right"]["voltage_v"]["real"] += 1
                return child

            with patch.object(cascade, "run_rlgc_line_fields", side_effect=damaged):
                with self.assertRaises(cascade.RLGCLineCascadeError) as caught:
                    cascade.run_rlgc_line_cascade(request())
                self.assertEqual(caught.exception.code, "RLGC_LINE_CASCADE_NUMERICAL_FAILURE")


if __name__ == "__main__":
    unittest.main()
