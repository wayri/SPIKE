from __future__ import annotations

from pathlib import Path
import sys
import unittest

STUDIO_PYTHON = Path(__file__).resolve().parents[2] / "studio/python"
if str(STUDIO_PYTHON) not in sys.path:
    sys.path.insert(0, str(STUDIO_PYTHON))

from spikes_studio.model_import import ModelImportError, convert_model_statement, parse_model_statement


class ModelStatementImportTests(unittest.TestCase):
    def test_diode_continuation_becomes_runnable_editable_part(self) -> None:
        part = convert_model_statement("""* vendor comment
.model DFAST D(Is=2n N=1.15
+ Rs=30m Cjo={c0*scale})
""")
        self.assertEqual(part["contract"], "spikes/studio-part/v1")
        self.assertEqual(part["family"], "diode")
        self.assertEqual([pin["id"] for pin in part["pins"]], ["a", "k"])
        self.assertEqual(part["simulation"]["status"], "runnable")
        self.assertEqual(
            [item["name"] for item in part["model"]["parameters"]],
            ["IS", "N", "RS", "CJO"],
        )
        self.assertEqual(part["model"]["parameters"][-1]["value_text"], "{c0*scale}")
        self.assertFalse(part["qualification"]["redistribution_approved"])

    def test_mosfet_maps_four_terminals_and_preserves_expressions(self) -> None:
        part = convert_model_statement(
            ".MODEL POWER_NMOS NMOS (LEVEL=3 VTO=3.2 KP={gain/temp} LAMBDA=0.01)"
        )
        self.assertEqual(part["family"], "mosfet_n")
        self.assertEqual([pin["id"] for pin in part["pins"]], ["d", "g", "s", "b"])
        self.assertEqual(part["instance_prefix"], "M")
        self.assertFalse(part["requires_pin_mapping"])
        self.assertEqual(part["simulation"]["status"], "backend_required")

    def test_vendor_technology_hint_does_not_imply_qualification(self) -> None:
        part = convert_model_statement(".model EPC_GAN_100V NMOS (VTO=1.6 RDS=8m)")
        self.assertEqual(part["technology"], "gan")
        self.assertEqual(part["qualification"]["state"], "unreviewed")

    def test_unknown_type_creates_visible_generic_block_requiring_pin_mapping(self) -> None:
        part = convert_model_statement(".model SENSORX CUSTOMPHY (GAIN=4 DELAY=1u)")
        self.assertEqual(part["family"], "generic_spice_model")
        self.assertEqual(part["pins"], [])
        self.assertTrue(part["requires_pin_mapping"])
        self.assertEqual(part["symbol"]["library_id"], "spikes.generic.model_block")

    def test_malformed_or_ambiguous_pastes_fail_closed(self) -> None:
        invalid = (
            ".model D1 D(IS=1n)\n.model D2 D(IS=2n)",
            "+ IS=1n",
            ".model D1 D(IS=1n IS=2n)",
            ".model D1 D(IS=)",
            ".model D1 D(IS={x)",
        )
        for statement in invalid:
            with self.subTest(statement=statement), self.assertRaises(ModelImportError):
                parse_model_statement(statement)


if __name__ == "__main__":
    unittest.main()
