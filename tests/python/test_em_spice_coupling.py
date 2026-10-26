# SPDX-License-Identifier: Apache-2.0
"""Independent analytic and actually executed owned-SPICE coupling checks."""
import cmath
from copy import deepcopy
import math
import unittest
from unittest.mock import patch

from python.spike_core.solvers.execution.coupling.em_network_ac import WAVE_CONVENTION
from python.spike_core.solvers.execution.coupling.em_spice_coupling import REQUEST_CONTRACT, run_em_spice_coupling
from python.spike_core.spikes_runtime import run_netlist


def element(name, kind, p, n, value):
    return {"id": name, "type": kind, "positive_node": p, "negative_node": n,
            "phasor" if kind.endswith("source") else "value": value}


def request(frequencies=(1000.,), matrices=None):
    matrices = matrices or [[[0j]] for _ in frequencies]
    ports = [f"P{i+1}" for i in range(len(matrices[0]))]
    return {"contract": REQUEST_CONTRACT, "wave_convention": WAVE_CONVENTION,
        "source": {"id": "independently-authored-analytic-fixture", "port_names": ports,
            "reference_impedance_ohm": 50., "frequencies_hz": list(frequencies),
            "s_parameters": [[[{"real": complex(v).real, "imag": complex(v).imag} for v in row]
                for row in matrix] for matrix in matrices]},
        "circuit": {"ground_node": "gnd", "elements": [
            element("V1", "voltage_source", "src", "gnd", [2., 0.]),
            element("R1", "resistor", "src", "p1", 25.)]},
        "port_bindings": {p: {"positive_node": f"p{i+1}", "negative_node": "gnd",
            "reference_plane": "explicit synthetic terminal plane"} for i, p in enumerate(ports)}}


def z(pair):
    return complex(*pair)


class EmSpiceCouplingTests(unittest.TestCase):
    def assertComplexClose(self, actual, expected, rtol=2e-11, atol=1e-14):
        self.assertLessEqual(abs(actual-expected), atol + rtol*abs(expected))

    def test_matched_resistor_executes_native_and_matches_physical_native_circuit(self):
        candidate = request()
        before = deepcopy(candidate)
        result = run_em_spice_coupling(candidate)
        physical = run_netlist({"netlist": "Independent physical divider\nV1 src 0 2\nR1 src p 25\nR2 p 0 50\n.op\n.end\n"})
        self.assertEqual(physical["status"], "completed")
        sample = result["samples"][0]
        self.assertComplexClose(z(sample["voltage_rms_v"][0]), 4/3)
        self.assertComplexClose(z(sample["voltage_rms_v"][0]), physical["data"]["node_voltage_v"]["p"])
        self.assertComplexClose(z(sample["current_into_network_rms_a"][0]), physical["data"]["element_current_a"]["R2"])
        self.assertEqual(result["provenance"]["native_execution_count"], 1)
        self.assertEqual(result["provenance"]["library_origin"], "release_owned")
        self.assertFalse(result["provenance"]["native_ac_route"])
        self.assertEqual(len(sample["lowered_netlist_sha256"]), 64)
        self.assertGreater(sample["native_diagnostics"]["matrix_order"], 0)
        self.assertNotIn("library", sample["native_diagnostics"])
        self.assertEqual(candidate, before)

    def test_reactive_rlc_and_complex_source_closed_form_on_irregular_grid(self):
        frequencies = (1000., 12345., 900000.)
        candidate = request(frequencies)
        vs = 2 * cmath.exp(0.37j)
        candidate["circuit"]["elements"] = [
            element("V1", "voltage_source", "src", "gnd", [vs.real, vs.imag]),
            element("R1", "resistor", "src", "mid", 25.),
            element("L1", "inductor", "mid", "p1", 40e-6),
            element("C1", "capacitor", "p1", "gnd", 3e-9)]
        result = run_em_spice_coupling(candidate)
        for sample, frequency in zip(result["samples"], frequencies):
            w = 2*math.pi*frequency
            y = 1/50 + 1j*w*3e-9
            v = vs/(1+(25+1j*w*40e-6)*y)
            source_current = y*v
            self.assertEqual(sample["frequency_hz"], frequency)
            self.assertComplexClose(z(sample["voltage_rms_v"][0]), v)
            self.assertComplexClose(z(sample["current_into_network_rms_a"][0]), v/50)
            self.assertComplexClose(z(sample["elements"]["L1"]["current_positive_to_negative_rms_a"]), source_current)
            self.assertComplexClose(z(sample["elements"]["C1"]["current_positive_to_negative_rms_a"]), 1j*w*3e-9*v)
            self.assertAlmostEqual(sample["circuit_resistor_heat_w"], 25*abs(source_current)**2, delta=1e-13)
            self.assertLess(sample["power_balance_error_w"], 1e-13)

    def test_ideal_through_and_frequency_dependent_series_em_network(self):
        for impedance in (0j, 30+20j):
            reflection = impedance/(100+impedance)
            transmission = 100/(100+impedance)
            candidate = request(matrices=[[[reflection, transmission], [transmission, reflection]]])
            candidate["circuit"]["elements"].append(element("RL", "resistor", "p2", "gnd", 75.))
            sample = run_em_spice_coupling(candidate)["samples"][0]
            current = 2/(100+impedance)
            self.assertComplexClose(z(sample["current_into_network_rms_a"][0]), current)
            self.assertComplexClose(z(sample["current_into_network_rms_a"][1]), -current)
            self.assertComplexClose(z(sample["voltage_rms_v"][1]), 75*current)
            self.assertAlmostEqual(sample["unclassified_network_power_w"], impedance.real*abs(current)**2, delta=1e-14)

    def test_nonreciprocal_receive_excitation_order_and_port_permutation(self):
        candidate = request(matrices=[[[0j, 0j], [0.5j, 0j]]])
        candidate["circuit"]["elements"] = [
            element("V1", "voltage_source", "s1", "gnd", [2., 0.]),
            element("R1", "resistor", "s1", "p1", 50.),
            element("V2", "voltage_source", "s2", "gnd", [0., 1.]),
            element("R2", "resistor", "s2", "p2", 50.)]
        first = run_em_spice_coupling(candidate)["samples"][0]
        self.assertComplexClose(z(first["voltage_rms_v"][0]), 1)
        self.assertComplexClose(z(first["voltage_rms_v"][1]), 1j)
        candidate["source"]["port_names"].reverse()
        candidate["source"]["s_parameters"][0] = [row[::-1] for row in candidate["source"]["s_parameters"][0][::-1]]
        second = run_em_spice_coupling(candidate)["samples"][0]
        for i in range(2):
            self.assertComplexClose(z(first["voltage_rms_v"][i]), z(second["voltage_rms_v"][1-i]))

    def test_non_ground_return_and_reversed_polarity(self):
        candidate = request()
        candidate["circuit"]["elements"].append(element("RR", "resistor", "return", "gnd", 20.))
        candidate["port_bindings"]["P1"]["negative_node"] = "return"
        first = run_em_spice_coupling(candidate)["samples"][0]
        self.assertComplexClose(z(first["current_into_network_rms_a"][0]), 2/95)
        self.assertComplexClose(z(first["voltage_rms_v"][0]), 100/95)
        candidate["port_bindings"]["P1"].update(positive_node="return", negative_node="p1")
        second = run_em_spice_coupling(candidate)["samples"][0]
        self.assertComplexClose(z(second["voltage_rms_v"][0]), -100/95)

    def test_current_source_and_zero_excitation(self):
        candidate = request()
        candidate["circuit"]["elements"] = [element("I1", "current_source", "gnd", "p1", [0., 0.02])]
        sample = run_em_spice_coupling(candidate)["samples"][0]
        self.assertComplexClose(z(sample["voltage_rms_v"][0]), 1j)
        candidate["circuit"]["elements"][0]["phasor"] = [0., 0.]
        sample = run_em_spice_coupling(candidate)["samples"][0]
        self.assertEqual(sample["voltage_rms_v"], [[0., 0.]])
        self.assertEqual(sample["source_real_power_w"], 0.)

    def test_small_excitation_preserves_relative_results(self):
        for magnitude in (1e-6, 1e-12):
            candidate = request()
            candidate["circuit"]["elements"][0]["phasor"] = [magnitude, 0.]
            sample = run_em_spice_coupling(candidate)["samples"][0]
            self.assertComplexClose(z(sample["voltage_rms_v"][0]), magnitude*2/3, atol=0)

    def test_rejects_nonpassive_dc_malformed_and_unsupported_input_before_engine(self):
        mutations = [
            lambda r: r.update(netlist=".include external"),
            lambda r: r["circuit"]["elements"][1].update(type="diode"),
            lambda r: r["circuit"]["elements"][1].update(value="25"),
            lambda r: r["circuit"]["elements"][1].update(value=float("nan")),
            lambda r: r["port_bindings"]["P1"].update(positive_node="missing"),
            lambda r: r["port_bindings"]["P1"].update(reference_plane=""),
            lambda r: r["source"]["frequencies_hz"].__setitem__(0, 0),
            lambda r: r["source"]["s_parameters"][0][0][0].update(real=1.01),
            lambda r: r.update(wave_convention="peak_voltage"),
        ]
        for mutate in mutations:
            candidate = request()
            mutate(candidate)
            with self.subTest(mutation=mutate), patch("python.spike_core.solvers.execution.coupling.em_spice_coupling.run_netlist") as engine:
                with self.assertRaises((ValueError, TypeError)):
                    run_em_spice_coupling(candidate)
                engine.assert_not_called()

    def test_singular_open_with_current_source_rejected(self):
        candidate = request(matrices=[[[1j*0+1]]])
        candidate["circuit"]["elements"] = [element("I1", "current_source", "gnd", "p1", [1., 0.])]
        with self.assertRaisesRegex(ValueError, "Singular"):
            run_em_spice_coupling(candidate)

    def test_oversized_circuit_and_sample_budget_rejected_before_native_execution(self):
        oversized = request()
        oversized["circuit"]["elements"] = [
            element(f"R{i}", "resistor", f"n{i}", "gnd", 50.) for i in range(65)]
        oversampled = request(tuple(float(i+1) for i in range(65)))
        for candidate in (oversized, oversampled):
            with patch("python.spike_core.solvers.execution.coupling.em_spice_coupling.run_netlist") as engine:
                with self.assertRaisesRegex(ValueError, "64"):
                    run_em_spice_coupling(candidate)
                engine.assert_not_called()

    def test_ill_conditioned_circuit_rejected_without_regularization(self):
        candidate = request(matrices=[[[-1+0j]]])
        candidate["circuit"]["elements"][1]["value"] = 1e-15
        with patch("python.spike_core.solvers.execution.coupling.em_spice_coupling.run_netlist") as engine:
            with self.assertRaisesRegex(ValueError, "ill-conditioned"):
                run_em_spice_coupling(candidate)
            engine.assert_not_called()

    def test_actual_native_bad_digest_and_node_corruption_are_rejected(self):
        original = run_netlist
        for mutation, expected in (("digest", "digest"), ("node", "residual")):
            def corrupt(params):
                raw = original(params)
                if mutation == "digest":
                    raw["provenance"]["source_sha256"] = "0"*64
                else:
                    raw["data"]["node_voltage_v"]["x0"] += 1e-7
                return raw
            with patch("python.spike_core.solvers.execution.coupling.em_spice_coupling.run_netlist", side_effect=corrupt):
                with self.assertRaisesRegex(ValueError, expected):
                    run_em_spice_coupling(request())

    def test_strong_source_cannot_mask_weak_node_error(self):
        candidate = request(matrices=[[[0j, 0j], [0j, 0j]]])
        candidate["circuit"]["elements"] = [
            element("V1", "voltage_source", "s1", "gnd", [1e8, 0.]),
            element("R1", "resistor", "s1", "p1", 50.),
            element("V2", "voltage_source", "s2", "gnd", [1e-6, 0.]),
            element("R2", "resistor", "s2", "p2", 50.)]
        clean = run_em_spice_coupling(candidate)["samples"][0]
        self.assertComplexClose(z(clean["voltage_rms_v"][1]), 5e-7, atol=0)
        def corrupt(params):
            raw = run_netlist(params)
            raw["data"]["node_voltage_v"]["x1"] += 1e-12
            return raw
        with patch("python.spike_core.solvers.execution.coupling.em_spice_coupling.run_netlist", side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, "Per-equation.*residual"):
                run_em_spice_coupling(candidate)

    def test_native_library_substitution_and_failed_execution_are_rejected(self):
        for mutation in ("library", "status"):
            def corrupt(params):
                raw = run_netlist(params)
                if mutation == "library":
                    raw["provenance"]["library"] = "untrusted.dll"
                else:
                    raw["status"] = "failed"
                return raw
            with patch("python.spike_core.solvers.execution.coupling.em_spice_coupling.run_netlist", side_effect=corrupt):
                with self.assertRaises(ValueError):
                    run_em_spice_coupling(request())

    def test_cancellation_before_and_after_actual_native_call_returns_no_partial_result(self):
        with patch("python.spike_core.solvers.execution.coupling.em_spice_coupling.run_netlist") as engine:
            with self.assertRaisesRegex(ValueError, "CANCELLED"):
                run_em_spice_coupling(request(), cancel_check=lambda: True)
            engine.assert_not_called()
        called = False
        def execute(params):
            nonlocal called
            raw = run_netlist(params)
            called = True
            return raw
        with patch("python.spike_core.solvers.execution.coupling.em_spice_coupling.run_netlist", side_effect=execute):
            with self.assertRaisesRegex(ValueError, "CANCELLED"):
                run_em_spice_coupling(request(), cancel_check=lambda: called)


if __name__ == "__main__":
    unittest.main()
