# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
from pathlib import Path
import tempfile
import unittest
from python.spike_core.openfoam_pressure_work import pressure_work_policy
from python.spike_core.openfoam_multiregion import prepare_runnable_multiregion_case
from tests.python.test_openfoam_multiregion import materialize_runnable_request


class PressureWorkTests(unittest.TestCase):
    def test_legacy_default_and_explicit_models(self):
        materials=[{"phase":"fluid"}]
        self.assertEqual(pressure_work_policy({},materials,[0,0,0]),{})
        self.assertEqual(pressure_work_policy({"dpdt_enabled":False},materials,[0,0,0])["pressure_work_model"],"constant_density_no_dpdt")
        self.assertEqual(pressure_work_policy({"dpdt_enabled":True},materials,[0,0,0])["pressure_work_model"],"enthalpy_dpdt")

    def test_unsafe_or_ambiguous_policy_rejected(self):
        for environment,materials,gravity in (({"dpdt_enabled":0},[{"phase":"fluid"}],[0,0,0]),
            ({"dpdt_enabled":False},[{"phase":"fluid"}],[0,0,9.81]),
            ({"dpdt_enabled":False},[{"phase":"fluid","density_model":{"kind":"Boussinesq"}}],[0,0,0]),
            ({"dpdt_enabled":False},[{"phase":"solid"}],[0,0,0])):
            with self.subTest(environment=environment,materials=materials,gravity=gravity),self.assertRaises(ValueError):
                pressure_work_policy(environment,materials,gravity)

    def test_normal_case_api_renders_explicit_false(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            request=materialize_runnable_request(root/"mesh")
            request["environment"]["dpdt_enabled"]=False
            prepared=prepare_runnable_multiregion_case(request,root/"case",root/"mesh")
            self.assertEqual(prepared["status"],"prepared_runnable_case")
            self.assertEqual(prepared["manifest"]["environment"]["pressure_work_model"],"constant_density_no_dpdt")
            self.assertIn("dpdt false;",(root/"case/constant/air/thermophysicalProperties").read_text())


if __name__=="__main__":
    unittest.main()
