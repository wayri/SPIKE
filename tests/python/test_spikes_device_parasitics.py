# SPDX-License-Identifier: Apache-2.0
"""Generic package-parasitic topology, admission, and native RLC checks."""

import math
import os
from pathlib import Path
import unittest

from python.spikes.device_parasitics import compose_device_parasitics
from python.spikes.native_abi import load_native_library
from python.spikes.netlist import parse_netlist
from python.spikes.native_runner import _populate


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = Path(os.environ.get(
    "SPIKES_TEST_LIBRARY",
    ROOT / "build-spikes-native-analysis-20261013" / "Release" / "spikes_c_api.dll",
))


class DeviceParasiticsTests(unittest.TestCase):
    def test_arbitrary_hemt_pins_wrap_in_order_without_family_inference(self):
        dependency = (
            ".subckt USER_HEMT D G S SUB FP\n"
            "RDS D S 100\nRGS G S 1e9\nRSUB SUB S 1e9\nRFP FP S 1e9\n"
            ".ends USER_HEMT\n"
        )
        package = compose_device_parasitics(
            "USER_HEMT", ["D", "G", "S", "SUB", "FP"], name="HEMT_PACKAGE",
            pin_parasitics={
                "D": {"resistance_ohm": 0.02, "inductance_h": 2e-9},
                "G": {"resistance_ohm": 1.5},
                "S": {"inductance_h": 1e-9},
            },
            between_pin_parasitics=[
                {"pins": ["D", "S"], "capacitance_f": 20e-12},
                {"pins": ["G", "S"], "leakage_resistance_ohm": 1e9},
                {"pins": ["SUB", "FP"], "capacitance_f": 0, "leakage_resistance_ohm": 0},
            ],
            core_dependencies=[dependency],
        )
        self.assertEqual(package["pins"], ["D", "G", "S", "SUB", "FP"])
        self.assertEqual(package["model_status"], "generic_unqualified")
        self.assertEqual(package["core_dependencies"], [dependency])
        self.assertNotIn("RDS D S", package["source"])
        self.assertIn("XCORE __SPK_CORE_1 __SPK_CORE_2 __SPK_CORE_3 __SPK_CORE_4 __SPK_CORE_5 USER_HEMT", package["source"])
        self.assertIn("VPKG4 SUB __SPK_CORE_4 0", package["source"])
        self.assertIn("VPKG5 FP __SPK_CORE_5 0", package["source"])
        self.assertNotIn("CPKG3", package["source"])
        self.assertNotIn("RLEAK3", package["source"])
        self.assertTrue(any("voltage-dependent charge" in item for item in package["limitations"]))
        self.assertTrue(any("self-heating" in item for item in package["limitations"]))
        self.assertTrue(any("reverse-recovery" in item for item in package["limitations"]))

        project = parse_netlist(
            dependency + package["source"]
            + "XU drain gate 0 substrate field HEMT_PACKAGE\n"
              "VREF drain 0 0\n.op\n",
            native_extensions=True,
        )
        kinds = [element.kind for element in project.elements]
        self.assertIn("inductor", kinds)
        self.assertIn("capacitor", kinds)
        self.assertIn("resistor", kinds)
        core_resistor = next(element for element in project.elements if element.name == "XU:XCORE:RDS")
        self.assertEqual(
            (core_resistor.positive_node, core_resistor.negative_node),
            ("xu:__spk_core_1", "xu:__spk_core_3"),
        )

    def test_family_names_are_not_special_cases_and_zero_shunts_are_omitted(self):
        for core, pins in (
            ("MOS_CORE", ["D", "G", "S", "B"]),
            ("BJT_CORE", ["C", "B", "E"]),
            ("IGBT_CORE", ["C", "G", "E", "KELVIN"]),
            ("THYRISTOR_CORE", ["A", "K", "G"]),
            ("SWITCH_CORE", ["P", "N", "CP", "CN"]),
        ):
            with self.subTest(core=core):
                result = compose_device_parasitics(
                    core, pins,
                    between_pin_parasitics=[{
                        "pins": pins[:2], "capacitance_f": 0,
                        "leakage_resistance_ohm": 0,
                    }],
                )
                self.assertEqual(result["pins"], pins)
                self.assertEqual(result["resolved_config"]["between_pin_parasitics"], [])
                self.assertNotIn("\nC", result["source"])
                self.assertNotIn("\nRLEAK", result["source"])

    def test_mutual_terms_require_positive_pin_l_and_psd_matrix(self):
        package = compose_device_parasitics(
            "CORE", ["A", "B", "C"],
            pin_parasitics={pin: {"inductance_h": value} for pin, value in zip(
                ("A", "B", "C"), (1e-6, 4e-6, 9e-6), strict=True
            )},
            mutual_couplings=[
                {"pins": ["A", "B"], "coupling_coefficient": 0.2},
                {"pins": ["B", "C"], "coupling_coefficient": -0.3},
                {"pins": ["A", "C"], "coupling_coefficient": 0},
            ],
        )
        matrix = package["resolved_config"]["inductance_matrix_h"]
        self.assertAlmostEqual(matrix[0][1], 0.4e-6)
        self.assertAlmostEqual(matrix[1][2], -1.8e-6)
        self.assertEqual(matrix[0][2], 0)
        self.assertGreaterEqual(package["resolved_config"]["minimum_inductance_eigenvalue_h"], 0)
        self.assertIn("KPKG1 LPKG1 LPKG2 0.20000000000000001", package["source"])
        self.assertIn("KPKG2 LPKG2 LPKG3 -0.29999999999999999", package["source"])
        self.assertNotIn("KPKG3", package["source"])

        with self.assertRaisesRegex(ValueError, "positive inductance_h"):
            compose_device_parasitics(
                "CORE", ["A", "B"],
                pin_parasitics={"A": {"inductance_h": 1e-6}},
                mutual_couplings=[{"pins": ["A", "B"], "coupling_coefficient": 0.5}],
            )
        with self.assertRaisesRegex(ValueError, "positive-semidefinite"):
            compose_device_parasitics(
                "CORE", ["A", "B", "C"],
                pin_parasitics={pin: {"inductance_h": 1e-12} for pin in ("A", "B", "C")},
                mutual_couplings=[
                    {"pins": ["A", "B"], "coupling_coefficient": 0.9},
                    {"pins": ["A", "C"], "coupling_coefficient": 0.9},
                    {"pins": ["B", "C"], "coupling_coefficient": -0.9},
                ],
            )

    def test_invalid_inputs_and_collisions_fail_closed(self):
        invalid_calls = (
            lambda: compose_device_parasitics("CORE\nV1 A 0 1", ["A"]),
            lambda: compose_device_parasitics("CORE", ["A", "a"]),
            lambda: compose_device_parasitics("CORE", ["0"]),
            lambda: compose_device_parasitics("CORE", ["A"], name="core"),
            lambda: compose_device_parasitics("CORE", ["A"], pin_parasitics={"A": {"resistance_ohm": True}}),
            lambda: compose_device_parasitics("CORE", ["A"], pin_parasitics={"A": {"inductance_h": math.inf}}),
            lambda: compose_device_parasitics("CORE", ["A", "B"], between_pin_parasitics=[{"pins": ["A", "B"], "capacitance_f": -1}]),
            lambda: compose_device_parasitics("CORE", ["A", "B"], between_pin_parasitics=[{"pins": ["A", "B"], "leakage_resistance_ohm": math.nan}]),
            lambda: compose_device_parasitics("CORE", ["A", "B"], mutual_couplings=[{"pins": ["A", "B"], "coupling_coefficient": 1}]),
            lambda: compose_device_parasitics("CORE", ["A", "B"], mutual_couplings=[{"pins": ["A", "B"], "coupling_coefficient": "0.5"}]),
            lambda: compose_device_parasitics("CORE", ["A"], core_dependencies=".include bad.lib"),
        )
        for call in invalid_calls:
            with self.subTest(call=call), self.assertRaises(ValueError):
                call()

    def test_private_nodes_do_not_collide_with_adversarial_valid_pin(self):
        package = compose_device_parasitics("CORE", ["A", "__SPK_CORE_1"])
        instance = next(line for line in package["source"].splitlines() if line.startswith("XCORE "))
        self.assertIn("__SPK_CORE_1_1", instance)
        self.assertEqual(len(instance.split()), 4)


@unittest.skipUnless(LIBRARY.is_file(), "Set SPIKES_TEST_LIBRARY to the current native library")
class NativeDeviceParasiticsTests(unittest.TestCase):
    def test_series_rl_and_between_pin_c_execute_in_owned_native_transient(self):
        core = ".subckt OPEN_CORE P N\nRCORE P N 1e12\n.ends OPEN_CORE\n"
        package = compose_device_parasitics(
            "OPEN_CORE", ["P", "N"],
            pin_parasitics={"P": {"resistance_ohm": 10, "inductance_h": 1e-6}},
            between_pin_parasitics=[{"pins": ["P", "N"], "capacitance_f": 1e-6}],
        )
        project = parse_netlist(
            core + package["source"]
            + "VSTEP supply 0 PULSE(0 1 0 1u 1u 1 2)\n"
              "X1 supply 0 SPK_DEVICE_PACKAGE\n.tran 1u 20u UIC\n",
            native_extensions=True,
        )
        library = load_native_library(LIBRARY)
        circuit = library.circuit()
        self.addCleanup(circuit.close)
        _populate(circuit, project)
        with circuit.solve_transient(
            time_step_s=1e-6, stop_time_s=20e-6,
            integration_method="backward_euler",
        ) as result:
            self.assertEqual(result.status, "converged", result.message)
            values = [
                result.node_voltage(index, "x1:__spk_core_1")
                for index in range(result.point_count)
            ]
            self.assertTrue(all(math.isfinite(value) for value in values))
            self.assertGreater(values[-1], values[1])
            self.assertGreater(values[-1], 0.5)
            self.assertLessEqual(values[-1], 1.01)


if __name__ == "__main__":
    unittest.main()
