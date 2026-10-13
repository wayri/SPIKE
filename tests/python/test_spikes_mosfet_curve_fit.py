# SPDX-License-Identifier: Apache-2.0
"""Independent synthetic oracles for the bounded, unqualified DC fit."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from python.spikes.mosfet_curve_fit import (
    MAX_BYTES, current_and_jacobian, fit_csv, model_card, read_csv,
)


def oracle(gate, drain, vto=1.7, kp=.32, lam=.025):
    # Independent integrated-channel expression, not implementation branches.
    over = max(gate-vto, 0)
    remaining = max(over-drain, 0)
    return .5*kp*(over**2-remaining**2)*(1+lam*drain)+1e-12*drain


class MosfetCurveFitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/"curves.csv"
        self.rows = [(gate, drain, oracle(gate, drain)) for gate in (0, 1, 2, 3, 4, 6)
                     for drain in (.1, .4, 1, 2, 4, 8, 12)]
        self.write(self.rows)

    def write(self, rows):
        self.path.write_text("vgs_v,vds_v,id_a\n" + "\n".join(",".join(format(v, ".17g") for v in row) for row in rows), encoding="utf-8")

    def test_exact_known_parameters_and_validity(self):
        result = fit_csv(self.path, temperature_k=310, source_kind="datasheet_table", source_note="Synthetic independent oracle")
        for name, expected in (("VTO", 1.7), ("KP", .32), ("LAMBDA", .025)):
            self.assertAlmostEqual(result["parameters"][name], expected, delta=1e-8)
        self.assertLess(result["fit_metrics"]["rmse_a"], 1e-9)
        self.assertLess(result["heldout_metrics"]["rmse_a"], 1e-9)
        self.assertEqual(result["status"], "unqualified_draft")
        self.assertEqual(result["validity"]["vgs_v"], [0, 6])
        self.assertEqual(result["validity"]["temperature_k"], 310)
        self.assertEqual(result["heldout_metrics"]["samples"], 8)
        self.assertEqual(len(result["source"]["sha256"]), 64)
        json.dumps(result, allow_nan=False)

    def test_deterministic_under_row_reordering(self):
        first = fit_csv(self.path)
        self.write(list(reversed(self.rows)))
        second = fit_csv(self.path)
        self.assertEqual(first["parameters"], second["parameters"])
        self.assertEqual(first["points"], second["points"])
        self.assertNotEqual(first["source"]["sha256"], second["source"]["sha256"])

    def test_holdout_never_fitted(self):
        rows = [(g, d, i+10 if index % 5 == 4 else i) for index, (g, d, i) in enumerate(sorted(self.rows))]
        self.write(rows)
        result = fit_csv(self.path)
        self.assertAlmostEqual(result["parameters"]["VTO"], 1.7, delta=1e-8)
        self.assertLess(result["fit_metrics"]["rmse_a"], 1e-9)
        self.assertAlmostEqual(result["heldout_metrics"]["rmse_a"], 10, delta=1e-8)
        self.assertTrue(any("exceeds 5%" in text for text in result["warnings"]))

    def test_small_signal_and_high_current_scaling(self):
        for kp in (1e-7, 200):
            with self.subTest(kp=kp):
                self.write([(g, d, oracle(g, d, kp=kp)) for g, d, _ in self.rows])
                result = fit_csv(self.path)
                self.assertAlmostEqual(result["parameters"]["KP"]/kp, 1, delta=1e-6)

    def test_analytic_jacobian_against_centered_differences(self):
        gate = np.array([.5, 1.7, 2, 3, 3, 6])
        drain = np.array([1, 2, 4, .2, 1.3, 2])
        params = np.array([1.7, .32, .025])
        _, jac = current_and_jacobian(gate, drain, params)
        for column in range(3):
            step = 1e-6
            left = params.copy(); left[column] -= step
            right = params.copy(); right[column] += step
            finite_difference = (current_and_jacobian(gate, drain, right)[0]-current_and_jacobian(gate, drain, left)[0])/(2*step)
            np.testing.assert_allclose(jac[:, column], finite_difference, rtol=2e-6, atol=1e-7)

    def test_header_units_nonfinite_negative_and_duplicate_rejected(self):
        for text in ("Vgs,Vds,Id\n1,2,3", "vgs_v,vds_v,id_ma\n1,2,3", "vgs_v,vds_v,id_a\n1,2,nan",
                     "vgs_v,vds_v,id_a\n1,2,inf", "vgs_v,vds_v,id_a\n1,2,3mA",
                     "vgs_v,vds_v,id_a\n1,-2,3", "vgs_v,vds_v,id_a\n1,2,-3",
                     "vgs_v,vds_v,id_a\n101,2,3", "vgs_v,vds_v,id_a\n1,2,3,4",
                     "vgs_v,vds_v,id_a\n1,2,3\n1,2,4"):
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError): read_csv(self.path)

    def test_byte_row_and_minimum_limits(self):
        self.path.write_bytes(b"x"*(MAX_BYTES+1))
        with self.assertRaisesRegex(ValueError, "1 MiB"): read_csv(self.path)
        self.write(self.rows[:5])
        with self.assertRaisesRegex(ValueError, "15 unique"): read_csv(self.path)
        self.write(self.rows)
        with patch("python.spikes.mosfet_curve_fit.MAX_ROWS", 20):
            with self.assertRaisesRegex(ValueError, "5,000"): read_csv(self.path)

    def test_inadequate_bias_and_current_rejected(self):
        self.write([(2, d/10, 1) for d in range(20)])
        with self.assertRaisesRegex(ValueError, "distinct"): fit_csv(self.path)
        self.write([(g, d, 0) for g, d, _ in self.rows])
        with self.assertRaisesRegex(ValueError, "conducting"): fit_csv(self.path)

    def test_metadata_and_unsupported_image_inputs(self):
        for temperature in (True, 0, float("nan"), 1000, "298"):
            with self.assertRaises(ValueError): fit_csv(self.path, temperature_k=temperature)
        with self.assertRaises(ValueError): fit_csv(self.path, source_kind="image")
        with self.assertRaises(ValueError): fit_csv(self.path, source_note="x"*2001)

    def test_review_export_and_native_parser(self):
        result = fit_csv(self.path)
        with self.assertRaisesRegex(ValueError, "Review"): model_card(result)
        with self.assertRaises(ValueError): model_card(result, "BAD\n.end", reviewed=True)
        card = model_card(result, "NMOS_DRAFT", reviewed=True)
        self.assertIn("UNQUALIFIED", card)
        from python.spikes.netlist import parse_netlist
        source = "Fit parser check\n" + card + "V1 d 0 2\nV2 g 0 3\nM1 d g 0 0 NMOS_DRAFT\n.op\n.end\n"
        project = parse_netlist(source, native_extensions=True)
        self.assertEqual(len(project.elements), 3)

    def test_placement_plan_keeps_sheet_and_review_evidence(self):
        studio = Path(__file__).resolve().parents[2]/"standalone/spikes_project/studio/python"
        sys.path.insert(0, str(studio)); self.addCleanup(sys.path.remove, str(studio))
        from spikes_studio.document import Document
        from spikes_studio.model_placement import prepare, insert
        result = fit_csv(self.path)
        document = Document.from_netlist("Existing sheet\nR1 a 0 1k\nV1 a 0 1\n.op\n.end\n")
        before = document.data["source"]
        plan = prepare(document, model_card(result, reviewed=True))
        self.assertEqual(document.data["source"], before)
        plan["part"]["evidence"] = json.dumps(result)
        part_id = insert(document, plan, (100, 200))
        part = next(p for p in document.data["components"] if p["id"] == part_id)
        self.assertEqual(json.loads(part["evidence"])["source"]["sha256"], result["source"]["sha256"])
        self.assertEqual(len(document.data["components"]), 3)
        self.assertIn("R1 a 0 1k", document.data["source"])
        with self.assertRaisesRegex(ValueError, "Sheet changed"): insert(document, plan, (0, 0))


if __name__ == "__main__":
    unittest.main()
