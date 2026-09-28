import tempfile
import unittest
from pathlib import Path

import numpy as np

from python.spike_core.sparameters import (
    NetworkData,
    TouchstoneError,
    analyze_network,
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

    def test_matched_reflection_vswr_masks_open_and_active_samples(self):
        gamma = np.asarray([0, 0.5, 1, 1.2], dtype=complex).reshape(4, 1, 1)
        network = NetworkData(np.asarray([1e6, 2e6, 3e6, 4e6]), gamma, np.asarray([50.0]))
        rows = analyze_network(network)["reflection_vswr"]["ports"][0]["trace"]
        self.assertEqual([row["vswr_status"] for row in rows],
                         ["finite", "finite", "infinite", "non_passive_reflection"])
        self.assertEqual([row["vswr"] for row in rows], [1.0, 3.0, None, None])
        self.assertEqual(rows[2]["reflection_magnitude"], 1.0)

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


if __name__ == "__main__":
    unittest.main()
