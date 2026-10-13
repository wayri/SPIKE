# SPDX-License-Identifier: Apache-2.0
"""Snapshot identity, bounded protocol and real worker/extension checks."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "integrations" / "prism"
SPIKE = Path(os.environ.get("SPIKE_PRISM_TEST_ROOT", str(ROOT))).resolve()
sys.path.insert(0, str(SPIKE)); sys.path.insert(0, str(PACKAGE))
import bridge
import extension


BOARD = '''(kicad_pcb (version 20240108) (generator "prism-original-test")
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
  (setup (stackup
    (layer "F.Cu" (type "copper") (thickness 0.035))
    (layer "dielectric 1" (type "core") (thickness 1.53) (epsilon_r 4.2))
    (layer "B.Cu" (type "copper") (thickness 0.035))))
  (net 0 "") (net 1 "VCC")
  (segment (start 0 0) (end 10 0) (width 1) (layer "F.Cu") (net 1)
    (uuid "10000000-0000-4000-8000-000000000001"))
  (gr_rect (start -1 -1) (end 11 1) (stroke (width 0.05) (type default))
    (fill none) (layer "Edge.Cuts") (uuid "10000000-0000-4000-8000-000000000002")))
'''


def source(text=BOARD):
    return {"file_name": "Fixture.kicad_pcb", "encoding": "utf-8", "data": text,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def spec():
    return {"contract": "spike/v1", "analysis_id": "prism-fixture", "mode": "dc",
            "solver_id": "spike.routed_dc", "formulation": "resistive_network", "net_names": ["VCC"],
            "sources": [{"id": "source", "position_mm": [0, 0], "layer": "F.Cu", "voltage_v": 5.}],
            "loads": [{"id": "load", "position_mm": [10, 0], "layer": "F.Cu", "current_a": 1.}],
            "return_path": {"mode": "implicit"}, "probes": [], "mesh": {"target_size_mm": 2.},
            "limits": {}, "options": {}}


def request(operation="analyze"):
    value = {"contract": bridge.REQUEST_CONTRACT, "api_version": 1,
             "request_id": "fixture-1", "operation": operation}
    if operation != "capabilities": value["source"] = source()
    if operation == "analyze": value["analysis_spec"] = spec()
    return value


def fake_import(path):
    payload = Path(path).read_bytes()
    return {"contract": "spike/v1", "design_id": "fixture", "name": "Fixture", "units": "mm",
            "source_format": "kicad", "layers": [], "nets": [], "vias": [], "pads": [], "zones": [], "stackup": [],
            "source_path": path, "metadata": {"source_sha256": hashlib.sha256(payload).hexdigest()},
            "tracks": [{"uuid": "track-1", "start": [1., 2.], "end": [3., 4.], "layer": "F.Cu"}],
            "components": [], "issues": []}


def raw_result():
    return {"contract": "spike/v1", "analysis_id": "fixture", "mode": "dc", "status": "completed",
            "model_status": "approximate", "summary": {"value": 1.}, "fields": {"raw": [1., 2.]},
            "networks": {}, "probes": [], "issues": [{"code": "APPROXIMATE", "severity": "warning", "message": "Fixture status"}],
            "provenance": {"solver": "fixture/1"}}


def dispatch(call):
    if call["method"] == "run_preflighted_analysis":
        return {"ok": True, "result": {"contract": "spike/preflighted-analysis/v1", "status": "completed",
                "preflight": {"can_solve": True, "issues": []}, "analysis_result": raw_result()}}
    return {"ok": True, "result": {"method": call["method"], "model_status": "unsupported"}}


class PrismBridgeTests(unittest.TestCase):
    def test_snapshot_exact_utf8_crlf_and_temporary_file_cleanup(self):
        observed = []
        snapshot = source(BOARD.replace("\n", "\r\n") + '; UTF-8: \u03bc\n')
        def importer(path):
            observed.append(path)
            self.assertEqual(Path(path).read_bytes(), snapshot["data"].encode("utf-8"))
            return fake_import(path)
        result = bridge.execute({**request("inspect-board"), "source": snapshot}, importer=importer)
        self.assertFalse(Path(observed[0]).exists())
        self.assertEqual(result["design"]["source_path"], "Fixture.kicad_pcb")
        self.assertEqual(result["design"]["tracks"][0]["uuid"], "track-1")
        self.assertEqual(result["design"]["tracks"][0]["start"], [1., 2.])
        self.assertEqual(result["source_binding"]["sha256"], snapshot["sha256"])

    def test_source_only_model_resolution_is_deterministic_across_machines(self):
        def importer(resolved):
            def load(path):
                value = fake_import(path)
                value["components"] = [{"id": "U1", "model_path": "${KICAD10_3DMODEL_DIR}/Package.step", "model_resolved": resolved}]
                return value
            return load
        a = bridge.execute(request("inspect-board"), importer=importer("C:/KiCad/models/Package.step"))
        b = bridge.execute(request("inspect-board"), importer=importer("/usr/share/kicad/models/Package.step"))
        self.assertEqual(a["design_binding"], b["design_binding"])
        self.assertEqual(a["design"]["components"][0]["model_resolved"], "")
        self.assertIn("KICAD10_3DMODEL_DIR", a["design"]["components"][0]["model_path"])
        self.assertFalse(a["design"]["metadata"]["prism_snapshot_policy"]["dependent_3d_assets_supplied"])
        self.assertEqual(a["design"]["issues"][-1]["code"], "PRISM_DEPENDENT_ASSETS_OMITTED")

    def test_only_allowlisted_worker_methods_are_called_and_raw_result_is_preserved(self):
        calls = []
        def worker(call): calls.append(copy.deepcopy(call)); return dispatch(call)
        study = request(); original = copy.deepcopy(study)
        result = bridge.execute(study, dispatch=worker, importer=fake_import)
        self.assertEqual([call["method"] for call in calls], ["run_preflighted_analysis"])
        self.assertEqual(calls[0]["params"]["spec"], study["analysis_spec"])
        produced = result["analysis"]["analysis_result"]
        self.assertEqual({k: v for k, v in produced.items() if k != "provenance"},
                         {k: v for k, v in raw_result().items() if k != "provenance"})
        self.assertEqual(produced["provenance"]["solver"], "fixture/1")
        self.assertEqual(produced["provenance"]["input_analysis_spec_sha256"], bridge.digest(spec()))
        self.assertEqual(produced["provenance"]["input_source_sha256"], study["source"]["sha256"])
        self.assertEqual(study, original)
        calls.clear(); capabilities = bridge.execute(request("capabilities"), dispatch=worker)
        self.assertEqual([call["method"] for call in calls], ["capabilities", "list_solvers"])
        self.assertEqual(capabilities["capabilities"]["capabilities"]["model_status"], "unsupported")
        with self.assertRaisesRegex(ValueError, "not allowed"):
            bridge._call("run_script", {}, worker)

    def test_failed_and_preflight_blocked_statuses_are_not_promoted(self):
        failed = {**raw_result(), "status": "failed_to_converge", "model_status": "unsupported"}
        payload = {"contract": "spike/preflighted-analysis/v1", "status": "blocked",
                   "preflight": {"can_solve": False, "issues": [{"code": "LOAD_REQUIRED"}]}, "analysis_result": failed}
        result = bridge.execute(request(), dispatch=lambda call: {"ok": True, "result": payload}, importer=fake_import)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["analysis"]["preflight"], payload["preflight"])
        self.assertEqual({k: v for k, v in result["analysis"]["analysis_result"].items() if k != "provenance"},
                         {k: v for k, v in failed.items() if k != "provenance"})
        self.assertEqual(payload["analysis_result"]["provenance"], {"solver": "fixture/1"})
        error = {"ok": False, "error": "Missing runtime", "error_detail": {"suggestion": "Install approved runtime"}}
        self.assertEqual(bridge.execute(request(), dispatch=lambda call: error, importer=fake_import)["error"], error)

    def test_strict_request_snapshot_and_explicit_spec_rejections(self):
        variants = []
        for key, value in (("api_version", True), ("operation", ["analyze"]), ("request_id", {}), ("worker_method", "run_script")):
            variants.append({**request(), key: value})
        value = request(); value.pop("analysis_spec"); variants.append(value)
        value = request(); value["analysis_spec"]["inferred_terminal"] = True; variants.append(value)
        value = request("capabilities"); value["source"] = source(); variants.append(value)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ValueError):
                bridge.execute(value, dispatch=dispatch, importer=fake_import)
        for change in ({"file_name": "../bad.kicad_pcb"}, {"file_name": "CON.kicad_pcb"}, {"sha256": "0" * 64},
                       {"encoding": "base64"}, {"data": ""}, {"data": "\ud800"}, {"extra": True}):
            with self.subTest(change=change), self.assertRaises(ValueError): bridge.snapshot({**source(), **change})

    def test_malformed_spec_entries_reject_before_dispatch_and_cli_writes_error(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "request.json"; result_path = Path(directory) / "result.json"
            for key, entry in (("sources", "voltage_v"), ("loads", "current_a"), ("probes", None),
                               ("net_names", {}), ("required_capabilities", 42)):
                study = request(); study["analysis_spec"][key] = [entry]
                with self.subTest(key=key), patch.object(bridge, "_call") as worker:
                    with self.assertRaisesRegex(ValueError, "entries must"):
                        bridge.execute(study, importer=fake_import)
                    worker.assert_not_called()
                    bridge.write_json(input_path, study)
                    self.assertEqual(bridge.main(["--request", str(input_path), "--result", str(result_path)]), 2)
                    result = bridge.read_json(result_path)
                    self.assertEqual(result["status"], "error")
                    self.assertIn("AnalysisSpec." + key, result["error"]["message"])

    def test_malformed_terminal_positions_reject_before_dispatch(self):
        for field in ("position_mm", "at"):
            for point in ([0], [0, 1, 2, 3], "0,0", {"x": 0}, {"x": False, "y": 0}, [0, "0"]):
                study = request(); study["analysis_spec"]["sources"][0][field] = point
                with self.subTest(field=field, point=point), patch.object(bridge, "_call") as worker:
                    with self.assertRaisesRegex(ValueError, field): bridge.execute(study, importer=fake_import)
                    worker.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "request.json"; result_path = Path(directory) / "result.json"
            study = request(); study["analysis_spec"]["sources"][0]["position_mm"] = [0]
            bridge.write_json(input_path, study)
            self.assertEqual(bridge.main(["--request", str(input_path), "--result", str(result_path)]), 2)
            self.assertEqual(bridge.read_json(result_path)["status"], "error")
            bridge.write_json(input_path, request())
            with patch.object(bridge, "execute", side_effect=IndexError("worker fixture failure")):
                self.assertEqual(bridge.main(["--request", str(input_path), "--result", str(result_path)]), 2)
            self.assertIn("worker fixture failure", bridge.read_json(result_path)["error"]["message"])

    def test_bounded_finite_json_duplicate_keys_and_depth(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}', '{"x":{"a":1,"a":2}}'):
                path.write_text(text, encoding="utf-8")
                with self.subTest(text=text), self.assertRaises(ValueError): bridge.read_json(path)
            path.write_text('"' + "a" * 128 + '"', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "byte limit"): bridge.read_json(path, limit=16)
        nested = None
        for _ in range(33): nested = [nested]
        with self.assertRaisesRegex(ValueError, "32 levels"): bridge.finite_tree(nested)
        with patch.object(bridge, "MAX_SOURCE_BYTES", 8), self.assertRaisesRegex(ValueError, "32 MiB"):
            bridge.snapshot(source())
        with patch.object(bridge, "MAX_EXCHANGE_BYTES", 8), self.assertRaisesRegex(ValueError, "64 MiB"):
            bridge._encoded({"long": "value"})

    def test_atomic_output_collision_alias_and_failed_write_preserve_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"; path.write_bytes(b"original")
            with self.assertRaisesRegex(ValueError, "overwrite"): bridge.write_json(path, {}, protected=(path,))
            alias = Path(directory) / "alias.json"; os.link(path, alias)
            with self.assertRaisesRegex(ValueError, "overwrite"): bridge.check_output(alias, (path,))
            result = Path(directory) / "result.json"; result.write_bytes(b"old result")
            with patch.object(bridge.os, "replace", side_effect=OSError("simulated disk failure")), self.assertRaises(OSError):
                bridge.write_json(result, {"new": 1})
            self.assertEqual(path.read_bytes(), b"original")
            self.assertEqual(result.read_bytes(), b"old result")
            self.assertFalse(list(Path(directory).glob("*.tmp")))
            bridge.write_json(result, {"completed": True})
            self.assertEqual(bridge.read_json(result), {"completed": True})

    def test_bound_result_import_rejects_board_settings_and_raw_provenance_tampering(self):
        from python.spike_core.extension_analysis_results import design_binding
        exchange = bridge.execute(request(), dispatch=dispatch, importer=fake_import)
        design = exchange["design"]; binding = design_binding(design); expected = bridge.digest(spec())
        result = bridge.admit_exchange(exchange, design, binding, expected_spec_digest=expected)
        self.assertEqual(result["fields"], raw_result()["fields"])
        self.assertEqual(result["issues"], raw_result()["issues"])
        self.assertEqual(result["model_status"], "approximate")
        self.assertEqual(result["provenance"]["extension_id"], "spike.prism-bridge")
        for mutator in (lambda x: x["design"]["tracks"][0].update(start=[9.,9.]),
                        lambda x: x["analysis_spec"].update(mode="ac"),
                        lambda x: x["source_binding"].update(sha256="0"*64),
                        lambda x: x["analysis"]["analysis_result"]["provenance"].update(design_digest_sha256="0"*64)):
            wrong = copy.deepcopy(exchange); mutator(wrong)
            with self.assertRaises(ValueError): bridge.admit_exchange(wrong, design, binding, expected_spec_digest=expected)
        with self.assertRaisesRegex(ValueError, "stale"): bridge.admit_exchange(exchange, design, binding, expected_spec_digest="0"*64)
        with self.assertRaisesRegex(ValueError, "current explicit"): bridge.admit_exchange(exchange, design, binding, expected_spec_digest=None)
        blocked = copy.deepcopy(exchange); blocked["status"] = "blocked"
        with self.assertRaisesRegex(ValueError, "blocked/failed"): bridge.admit_exchange(blocked, design, binding, expected_spec_digest=expected)

    def test_production_rejects_conflicting_existing_bindings_and_never_mutates_worker_result(self):
        payload = dispatch({"method": "run_preflighted_analysis"})
        payload["result"]["analysis_result"]["provenance"]["input_analysis_spec_sha256"] = "0" * 64
        original = copy.deepcopy(payload)
        with self.assertRaisesRegex(ValueError, "conflicting production provenance"):
            bridge.execute(request(), importer=fake_import, dispatch=lambda call: payload)
        self.assertEqual(payload, original)

    def test_two_real_runs_cannot_swap_results_or_drop_any_production_binding(self):
        from python.spike_core.service import handle
        from python.spike_core.extension_analysis_results import design_binding
        first = bridge.execute(request(), dispatch=handle)
        study = request(); study["analysis_spec"]["loads"][0]["current_a"] = 2.
        second = bridge.execute(study, dispatch=handle)
        a = first["analysis"]["analysis_result"]; b = second["analysis"]["analysis_result"]
        self.assertAlmostEqual(b["summary"]["max_voltage_drop_v"], 2 * a["summary"]["max_voltage_drop_v"], places=10)
        binding = design_binding(first["design"]); expected = bridge.digest(spec())
        swapped = copy.deepcopy(first); swapped["analysis"]["analysis_result"] = b
        with self.assertRaisesRegex(ValueError, "production provenance"):
            bridge.admit_exchange(swapped, first["design"], binding, expected_spec_digest=expected)
        for key in bridge._analysis_bindings(first):
            missing = copy.deepcopy(first); del missing["analysis"]["analysis_result"]["provenance"][key]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "production provenance"):
                bridge.admit_exchange(missing, first["design"], binding, expected_spec_digest=expected)

    def test_error_diagnostics_are_bounded_and_schema_safe(self):
        value = bridge.error_result({"request_id": {}, "operation": []}, ValueError("x" * 5000))
        self.assertIsNone(value["request_id"]); self.assertIsNone(value["operation"])
        self.assertEqual(len(value["error"]["message"]), 4000)

    def test_versioned_schemas_resolve_only_from_local_registered_resources(self):
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        schemas = {}
        resources = []
        for filename in ("prism-request-v1.schema.json", "prism-board-v1.schema.json", "prism-result-v1.schema.json",
                         "analysis-spec-v1.schema.json", "analysis-result-v1.schema.json", "design-ir-v1.schema.json"):
            path = (ROOT if filename.startswith("prism-") else SPIKE) / "schemas" / filename
            schema = bridge.read_json(path); Draft202012Validator.check_schema(schema)
            schemas[filename] = schema; resources.append((schema["$id"], Resource.from_contents(schema)))
        # Registry has no network retrieval callback. Every $ref is supplied here.
        registry = Registry().with_resources(resources)
        validate = lambda filename, value: Draft202012Validator(schemas[filename], registry=registry).validate(value)
        for operation in ("capabilities", "inspect-board", "analyze"):
            validate("prism-request-v1.schema.json", request(operation))
            validate("prism-result-v1.schema.json", bridge.execute(request(operation), dispatch=dispatch, importer=fake_import))
        validate("prism-board-v1.schema.json", {"contract": bridge.BOARD_CONTRACT, "api_version": 1, "source": source()})
        validate("prism-result-v1.schema.json", bridge.error_result({}, ValueError("invalid request")))
        blocked = request(); blocked["analysis_spec"]["loads"] = []
        validate("prism-result-v1.schema.json", bridge.execute(blocked))
        validate("prism-result-v1.schema.json", bridge.execute(request()))
        failed = dispatch({"method": "run_preflighted_analysis"})
        failed["result"]["status"] = "blocked"; failed["result"]["analysis_result"]["status"] = "failed_to_converge"
        validate("prism-result-v1.schema.json", bridge.execute(request(), importer=fake_import, dispatch=lambda call: failed))
        validator = Draft202012Validator(schemas["prism-request-v1.schema.json"], registry=registry)
        for field in bridge.SPEC_REQUIRED:
            missing = request(); del missing["analysis_spec"][field]
            with self.subTest(field=field): self.assertFalse(validator.is_valid(missing))
        malformed = request(); malformed["analysis_spec"]["sources"][0]["position_mm"] = [0]
        self.assertFalse(validator.is_valid(malformed))
        for name in ("CON.kicad_pcb", "../bad.kicad_pcb", "C:\\bad.kicad_pcb"):
            malformed = request("inspect-board"); malformed["source"]["file_name"] = name
            with self.subTest(name=name): self.assertFalse(validator.is_valid(malformed))

    def test_real_import_worker_analytical_fixture_and_registry_process(self):
        from python.spike_core.service import handle
        from python.spike_core.extensions import ExtensionManifest, ProcessExtension, ExtensionRegistry
        from python.spike_core.extension_importers import ExtensionDesignImporter
        from python.spike_core.extension_analysis_results import design_binding
        exchange = bridge.execute(request(), dispatch=handle)
        self.assertEqual(exchange["status"], "completed", exchange.get("analysis"))
        design = exchange["design"]
        self.assertEqual(len(design["tracks"]), 1)
        self.assertEqual(design["tracks"][0]["start"], [0., 0.])
        self.assertEqual(design["tracks"][0]["uuid"], "10000000-0000-4000-8000-000000000001")
        expected_drop = .01 / (5.8e7 * .001 * .000035)
        raw = exchange["analysis"]["analysis_result"]
        self.assertAlmostEqual(raw["summary"]["max_voltage_drop_v"], expected_drop, places=10)
        self.assertEqual(raw["model_status"], "approximate")
        registry = ExtensionRegistry(); catalog = registry.discover([ROOT / "integrations"], trusted_roots=[SPIKE / "extensions"])
        self.assertFalse(next(row for row in catalog if row["id"] == "spike.prism-bridge")["trusted"])
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            # Staging is outside the SPIKE checkout. This test-only bootstrap
            # supplies that reviewed source runtime to the normal SDK host.
            entry = folder / "test_entry.py"
            entry.write_text("import sys, runpy\nsys.path.insert(0," + repr(str(SPIKE)) + ")\nsys.path.insert(0," + repr(str(PACKAGE)) + ")\nrunpy.run_path(" + repr(str(PACKAGE / "extension.py")) + ",run_name='__main__')\n", encoding="utf-8")
            manifest = bridge.read_json(PACKAGE / "spike-extension.json"); manifest["entrypoint"] = entry.name
            package = ProcessExtension(ExtensionManifest.from_dict(manifest), folder, trusted=True)
            board_file = folder / "input.prism-board.json"
            bridge.write_json(board_file, {"contract": bridge.BOARD_CONTRACT, "api_version": 1, "source": source()})
            contribution = manifest["contributes"]["importers"][0]
            imported = ExtensionDesignImporter(package, contribution).import_design(str(board_file)).to_dict()
            self.assertEqual(design_binding(imported), exchange["design_binding"])
            outcome = package.invoke("prism-import-result", {"design": design,
                "parameters": {"exchange": exchange, "expected_analysis_spec_sha256": bridge.digest(spec())}})
            admitted = outcome["data"]["analysis_result"]
            self.assertEqual(admitted["fields"], raw["fields"])
            self.assertEqual(admitted["model_status"], raw["model_status"])
            with self.assertRaisesRegex(RuntimeError, "stale"):
                package.invoke("prism-import-result", {"design": design,
                    "parameters": {"exchange": exchange, "expected_analysis_spec_sha256": "0"*64}})

    def test_real_preflight_blocks_missing_terminals_and_endpoint_roundtrip(self):
        study = request(); study["analysis_spec"]["loads"] = []
        exchange = bridge.execute(study)
        self.assertEqual(exchange["status"], "blocked")
        self.assertIsNone(exchange["analysis"]["analysis_result"])
        self.assertTrue(any(row["code"] == "LOAD_REQUIRED" for row in exchange["analysis"]["preflight"]["issues"]))
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "request.json"; result_path = Path(directory) / "result.json"
            bridge.write_json(input_path, request("inspect-board"))
            environment = {**os.environ, "PYTHONPATH": str(SPIKE), "PYTHONDONTWRITEBYTECODE": "1"}
            process = subprocess.run([sys.executable, "-B", str(PACKAGE / "bridge.py"), "--request", str(input_path),
                                      "--result", str(result_path)], env=environment, capture_output=True, timeout=60)
            self.assertEqual(process.returncode, 0, process.stderr.decode())
            self.assertEqual(bridge.read_json(result_path)["status"], "completed")
            original = input_path.read_bytes()
            self.assertEqual(bridge.main(["--request", str(input_path), "--result", str(input_path)]), 2)
            self.assertEqual(input_path.read_bytes(), original)


if __name__ == "__main__": unittest.main()
