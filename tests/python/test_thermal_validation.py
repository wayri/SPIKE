import unittest

from python.spike_core.thermal_validation import (
    Layer,
    assess_mesh_convergence,
    electrothermal_fixed_point_reference,
    layered_conduction_reference,
)


class ThermalValidationTests(unittest.TestCase):
    def test_layered_conduction_includes_contact_and_conserves_energy(self):
        report = layered_conduction_reference(
            layers=[Layer(0.001, 200), Layer(0.002, 2)], area_m2=1e-4,
            contact_resistances_k_per_w=[0.5], heat_w=3, cold_temperature_k=300,
        )
        self.assertAlmostEqual(report["total_resistance_k_per_w"], 10.55)
        self.assertAlmostEqual(report["hot_temperature_k"], 331.65)
        self.assertTrue(report["conservation"]["passed"])
        self.assertLess(report["conservation"]["relative_residual"], 1e-12)

    def test_mesh_convergence_requires_three_refining_levels_and_uses_finest_pair(self):
        report = assess_mesh_convergence([
            {"cells": 100, "hot_temperature_k": 330.0},
            {"cells": 400, "hot_temperature_k": 331.0},
            {"cells": 1600, "hot_temperature_k": 331.2},
        ], relative_tolerance=0.001)
        self.assertTrue(report["passed"])
        self.assertAlmostEqual(report["finest_relative_change"], 0.2 / 331.2)
        with self.assertRaises(ValueError):
            assess_mesh_convergence([{"cells": 1, "hot_temperature_k": 1}, {"cells": 2, "hot_temperature_k": 1}])

    def test_electrothermal_fixed_point_has_exact_reference_and_explicit_residual(self):
        report = electrothermal_fixed_point_reference(
            voltage_v=12, resistance_at_ambient_ohm=4, temperature_coefficient_per_k=0.004,
            thermal_resistance_k_per_w=3, relaxation=0.5,
        )
        self.assertEqual(report["status"], "converged")
        self.assertLess(report["relative_temperature_error"], 1e-8)
        self.assertLess(report["electrothermal_balance_residual_w"], 1e-6)
        self.assertGreater(report["iterations"], 1)


if __name__ == "__main__":
    unittest.main()
