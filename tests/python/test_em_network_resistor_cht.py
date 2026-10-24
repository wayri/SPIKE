# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Independent circuit watts, volume deposition, retained-flow and failure checks."""
from copy import deepcopy
import json
import math
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core import em_network_resistor_cht as bridge
from tests.python import test_cfd_tetra_cht as cht_fixtures
from tests.python import test_em_network_cosimulation as ac_fixtures


def request(n=1, *, flowing=True):
    cht, geometry = cht_fixtures.affine_two_phase_request(n)
    cht["energy"]["source_w_m3"] = [0.] * len(geometry["cells"])
    for boundary in cht["energy"]["boundaries"].values():
        boundary["temperature_k"] = [300.] * len(boundary["temperature_k"])
    if not flowing:
        for boundary in cht["flow"]["boundary_conditions"].values():
            boundary["face_average_velocity_m_s"] = [[0., 0., 0.]] * len(boundary["face_average_velocity_m_s"])
    ac = ac_fixtures.request()
    ac["boundaries"][0]["p0"]["voltage_v"] = [20., 0.]
    solid = [i for i, material in enumerate(cht["energy"]["cell_material_ids"]) if material == "solid"]
    volume = math.fsum(float(geometry["cell_volumes"][i]) for i in solid)
    weights = {str(i): float(geometry["cell_volumes"][i])/volume for i in solid}
    raw = {"contract": bridge.REQUEST_CONTRACT, "ac_request": ac, "cht_request": cht,
           "sample_index": 0, "resistor_cell_weights": {"p0": weights}}
    # The authored mathematical fixture contains NumPy scalar face averages;
    # the bridge admits plain JSON, as supplied by a serialized worker client.
    return json.loads(json.dumps(raw, allow_nan=False)), geometry


class NetworkResistorChtTests(unittest.TestCase):
    def test_layered_exact_mean_temperature_refinement(self):
        from scripts.benchmark_em_network_cht import run_level
        for flowing in (False, True):
            errors = []
            for level in (1, 2, 4):
                _, _, row = run_level(level, flowing=flowing)
                errors.append(row["relative_rise_l2_error"])
                self.assertLessEqual(row["energy"]["cell_energy_relative_defect"], 1e-9)
                self.assertLessEqual(row["energy"]["global_energy_relative_defect"], 1e-9)
                self.assertLessEqual(row["energy"]["mixed_relative_residual"], 1e-10)
                if flowing:
                    self.assertGreater(row["maximum_face_mass_flow_kg_s"], 0.)
            self.assertLessEqual(errors[-1], .05)
            for a, b in zip(errors, errors[1:]):
                self.assertGreaterEqual(math.log(a/b, 2.), .8)

    def test_multiport_unequal_losses_and_nonuniform_cell_weights(self):
        raw, _ = request()
        ac = ac_fixtures.request([[[0., 0.]]*3 for _ in range(3)])
        for port, voltage, resistance in (("p0", 20., 50.), ("p1", 10., 25.), ("p2", 30., 50.)):
            ac["boundaries"][0][port] = {"voltage_v": [voltage, 0.], "impedance_ohm": [resistance, 0.]}
        raw["ac_request"] = ac
        solid = list(raw["resistor_cell_weights"]["p0"])
        first, second = solid[:2]
        raw["resistor_cell_weights"] = {"p0": {first: .25, second: .75}, "p1": {first: 1.}, "p2": None}
        result = bridge.run_em_network_resistor_cht(raw)
        expected = [0.] * len(result["cell_power_w"])
        expected[int(first)] = .25*2. + 25.*(10./75.)**2
        expected[int(second)] = .75*2.
        np.testing.assert_allclose(result["cell_power_w"], expected, rtol=1e-14, atol=0.)
        self.assertAlmostEqual(result["outside_series_resistor_power_w"], 4.5)
        self.assertAlmostEqual(result["cht"]["diagnostics"]["energy"]["generated_heat_w"], sum(expected))
        permuted = deepcopy(raw)
        permuted["ac_request"]["source"]["port_names"] = ["p2", "p0", "p1"]
        # The zero S matrix is unchanged by this permutation; named boundaries
        # and named heat destinations must produce the identical cell source.
        reordered = bridge.run_em_network_resistor_cht(permuted)
        np.testing.assert_allclose(reordered["cell_power_w"], expected, rtol=1e-14, atol=0.)

    def test_rms_circuit_watts_and_conservative_solid_heat_with_solved_flow(self):
        raw, geometry = request()
        original = deepcopy(raw)
        result = bridge.run_em_network_resistor_cht(raw)
        # Independent 20 V RMS source, external R=50 and matched network R=50.
        expected = 50. * (20./100.)**2
        self.assertAlmostEqual(result["deposited_series_resistor_power_w"], expected, places=13)
        self.assertAlmostEqual(result["unclassified_em_network_power_w"], expected, places=13)
        self.assertEqual(result["outside_series_resistor_power_w"], 0.)
        self.assertEqual(raw, original)
        self.assertFalse(result["production_qualified"])
        fields = result["cht"]["fields"]
        self.assertGreater(max(abs(f) for f in fields["face_mass_flow_kg_s"]), 0.)
        for material, power in zip(raw["cht_request"]["energy"]["cell_material_ids"], result["cell_power_w"]):
            self.assertEqual(power == 0., material == "fluid")
        energy = result["cht"]["diagnostics"]["energy"]
        self.assertAlmostEqual(energy["generated_heat_w"], expected, places=13)
        self.assertLessEqual(energy["cell_energy_relative_defect"], 1e-9)
        self.assertLessEqual(energy["global_energy_relative_defect"], 1e-9)
        self.assertGreater(max(fields["energy"]["temperature_k"]), 300.)

    def test_outside_resistor_does_not_deposit_network_deficit(self):
        raw, _ = request()
        raw["resistor_cell_weights"]["p0"] = None
        result = bridge.run_em_network_resistor_cht(raw)
        self.assertEqual(result["deposited_series_resistor_power_w"], 0.)
        self.assertAlmostEqual(result["outside_series_resistor_power_w"], 2.)
        self.assertAlmostEqual(result["unclassified_em_network_power_w"], 2.)
        self.assertTrue(all(p == 0. for p in result["cell_power_w"]))
        np.testing.assert_array_equal(result["cht"]["fields"]["energy"]["temperature_k"], 300.)

    def test_reactive_external_impedance_is_not_heat(self):
        raw, _ = request()
        raw["ac_request"]["boundaries"][0]["p0"]["impedance_ohm"] = [0., 50.]
        result = bridge.run_em_network_resistor_cht(raw)
        self.assertEqual(result["deposited_series_resistor_power_w"], 0.)
        self.assertGreater(result["unclassified_em_network_power_w"], 0.)

    def test_frequency_selection_not_sweep_power_sum(self):
        raw, _ = request()
        source = raw["ac_request"]["source"]
        source["frequencies_hz"].append(2e6)
        source["s_parameters"].append(deepcopy(source["s_parameters"][0]))
        boundary = deepcopy(raw["ac_request"]["boundaries"][0])
        boundary["p0"]["voltage_v"] = [40., 0.]
        raw["ac_request"]["boundaries"].append(boundary)
        raw["sample_index"] = 1
        result = bridge.run_em_network_resistor_cht(raw)
        self.assertEqual(result["frequency_hz"], 2e6)
        self.assertAlmostEqual(result["deposited_series_resistor_power_w"], 8.)

    def test_invalid_mappings_and_double_heat_fail_before_ac(self):
        raw, _ = request()
        fluid = raw["cht_request"]["energy"]["cell_material_ids"].index("fluid")
        mutations = [lambda r: r["resistor_cell_weights"].clear(),
                     lambda r: r["resistor_cell_weights"].update(p0={str(fluid): 1.}),
                     lambda r: r["resistor_cell_weights"].update(p0={"0": .9}),
                     lambda r: r["resistor_cell_weights"].update(p0={"00": 1.}),
                     lambda r: r["resistor_cell_weights"].update(p0={"-1": 1.}),
                     lambda r: r["resistor_cell_weights"].update(p0={"0": float("nan")}),
                     lambda r: r.update(sample_index=True),
                     lambda r: r["cht_request"]["energy"]["source_w_m3"].__setitem__(0, 1.)]
        for mutate in mutations:
            candidate = deepcopy(raw)
            mutate(candidate)
            with self.subTest(mutate=mutate), patch.object(bridge, "solve_em_network_ac") as ac:
                with self.assertRaises(ValueError):
                    bridge.run_em_network_resistor_cht(candidate)
                ac.assert_not_called()

    def test_cancel_and_failed_cht_never_publish_partial_result(self):
        raw, _ = request()
        with self.assertRaisesRegex(ValueError, "CANCELLED"):
            bridge.run_em_network_resistor_cht(raw, cancel_check=lambda: True)
        with patch.object(bridge, "solve_cfd_tetra_cht", return_value={"status": "blocked", "issues": []}):
            with self.assertRaisesRegex(ValueError, "CHT stage did not complete"):
                bridge.run_em_network_resistor_cht(raw)
        with patch.object(bridge, "solve_cfd_tetra_cht", return_value={"status": "cancelled"}):
            with self.assertRaisesRegex(ValueError, "CANCELLED"):
                bridge.run_em_network_resistor_cht(raw)

    def test_cancellation_after_ac_and_after_cht_does_not_publish(self):
        raw, _ = request()
        for stage in ("solve_em_network_ac", "solve_cfd_tetra_cht"):
            cancelled = False
            original = getattr(bridge, stage)
            def finish_then_cancel(*args, **kwargs):
                nonlocal cancelled
                result = original(*args, **kwargs)
                cancelled = True
                return result
            with self.subTest(stage=stage), patch.object(bridge, stage, side_effect=finish_then_cancel):
                with self.assertRaisesRegex(ValueError, "CANCELLED"):
                    bridge.run_em_network_resistor_cht(raw, cancel_check=lambda: cancelled)

    def test_structural_json_budgets_before_encoding(self):
        for malformed in ({"x": "x" * (bridge._REQUEST_BYTES+1)}, {"x": 1 << 2048}):
            with self.assertRaisesRegex(ValueError, "budget"):
                bridge._snapshot(malformed)
        cyclic = []
        cyclic.append(cyclic)
        with self.assertRaisesRegex(ValueError, "structure"):
            bridge._snapshot(cyclic)

    def test_retained_mesh_admitted_once_and_private_ticket_not_forgeable(self):
        from python.spike_core import cfd_tetra_cht
        raw, _ = request()
        with patch.object(bridge, "_admit_with_reuse", wraps=bridge._admit_with_reuse) as admit:
            with patch.object(cfd_tetra_cht, "_admit_with_reuse", wraps=cfd_tetra_cht._admit_with_reuse) as child:
                bridge.run_em_network_resistor_cht(raw)
        self.assertEqual(admit.call_count, 1)
        self.assertEqual(child.call_count, 1)  # Distinct fluid-only submesh.
        result = cfd_tetra_cht.solve_cfd_tetra_cht(raw["cht_request"], _mesh_reuse={})
        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("fields", result)


if __name__ == "__main__":
    unittest.main()
