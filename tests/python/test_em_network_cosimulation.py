# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Independent lumped-circuit oracles; EMerge adapter tests do not run FEM."""
from copy import deepcopy
import unittest

import numpy as np

from python.spike_core.em_network_ac import REQUEST_CONTRACT, WAVE_CONVENTION, solve_em_network_ac
from python.spike_core.em_network_resistor_thermal import run_em_network_resistor_thermal
from extensions.emerge_suite.cosimulation import prepare_cosimulation_source
from tests.python.test_assembly_tetra_thermal import request as heat_request


def request(s=None, impedance=(50., 0.)):
    s = s if s is not None else [[[0., 0.]]]
    ports = ["p"+str(i) for i in range(len(s))]
    return {"contract": REQUEST_CONTRACT, "wave_convention": WAVE_CONVENTION,
        "source": {"id": "synthetic", "port_names": ports, "reference_impedance_ohm": 50.,
                   "frequencies_hz": [1e6], "s_parameters": [[[{"real": pair[0], "imag": pair[1]}
                                                               for pair in row] for row in s]]},
        "boundaries": [{p: {"voltage_v": [2. if i == 0 else 0., 0.], "impedance_ohm": list(impedance)}
                        for i, p in enumerate(ports)}]}


def analysis():
    return {"contract": "spike/v1", "analysis_id": "synthetic-adapter-test", "status": "completed",
        "mode": "emerge-si", "model_status": "unvalidated", "summary": {}, "fields": {},
        "networks": {"s_parameters": {"frequencies_hz": [1e6], "ports": ["p0"],
            "reference_impedance_ohm": 50., "values": [[[[0., 0.]]]]}}, "probes": [], "issues": [],
        "provenance": {"solver": "EMerge/synthetic-test", "design_id": "board", "design_digest_sha256": "a"*64,
                       "board_case_sha256": "b"*64, "generated_script_sha256": "c"*64}}


def packet(raw=None, **options):
    return prepare_cosimulation_source(raw or analysis(), {"design_id": "board", "digest_sha256": "a"*64},
        expected_case_sha256="b"*64, expected_script_sha256="c"*64,
        port_bindings={"p0": {"positive_node": "signal", "negative_node": "0", "reference_plane": "declared-pad"}},
        wave_convention=options.get("wave_convention", WAVE_CONVENTION))


class EMNetworkCosimulationTests(unittest.TestCase):
    def test_matched_resistor_rms_power_and_input_unchanged(self):
        raw = request(); before = deepcopy(raw)
        sample = solve_em_network_ac(raw)["samples"][0]
        self.assertEqual(raw, before)
        np.testing.assert_allclose(sample["voltage_rms_v"], [[1., 0.]], atol=1e-15)
        np.testing.assert_allclose(sample["current_into_network_rms_a"], [[.02, 0.]], atol=1e-15)
        self.assertAlmostEqual(sample["series_resistor_power_w"][0], .02)
        self.assertAlmostEqual(sample["unclassified_network_power_w"], .02)
        self.assertAlmostEqual(sample["source_real_power_w"], .04)

    def test_reactive_series_component_uses_complex_current(self):
        sample = solve_em_network_ac(request(impedance=(50., 50.)))["samples"][0]
        exact_i = 2/(100+50j)
        np.testing.assert_allclose(sample["current_into_network_rms_a"], [[exact_i.real, exact_i.imag]], atol=1e-15)
        self.assertAlmostEqual(sample["series_resistor_power_w"][0], 50*abs(exact_i)**2)

    def test_ideal_through_does_not_need_singular_s_to_z(self):
        raw = request([[[0, 0], [1, 0]], [[1, 0], [0, 0]]])
        sample = solve_em_network_ac(raw)["samples"][0]
        np.testing.assert_allclose(sample["voltage_rms_v"], [[1, 0], [1, 0]], atol=1e-15)
        np.testing.assert_allclose(sample["current_into_network_rms_a"], [[.02, 0], [-.02, 0]], atol=1e-15)
        self.assertAlmostEqual(sample["unclassified_network_power_w"], 0.)

    def test_nonreciprocal_order_and_frequency_rows_are_preserved(self):
        # Matched boundaries give a=Vs/(2 sqrt(Z0)), independently of S.
        matrix = np.array([[.1, .2j, .03], [.04, -.1, .12j], [.2, .05, .08]])
        raw = request([[[z.real, z.imag] for z in row] for row in matrix])
        raw["source"]["frequencies_hz"] = [1e6, 2e6]
        raw["source"]["s_parameters"].append(
            [[{"real": .5*z.real, "imag": .5*z.imag} for z in row] for row in matrix])
        raw["boundaries"] *= 2
        before = deepcopy(raw)
        out = solve_em_network_ac(raw)
        incident = np.array([1/np.sqrt(50), 0., 0.])
        expected_v = np.sqrt(50)*(incident+matrix@incident)
        expected_i = (incident-matrix@incident)/np.sqrt(50)
        for sample, frequency, multiplier in zip(out["samples"], [1e6, 2e6], [1., .5]):
            self.assertEqual(sample["frequency_hz"], frequency)
            np.testing.assert_allclose(np.array(sample["voltage_rms_v"])@[1, 1j],
                np.sqrt(50)*(incident+multiplier*matrix@incident), atol=1e-15)
            np.testing.assert_allclose(np.array(sample["current_into_network_rms_a"])@[1, 1j],
                (incident-multiplier*matrix@incident)/np.sqrt(50), atol=1e-15)
        self.assertEqual(raw, before)
        # Source-order permutation must only permute results, not transpose S.
        order = [2, 0, 1]
        permuted = deepcopy(raw)
        permuted["source"]["port_names"] = [raw["source"]["port_names"][i] for i in order]
        permuted["source"]["s_parameters"] = [
            [[m[i][j] for j in order] for i in order] for m in raw["source"]["s_parameters"]]
        sample = solve_em_network_ac(permuted)["samples"][0]
        np.testing.assert_allclose(np.array(sample["voltage_rms_v"])@[1, 1j], expected_v[order], atol=1e-15)
        np.testing.assert_allclose(np.array(sample["current_into_network_rms_a"])@[1, 1j], expected_i[order], atol=1e-15)

    def test_bad_network_boundary_active_and_singular_cases_fail(self):
        for kind in ("missing_port", "active", "singular", "convention", "frequency"):
            raw = request()
            if kind == "missing_port": raw["boundaries"][0] = {}
            if kind == "active": raw["source"]["s_parameters"][0][0][0] = {"real": 1.2, "imag": 0}
            if kind == "singular":
                raw["source"]["s_parameters"][0][0][0] = {"real": -1, "imag": 0}
                raw["boundaries"][0]["p0"]["impedance_ohm"] = [0, 0]
            if kind == "convention": raw["wave_convention"] = "unknown"
            if kind == "frequency": raw["source"]["frequencies_hz"] = [float("nan")]
            with self.subTest(kind=kind), self.assertRaises(ValueError): solve_em_network_ac(raw)
        with self.assertRaisesRegex(ValueError, "CANCELLED"):
            solve_em_network_ac(request(), cancel_check=lambda: True)

    def test_large_source_cannot_mask_weak_port_roundoff_failure(self):
        raw = request([[[0, 0], [0, 0]], [[0, 0], [1-2**-53, 0]]])
        raw["boundaries"][0]["p0"]["voltage_v"] = [1e8, 0]
        raw["boundaries"][0]["p1"] = {"voltage_v": [2., 0], "impedance_ohm": [1e12, 0]}
        # Natural cancellation, no injected solve defect. The aggregate check
        # previously hid a ~77% weak-current error behind the 1e8 V port.
        with self.assertRaisesRegex(ValueError, "Per-port physical"):
            solve_em_network_ac(raw)

    def test_bound_emerge_packet_preserves_status_and_rejects_stale_source(self):
        out = packet()
        self.assertEqual(out["model_status"], "unvalidated")
        self.assertEqual(out["network_source"]["port_names"], ["p0"])
        raw = request(); raw["source"] = out["network_source"]
        self.assertAlmostEqual(solve_em_network_ac(raw)["samples"][0]["unclassified_network_power_w"], .02)
        for key in ("board_case_sha256", "generated_script_sha256", "design_digest_sha256"):
            raw = analysis(); raw["provenance"][key] = "f"*64
            with self.subTest(key=key), self.assertRaises(ValueError): packet(raw)
        with self.assertRaises(ValueError): packet(wave_convention="not calibrated")

    def test_source_diagnostics_preserved_and_error_issues_rejected(self):
        raw = analysis(); raw["status"] = "completed_with_warnings"
        issue = {"code": "OMITTED_LOSS", "severity": "warning", "message": "Loss was not modeled"}
        raw["issues"] = [issue]
        out = packet(raw)
        self.assertEqual(out["source_status"], "completed_with_warnings")
        self.assertEqual(out["source_issues"], [issue])
        issue["severity"] = "error"
        self.assertEqual(out["source_issues"][0]["severity"], "warning")
        with self.assertRaisesRegex(ValueError, "blocking error"):
            packet(raw)

    def test_known_resistor_heat_maps_conservatively_without_em_deficit(self):
        heat = heat_request()
        thermal = {"contract": "spike/em-network-resistor-thermal-request/v1", "ac_request": request(),
            "thermal_request": heat, "sample_index": 0,
            "resistor_cell_weights": {"p0": {c["id"]: 1/6 for c in heat["mesh"]["cells"]}}}
        out = run_em_network_resistor_thermal(thermal)
        self.assertAlmostEqual(out["deposited_series_resistor_power_w"], .02)
        self.assertAlmostEqual(out["thermal"]["heat_balance"]["source_w"], .02)
        self.assertAlmostEqual(out["unclassified_em_network_power_w"], .02)
        # Deposited heat is not .04: unclassified EM deficit was not added.
        thermal["resistor_cell_weights"]["p0"] = None
        out = run_em_network_resistor_thermal(thermal)
        self.assertEqual(out["deposited_series_resistor_power_w"], 0.)
        self.assertAlmostEqual(out["outside_series_resistor_power_w"], .02)

    def test_bad_mapping_and_double_counting_fail(self):
        heat = heat_request()
        raw = {"contract": "spike/em-network-resistor-thermal-request/v1", "ac_request": request(),
            "thermal_request": heat, "sample_index": 0, "resistor_cell_weights": {"p0": {"solid-0": .5}}}
        with self.assertRaisesRegex(ValueError, "weights"): run_em_network_resistor_thermal(raw)
        raw["resistor_cell_weights"]["p0"] = None
        heat["heat_sources_w_m3"] = {"solid-0": 1.}
        with self.assertRaisesRegex(ValueError, "double counting"): run_em_network_resistor_thermal(raw)


if __name__ == "__main__":
    unittest.main()
