# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Independent lossy-Maxwell plane-wave / Poynting and conduction oracles."""
import cmath
from copy import deepcopy
import math
from types import SimpleNamespace
import unittest

import numpy as np

from extensions.emerge_suite.volume_capture import capture_volume_fields
from python.spike_core.solvers.execution.coupling.em_body_heating import CONTRACT, field_quadrature, run_em_body_heating
from python.spike_core.solvers.execution.coupling.em_network_ac import _digest
from tests.python.test_assembly_tetra_thermal import cube, request as heat_request
from tests.python.test_em_network_cosimulation import request as ac_request

SIGMA, EPSILON, MU = .001, 4*8.8541878128e-12, 4e-7*math.pi


class PlaneWave:
    def __init__(self, frequency, amplitude=1+0j):
        self.gamma = cmath.sqrt(1j*2*math.pi*frequency*MU*(SIGMA+1j*2*math.pi*frequency*EPSILON))
        self.impedance = 1j*2*math.pi*frequency*MU/self.gamma
        self.amplitude = amplitude

    def interpolate(self, x, y, z, *, usenan):
        e = self.amplitude*np.exp(-self.gamma*x)
        zero = np.zeros_like(e)
        return SimpleNamespace(Ex=zero, Ey=e, Ez=zero, Hx=zero, Hy=zero, Hz=e/self.impedance)


def request(n=1, frequency=300e6, amplitude=1+0j):
    heat = heat_request(cube(n))
    for boundary in heat["boundaries"]:
        boundary["temperature_k"] = 300.
    ac = ac_request(); ac["source"]["frequencies_hz"] = [frequency]
    wave = PlaneWave(frequency, amplitude)
    rule = field_quadrature(heat)
    port = [key for key, value in rule["boundary_faces"].items()
            if all(abs(p[0]) < 1e-12 for p in value["points_m"])]
    loss = {"k": {"conductivity_s_m": SIGMA, "permittivity_f_m": EPSILON, "loss_tangent": 0.}}
    fields = capture_volume_fields(wave, heat, frequency_hz=frequency, loss_materials=loss,
        ac_source=ac["source"], port_faces=port, solver_run_digest="a"*64)
    return {"contract": CONTRACT, "ac_request": ac, "thermal_request": heat,
        "loss_materials": loss, "port_faces": port, "field_samples": fields,
        "source_binding": {"mesh_digest": _digest(heat["mesh"]), "ac_request_digest": _digest(ac),
            "solver_run_digest": "a"*64, "field_samples_digest": _digest(fields)}}, wave


class EMBodyHeatingTests(unittest.TestCase):
    def test_maxwell_loss_and_escaping_power_at_300mhz_1ghz_3ghz(self):
        for frequency in (300e6, 1e9, 3e9):
            with self.subTest(frequency=frequency):
                raw, wave = request(frequency=frequency)
                before = deepcopy(raw)
                result = run_em_body_heating(raw)
                attenuation = 2*wave.gamma.real
                exact = .02*(-math.expm1(-attenuation))
                self.assertAlmostEqual(result["deposited_body_power_w"]/exact, 1., places=10)
                self.assertAlmostEqual(result["nonport_outward_power_w"]/.02, math.exp(-attenuation), places=10)
                self.assertAlmostEqual(result["thermal"]["heat_balance"]["source_w"], exact, places=12)
                self.assertLess(result["raw_balance_error"], 1e-10)
                self.assertLess(result["deposited_body_power_w"], .02)  # escaping EM power is not heat
                self.assertEqual(raw, before)

    def test_power_calibration_removes_unknown_common_complex_field_scale(self):
        first, _ = request(amplitude=1+0j)
        second, _ = request(amplitude=3+4j)
        a, b = run_em_body_heating(first), run_em_body_heating(second)
        self.assertAlmostEqual(a["field_power_scale"]/b["field_power_scale"], 25., places=10)
        self.assertAlmostEqual(a["deposited_body_power_w"], b["deposited_body_power_w"], places=12)

    def test_thermal_temperature_refinement(self):
        errors = []
        for n in (1, 2, 3, 4):
            raw, wave = request(n=n)
            out = run_em_body_heating(raw)
            xyz = np.array(raw["thermal_request"]["mesh"]["vertices"])
            temperatures = np.array(out["thermal"]["node_temperatures_k"])
            alpha = 2*wave.gamma.real
            q0 = .02*SIGMA/(1/wave.impedance).real
            total = 0.
            for cell, rule in zip(raw["thermal_request"]["mesh"]["cells"], field_quadrature(raw["thermal_request"])["cells"].values()):
                vertices = xyz[cell["vertices"]]
                inverse = np.linalg.inv(np.vstack([vertices.T, np.ones(4)]))
                points = np.array(rule["points_m"])
                bary = (inverse@np.vstack([points.T, np.ones(len(points))])).T
                numerical = bary@temperatures[cell["vertices"]]
                exact = 300+q0/(2*alpha**2)*(-np.expm1(-alpha*points[:, 0])+points[:, 0]*math.expm1(-alpha))
                total += np.dot(rule["weights_m3"], (numerical-exact)**2)
            errors.append(math.sqrt(total))
        for n, (a, b) in enumerate(zip(errors, errors[1:]), 1):
            self.assertGreater(math.log(a/b)/math.log((n+1)/n), 1.7)

    def test_bad_calibration_missing_fields_and_double_heat_fail(self):
        for change in ("stale", "field", "material", "missing", "heat"):
            raw, _ = request()
            if change == "stale": raw["source_binding"]["mesh_digest"] = "f"*64
            if change == "field":
                for values in raw["field_samples"]["cells"].values():
                    for vector in values:
                        vector[1][0] *= 2; vector[1][1] *= 2
                # A fresh packet digest must not substitute for physical closure.
                raw["source_binding"]["field_samples_digest"] = _digest(raw["field_samples"])
            if change == "material": raw["loss_materials"]["k"]["conductivity_s_m"] *= 2
            if change == "missing": raw["field_samples"]["boundary_faces"].pop(next(iter(raw["field_samples"]["boundary_faces"])))
            if change == "heat": raw["thermal_request"]["heat_sources_w_m3"] = {"solid-0": 1}
            pattern = "Raw Poynting" if change == "field" else ".*"
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, pattern):
                run_em_body_heating(raw)
        raw, _ = request()
        with self.assertRaisesRegex(ValueError, "CANCELLED"):
            run_em_body_heating(raw, cancel_check=lambda: True)

    def test_stale_frequency_material_port_network_and_packet_rejected(self):
        for mutation in ("frequency", "material", "port", "network", "packet"):
            raw, _ = request()
            if mutation == "frequency": raw["ac_request"]["source"]["frequencies_hz"] = [3e9]
            if mutation == "material": raw["loss_materials"]["k"]["conductivity_s_m"] *= 2
            if mutation == "port": raw["port_faces"] = raw["port_faces"][:1]
            if mutation == "network": raw["ac_request"]["source"]["id"] = "another-run"
            if mutation == "packet": next(iter(raw["field_samples"]["cells"].values()))[0][1][0] *= 2
            raw["source_binding"]["ac_request_digest"] = _digest(raw["ac_request"])
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "context mismatch|packet digest"):
                run_em_body_heating(raw)


if __name__ == "__main__":
    unittest.main()
