# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import unittest
from python.spike_core.openfoam_flow_diagnostics import render_flow_energy_objects


class FlowEnergyObjectsTests(unittest.TestCase):
    def test_fields_sign_cadence_and_scope(self):
        result = render_flow_energy_objects({"air": "fluid", "pcb": "solid"}, {"air": ["outlet", "inlet"]})
        text = result["dictionary_entries"]
        self.assertIn("fields (h K p);", text)
        self.assertIn("fields (h);", text)
        self.assertEqual(text.count("operation weightedSum;"), 2)
        self.assertEqual(text.count("weightField phi;"), 2)
        self.assertEqual(text.count("writeInterval 1;"), 6)
        self.assertNotIn("absWeighted", text)
        self.assertNotIn("coded", text)
        self.assertFalse(result["energy_qualification_complete"])

    def test_untrusted_names_and_shapes(self):
        for regions, patches in (({"a;code": "fluid"}, {}), ({"a": "fluid"}, {"a": ["x", "x"]}),
                ({"a": "solid"}, {"a": ["inlet"]}), ({"a": "fluid"}, {"a": [".*"]}),
                ({"a": "fluid"}, {"other": []}), ({}, {})):
            with self.assertRaises(ValueError):
                render_flow_energy_objects(regions, patches)

    def test_deterministic_order(self):
        a = render_flow_energy_objects({"b": "solid", "a": "fluid"}, {"a": ["y", "x"]})
        b = render_flow_energy_objects({"a": "fluid", "b": "solid"}, {"a": ["x", "y"]})
        self.assertEqual(a, b)

    def test_explicit_orthogonal_conduction_order_and_sign(self):
        result = render_flow_energy_objects({"air": "fluid"}, {"air": ["inlet"]}, orthogonal_constant_k=True)
        text = result["dictionary_entries"]
        self.assertLess(text.index("type grad;"), text.index("operation areaNormalIntegrate;"))
        self.assertIn("result spikeEnergyGradT;", text)
        self.assertEqual(text.count("writeControl none;"), 1)
        observation = result["observations"][-1]
        self.assertEqual(observation["power_multiplier"], "minus_region_conductivity_w_mk")
        self.assertEqual(observation["scalar_component"], 0)
        self.assertFalse(result["energy_qualification_complete"])
        with self.assertRaises(ValueError):
            render_flow_energy_objects({"air": "fluid"}, {}, orthogonal_constant_k="yes")
