# SPDX-License-Identifier: Apache-2.0
"""Independent fixtures for inert local LTspice declaration indexing."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "studio" / "python"))
from spikes_studio.ltspice_local_library import index_library,read_model_declaration,read_model_file


class LTspiceLocalLibraryTests(unittest.TestCase):
    def test_duplicates_continuations_and_subckt_terminals(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/"a").mkdir();(root/"b").mkdir()
            first=("* independently authored syntax fixture\n"
                   ".subckt DUP IN OUT VPLUS\n+ VMINUS params: gain=10\n"
                   "+ offset=0\nR1 IN OUT 1k\n.ends DUP\n"
                   ".model EDGE\n+ NMOS(VTO=1)\n")
            second=".subckt DUP A B PARAMS: R=1k\n.ends\n.model EDGE D(Is=1p)\n"
            (root/"a"/"one.lib").write_text(first,encoding="utf-8")
            (root/"b"/"two.sub").write_text(second,encoding="utf-8")
            index=index_library(root)
            duplicates=[item for item in index["models"] if item["name"]=="DUP"]
            self.assertEqual(len(duplicates),2)
            self.assertEqual({item["source_path"] for item in duplicates},{"a/one.lib","b/two.sub"})
            pins={item["source_path"]:item["pins"] for item in duplicates}
            self.assertEqual(pins["a/one.lib"],["IN","OUT","VPLUS","VMINUS"])
            self.assertEqual(pins["b/two.sub"],["A","B"])
            self.assertEqual(len({item["id"] for item in index["models"]}),4)
            self.assertNotIn("R1 IN OUT",json.dumps(index))
            self.assertEqual(index["status"]["execution"],"not_executed")

    def test_asy_metadata_is_separate_from_model_declarations(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);symbol=root/"device.asy";(root/"sub").mkdir()
            (root/"sub"/"demo.lib").write_text(
                ".subckt DEMO_CORE A B\n.ends DEMO_CORE\n",encoding="utf-8")
            symbol.write_text("Version 4\nSymbolType CELL\nSYMATTR Prefix X\n"
                              "SYMATTR Value DEMO\nSYMATTR SpiceModel DEMO_CORE\n"
                              "SYMATTR ModelFile demo.lib\n",encoding="utf-8")
            index=index_library(root)
            self.assertEqual(len(index["models"]),1);self.assertEqual(len(index["symbols"]),1)
            item=index["symbols"][0]
            self.assertEqual((item["symbol_type"],item["prefix"],item["value"]),("CELL","X","DEMO"))
            self.assertEqual((item["spice_model"],item["model_file"]),("DEMO_CORE","demo.lib"))
            self.assertEqual(item["sha256"],hashlib.sha256(symbol.read_bytes()).hexdigest())
            self.assertEqual(item["dependency"]["model_ids"],[index["models"][0]["id"]])

    def test_symlinks_and_size_limits_are_explicit(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as outside:
            root=Path(folder);external=Path(outside)/"secret.lib"
            external.write_text(".model SECRET D\n",encoding="utf-8")
            (root/"large.lib").write_text(".model TOO_BIG D\n",encoding="utf-8")
            try:(root/"linked.lib").symlink_to(external)
            except OSError:linked=False
            else:linked=True
            index=index_library(root,max_file_bytes=8)
            self.assertEqual(index["models"],[])
            self.assertIn("file_too_large",{item["code"] for item in index["diagnostics"]})
            if linked:self.assertIn("link_skipped",{item["code"] for item in index["diagnostics"]})
            limited=index_library(root,max_files=1,max_file_bytes=1024)
            self.assertLessEqual(len(limited["files"]),1)
            byte_limited=index_library(root,max_total_bytes=8,max_file_bytes=1024)
            self.assertFalse(byte_limited["status"]["complete"])
            (root/"many.mod").write_text(".model A D\n.model B D\n",encoding="utf-8")
            entry_limited=index_library(root,max_entries=1,max_file_bytes=1024)
            self.assertFalse(entry_limited["status"]["complete"])
            self.assertLessEqual(len(entry_limited["models"])+len(entry_limited["symbols"]),1)
            with self.assertRaises(ValueError):index_library(root,max_entries=0)

    def test_indexing_never_starts_a_process_or_emits_raw_body(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/"device.cir").write_text(
                ".subckt SAFE P N\nBSECRET P N V=table(V(P),0,0,1,1)\n.ends\n",encoding="utf-8")
            with patch("subprocess.Popen",side_effect=AssertionError("execution attempted")):
                index=index_library(root)
            encoded=json.dumps(index)
            self.assertNotIn("BSECRET",encoded)
            self.assertEqual(index["models"][0]["pins"],["P","N"])
            self.assertIn("may not run in SPIKES",index["notice"])
            json.loads(encoded)

    def test_selected_file_review_revalidates_hash_and_returns_full_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/"review.lib"
            text=".model FIRST D(Is=1p)\n.model SECOND D(Is=2p)\n"
            source.write_text(text,encoding="utf-8");index=index_library(root)
            self.assertEqual(read_model_file(index,index["models"][0]["id"]),source.read_bytes().decode("utf-8"))
            source.write_text(".model CHANGED D\n",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"changed since indexing"):
                read_model_file(index,index["models"][0]["id"])

    def test_intrinsic_declaration_preserves_continuations_and_rejects_ambiguity(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/"models.mod"
            source.write_text("* lead\n.model ONLY NMOS(VTO=1\n\n* retained note\n+ KP=2m)\nR1 A B 1k\n",encoding="utf-8")
            index=index_library(root);entry=index["models"][0]
            raw=source.read_bytes().decode("utf-8").splitlines(keepends=True)
            self.assertEqual(read_model_declaration(index,entry["id"]),"".join(raw[1:5]))
            source.write_text(".model DUP D(Is=1p)\n.model DUP D(Is=2p)\n",encoding="utf-8")
            duplicate=index_library(root)
            with self.assertRaisesRegex(ValueError,"ambiguous within"):
                read_model_declaration(duplicate,duplicate["models"][0]["id"])
            sub=root/"part.sub";sub.write_text(".subckt BLOCK A B\n.ends\n",encoding="utf-8")
            mixed=index_library(root);subckt=next(item for item in mixed["models"] if item["kind"]=="subckt")
            with self.assertRaisesRegex(ValueError,"dependency-aware"):
                read_model_declaration(mixed,subckt["id"])

    def test_bomless_utf16le_models_symbols_and_review_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/"sub").mkdir()
            model_text=".model UTFPART NPN(Is=1f\r\n+ Bf=100)\r\n"
            model=root/"sub"/"utf.mod";model.write_bytes(model_text.encode("utf-16-le"))
            symbol_text=("Version 4\r\nSymbolType CELL\r\nSYMATTR Prefix Q\r\n"
                         "SYMATTR Value UTFPART\r\nSYMATTR SpiceModel UTFPART\r\n"
                         "SYMATTR ModelFile utf.mod\r\n")
            (root/"utf.asy").write_bytes(symbol_text.encode("utf-16-le"))
            index=index_library(root);entry=index["models"][0]
            self.assertEqual(entry["name"],"UTFPART")
            self.assertEqual(read_model_file(index,entry["id"]),model_text)
            self.assertEqual(read_model_declaration(index,entry["id"]),model_text)
            self.assertEqual(index["symbols"][0]["dependency"]["model_ids"],[entry["id"]])
            self.assertEqual(entry["sha256"],hashlib.sha256(model.read_bytes()).hexdigest())
            self.assertTrue(any(item["code"]=="encoding_fallback" for item in index["diagnostics"]))

    def test_malformed_binary_remains_diagnostic(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/"bad.lib").write_bytes(b".\x00m\x00o\x00d\x00e\x00l\x00 \x00X")
            index=index_library(root)
            self.assertEqual(index["models"],[])
            self.assertIn("binary_skipped",{item["code"] for item in index["diagnostics"]})

    def test_walk_budget_bounds_directory_enumeration_before_sorting(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for number in range(10):(root/f"{number}.txt").write_text("ignored",encoding="utf-8")
            real_scandir=self.module_scandir=__import__("os").scandir;count=[0]
            class CountingScandir:
                def __init__(self,path):self.inner=real_scandir(path)
                def __enter__(self):return self
                def __exit__(self,*args):self.inner.close()
                def __iter__(self):return self
                def __next__(self):
                    item=next(self.inner);count[0]+=1;return item
            with patch("spikes_studio.ltspice_local_library.os.scandir",CountingScandir):
                index=index_library(root,max_walk_entries=3)
            self.assertEqual(count[0],3);self.assertFalse(index["status"]["complete"])


if __name__ == "__main__":
    unittest.main()
