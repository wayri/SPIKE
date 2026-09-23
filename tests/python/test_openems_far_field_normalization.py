# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""One-watt normalization of pulse spectral far fields, without an engine."""
import ast
import math
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from python.spike_core.openems_adapter_source import OPENEMS_DRIVER


class FarFieldNormalizationTests(unittest.TestCase):
    def setUp(self):
        names = {"finite_array", "normalized_far_field"}
        parsed = ast.parse(OPENEMS_DRIVER)
        module = ast.Module(body=[node for node in parsed.body if isinstance(node, ast.FunctionDef)
                                  and node.name in names], type_ignores=[])
        scope = {"np": np, "math": math}
        exec(compile(module, "normalization-driver", "exec"), scope)
        self.normalize = scope["normalized_far_field"]
        self.request = {"shape": (2, 2, 2), "frequencies": np.array([1e9, 2e9]),
                        "theta": np.array([0, 90]), "phi": np.array([0, 180]),
                        "radius": 1., "center": np.zeros(3)}

    def evaluate(self, incident, impedance=50):
        incident = np.asarray(incident, dtype=complex)
        shape = self.request["shape"]
        field = np.ones(shape, dtype=complex)*(5+3j)/self.request["radius"]
        scale = incident.reshape((-1, 1, 1))/10
        raw = SimpleNamespace(freq=self.request["frequencies"], E_theta=field*scale,
                              E_phi=0*field, E_norm=np.abs(field*scale),
                              P_rad=np.ones(shape)*np.abs(scale)**2/(4*math.pi*self.request["radius"]**2),
                              Prad=np.abs(incident)**2/100, Dmax=np.ones(2))
        def transform(**kwargs):
            self.transform_arguments = kwargs
            return raw
        engine = SimpleNamespace(CalcNF2FF=transform)
        return self.normalize(engine, Path("unused"), self.request, 0, incident, impedance)

    def test_known_incident_power_and_phase_removed(self):
        incident = np.array([2e-12*np.exp(.7j), 4e-12*np.exp(-1.3j)])
        result = self.evaluate(incident)
        theta = result["e_field_v_m"]["theta"]
        np.testing.assert_allclose(theta["real"], 5, rtol=1e-14)
        np.testing.assert_allclose(theta["imag"], 3, rtol=1e-14)
        np.testing.assert_allclose(result["radiated_power"]["total_w"], 1, rtol=1e-14)
        np.testing.assert_allclose(result["directivity"]["linear"], 1, rtol=1e-14)
        self.assertEqual(result["normalization"]["incident_power_w"], 1.)
        self.assertEqual(result["normalization"]["incident_voltage_phase_deg"], 0.)

    def test_pulse_amplitude_and_phase_do_not_change_phasors(self):
        first = self.evaluate([2e-12, 3e-12])
        second = self.evaluate(np.array([2e-12, 3e-12])*7*np.exp(1.2j))
        for part in ("real", "imag"):
            np.testing.assert_allclose(first["e_field_v_m"]["theta"][part],
                                       second["e_field_v_m"]["theta"][part], rtol=1e-14)

    def test_radius_independent_intensity_and_si_phase_center(self):
        first = self.evaluate([2e-12, 3e-12])
        self.request["radius"] = 2.
        self.request["center"] = np.array([10., -20., .5])
        second = self.evaluate([2e-12, 3e-12])
        np.testing.assert_allclose(self.transform_arguments["center"], [.01, -.02, .0005])
        self.assertEqual(second["center_mm"], [10., -20., .5])
        self.assertEqual(second["radiated_power"]["angular_units"], "W/sr")
        np.testing.assert_allclose(first["radiated_power"]["angular_w"], second["radiated_power"]["angular_w"])
        np.testing.assert_allclose(first["directivity"]["linear"], second["directivity"]["linear"])
        np.testing.assert_allclose(np.array(first["e_field_v_m"]["magnitude"])/2,
                                   second["e_field_v_m"]["magnitude"])

    def test_bad_reference_and_incident_rejected(self):
        for value in (0, -1, math.nan, math.inf, True, "50", 10**1000):
            with self.subTest(reference=value), self.assertRaises(RuntimeError):
                self.evaluate([1e-12, 1e-12], value)
        for values in ([0, 1e-12], [1e-200, 1e-12], [1e-30, 1e-12], [math.nan, 1], [math.inf, 1]):
            with self.subTest(incident=values), self.assertRaises(RuntimeError):
                self.normalize(None, Path("unused"), self.request, 0, values, 50)
        for values in ([], [1e-12], [[1e-12, 1e-12]]):
            with self.assertRaises(RuntimeError):
                self.normalize(None, Path("unused"), self.request, 0, values, 50)


if __name__ == "__main__":
    unittest.main()
