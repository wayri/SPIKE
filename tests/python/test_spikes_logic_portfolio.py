# SPDX-License-Identifier: Apache-2.0
import itertools
import unittest

from python.spikes.digital import DigitalKernel, LogicValue
from python.spikes.logic_portfolio import (
    BACKEND,
    UnsupportedLogicModelError,
    bind,
    catalog,
    coverage_summary,
    library_model,
)


class LogicPortfolioTests(unittest.TestCase):
    def fixture(self, model_id):
        descriptor = library_model(model_id)
        kernel = DigitalKernel(max_delta_cycles=4096)
        mapping = {pin["number"]: f"pin{pin['number']}" for pin in descriptor["pins"]}
        for signal in mapping.values():
            kernel.add_signal(signal)
        bind(kernel, model_id, "U1", mapping, delay_ticks=0)
        by_name = {pin["name"]: mapping[pin["number"]] for pin in descriptor["pins"]}
        return kernel, descriptor, by_name, mapping

    @staticmethod
    def drive(kernel, by_name, values):
        for name, value in values.items():
            kernel.drive(by_name[name], f"stim_{name}", value)
        kernel.run_until(kernel.time_tick)

    def test_catalog_counts_genuine_functions_not_series_aliases(self):
        summary = coverage_summary()
        self.assertEqual(summary["executable_distinct_device_families"], 20)
        self.assertEqual(summary["executable_generic_cores"], 3)
        self.assertEqual(summary["review_only_device_families"], 5)
        self.assertEqual(summary["documented_54_family_names"], 16)
        self.assertEqual(summary["documented_74_family_names"], 20)
        self.assertEqual(summary["package_or_orderable_variants"], 0)
        executable = catalog(include_review_only=False)
        self.assertEqual(len(executable), 23)
        self.assertEqual(len({item["model_id"] for item in catalog()}), len(catalog()))
        self.assertTrue(all(item["backend"] == BACKEND for item in executable))
        self.assertTrue(all(item["model_status"] == "generic_functional_unqualified"
                            for item in executable))
        first = catalog()
        first[0]["pins"].clear()
        self.assertTrue(catalog()[0]["pins"])

    def test_manufacturer_pinouts_and_power_declarations_are_retained(self):
        hc138 = library_model("HC138")
        pins = {pin["number"]: (pin["name"], pin["role"]) for pin in hc138["pins"]}
        self.assertEqual(pins["1"], ("A", "input"))
        self.assertEqual(pins["8"], ("GND", "power"))
        self.assertEqual(pins["15"], ("Y0", "output"))
        self.assertEqual(pins["16"], ("VCC", "power"))
        hc245 = library_model("HC245")
        pins = {pin["number"]: pin["name"] for pin in hc245["pins"]}
        self.assertEqual((pins["1"], pins["10"], pins["19"], pins["20"]),
                         ("DIR", "GND", "OE", "VCC"))
        self.assertEqual(hc245["source"]["manufacturer"], "Texas Instruments")
        self.assertTrue(hc245["source"]["url"].startswith("https://www.ti.com/"))

    def test_all_ten_gate_package_truth_tables(self):
        operations = {
            "HC00": lambda values: not all(values), "HC02": lambda values: not any(values),
            "HC04": lambda values: not values[0], "HC08": all,
            "HC10": lambda values: not all(values), "HC11": all,
            "HC20": lambda values: not all(values), "HC21": all,
            "HC32": any, "HC86": lambda values: sum(values) % 2 == 1,
        }
        for model_id, operation in operations.items():
            descriptor = library_model(model_id)
            first = descriptor["primitives"][0]
            arity = len(first["inputs"])
            for bits in itertools.product((0, 1), repeat=arity):
                kernel, descriptor, by_name, _ = self.fixture(model_id)
                stimulus = {}
                for primitive in descriptor["primitives"]:
                    for name, bit in zip(primitive["inputs"], bits):
                        stimulus[name] = bit
                self.drive(kernel, by_name, stimulus)
                expected = LogicValue.ONE if operation(bits) else LogicValue.ZERO
                for primitive in descriptor["primitives"]:
                    self.assertEqual(kernel.value(by_name[primitive["output"]]), expected, model_id)

    def test_tristate_enable_polarities(self):
        for model_id, enabled, disabled in (("HC125", 0, 1), ("HC126", 1, 0)):
            kernel, _, pins, _ = self.fixture(model_id)
            self.drive(kernel, pins, {"1A": 1, "1OE": disabled})
            self.assertEqual(kernel.value(pins["1Y"]), LogicValue.Z)
            self.drive(kernel, pins, {"1OE": enabled})
            self.assertEqual(kernel.value(pins["1Y"]), LogicValue.ONE)

    def test_decoders_and_multiplexers(self):
        for address in range(8):
            kernel, _, pins, _ = self.fixture("HC138")
            values = {"A": address & 1, "B": (address >> 1) & 1, "C": (address >> 2) & 1,
                      "G1": 1, "G2A": 0, "G2B": 0}
            self.drive(kernel, pins, values)
            self.assertEqual([kernel.value(pins[f"Y{i}"]).value for i in range(8)],
                             ["0" if i == address else "1" for i in range(8)])
        kernel, _, pins, _ = self.fixture("HC139")
        self.drive(kernel, pins, {"1G": 0, "1A": 1, "1B": 0})
        self.assertEqual([kernel.value(pins[f"1Y{i}"]).value for i in range(4)],
                         ["1", "0", "1", "1"])

        for selected in range(8):
            kernel, _, pins, _ = self.fixture("HC151")
            values = {f"I{i}": int(i == selected) for i in range(8)}
            values.update({"S0": selected & 1, "S1": (selected >> 1) & 1,
                           "S2": (selected >> 2) & 1, "E": 0})
            self.drive(kernel, pins, values)
            self.assertEqual(kernel.value(pins["Y"]), LogicValue.ONE)
            self.assertEqual(kernel.value(pins["Y_N"]), LogicValue.ZERO)
        kernel, _, pins, _ = self.fixture("HC153")
        self.drive(kernel, pins, {"S0": 0, "S1": 1, "1G": 0,
                                  "1I0": 0, "1I1": 0, "1I2": 1, "1I3": 0})
        self.assertEqual(kernel.value(pins["1Y"]), LogicValue.ONE)
        kernel, _, pins, _ = self.fixture("HC157")
        self.drive(kernel, pins, {"S": 1, "G": 0, "1A": 0, "1B": 1})
        self.assertEqual(kernel.value(pins["1Y"]), LogicValue.ONE)
        self.drive(kernel, pins, {"G": 1})
        self.assertEqual(kernel.value(pins["1Y"]), LogicValue.ZERO)

    def test_adder_and_identity_comparator(self):
        for a in range(16):
            for b in range(16):
                for carry in (0, 1):
                    kernel, _, pins, _ = self.fixture("HC283")
                    values = {f"A{i + 1}": (a >> i) & 1 for i in range(4)}
                    values.update({f"B{i + 1}": (b >> i) & 1 for i in range(4)})
                    values["CIN"] = carry
                    self.drive(kernel, pins, values)
                    observed = sum((kernel.value(pins[f"S{i + 1}"]) is LogicValue.ONE) << i for i in range(4))
                    observed += (kernel.value(pins["COUT"]) is LogicValue.ONE) << 4
                    self.assertEqual(observed, a + b + carry)
        for p, q, enable, expected in ((0xA5, 0xA5, 0, "0"), (0xA5, 0xA4, 0, "1"),
                                       (0xA5, 0xA5, 1, "1")):
            kernel, _, pins, _ = self.fixture("HC688")
            values = {f"P{i}": (p >> i) & 1 for i in range(8)}
            values.update({f"Q{i}": (q >> i) & 1 for i in range(8)})
            values["G"] = enable
            self.drive(kernel, pins, values)
            self.assertEqual(kernel.value(pins["P_EQ_Q_N"]).value, expected)

    def test_bidirectional_transceiver(self):
        for direction, source_bus, target_bus in ((1, "A", "B"), (0, "B", "A")):
            kernel, _, pins, _ = self.fixture("HC245")
            values = {"DIR": direction, "OE": 0}
            values.update({f"{source_bus}{i}": i % 2 for i in range(1, 9)})
            self.drive(kernel, pins, values)
            self.assertEqual([kernel.value(pins[f"{target_bus}{i}"]).value for i in range(1, 9)],
                             [str(i % 2) for i in range(1, 9)])
            self.drive(kernel, pins, {"OE": 1})
            self.assertTrue(all(kernel.value(pins[f"{target_bus}{i}"]) is LogicValue.Z
                                for i in range(1, 9)))

    def test_kernel_primitive_dff_shift_and_counter_sequences(self):
        kernel, _, pins, _ = self.fixture("CORE_DFF")
        self.drive(kernel, pins, {"CLK": 0, "D": 1})
        self.drive(kernel, pins, {"CLK": 1})
        self.assertEqual(kernel.value(pins["Q"]), LogicValue.ONE)

        kernel, _, pins, _ = self.fixture("CORE_SIPO8")
        self.drive(kernel, pins, {"CLK": 0, "SER": 1})
        for bit in (1, 0, 1):
            self.drive(kernel, pins, {"SER": bit, "CLK": 0})
            self.drive(kernel, pins, {"CLK": 1})
            self.drive(kernel, pins, {"CLK": 0})
        self.assertEqual([kernel.value(pins[f"Q{i}"]).value for i in range(3)], ["1", "0", "1"])

        kernel, _, pins, _ = self.fixture("CORE_COUNTER4_SYNC")
        initial = {"CLK": 0, "LOAD": 1, "EN": 0, "D0": 1, "D1": 0, "D2": 1, "D3": 0}
        self.drive(kernel, pins, initial)
        self.drive(kernel, pins, {"CLK": 1})
        self.drive(kernel, pins, {"CLK": 0, "LOAD": 0, "EN": 1})
        self.drive(kernel, pins, {"CLK": 1})
        observed = sum((kernel.value(pins[f"Q{i}"]) is LogicValue.ONE) << i for i in range(4))
        self.assertEqual(observed, 6)

    def test_review_only_and_alias_errors_fail_before_mutation(self):
        with self.assertRaises(ValueError):
            library_model("SN74HC138N")
        descriptor = library_model("HC74_FULL")
        self.assertEqual(descriptor["support"], "review_only")
        kernel = DigitalKernel()
        before = kernel.model()
        with self.assertRaises(UnsupportedLogicModelError):
            bind(kernel, "HC74_FULL", "U1", {}, delay_ticks=0)
        self.assertEqual(kernel.model(), before)

        kernel, _, _, mapping = self.fixture("HC138")
        before = kernel.model()
        bad = dict(mapping)
        bad["1"] = "missing"
        with self.assertRaises(ValueError):
            bind(kernel, "HC138", "U2", bad, delay_ticks=0)
        self.assertEqual(kernel.model(), before)


if __name__ == "__main__":
    unittest.main()
