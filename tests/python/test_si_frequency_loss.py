# SPDX-License-Identifier: Apache-2.0
import copy
import json
from pathlib import Path
import unittest
import numpy as np
from jsonschema import Draft202012Validator
from tests.python import test_si_channel as fixture_module
from python.spike_core.si_channel import extract_uniform_path_rlgc, uniform_rlgc_network, SiChannelError
from python.spike_core.si_coupled_channel import extract_coupled_path_rlgc, multiconductor_rlgc_network
from python.spike_core.si_frequency_loss import validate_loss_model, trace_impedance
from python.spike_core.ac_power_integrity import analyze_ac_power_integrity

class FrequencyLossTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.SiUniformChannelTests()

    def test_skin_reduces_high_frequency_transmission_and_preserves_dc(self):
        req = self.fixture.request()
        ext = extract_uniform_path_rlgc(self.fixture.design(), req)
        legacy = copy.deepcopy(ext)
        legacy["rlgc_per_m"].pop("conductor_loss")
        skin = uniform_rlgc_network(ext, req["frequencies_hz"], 50).parameters
        dc = uniform_rlgc_network(legacy, req["frequencies_hz"], 50).parameters
        np.testing.assert_allclose(skin[0], dc[0], rtol=1e-12, atol=1e-12)
        self.assertLess(abs(skin[-1,1,0]), abs(dc[-1,1,0]))
        self.assertLessEqual(np.linalg.svd(skin, compute_uv=False).max(), 1+1e-10)
        np.testing.assert_allclose(skin[:,0,1], skin[:,1,0], atol=1e-12)

    def test_roughness_preserves_dc_increases_real_loss_not_phase(self):
        req = self.fixture.request()
        smooth = extract_uniform_path_rlgc(self.fixture.design(), req)
        req["loss_model"] = {"roughness_model":"hammerstad", "rms_roughness_um":2}
        rough = extract_uniform_path_rlgc(self.fixture.design(), req)
        for f in (0, 200e6, 4e9):
            zs,zr = [trace_impedance(e,f,e["geometry"]["width_m"],e["rlgc_per_m"]["resistance_ohm_per_m"]) for e in (smooth,rough)]
            self.assertAlmostEqual(zs.imag,zr.imag)
            self.assertGreaterEqual(zr.real,zs.real)
            self.assertLessEqual(zr.real,2*zs.real)
        schema=json.loads((Path.cwd()/"schemas/si-uniform-channel-request-v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(req)

    def test_coupled_skin_passive_reciprocal(self):
        req=self.fixture.coupled_request()
        ext=extract_coupled_path_rlgc(self.fixture.coupled_design(),req)
        s=multiconductor_rlgc_network(ext,req["frequencies_hz"],50).parameters
        self.assertLessEqual(np.linalg.svd(s,compute_uv=False).max(),1+1e-9)
        np.testing.assert_allclose(s,np.transpose(s,(0,2,1)),atol=1e-10)

    def test_reject_ignored_loss_controls(self):
        for model in ({"rms_roughness_um":2},{"conductor":"dc","roughness_model":"hammerstad"},
                      {"rms_roughness_um":float("nan")},{"conductor":"proximity"},{"unknown":1},False):
            with self.assertRaises(ValueError): validate_loss_model(model)
            req=self.fixture.request();req["loss_model"]=model
            with self.assertRaises(SiChannelError): extract_uniform_path_rlgc(self.fixture.design(),req)

    def test_pi_internal_energy_opt_in_and_roughness(self):
        req={"contract":"spike/ac-pi-request/v1","frequencies_hz":[0,200e6,1e9],
             "length_m":.05,"R_ohm_per_m":0,"L_h_per_m":250e-9,"G_s_per_m":0,"C_f_per_m":100e-12,
             "source_impedance_ohm":[50,0],"load_impedance_ohm":[50,0],
             "conductor":{"width_m":.001,"thickness_m":35e-6,"conductivity_s_m":5.8e7}}
        old=analyze_ac_power_integrity(req)
        req["conductor"].update(include_internal_reactance=True,roughness_rms_um=2)
        new=analyze_ac_power_integrity(req)
        self.assertEqual(new["samples"][0]["internal_reactance_ohm_per_m"],0)
        self.assertGreater(new["samples"][-1]["internal_reactance_ohm_per_m"],0)
        self.assertGreater(new["samples"][-1]["R_ohm_per_m"],old["samples"][-1]["R_ohm_per_m"])
        req["conductor"]["field_bias_ratio"]=[1,0]
        with self.assertRaises(ValueError): analyze_ac_power_integrity(req)

if __name__ == "__main__": unittest.main()
