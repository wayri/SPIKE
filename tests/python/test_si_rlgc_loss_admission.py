# SPDX-License-Identifier: Apache-2.0
"""Supplied RLGC remains geometry-independent unless skin loss is selected."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np

from scripts.benchmark_si_crosstalk import independent_modal_s, line_fixture
from python.spike_core.si_channel import SiChannelError
from python.spike_core.si_coupled_channel import multiconductor_rlgc_network


class SiRlgcLossAdmissionTests(unittest.TestCase):
    def test_supplied_constant_matrices_need_no_widths_or_slab_call(self):
        for model in (None, {"conductor": "dc"}):
            extraction = line_fixture()
            if model is not None:
                extraction["rlgc_per_m"]["conductor_loss"] = model
            original = deepcopy(extraction)
            frequencies = [0., 5e8, 1e9]
            with patch("python.spike_core.si_coupled_channel.trace_impedance",
                       side_effect=AssertionError("No geometric loss is authorized")):
                network = multiconductor_rlgc_network(extraction, frequencies, 50.)
            np.testing.assert_allclose(network.s_parameters(), independent_modal_s(extraction, frequencies),
                                       rtol=1e-10, atol=1e-11)
            self.assertEqual(extraction, original)
            self.assertIn("constant-R", network.warnings[0])

    def test_selected_skin_with_missing_parameters_is_structured_error(self):
        extraction = line_fixture()
        extraction["rlgc_per_m"]["conductor_loss"] = {"conductor": "slab_skin"}
        extraction["geometry"].update(signal_width_m=.0002, victim_width_m=.0002)
        extraction["rlgc_per_m"].update(conductor_thickness_m=35e-6, conductivity_s_per_m=5.8e7)
        for owner, key in (("geometry", "signal_width_m"), ("geometry", "victim_width_m"),
                           ("rlgc_per_m", "conductor_thickness_m"), ("rlgc_per_m", "conductivity_s_per_m")):
            for value in (None, True, -1., float("nan"), "0.001"):
                altered = deepcopy(extraction)
                if value is None:
                    altered[owner].pop(key)
                else:
                    altered[owner][key] = value
                with self.subTest(key=key, value=value), self.assertRaisesRegex(SiChannelError, "conductor-loss"):
                    multiconductor_rlgc_network(altered, [0., 5e8, 1e9], 50.)

    def test_unknown_loss_model_does_not_silently_fall_back_to_dc(self):
        for model in ({"conductor": "unknown"}, {"unexpected": 1}, False):
            extraction = line_fixture()
            extraction["rlgc_per_m"]["conductor_loss"] = model
            with self.subTest(model=model), self.assertRaises(SiChannelError):
                multiconductor_rlgc_network(extraction, [0., 5e8, 1e9], 50.)


if __name__ == "__main__":
    unittest.main()
