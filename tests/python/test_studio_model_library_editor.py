# SPDX-License-Identifier: Apache-2.0
import sys
from pathlib import Path
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
STUDIO = ROOT / "standalone" / "spikes_project" / "studio" / "python"
sys.path.insert(0, str(STUDIO))
sys.modules.setdefault("wx", mock.MagicMock())

from spikes_studio.model_library_editor import ModelLibraryDocument, parameter_field


class ModelLibraryEditorDocumentTests(unittest.TestCase):
    def test_model_noop_preserves_source_exactly(self):
        source = "* vendor note\n.MODEL FastGan NMOS (VTO={base+1} XUNKNOWN='a b' OFF)\n"
        document = ModelLibraryDocument(source)
        self.assertEqual(document.source_text(), source)
        self.assertEqual([field.name for field in document.fields], ["VTO", "XUNKNOWN", "OFF"])
        self.assertEqual(document.fields[0].category, "Electrical")
        self.assertEqual(document.fields[1].category, "Other")

    def test_model_edit_preserves_expressions_flags_unknowns_and_order(self):
        document = ModelLibraryDocument(".model QX NPN (BF={GAIN*2} VENDORFLAG ODD=9)")
        document.set_value("BF", "{GAIN*3}")
        self.assertEqual(document.source_text(),
                         ".MODEL QX NPN (BF={GAIN*3} VENDORFLAG ODD=9)")
        document.add_parameter("rth", "2.5")
        self.assertEqual(document.source_text(),
                         ".MODEL QX NPN (BF={GAIN*3} VENDORFLAG ODD=9 RTH=2.5)")

    def test_model_edit_preserves_vendor_license_comments_and_blank_lines(self):
        source = ("* Vendor compact-model license: retain this notice\r\n"
                  "\r\n"
                  "  .model WG NMOS (VTO=2\r\n"
                  "* Source: vendor application model revision 7\r\n"
                  "+ COSS={C0*scale})\r\n"
                  "\r\n"
                  "* Redistribution remains subject to the notice above\r\n")
        document = ModelLibraryDocument(source)
        document.set_value("VTO", "2.5")
        self.assertEqual(
            document.source_text(),
            ("* Vendor compact-model license: retain this notice\r\n"
             "\r\n"
             "  .MODEL WG NMOS (VTO=2.5 COSS={C0*scale})\r\n"
             "* Source: vendor application model revision 7\r\n"
             "\r\n"
             "* Redistribution remains subject to the notice above\r\n"),
        )

    def test_subckt_params_edit_keeps_body_exactly(self):
        source = ("* retained vendor note\r\n"
                  ".SUBCKT AMP IN OUT VCC VEE PARAMS: GAIN={A*2} SLEW=5Meg\r\n"
                  "E1 OUT 0 VALUE={V(IN)*GAIN}\r\n.ENDS AMP\r\n")
        document = ModelLibraryDocument(source)
        document.set_value("GAIN", "{A*4}")
        edited = document.source_text()
        self.assertTrue(edited.startswith("* retained vendor note\r\n"
                                          ".SUBCKT AMP IN OUT VCC VEE PARAMS: GAIN={A*4} SLEW=5Meg\n"))
        self.assertTrue(edited.endswith("E1 OUT 0 VALUE={V(IN)*GAIN}\r\n.ENDS AMP\r\n"))

    def test_subckt_without_params_can_add_named_default(self):
        document = ModelLibraryDocument(".SUBCKT IC A B\nR1 A B 1k\n.ENDS IC\n")
        document.add_parameter("corner", "{NOMINAL}")
        self.assertEqual(document.source_text(),
                         ".SUBCKT IC A B PARAMS: CORNER={NOMINAL}\nR1 A B 1k\n.ENDS IC\n")

    def test_unsafe_subckt_params_is_read_only_and_preserved(self):
        source = ".SUBCKT IC A B PARAMS: BROKEN\nR1 A B 1k\n.ENDS\n"
        document = ModelLibraryDocument(source)
        self.assertTrue(document.read_only_reason)
        self.assertEqual(document.source_text(), source)
        with self.assertRaises(ValueError):
            document.add_parameter("X", "1")

    def test_duplicate_subckt_params_are_read_only_not_overwritten(self):
        source = ".SUBCKT IC A B PARAMS: GAIN=1 GAIN=2\n.ENDS IC\n"
        document = ModelLibraryDocument(source)
        self.assertIn("Duplicate", document.read_only_reason)
        self.assertEqual(document.source_text(), source)

    def test_parameter_edits_reject_directive_injection_controls(self):
        document = ModelLibraryDocument(".MODEL DIODE D (IS=1e-12)")
        for name, value in (("EVIL\n.MODEL X D", "1"), ("SAFE", "1\n.END"),
                            ("TAB\tNAME", "1"), ("SAFE", "bad\x7fvalue")):
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                document.add_parameter(name, value)
        with self.assertRaises(ValueError):
            document.set_value("IS", "1e-9\r.END")

    def test_read_only_source_text_has_no_editable_fields(self):
        source = ".SUBCKT IC A B PARAMS: FLAG\n.ENDS\n"
        document = ModelLibraryDocument(source)
        self.assertEqual(document.fields, ())
        self.assertEqual(document.source_text(), source)

    def test_labels_are_descriptive_but_do_not_supply_values(self):
        known = parameter_field("CJO", "{C0}")
        unknown = parameter_field("vendor_x", "abc")
        self.assertEqual((known.label, known.unit, known.value),
                         ("Zero-bias junction capacitance", "F", "{C0}"))
        self.assertEqual((unknown.category, unknown.value), ("Other", "abc"))

    def test_opamp_and_wide_bandgap_parameter_labels(self):
        self.assertEqual((parameter_field("GBW", "1Meg").unit,
                          parameter_field("SLEW", "2Meg").label),
                         ("Hz", "Slew rate"))
        charge = parameter_field("VENDOR_COSS", "4p")
        thermal = parameter_field("DIE_RTHJC", "0.5")
        resistance = parameter_field("GAN_RDSON", "30m")
        self.assertEqual((charge.category, charge.unit), ("Charge & parasitics", "F"))
        self.assertEqual((thermal.category, thermal.unit), ("Thermal", "K/W"))
        self.assertEqual((resistance.category, resistance.unit), ("Electrical", "ohm"))


if __name__ == "__main__":
    unittest.main()
