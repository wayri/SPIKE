# SPDX-License-Identifier: Apache-2.0
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from spike_core.assistant_harness import HarnessError, MAX_FILE_BYTES, MAX_SCANNED_ENTRIES, handle_work_request
from spike_core import assistant_harness

REPOSITORY = Path(__file__).resolve().parents[2]


class AssistantHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=REPOSITORY)
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.assertTrue(self.root.resolve().is_relative_to(REPOSITORY.resolve()))
        self.temp.cleanup()

    def test_list_is_paged_bounded_and_does_not_disclose_hidden_or_secret_names(self):
        (self.root / "notes.md").write_text("notes", encoding="utf-8")
        (self.root / "data.csv").write_text("x\n1\n", encoding="utf-8")
        (self.root / ".env").write_text("PRIVATE", encoding="utf-8")
        (self.root / "credentials.json").write_text("PRIVATE", encoding="utf-8")
        result = handle_work_request(str(self.root), {"action": "list", "offset": 1, "limit": 1})
        self.assertEqual(result["scannedCount"], 4)
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["entries"]), 1)
        self.assertNotIn("PRIVATE", str(result))
        for index in range(MAX_SCANNED_ENTRIES + 1):
            (self.root / f"extra-{index}.txt").touch()
        with self.assertRaisesRegex(ValueError, "2000-entry"):
            handle_work_request(str(self.root), {"action": "list"})

    def test_read_returns_utf8_text_and_whole_source_provenance(self):
        raw = "bounded evidence\n".encode()
        (self.root / "notes.md").write_bytes(raw)
        result = handle_work_request(str(self.root), {"action": "read", "relativeName": "notes.md"})
        self.assertEqual(result["text"], raw.decode())
        self.assertEqual(result["source"], {"relativeName": "notes.md", "bytes": len(raw),
                                             "sha256": hashlib.sha256(raw).hexdigest(),
                                             "decodedTextSha256": hashlib.sha256(raw).hexdigest()})
        self.assertNotIn(str(self.root), str(result))

    @unittest.skipUnless(os.name == "nt", "Windows extended-path native picker regression")
    def test_native_picker_extended_root_supports_read_and_summary(self):
        (self.root / "native.csv").write_bytes(b"value_V\n3.2\n3.3\n3.4\n")
        root = "\\\\?\\" + str(self.root.resolve())
        result = handle_work_request(root, {"action": "read", "relativeName": "native.csv"})
        self.assertIn("3.3", result["text"])
        summary = handle_work_request(root, {"action": "csv_summary", "relativeName": "native.csv", "column": "value_V", "units": "V"})
        self.assertEqual(summary["statistics"]["count"], 3)
        self.assertAlmostEqual(summary["statistics"]["mean"], 3.3)
        outside = self.root.parent / "native-outside.csv"
        outside.write_bytes(b"x\n1\n")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        with patch.object(assistant_harness, "_final_handle_path", return_value=outside):
            with self.assertRaisesRegex(HarnessError, "outside"):
                handle_work_request(root, {"action": "read", "relativeName": "native.csv"})

    def test_utf8_bom_is_removed_but_raw_and_decoded_hashes_remain_distinct(self):
        canonical = "title\nvalue\n"
        raw = b"\xef\xbb\xbf" + canonical.encode("utf-8")
        (self.root / "bom.md").write_bytes(raw)
        read = handle_work_request(str(self.root), {"action": "read", "relativeName": "bom.md"})
        self.assertEqual(read["text"], canonical)
        self.assertEqual(read["source"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(read["source"]["decodedTextSha256"], hashlib.sha256(canonical.encode()).hexdigest())

        csv_text = "sample,current\n1,2\n2,4\n"
        csv_raw = b"\xef\xbb\xbf" + csv_text.encode("utf-8")
        (self.root / "bom.csv").write_bytes(csv_raw)
        summary = handle_work_request(str(self.root), {"action": "csv_summary", "relativeName": "bom.csv",
                                                        "column": "current", "units": "A"})
        self.assertEqual(summary["statistics"], {"count": 2, "min": 2.0, "max": 4.0, "mean": 3.0})
        self.assertEqual(summary["source"]["sha256"], hashlib.sha256(csv_raw).hexdigest())
        self.assertEqual(summary["source"]["decodedTextSha256"], hashlib.sha256(csv_text.encode()).hexdigest())

    def test_csv_summary_has_known_statistics_and_supplied_unit_provenance(self):
        raw = b"time,current\n0,1.5\n1,2.5\n2,5.0\n"
        (self.root / "measurements.csv").write_bytes(raw)
        result = handle_work_request(str(self.root), {"action": "csv_summary", "relativeName": "measurements.csv",
                                                       "column": "current", "units": "A"})
        self.assertEqual(result["statistics"], {"count": 3, "min": 1.5, "max": 5.0, "mean": 3.0})
        self.assertEqual(result["units"], {"value": "A", "provenance": "supplied"})
        self.assertEqual(result["source"]["sha256"], hashlib.sha256(raw).hexdigest())

    def test_invalid_paths_types_and_content_fail_closed(self):
        (self.root / "binary.txt").write_bytes(b"a\0b")
        (self.root / "bad.txt").write_bytes(b"\xff")
        (self.root / "image.png").write_bytes(b"png")
        (self.root / "config.json").write_text("{}", encoding="utf-8")
        outside = self.root.parent / "outside-assistant-harness.txt"
        outside.write_text("outside", encoding="utf-8")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        for name in ("../outside-assistant-harness.txt", str(outside), "binary.txt", "bad.txt", "image.png", "config.json"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                handle_work_request(str(self.root), {"action": "read", "relativeName": name})
        with self.assertRaises(ValueError):
            handle_work_request(str(self.root), {"action": "list", "limit": 201})
        with self.assertRaises(ValueError):
            handle_work_request(str(self.root), {"action": "read", "relativeName": "notes.md", "path": "x"})
        missing_root = self.root / "missing-root"
        with self.assertRaises(HarnessError) as raised:
            handle_work_request(str(missing_root), {"action": "list"})
        self.assertNotIn(str(missing_root), str(raised.exception))
        for name in ("C:drive-relative.txt", "notes.txt:secret", "control\x01.txt"):
            with self.subTest(name=name), self.assertRaises(HarnessError):
                handle_work_request(str(self.root), {"action": "read", "relativeName": name})

    def test_directory_scan_stops_after_cap_plus_one(self):
        class Entries:
            def __init__(self):
                self.count = 0
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False
            def __iter__(self):
                return self
            def __next__(self):
                self.count += 1
                if self.count > MAX_SCANNED_ENTRIES + 100:
                    raise AssertionError("directory enumeration was not bounded")
                return object()
        entries = Entries()
        with patch.object(assistant_harness.os, "scandir", return_value=entries):
            with self.assertRaisesRegex(HarnessError, "2000-entry"):
                handle_work_request(str(self.root), {"action": "list"})
        self.assertEqual(entries.count, MAX_SCANNED_ENTRIES + 1)

    def test_open_handle_outside_root_is_rejected_before_read(self):
        source = self.root / "notes.txt"
        source.write_text("must not be returned", encoding="utf-8")
        outside_temp = tempfile.TemporaryDirectory(dir=REPOSITORY)
        self.addCleanup(outside_temp.cleanup)
        outside = Path(outside_temp.name) / "other.txt"
        outside.write_text("outside", encoding="utf-8")
        with patch.object(assistant_harness, "_final_handle_path", return_value=outside):
            with self.assertRaisesRegex(HarnessError, "outside the work folder"):
                handle_work_request(str(self.root), {"action": "read", "relativeName": "notes.txt"})

    def test_oversized_file_is_rejected_without_partial_read(self):
        (self.root / "large.log").write_bytes(b"x" * (MAX_FILE_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "256 KiB"):
            handle_work_request(str(self.root), {"action": "read", "relativeName": "large.log"})

    def test_file_read_uses_a_bounded_single_handle(self):
        source = self.root / "bounded.txt"
        source.write_text("bounded", encoding="utf-8")
        underlying = source.open("rb")
        requested = []
        class Stream:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                underlying.close()
            def fileno(self):
                return underlying.fileno()
            def read(self, size):
                requested.append(size)
                return underlying.read(size)
        with patch.object(Path, "open", return_value=Stream()):
            result = handle_work_request(str(self.root), {"action": "read", "relativeName": "bounded.txt"})
        self.assertEqual(result["text"], "bounded")
        self.assertEqual(requested, [MAX_FILE_BYTES + 1])

    def test_csv_rejects_ambiguous_or_invalid_numeric_data(self):
        cases = {
            "duplicate.csv": "x,x\n1,2\n",
            "missing-column.csv": "x\n1\n",
            "missing-cell.csv": "x,y\n1,\n",
            "nonfinite.csv": "x\nNaN\n",
            "overflow.csv": "x\n1e308\n1e308\n",
            "ragged.csv": "x,y\n1\n",
            "empty.csv": "x\n",
        }
        for name, content in cases.items():
            (self.root / name).write_text(content, encoding="utf-8")
            column = "absent" if name == "missing-column.csv" else "x" if name != "missing-cell.csv" else "y"
            with self.subTest(name=name), self.assertRaises(ValueError):
                handle_work_request(str(self.root), {"action": "csv_summary", "relativeName": name,
                                                     "column": column, "units": "V"})

    def test_symlink_or_junction_cannot_escape(self):
        outside_temp = tempfile.TemporaryDirectory(dir=REPOSITORY)
        self.addCleanup(outside_temp.cleanup)
        outside = Path(outside_temp.name)
        (outside / "secret.txt").write_text("secret", encoding="utf-8")
        link = self.root / "escape"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                raise
            self.skipTest("Windows symlink creation is unavailable")
        listing = handle_work_request(str(self.root), {"action": "list"})
        self.assertIn({"name": "escape", "type": "link"}, listing["entries"])
        with self.assertRaisesRegex(ValueError, "Symlinks and junctions"):
            handle_work_request(str(self.root), {"action": "read", "relativeName": "escape/secret.txt"})


if __name__ == "__main__":
    unittest.main()
