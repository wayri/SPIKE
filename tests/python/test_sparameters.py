import tempfile
import unittest
from pathlib import Path

import numpy as np

from python.spike_core.sparameters import (
    TouchstoneError,
    analyze_network,
    parse_touchstone_text,
    read_touchstone,
    renormalize_s,
    single_ended_to_mixed_mode,
    s_to_y,
    s_to_z,
    write_touchstone,
    z_to_s,
)


class SParameterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def fixture(self, transmission: float = 0.5) -> Path:
        path = self.root / "channel.s2p"
        path.write_text(
            "! reciprocal passive two-port\n"
            "# GHz S RI R 50\n"
            f"1 0 0 {transmission} 0 {transmission} 0 0 0\n"
            f"2 0 0 {transmission} 0 {transmission} 0 0 0\n",
            encoding="ascii",
        )
        return path

    def test_touchstone_parser_uses_column_major_port_order(self):
        network = read_touchstone(self.fixture(0.5))
        self.assertEqual(network.port_count, 2)
        self.assertEqual(network.frequencies_hz.tolist(), [1e9, 2e9])
        self.assertAlmostEqual(network.parameters[0, 1, 0], 0.5)
        self.assertAlmostEqual(network.parameters[0, 0, 1], 0.5)
        self.assertEqual(network.reference_impedance_ohm.tolist(), [50.0, 50.0])

    def test_network_checks_passive_and_reciprocal_fixture(self):
        report = analyze_network(read_touchstone(self.fixture(0.5)))
        self.assertEqual(report["checks"]["passivity"]["status"], "pass")
        self.assertEqual(report["checks"]["reciprocity"]["status"], "pass")
        self.assertEqual(len(report["traces"]["S21"]), 2)
        self.assertAlmostEqual(report["traces"]["S21"][0]["magnitude_db"], -6.020599913, places=6)
        self.assertEqual(report["checks"]["causality"]["status"], "not_evaluated")

    def test_passivity_violation_is_visible(self):
        report = analyze_network(read_touchstone(self.fixture(1.2)))
        self.assertEqual(report["checks"]["passivity"]["status"], "fail")
        self.assertTrue(any(issue["code"] == "SPARAM_PASSIVITY_VIOLATION" for issue in report["issues"]))

    def test_s_z_y_and_renormalization_are_consistent(self):
        impedance = np.asarray([[75.0 + 3j]])
        s = z_to_s(impedance, 50.0)
        np.testing.assert_allclose(s_to_z(s, 50.0), impedance, rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(s_to_y(s, 50.0), np.linalg.inv(impedance), rtol=1e-12, atol=1e-12)
        renormalized = renormalize_s(s, 50.0, 75.0)
        np.testing.assert_allclose(renormalized, np.asarray([[3j / (150.0 + 3j)]]), rtol=1e-12, atol=1e-12)

    def test_touchstone_writer_round_trips(self):
        source = read_touchstone(self.fixture(0.7))
        output = self.root / "roundtrip.s2p"
        write_touchstone(
            output,
            source.frequencies_hz,
            source.s_parameters(),
            source.reference_impedance_ohm,
            data_format="DB",
            comments=["SPIKE round-trip fixture"],
        )
        restored = read_touchstone(output)
        np.testing.assert_allclose(restored.s_parameters(), source.s_parameters(), rtol=1e-10, atol=1e-12)

    def test_renormalize_ideal_through_and_series_resistor_at_dc(self):
        # Independently derive the series two-port from V1-V2=R*I1,
        # I1=-I2. This network has no finite open-circuit Z matrix.
        def series(resistance, references):
            left, right = references
            denominator = resistance + left + right
            transmission = 2 * np.sqrt(left * right) / denominator
            return np.array([[(resistance + right - left) / denominator, transmission],
                             [transmission, (resistance + left - right) / denominator]])

        for resistance in (0, 27):
            for old, new in (([50, 50], [75, 75]), ([40, 90], [65, 25])):
                with self.subTest(resistance=resistance, old=old, new=new):
                    source, expected = series(resistance, old), series(resistance, new)
                    actual = renormalize_s(source, old, new)
                    np.testing.assert_allclose(actual, expected, rtol=1e-13, atol=1e-14)
                    np.testing.assert_allclose(renormalize_s(actual, new, old), source, rtol=1e-13, atol=1e-14)
                    stack = renormalize_s(np.array([source, source]), old, new)
                    np.testing.assert_allclose(stack, [expected, expected], rtol=1e-13, atol=1e-14)

    def test_renormalize_unequal_reference_nonreciprocal_three_port(self):
        impedance = np.array([[80+3j, 4+2j, 7-1j], [9-1j, 110+4j, 2+1j],
                              [3+2j, 8-3j, 65+7j]])
        old, new = [35, 50, 90], [85, 25, 60]
        # Independent finite-Z route is valid for this nonsingular fixture.
        source = z_to_s(impedance, old)
        expected = z_to_s(impedance, new)
        np.testing.assert_allclose(renormalize_s(source, old, new), expected, rtol=1e-13, atol=1e-14)

    def test_renormalize_rejects_singular_nonfinite_and_malformed_inputs(self):
        for value in (np.nan, np.inf, complex(0, np.inf)):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "finite"):
                renormalize_s([[value]], 50, 75)
        for references in ([0, 50], [50, np.inf], [50]):
            with self.subTest(references=references), self.assertRaises(ValueError):
                renormalize_s(np.eye(2), references, 75)
        for shape in ((2,), (2, 3), (0, 0), (1, 2, 3)):
            with self.subTest(shape=shape), self.assertRaises(ValueError):
                renormalize_s(np.zeros(shape), 50, 75)
        # Active reflection pole: A+B*S=0 for old/new=4 and S=-5/3.
        for reflection in (-5/3, -5/3 + 1e-15):
            with self.subTest(reflection=reflection), self.assertRaisesRegex(ValueError, "singular|ill-conditioned"):
                renormalize_s([[reflection]], 100, 25)
        with self.assertRaisesRegex(ValueError, "Non-finite"):
            renormalize_s([[1e308]], 1e308, 1e-308)

    def test_four_port_adjacent_pairs_convert_to_mixed_mode(self):
        single_ended = np.zeros((4, 4), dtype=complex)
        single_ended[2, 0] = 1
        single_ended[0, 2] = 1
        single_ended[3, 1] = 1
        single_ended[1, 3] = 1
        mixed = single_ended_to_mixed_mode(single_ended)
        self.assertAlmostEqual(mixed[1, 0], 1)
        self.assertAlmostEqual(mixed[0, 1], 1)
        self.assertAlmostEqual(mixed[3, 2], 1)
        self.assertAlmostEqual(mixed[2, 3], 1)
        self.assertAlmostEqual(abs(mixed[3, 0]), 0)

    def test_incomplete_network_record_is_rejected(self):
        path = self.root / "broken.s2p"
        path.write_text("# GHz S RI R 50\n1 0 0 1 0\n", encoding="ascii")
        with self.assertRaises(TouchstoneError):
            read_touchstone(path)

    def test_touchstone_21_multiline_reference_nonreciprocal_three_port(self):
        # Independently authored matrix: distinct entries expose transposition.
        # Invariants: IBIS Open Forum Touchstone 2.1, Option Line, [Reference],
        # [Number of Frequencies], and full n-port ordering (no copied samples).
        network = parse_touchstone_text(
            "[Version] 2.1\n# RI R 60 S MHz\n[Number of Ports] 3\n"
            "[Number of Frequencies] 2\n[Reference]\n40 ! first port\n"
            "55 80\n[Network Data]\n"
            "0 0.11 0.01 0.12 0.02 0.13 0.03\n"
            "0.21 0.04 0.22 0.05 0.23 0.06\n"
            "0.31 0.07 0.32 0.08 0.33 0.09\n"
            "2 0.11 0.01 0.12 0.02 0.13 0.03\n"
            "0.21 0.04 0.22 0.05 0.23 0.06\n"
            "0.31 0.07 0.32 0.08 0.33 0.09\n[End]\n",
            "independent.ts",
        )
        expected = np.array([[.11+.01j, .12+.02j, .13+.03j],
                             [.21+.04j, .22+.05j, .23+.06j],
                             [.31+.07j, .32+.08j, .33+.09j]])
        np.testing.assert_array_equal(network.frequencies_hz, [0, 2e6])
        np.testing.assert_array_equal(network.reference_impedance_ohm, [40, 55, 80])
        np.testing.assert_allclose(network.parameters, [expected, expected], rtol=0, atol=1e-16)

    def test_touchstone_two_port_explicit_orders_are_not_interchanged(self):
        for order, pairs in (("12_21", "0.2 0 0.7 0"), ("21_12", "0.7 0 0.2 0")):
            with self.subTest(order=order):
                network = parse_touchstone_text(
                    "[Version] 2.1\n# kHz S RI\n[Number of Ports] 2\n"
                    f"[Two-Port Data Order] {order}\n[Number of Frequencies] 1\n"
                    f"[Reference] 45\n65\n[Network Data]\n3 0.1 0 {pairs} 0.3 0\n[End]\n"
                )
                np.testing.assert_array_equal(network.frequencies_hz, [3000])
                np.testing.assert_allclose(network.parameters[0], [[.1, .2], [.7, .3]])

    def test_touchstone_option_defaults_and_subsequent_options(self):
        network = parse_touchstone_text("# RI\n# THz Z DB R 90\n1 0 0 0.7 0 0.2 0 0 0\n")
        self.assertEqual(network.parameter_kind, "S")
        self.assertEqual(network.data_format, "RI")
        np.testing.assert_array_equal(network.frequencies_hz, [1e9])
        np.testing.assert_array_equal(network.reference_impedance_ohm, [50, 50])

    def test_touchstone_rejects_invalid_options_and_declared_metadata(self):
        for options in ("THz S RI", "Hz GHz S RI", "Hz S RI R", "Hz S RI R nan", "Hz S RI R 50 75"):
            with self.subTest(options=options), self.assertRaises(TouchstoneError):
                parse_touchstone_text(f"# {options}\n1 0 0 0.7 0 0.2 0 0 0\n")
        for metadata in (
            "[Number of Frequencies] 2", "[Number of Frequencies] 0",
            "[Number of Frequencies] 1.5", "[Number of Frequencies] -1",
            "[Number of Frequencies] 1\n[Number of Frequencies] 1",
            "[Reference] 50", "[Reference]", "[Reference] 50 60 70",
            "[Reference] 50\n-60", "[Reference] 50 60\n[Reference] 50 60",
        ):
            with self.subTest(metadata=metadata), self.assertRaises(TouchstoneError):
                parse_touchstone_text(
                    "[Version] 2.1\n# Hz S RI\n[Number of Ports] 2\n"
                    f"{metadata}\n[Network Data]\n1 0 0 0.7 0 0.2 0 0 0\n[End]\n"
                )


if __name__ == "__main__":
    unittest.main()
