# SPDX-License-Identifier: Apache-2.0
"""Focused tests for digest-approved component compilation."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "standalone/spikes_project/studio/python"))

from spikes_studio.component_build import build_component
from spikes_studio.component_package import (
    behavior_digest,
    controller_config,
    new_component,
)
from spikes_studio.ide import find_tool


CPP_SOURCE = """void control_step(double time_s, double step_s,
                  const double *inputs, double *outputs, double *state) {
    (void)time_s; (void)step_s; (void)state;
    outputs[0] = inputs[0];
}
"""


def cpp_component(source=CPP_SOURCE):
    value = new_component()
    value["id"] = "user.cpp_component"
    value["implementation"] = {
        "language": "C++",
        "entry": "control_step",
        "source": source,
        "controller": controller_config(value["symbol"], source),
    }
    return value


def verilog_component(source="module passthrough(input IN, output OUT); assign OUT = IN; endmodule\n"):
    value = new_component()
    value["id"] = "user.verilog_component"
    value["implementation"] = {
        "language": "Verilog",
        "entry": "passthrough",
        "source": source,
    }
    return value


def spice_component(source):
    value = new_component()
    value["implementation"]["source"] = source
    return value


class ComponentBuildTests(unittest.TestCase):
    def test_spice_preflight_packages_exact_source_without_mutating_input(self):
        value = new_component()
        original = deepcopy(value)
        digest = behavior_digest(value)
        with tempfile.TemporaryDirectory() as directory:
            report = build_component(value, directory, trusted=True, approval_sha256=digest)
            artifact = Path(report["artifact_path"])
            metadata = json.loads((artifact.parent / "component.spice.metadata.json").read_text())
            self.assertEqual(report["status"], "preflighted")
            self.assertEqual(report["behavior_sha256"], digest)
            self.assertFalse(report["qualified"])
            self.assertEqual(artifact.read_text(encoding="utf-8"), value["implementation"]["source"])
            self.assertEqual(report["artifact_sha256"], hashlib.sha256(artifact.read_bytes()).hexdigest())
            self.assertEqual(metadata["artifact_sha256"], report["artifact_sha256"])
            repeated = build_component(value, directory, trusted=True, approval_sha256=digest)
            self.assertEqual(repeated["artifact_path"], report["artifact_path"])
        self.assertEqual(value, original)

    def test_build_refuses_unowned_content_addressed_output(self):
        value = new_component()
        digest = behavior_digest(value)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / f"{value['id']}--{value['version']}--{digest[:12]}"
            output.mkdir()
            unrelated = output / "component.spice"
            unrelated.write_text("unrelated user file", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not owned"):
                build_component(value, directory, trusted=True, approval_sha256=digest)
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "unrelated user file")

    def test_version_bump_keeps_old_build(self):
        value=new_component();digest=behavior_digest(value)
        with tempfile.TemporaryDirectory() as directory:
            first=build_component(value,directory,trusted=True,approval_sha256=digest)
            value['version']='1.0.1'
            second=build_component(value,directory,trusted=True,approval_sha256=digest)
            self.assertNotEqual(first['artifact_path'],second['artifact_path'])
            self.assertTrue(Path(first['artifact_path']).is_file())

    def test_spice_preflight_rejects_early_end_without_changing_source(self):
        value = spice_component(
            ".subckt UserPart IN OUT\nR1 IN OUT 1k\n.ends UserPart\n.end\n"
        )
        original = deepcopy(value)
        with tempfile.TemporaryDirectory() as directory:
            report = build_component(value, directory, trusted=True,
                                     approval_sha256=behavior_digest(value))
            self.assertEqual(report["status"], "failed")
            self.assertIsNone(report["artifact_path"])
            self.assertIn("analyses/global/host directives", report["log"])
            self.assertEqual(list(Path(directory).iterdir()), [])
        self.assertEqual(value, original)

    def test_spice_preflight_rejects_top_level_testbench_without_changing_source(self):
        value = spice_component(
            ".subckt UserPart IN OUT\nR1 IN OUT 1k\n.ends UserPart\nVTEST IN 0 1\n"
        )
        original = deepcopy(value)
        with tempfile.TemporaryDirectory() as directory:
            report = build_component(value, directory, trusted=True,
                                     approval_sha256=behavior_digest(value))
            self.assertEqual(report["status"], "failed")
            self.assertIsNone(report["artifact_sha256"])
            self.assertIn("top-level testbench", report["log"])
            self.assertEqual(list(Path(directory).iterdir()), [])
        self.assertEqual(value, original)

    def test_spice_preflight_rejects_include_before_parser_file_access(self):
        value = spice_component(
            ".subckt UserPart IN OUT\nR1 IN OUT 1k\n.ends UserPart\n.include missing.lib\n"
        )
        original = deepcopy(value)
        with tempfile.TemporaryDirectory() as directory, \
                patch("python.spikes.netlist.parse_netlist") as parser:
            report = build_component(value, directory, trusted=True,
                                     approval_sha256=behavior_digest(value))
            self.assertEqual(report["status"], "failed")
            self.assertIn("analyses/global/host directives", report["log"])
            parser.assert_not_called()
        self.assertEqual(value, original)

    def test_trust_and_exact_digest_gate_precede_tool_discovery(self):
        value = verilog_component()
        digest = behavior_digest(value)
        with tempfile.TemporaryDirectory() as directory, patch("spikes_studio.ide.find_tool") as discover:
            with self.assertRaisesRegex(ValueError, "trusted-code consent"):
                build_component(value, directory, approval_sha256=digest)
            with self.assertRaisesRegex(ValueError, "does not match"):
                build_component(value, directory, trusted=True, approval_sha256="0" * 64)
            discover.assert_not_called()

    def test_missing_compiler_is_explicit(self):
        value = verilog_component()
        with tempfile.TemporaryDirectory() as directory, patch("spikes_studio.ide.find_tool", return_value=None):
            with self.assertRaisesRegex(ValueError, "iverilog is not installed/configured"):
                build_component(value, directory, trusted=True,
                                approval_sha256=behavior_digest(value))

    @unittest.skipUnless(find_tool("clang++") or find_tool("cl"), "C++ compiler unavailable")
    def test_real_cpp_build_copies_but_does_not_execute_controller(self):
        value = cpp_component()
        original = deepcopy(value)
        with tempfile.TemporaryDirectory() as directory:
            report = build_component(value, directory, trusted=True,
                                     approval_sha256=behavior_digest(value))
            self.assertEqual(report["status"], "built", report["log"])
            self.assertTrue(Path(report["artifact_path"]).is_file())
            self.assertFalse(report["qualified"])
            metadata = json.loads((Path(report["artifact_path"]).parent /
                                   "component-controller.metadata.json").read_text())
            self.assertEqual(metadata["compiled_block_manifest"]["executable_sha256"],
                             report["artifact_sha256"])
        self.assertEqual(value, original)

    @unittest.skipUnless(find_tool("clang++") or find_tool("cl"), "C++ compiler unavailable")
    def test_cpp_compiler_error_is_structured(self):
        value = cpp_component("void control_step( this is not valid C++")
        with tempfile.TemporaryDirectory() as directory:
            report = build_component(value, directory, trusted=True,
                                     approval_sha256=behavior_digest(value))
            self.assertEqual(report["status"], "failed")
            self.assertIsNone(report["artifact_path"])
            self.assertTrue(report["log"])

    @unittest.skipUnless(find_tool("iverilog"), "iverilog unavailable")
    def test_real_verilog_build_produces_compile_only_vvp(self):
        value = verilog_component()
        original = deepcopy(value)
        with tempfile.TemporaryDirectory() as directory:
            report = build_component(value, directory, trusted=True,
                                     approval_sha256=behavior_digest(value))
            self.assertEqual(report["status"], "built", report["log"])
            self.assertEqual(Path(report["artifact_path"]).name, "block.vvp")
            self.assertTrue(Path(report["artifact_path"]).is_file())
            self.assertFalse(report["qualified"])
        self.assertEqual(value, original)

    @unittest.skipUnless(find_tool("iverilog"), "iverilog unavailable")
    def test_verilog_compiler_error_is_structured(self):
        value = verilog_component("module passthrough(input IN, output OUT); this is invalid endmodule\n")
        with tempfile.TemporaryDirectory() as directory:
            report = build_component(value, directory, trusted=True,
                                     approval_sha256=behavior_digest(value))
            self.assertEqual(report["status"], "failed")
            self.assertIsNone(report["artifact_sha256"])
            self.assertTrue(report["log"])


if __name__ == "__main__":
    unittest.main()
