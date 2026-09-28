# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import copy
import json
from pathlib import Path
import unittest
import numpy as np
from python.spike_core.actuator_force_map import CONTRACT, analyze_force_map


def fixture(kind="reluctance", count=65):
    x = np.linspace(0, 0.001, count)
    # Original conservative oracles, not measured or arbitrary-geometry fields.
    if kind == "permanent_magnet":
        # Uniform B=0.5T, active length=0.2m, I=2A: Lorentz F=B*l*I.
        force = np.full_like(x, 0.2)
        energy = 0.2 * x
    elif kind == "electrostatic":
        # Ideal parallel plate closing displacement; C=eps*A/(g-x).
        eps, area, gap, voltage = 8.8541878128e-12, 1e-4, 0.004, 100
        energy = 0.5 * eps * area * voltage**2 / (gap - x)
        force = 0.5 * eps * area * voltage**2 / (gap - x)**2
    else:
        # Linear-core magnetic gap: W'=mu0*A*(NI)^2/(2*(g-x)).
        coefficient = 0.5 * (4e-7 * np.pi) * 1e-4 * (100 * 2)**2
        energy = coefficient / (0.004 - x)
        force = coefficient / (0.004 - x)**2
    return {"contract": CONTRACT, "kind": kind, "position_m": x.tolist(),
            "force_n": force.tolist(), "coenergy_j": energy.tolist(),
            "fixed_excitation": {"voltage_v": 100} if kind == "electrostatic" else {"current_a": 2},
            "provenance": "Original ideal analytical test, not hardware measurement",
            "relative_tolerance": 1e-3, "absolute_force_tolerance_n": 1e-12}


class ActuatorForceMapTests(unittest.TestCase):
    def test_examples_conform_and_execute(self):
        import jsonschema
        root = Path(__file__).resolve().parents[2]
        schema = json.loads((root / "schemas/actuator-force-map-v1.schema.json").read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        examples = sorted((root / "examples/actuator").glob("*-force-map.json"))
        self.assertEqual(len(examples), 3)
        for path in examples:
            request = json.loads(path.read_text())
            jsonschema.validate(request, schema)
            self.assertEqual(analyze_force_map(request)["status"], "consistent")

    def test_all_three_analytical_families(self):
        for kind in ("reluctance", "permanent_magnet", "electrostatic"):
            with self.subTest(kind=kind):
                result = analyze_force_map(fixture(kind))
                self.assertEqual(result["status"], "consistent")
                self.assertFalse(result["production_qualified"])

    def test_gradient_second_order_stroke_convergence(self):
        for kind in ("reluctance", "electrostatic"):
            errors = [analyze_force_map(fixture(kind, n))["checks"]["coenergy_gradient"]["maximum_error_n"]
                      for n in (17, 33, 65, 129)]
            for coarse, fine in zip(errors, errors[1:]):
                self.assertGreater(coarse / fine, 3.8)

    def test_reversed_force_is_rejected(self):
        request = fixture()
        request["force_n"] = [-f for f in request["force_n"]]
        self.assertEqual(analyze_force_map(request)["status"], "inconsistent")

    def test_constant_coenergy_offset_has_no_force(self):
        request = fixture("permanent_magnet")
        request["coenergy_j"] = [v + 0.001 for v in request["coenergy_j"]]
        self.assertEqual(analyze_force_map(request)["status"], "consistent")

    def test_input_admission(self):
        for key, value in (("position_m", [0]*65), ("coenergy_j", [float("nan")]*65),
                           ("fixed_excitation", {"voltage_v": 2}), ("force_n", [1]*4),
                           ("relative_tolerance", 1), ("moving_mass_kg", 0), ("unknown", 1)):
            request = copy.deepcopy(fixture())
            request[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                analyze_force_map(request)

    def test_nonuniform_quadratic_derivative(self):
        request = fixture("permanent_magnet")
        x = np.linspace(0, 1, 65)**2
        request.update(position_m=x.tolist(), coenergy_j=(x*x).tolist(), force_n=(2*x).tolist())
        result = analyze_force_map(request)
        self.assertEqual(result["status"], "consistent")
        np.testing.assert_allclose(result["coenergy_gradient_n"], 2*x, atol=1e-12)

    def test_extreme_and_unhashable_inputs_fail_cleanly(self):
        for key, value in (("kind", []), ("fixed_excitation", {"current_a": 10**400})):
            request = fixture()
            request[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                analyze_force_map(request)

    def test_nonfinite_derived_force_per_mass_is_rejected(self):
        request = fixture("permanent_magnet", 5)
        request.update(force_n=[1e300]*5,
                       coenergy_j=[1e300*x for x in request["position_m"]], moving_mass_kg=1e-12)
        with self.assertRaisesRegex(ValueError, "numerical range"):
            analyze_force_map(request)
