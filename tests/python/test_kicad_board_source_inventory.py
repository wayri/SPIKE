# SPDX-License-Identifier: Apache-2.0
"""Original native declarations exercise complete, single-parse pad evidence."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from python.core.board_parser import KicadParser
from python.spike_core.kicad_source_evidence import read_kicad_board_pad_inventory


def pad(identity="pth", kind="thru_hole", shape="circle", drill="(drill 0.4)",
        net='(net 1 "VDD")', extra=""):
    return (f'(pad "1" {kind} {shape} (at 1 2 30) (size 1 1.2) {drill} '
            f'(layers "*.Cu" "*.Mask") {net} {extra} (uuid "{identity}"))')


def via(identity="via1", kind="", extra="", layers='"F.Cu" "B.Cu"'):
    return (f'(via {kind} (at 4 5) (size 0.6) (drill 0.3) (layers {layers}) '
            f'(net 3) (uuid "{identity}") {extra})')


class KicadBoardPadInventoryTests(unittest.TestCase):
    def source(self, pads=None, suffix="", vias=""):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "original.kicad_pcb"
        contents = '(kicad_pcb (version 20240108) (footprint "original" ' + (pads or pad()) + ')' + vias + ')' + suffix
        path.write_text(contents, encoding="utf-8")
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_all_pad_types_explicit_defaults_and_plain_records(self):
        declarations = [pad(), pad("smd", "smd", "rect", "", ""),
                        pad("npth", "np_thru_hole", "oval", "(drill oval 0.4 0.7 (offset 0 0))", '(net 0 "")'),
                        pad("connect", "connect", "rect", "", '(net "SIGNAL")')]
        path, sha = self.source("\n".join(declarations))
        before = path.read_bytes()
        out = read_kicad_board_pad_inventory(path, sha)
        self.assertEqual(out["contract"], "spike/kicad-board-pad-inventory/v1")
        self.assertEqual(out["source_sha256"], sha)
        self.assertEqual(out["pad_count"], 4)
        self.assertEqual(set(out["pads"]), {"pth", "smd", "npth", "connect"})
        self.assertEqual(json.loads(json.dumps(out)), out)
        self.assertEqual(path.read_bytes(), before)
        pth, smd, npth = (out["pads"][key] for key in ("pth", "smd", "npth"))
        self.assertEqual((pth["pad_number"], pth["pad_kind"], pth["shape"]), ("1", "thru_hole", "circle"))
        self.assertEqual((pth["at_local_mm"], pth["rotation_deg"], pth["size_mm"]), ([1., 2.], 30., [1., 1.2]))
        self.assertEqual((pth["net_code"], pth["net_name"]), ("1", "VDD"))
        self.assertEqual((smd["drill_shape"], smd["drill_size_mm"], smd["drill_offset_mm"]), ("none", [0., 0.], [0., 0.]))
        self.assertEqual((smd["net_code"], smd["net_name"]), (None, ""))
        self.assertEqual((npth["drill_shape"], npth["drill_size_mm"], npth["net_name"]), ("oval", [.4, .7], ""))
        self.assertEqual(out["pads"]["connect"]["net_name"], "SIGNAL")

    def test_many_pads_tokenized_and_parsed_exactly_once_without_full_import(self):
        path, sha = self.source("\n".join(pad(f"id{i}") for i in range(200)),
                                vias="\n".join(via(f"via{i}") for i in range(100)))
        tokenize, parse = KicadParser.tokenize, KicadParser.parse_sexp
        counts = {"tokenize": 0, "parse": 0}
        def counted_tokenize(instance, text):
            counts["tokenize"] += 1
            return tokenize(instance, text)
        def counted_parse(instance, tokens):
            counts["parse"] += 1
            return parse(instance, tokens)
        with patch.object(KicadParser, "__init__", side_effect=AssertionError("full import must not run")), \
                patch.object(KicadParser, "tokenize", counted_tokenize), patch.object(KicadParser, "parse_sexp", counted_parse):
            out = read_kicad_board_pad_inventory(path, sha)
        self.assertEqual(out["pad_count"], 200)
        self.assertEqual(out["via_count"], 100)
        self.assertEqual(counts, {"tokenize": 1, "parse": 1})

    def test_native_via_evidence_types_and_source_binding(self):
        path, sha = self.source(vias=via(extra="(locked) (free no)") +
                                via("blind1", "blind", layers='"F.Cu" "In1.Cu"') +
                                via("micro1", "micro", layers='"F.Cu" "In1.Cu"'))
        before = path.read_bytes()
        out = read_kicad_board_pad_inventory(path, sha)
        self.assertEqual((out["pad_count"], out["via_count"]), (1, 3))
        self.assertEqual(out["vias"]["via1"], {"native_uuid": "via1", "source_sha256": sha,
                         "at_mm": [4., 5.], "size_mm": .6, "drill_mm": .3,
                         "layers": ["F.Cu", "B.Cu"], "via_kind": "through", "net_code": "3",
                         "locked": True, "free": False})
        self.assertEqual(out["vias"]["blind1"]["via_kind"], "blind")
        self.assertEqual(out["vias"]["micro1"]["via_kind"], "micro")
        self.assertEqual(path.read_bytes(), before)
        with patch.object(Path, "read_bytes", side_effect=[before, before.replace(b"(drill 0.3)", b"(drill 0.2)")]), \
                self.assertRaisesRegex(ValueError, "changed during"):
            read_kicad_board_pad_inventory(path, sha)

    def test_unsupported_native_via_geometry_and_identity_fail_closed(self):
        for extra in ("(padstack (mode front_inner_back))", "(backdrill (diameter .4))",
                      "(offset 0 0)", "(remove_unused_layers)", "(keep_end_layers yes)",
                      "(drill .2)", "(unknown_geometry .2)", "(free maybe)", "(size .7)"):
            path, sha = self.source(vias=via(extra=extra))
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                read_kicad_board_pad_inventory(path, sha)
        declarations = [via() + via(), via(identity="pth"), via().replace('(uuid "via1")', ''),
                        via().replace('(drill 0.3)', '(drill .3 (offset .1 0))'),
                        via().replace('(drill 0.3)', '(drill oval .3 .4)'),
                        via().replace('(size 0.6)', '(size .2)'),
                        via().replace('(size 0.6)', ''), via(kind="through"), via(kind="blind micro"),
                        via(layers='"F.Cu" "F.Cu"'), via(layers='"*.Cu" "B.Cu"'),
                        via().replace('(net 3)', '(net bad)'), via().replace('(at 4 5)', '(at nan 5)')]
        for declaration in declarations:
            path, sha = self.source(vias=declaration)
            with self.subTest(via=declaration), self.assertRaises(ValueError):
                read_kicad_board_pad_inventory(path, sha)

    def test_malformed_drill_and_nonzero_offset_rejected(self):
        for drill in ("(drill)", "(drill oval .4)", "(drill oval .4 .7 .8)", "(drill .4 .7)",
                      "(drill .4 unknown)", "(drill .4 (offset .01 0))", "(drill .4 (offset 0))",
                      "(drill .4 (offset 0 0) (offset 0 0))", "(drill .4 (plating .01))",
                      "(drill (offset 0 0) .4)", "(drill oval .4 (offset 0 0) .7)",
                      "(drill oval 0 .7)", "(drill nan)", "(drill -1)", ""):
            path, sha = self.source(pad(drill=drill))
            with self.subTest(drill=drill), self.assertRaises(ValueError):
                read_kicad_board_pad_inventory(path, sha)
        path, sha = self.source(pad(kind="smd"))
        with self.assertRaises(ValueError):
            read_kicad_board_pad_inventory(path, sha)

    def test_ambiguity_layer_policy_padstack_and_unknown_geometry_rejected(self):
        additions = ('(padstack (mode front_inner_back))', '(remove_unused_layers yes)',
                     '(remove_unused_layers)', '(remove_unused_layer)', '(keep_end_layers yes)',
                     '(keep_end_layers)', 'keep_end_layers', '(unreviewed_geometry 1)',
                     '(size 1 1)', '(uuid "second")', '(tstamp "second")',
                     '(remove_unused_layer no) (remove_unused_layers no)')
        for extra in additions:
            path, sha = self.source(pad(extra=extra))
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                read_kicad_board_pad_inventory(path, sha)
        for declarations in (pad() + pad(), pad().replace('(uuid "pth")', ''), pad(identity="")):
            path, sha = self.source(declarations)
            with self.subTest(declarations=declarations), self.assertRaises(ValueError):
                read_kicad_board_pad_inventory(path, sha)

    def test_shape_metadata_retained_and_custom_geometry_left_to_importer(self):
        path, sha = self.source(pad(kind="smd", shape="roundrect", drill="",
                                   extra='(roundrect_rratio .2) (chamfer_ratio .1) (chamfer top_left) '
                                         '(remove_unused_layers no) (keep_end_layers no)'))
        item = read_kicad_board_pad_inventory(path, sha)["pads"]["pth"]
        self.assertEqual(item["roundrect_rratio"], .2)
        self.assertEqual(item["chamfer_ratio"], .1)
        self.assertEqual(item["chamfer"], ["top_left"])
        self.assertEqual(item["keep_end_layers"], "no")
        path, sha = self.source(pad(kind="smd", shape="custom", drill="",
                                   extra='(options (clearance outline) (anchor rect)) '
                                         '(primitives (gr_poly (pts (xy 0 0) (xy 1 0) (xy 0 1)) (width 0)))'))
        item = read_kicad_board_pad_inventory(path, sha)["pads"]["pth"]
        self.assertEqual(item["shape"], "custom")
        self.assertNotIn("primitives", item)
        for extra in ('(roundrect_rratio nan)', '(chamfer_ratio 2)', '(chamfer unknown)', '(rect_delta 1)'):
            path, sha = self.source(pad(extra=extra))
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                read_kicad_board_pad_inventory(path, sha)

    def test_stale_hash_during_read_and_resource_limits_fail_closed(self):
        path, sha = self.source()
        with self.assertRaisesRegex(ValueError, "hash differs"):
            read_kicad_board_pad_inventory(path, "0" * 64)
        original = path.read_bytes()
        with patch.object(Path, "read_bytes", side_effect=[original, original + b" "]), \
                self.assertRaisesRegex(ValueError, "changed during"):
            read_kicad_board_pad_inventory(path, sha)
        with patch("python.spike_core.kicad_source_evidence.MAX_BOARD_INVENTORY_BYTES", len(original) - 1), \
                self.assertRaisesRegex(ValueError, "byte budget"):
            read_kicad_board_pad_inventory(path, sha)
        with patch("python.spike_core.kicad_source_evidence.MAX_SEXP_NODES", 2), \
                self.assertRaisesRegex(ValueError, "node budget"):
            read_kicad_board_pad_inventory(path, sha)

    def test_multiple_root_malformed_geometry_and_legacy_identity(self):
        path, sha = self.source(suffix="(kicad_pcb)")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            read_kicad_board_pad_inventory(path, sha)
        for text in (pad().replace("(size 1 1.2)", "(size 0 1)"),
                     pad().replace('(layers "*.Cu" "*.Mask")', '(layers "*.Cu" "*.Cu")'),
                     pad().replace('(net 1 "VDD")', '(net bad "VDD")'),
                     pad().replace('(at 1 2 30)', '(at inf 0)')):
            path, sha = self.source(text)
            with self.subTest(text=text), self.assertRaises(ValueError):
                read_kicad_board_pad_inventory(path, sha)
        path, sha = self.source(pad().replace('(uuid "pth")', '(tstamp "legacy")'))
        self.assertEqual(set(read_kicad_board_pad_inventory(path, sha)["pads"]), {"legacy"})


if __name__ == "__main__":
    unittest.main()
