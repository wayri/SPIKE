import copy
import json
from pathlib import Path
import unittest

import numpy as np

from python.spike_core.si_ibis import parse_ibis, reduce_ibis
from python.spike_core.si_network_workflow import line_network, edit_network
from python.spike_core.si_passives import KB, resolve_passive, resistor_noise
from python.spike_core.si_workflow import REQUEST, run_si_workflow, workflow_catalog
from python.spike_core.sparameters import NetworkData, parse_touchstone_text, touchstone_text


IBIS = """[IBIS Ver] 4.2
[File Name] fixture.ibs
[Component] CHIP
[Package]
R_pkg 0.1 0.08 0.12
L_pkg 1nH 0.8nH 1.2nH
C_pkg 0.2pF 0.1pF 0.3pF
[Pin] signal_name model_name R_pin L_pin C_pin
1 TX SELECT NA NA NA
2 RX input NA NA NA
[Model Selector] SELECT
output A simple source
[Model] output
Model_type Output
C_comp 2pF 1pF 3pF
[Voltage Range] 1.8 1.7 1.9
[Pulldown]
0 0 0 0
1 0.02 0.01 0.04
2 0.04 0.02 0.08
[Pullup]
0 0 0 0
1 -0.02 -0.01 -0.04
2 -0.04 -0.02 -0.08
[Ramp]
dV/dt_r 1.08/60p 1.02/70p 1.14/50p
dV/dt_f 1.08/60p 1.02/70p 1.14/50p
R_load = 50
[Rising Waveform]
R_fixture = 50
V_fixture = 0
0 0 0 0
1n 1.8 1.7 1.9
[Model] input
Model_type Input
Vinl = 0.5
Vinh = 1.2
C_comp 2p 1p 3p
[End]
"""


def through_request(points=129, stop=8e9):
    frequencies = np.linspace(0, stop, points)
    s = np.tile(np.array([[0, 1], [1, 0]], dtype=complex), (points, 1, 1))
    return {"contract": REQUEST, "channel": {"kind": "touchstone", "name": "through.s2p",
            "text": touchstone_text(frequencies, s)}, "sources": [{"port": 0, "rise_time_s": 0, "fall_time_s": 0}],
            "receivers": [{"port": 1, "capacitance_f": 0, "resistance_ohm": 50}], "run_time_domain": False}


def transfer(result, port=1):
    trace = next(t["trace"] for t in result["loaded_transfers"] if t["observed_port"] == port)
    return np.array([p["real"] + 1j * p["imag"] for p in trace])


class SiWorkflowTests(unittest.TestCase):
    def test_default_study_completes_with_portable_finite_result(self):
        r = run_si_workflow({"contract": REQUEST})
        self.assertEqual(r["time_domain"]["status"], "completed")
        self.assertEqual(r["network"]["port_count"], 4)
        self.assertEqual(r["network"]["checks"]["passivity"]["status"], "pass")
        self.assertFalse(r["production_qualified"])
        json.dumps(r, allow_nan=False)
        self.assertEqual(parse_touchstone_text(r["touchstone"]["text"], "channel.s4p").port_count, 4)

    def test_ideal_through_loading_and_thermal_noise(self):
        request = through_request()
        result = run_si_workflow(request)
        np.testing.assert_allclose(transfer(result), 0.5, atol=1e-12)
        expected = np.sqrt(4 * KB * 298.15 * 25 * 8e9)
        self.assertAlmostEqual(result["noise"]["thermal_rms_v_by_port"][1], expected, places=12)

    def test_shunt_capacitor_matches_analytic_rc_transfer(self):
        request = through_request()
        request["passives"] = [{"port": 1, "connection": "shunt", "model": {"kind": "capacitor", "grade": "C0G", "capacitance_f": 2e-12,
                                "esr_ohm": 0, "esl_h": 0, "leakage_ohm": 1e15}}]
        result = run_si_workflow(request)
        f = np.linspace(0, 8e9, 129)
        expected = 1 / (2 + 2j * np.pi * f * 50 * 2e-12)
        np.testing.assert_allclose(transfer(result), expected, atol=1e-12)

    def test_series_resistor_tolerance_changes_loaded_voltage(self):
        request = through_request()
        request["passives"] = [{"port": 0, "connection": "series", "model": {"resistance_ohm": 100, "inductance_h": 0,
                                "capacitance_f": 0, "tolerance_fraction": 0.1, "corner": "max"}}]
        result = run_si_workflow(request)
        np.testing.assert_allclose(transfer(result), 50 / 210, atol=1e-12)

    def test_capacitor_grade_envelope_and_bias_are_independent(self):
        a = resolve_passive({"kind": "capacitor", "grade": "X7R", "corner": "min", "bias_factor": 0.5})
        b = resolve_passive({"kind": "capacitor", "grade": "Y5V", "corner": "min", "bias_factor": 0.5})
        self.assertAlmostEqual(a["effective"]["capacitance_f"], 1e-7 * 0.9 * 0.85 * 0.5)
        self.assertAlmostEqual(b["effective"]["capacitance_f"], 1e-7 * 0.9 * 0.18 * 0.5)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            resolve_passive({"kind": "capacitor", "grade": "Y5"})
        with self.assertRaisesRegex(ValueError, "temperature"):
            resolve_passive({"kind": "capacitor", "grade": "X5R", "temperature_c": 100})

    def test_resistor_technology_changes_excess_not_johnson_noise(self):
        thick = resistor_noise(resolve_passive({"grade": "thick_film", "dc_voltage_v": 1}), 10, 1000)
        thin = resistor_noise(resolve_passive({"grade": "thin_film", "dc_voltage_v": 1}), 10, 1000)
        self.assertAlmostEqual(thick["thermal_rms_v"], thin["thermal_rms_v"])
        self.assertAlmostEqual(thick["excess_rms_v"] / thin["excess_rms_v"], 10)

    def test_uncoupled_line_has_no_cross_transfer(self):
        line = line_network({"coupled": True, "inductive_coupling": 0, "capacitive_coupling": 0, "frequency_points": 33})
        np.testing.assert_allclose(line.parameters[:, 1, 0], 0, atol=1e-14)
        np.testing.assert_allclose(line.parameters[:, 3, 0], 0, atol=1e-14)
        coupled = line_network({"coupled": True, "inductive_coupling": 0.2, "capacitive_coupling": 0.05, "frequency_points": 33})
        self.assertGreater(np.max(np.abs(coupled.parameters[:, 1, 0])), 0.01)
        self.assertGreater(np.max(np.abs(coupled.parameters[:, 3, 0])), 0.01)

    def test_lossless_line_admits_dc_and_renormalization(self):
        line = line_network({"coupled": False, "resistance_ohm_per_m": 0, "loss_tangent": 0, "frequency_points": 33})
        np.testing.assert_allclose(line.parameters[0], [[0, 1], [1, 0]], atol=1e-14)
        changed, _ = edit_network(line, [{"kind": "renormalize", "reference_impedance_ohm": 75},
                                       {"kind": "renormalize", "reference_impedance_ohm": 50}])
        np.testing.assert_allclose(line.parameters, changed.parameters, atol=1e-12)

    def test_port_extensions_and_reorder_are_exact(self):
        line = line_network({"coupled": False, "frequency_points": 33})
        changed, _ = edit_network(line, [{"kind": "port_extension", "delay_s": [1e-9, 2e-9]}])
        np.testing.assert_allclose(changed.parameters[:, 1, 0], line.parameters[:, 1, 0] * np.exp(-2j * np.pi * line.frequencies_hz * 3e-9), atol=1e-12)
        changed, _ = edit_network(line, [{"kind": "reorder", "ports": [1, 0]}])
        np.testing.assert_allclose(changed.parameters, line.parameters[:, ::-1, ::-1])
        with self.assertRaises(ValueError):
            edit_network(line, [{"kind": "reorder", "ports": [True, 0]}])

    def test_cascaded_matched_attenuators_multiply(self):
        f = [0, 1e9, 2e9]
        s = np.tile([[0, 0.5], [0.5, 0]], (3, 1, 1)).astype(complex)
        network = NetworkData(np.array(f), s, np.array([50, 50]))
        changed, _ = edit_network(network, [{"kind": "cascade", "channel": {"kind": "touchstone", "name": "attenuator.s2p", "text": touchstone_text(f, s)}}])
        np.testing.assert_allclose(changed.parameters[:, 1, 0], 0.25)

    def test_frequency_only_import_survives_time_domain_block(self):
        request = through_request()
        request["channel"]["text"] = touchstone_text([1e6, 2e6, 4e6], np.tile([[0, 1], [1, 0]], (3, 1, 1)))
        request["run_time_domain"] = True
        r = run_si_workflow(request)
        self.assertEqual(r["time_domain"]["status"], "blocked")
        self.assertTrue(r["touchstone"]["text"])

    def test_four_port_standard_order_does_not_transpose_nonreciprocal_data(self):
        # Hand-authored row-major record, intentionally not writer-generated.
        text = "# Hz S RI R 50\n0 " + " ".join(f"{n} 0" for n in range(16)) + "\n"
        network = parse_touchstone_text(text, "known.s4p")
        self.assertEqual(network.parameters[0, 0, 1], 1)
        self.assertEqual(network.parameters[0, 1, 0], 4)
        exported = touchstone_text([0], network.parameters)
        tokens = " ".join(exported.splitlines()[1:]).split()
        self.assertEqual([float(t) for t in tokens[1::2]], list(range(16)))

    def test_touchstone_v2_two_port_order(self):
        text = "[Version] 2.0\n[Number of Ports] 2\n[Two-Port Data Order] 12_21\n# Hz S RI R 50\n[Network Data]\n0 0 0 0.2 0 0.8 0 0 0\n[End]\n"
        network = parse_touchstone_text(text, "test.s2p")
        self.assertEqual(network.parameters[0, 1, 0], 0.8)

    def test_ibis_inventory_and_selected_corner_pin_package(self):
        inventory = parse_ibis(IBIS)
        self.assertEqual(len(inventory["models"]["output"]["waveforms"]), 1)
        binding = {"model": "output", "component": "CHIP", "pin": "1", "corner": "min", "operating_voltage_v": 0.9}
        reduction = reduce_ibis(inventory, binding, "source")
        self.assertAlmostEqual(reduction["values"]["resistance_ohm"], 100)
        self.assertAlmostEqual(reduction["values"]["package_l_h"], 0.8e-9)
        binding["state"] = "high"
        self.assertAlmostEqual(reduce_ibis(inventory, binding, "source")["values"]["resistance_ohm"], 100)
        binding["pin"] = "2"
        with self.assertRaisesRegex(ValueError, "not assigned"):
            reduce_ibis(inventory, binding, "source")

    def test_ibis_binding_changes_loaded_response(self):
        request = through_request()
        request["sources"] = [{"port": 0, "ibis": {"text": IBIS, "model": "output", "corner": "min"}}]
        result = run_si_workflow(request)
        self.assertAlmostEqual(transfer(result)[0].real, 1 / 3)
        self.assertEqual(result["ibis"][0]["corner"], "min")

    def test_receiver_ibis_scalar_thresholds_apply_at_every_corner(self):
        reduced = reduce_ibis(parse_ibis(IBIS), {"model": "input", "corner": "min"}, "receiver")
        self.assertEqual(reduced["values"]["vil_v"], 0.5)
        self.assertEqual(reduced["values"]["vih_v"], 1.2)
        self.assertEqual(reduced["values"]["capacitance_f"], 1e-12)

    def test_resistor_excess_noise_is_propagated_to_ports(self):
        request = through_request()
        request["passives"] = [{"port": 0, "connection": "series", "model": {"resistance_ohm": 50,
                                "dc_voltage_v": 1, "grade": "thick_film", "inductance_h": 0, "capacitance_f": 0}}]
        a = run_si_workflow(request)
        request["passives"][0]["model"]["grade"] = "thin_film"
        b = run_si_workflow(request)
        self.assertGreater(a["noise"]["excess_rms_v_by_port"][1], 0)
        self.assertAlmostEqual(a["noise"]["excess_rms_v_by_port"][1] / b["noise"]["excess_rms_v_by_port"][1], 10)

    def test_receiver_waveform_measures_after_package_series_resistance(self):
        request = through_request()
        request["run_time_domain"] = True
        request["receivers"][0]["package_r_ohm"] = 100
        r = run_si_workflow(request)
        self.assertEqual(r["time_domain"]["status"], "completed")
        # Source 50 + package 100 + receiver 50: die swing is 1.8 * 50/200.
        self.assertAlmostEqual(r["time_domain"]["receivers"][0]["eye_height_v"], 0.45, places=8)

    def test_published_schema_validates_defaults_and_results(self):
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        root = Path(__file__).resolve().parents[2]
        documents = [json.loads(p.read_text()) for p in (root / "schemas").glob("si-*.schema.json")]
        registry = Registry().with_resources((doc["$id"], Resource.from_contents(doc)) for doc in documents)
        request_schema = json.loads((root / "schemas/si-workflow-request-v1.schema.json").read_text())
        result_schema = json.loads((root / "schemas/si-workflow-result-v1.schema.json").read_text())
        Draft202012Validator.check_schema(request_schema)
        Draft202012Validator(request_schema, registry=registry).validate(workflow_catalog()["defaults"])
        Draft202012Validator(result_schema, registry=registry).validate(run_si_workflow(through_request()))

    def test_ibis_unknown_electrical_extensions_block_reduction(self):
        inventory = parse_ibis(IBIS.replace("[End]", "[External Model]\n[End]"))
        with self.assertRaisesRegex(ValueError, "keywords"):
            reduce_ibis(inventory, {"model": "output"}, "source")

    def test_duplicates_unknown_fields_and_nonfinite_are_rejected(self):
        request = through_request()
        for patch in [{"surprise": 1}, {"bit_count": True}, {"temperature_c": float("nan")},
                      {"sources": [{"port": 1}], "receivers": [{"port": 1}]}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                run_si_workflow({**request, **patch})

    def test_portable_catalog_matches_worker_authority(self):
        catalog_path = Path(__file__).resolve().parents[2] / "app/src/siWorkflowCatalog.json"
        self.assertEqual(json.loads(catalog_path.read_text()), workflow_catalog())

    def test_worker_service_reports_invalid_request(self):
        from python.spike_core.service import handle
        response = handle({"method": "run_si_workflow", "params": {"request": {"contract": "wrong"}}})
        self.assertFalse(response["ok"])
        self.assertIn("Expected", response["error"])


if __name__ == "__main__":
    unittest.main()
