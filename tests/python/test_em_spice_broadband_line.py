# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Distributed line / actual owned SPICE composition against spatial exponential.

This tests supplied RLGC mathematics, not extracted PCB validity at GHz.
"""
import math
import unittest

import numpy as np
from scipy.linalg import expm

from python.spike_core.solvers.execution.coupling.em_network_ac import WAVE_CONVENTION
from python.spike_core.solvers.execution.coupling.em_spice_coupling import run_em_spice_coupling
from python.spike_core.solvers.signal_integrity.lines.rlgc_line_network import build_rlgc_line_network
from tests.python.test_em_spice_coupling import element
from tests.python.test_rlgc_line_network import request as line_request


class BroadbandCircuitLineTests(unittest.TestCase):
    def test_distributed_line_loaded_with_series_l_and_shunt_c_to_three_ghz(self):
        frequencies = (1e6, 30e6, 100e6, 300e6, 700e6, 1e9, 2e9, 3e9)
        line = line_request(frequencies, length_m=.11, resistance=4., conductance=3e-4)
        source = build_rlgc_line_network(line)["network"]
        request = {"contract": "spike/em-spice-coupling-request/v1", "source": source,
            "wave_convention": WAVE_CONVENTION,
            "port_bindings": {name: {"positive_node": node, "negative_node": "0",
                "reference_plane": "declared analytic line end"}
                for name, node in (("left", "in"), ("right", "out"))},
            "circuit": {"ground_node": "0", "elements": [
                element("VS", "voltage_source", "src", "0", [1., .25]),
                element("RS", "resistor", "src", "mid", 7.),
                element("LS", "inductor", "mid", "in", 2e-9),
                element("RL", "resistor", "out", "0", 90.),
                element("CL", "capacitor", "out", "0", 1.5e-12)]}}
        result = run_em_spice_coupling(request)
        self.assertEqual(result["provenance"]["native_execution_count"], len(frequencies))
        self.assertFalse(result["production_qualified"])
        for frequency, sample in zip(frequencies, result["samples"]):
            omega = 2*math.pi*frequency
            z = 4 + 1j*omega*line["inductance_h_per_m"]
            y = 3e-4 + 1j*omega*line["capacitance_f_per_m"]
            chain = expm(np.array([[0, z], [y, 0]])*line["length_m"])
            load = 1/90 + 1j*omega*1.5e-12
            # V0=A*V1+B*I1, I0=C*V1+D*I1, I1=Yload*V1.
            source_impedance = 7 + 1j*omega*2e-9
            expected = (1+.25j)/(chain[0, 0]+chain[0, 1]*load +
                source_impedance*(chain[1, 0]+chain[1, 1]*load))
            actual = complex(*sample["voltage_rms_v"][1])
            self.assertLess(abs(actual-expected), 1e-11*abs(expected))
            self.assertLess(sample["power_balance_error_w"], 1e-12)


if __name__ == "__main__":
    unittest.main()
