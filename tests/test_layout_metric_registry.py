# SPDX-License-Identifier: Apache-2.0
import copy
import json
import unittest

from python.spike_core.layout_metric_registry import (
    LayoutMetricRegistryError,
    canonical_metric_registry_json,
    negotiate_layout_requirements,
    validate_metric_registry,
    validate_requirements_for_launch,
)


class LayoutMetricRegistryTests(unittest.TestCase):
    def setUp(self):
        evidence = {
            "id": "evidence.conformance-1",
            "kind": "conformance_suite",
            "artifact": {
                "path": "evidence/layout-conformance.json",
                "sha256": "e" * 64,
                "bytes": 4096,
                "contract": "spike/validation-evidence/v1",
            },
            "claim": "Metric output and SI dimension conformance.",
        }
        self.registry = {
            "contract": "spike/layout-metric-registry/v1",
            "registry_id": "custom.layout-evaluators",
            "registry_version": "1.2.0",
            "producer": {"implementation": "custom-evaluator-host", "version": "4.0"},
            "metrics": [
                {
                    "id": "thermal.max_temperature",
                    "dimension": [0, 0, 0, 0, 1, 0, 0],
                    "evaluator": "native_solver",
                    "result_key": "max_temperature_k",
                    "supported_consumers": ["autorouter", "autoplacer", "joint"],
                    "supported_kinds": ["hard_constraint", "soft_constraint", "objective"],
                    "supported_relations": ["le", "target", "minimize"],
                    "validation_state": "qualified",
                    "evidence": [evidence],
                    "batch": {"supported": True, "max_candidates": 8},
                    "incremental": {"supported": True, "change_kinds": ["placement", "routing"]},
                },
                {
                    "id": "pcb.minimum_clearance",
                    "dimension": [1, 0, 0, 0, 0, 0, 0],
                    "evaluator": "cad_drc",
                    "supported_consumers": ["autorouter", "autoplacer", "joint"],
                    "supported_kinds": ["hard_constraint", "soft_constraint"],
                    "supported_relations": ["ge"],
                    "validation_state": "cad_drc",
                    "evidence": [{**evidence, "id": "evidence.drc-1"}],
                    "batch": {"supported": True, "max_candidates": 128},
                    "incremental": {"supported": True, "change_kinds": ["placement", "routing", "geometry"]},
                },
            ],
        }
        self.request = {
            "contract": "spike/layout-evaluation/v1",
            "record_type": "request",
            "evaluation_id": "route.iteration-1",
            "consumer": {"kind": "autorouter", "implementation": "custom-router"},
            "candidate": {"path": "candidate.json", "sha256": "a" * 64, "bytes": 100, "contract": "spike/design-ir/v2"},
            "requirements": [
                {
                    "id": "max.temperature",
                    "metric_id": "thermal.max_temperature",
                    "evaluator": "native_solver",
                    "result_key": "max_temperature_k",
                    "kind": "hard_constraint",
                    "relation": "le",
                    "dimension": [0, 0, 0, 0, 1, 0, 0],
                    "upper_si": 358.15,
                    "scope": {"frame": "board", "entity_ids": []},
                },
                {
                    "id": "minimum.clearance",
                    "metric_id": "pcb.minimum_clearance",
                    "evaluator": "cad_drc",
                    "kind": "hard_constraint",
                    "relation": "ge",
                    "dimension": [1, 0, 0, 0, 0, 0, 0],
                    "lower_si": 0.0002,
                    "scope": {"frame": "board", "entity_ids": []},
                },
            ],
            "physics_evaluations": [],
            "resources": {"max_memory_bytes": 16777216, "max_wall_time_s": 30, "ranks": 1, "threads": 1},
            "deterministic": True,
        }

    def test_registry_decodes_to_immutable_typed_records_and_round_trips(self):
        typed = validate_metric_registry(self.registry)
        self.assertEqual(typed.registry_id, "custom.layout-evaluators")
        self.assertEqual(typed.capability("thermal.max_temperature").result_key, "max_temperature_k")
        self.assertEqual(json.loads(canonical_metric_registry_json(typed)), typed.to_dict())
        with self.assertRaises(AttributeError):
            typed.metrics = ()

    def test_strict_registry_rejects_unknown_fields_and_duplicate_metrics(self):
        bad = copy.deepcopy(self.registry)
        bad["shell"] = "never"
        with self.assertRaises(LayoutMetricRegistryError) as caught:
            validate_metric_registry(bad)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-REGISTRY-0001")
        duplicate = copy.deepcopy(self.registry)
        duplicate["metrics"].append(copy.deepcopy(duplicate["metrics"][0]))
        with self.assertRaises(LayoutMetricRegistryError) as caught:
            validate_metric_registry(duplicate)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-REGISTRY-0004")

    def test_registry_requires_digest_bound_validation_evidence(self):
        bad = copy.deepcopy(self.registry)
        bad["metrics"][0]["evidence"] = []
        with self.assertRaises(LayoutMetricRegistryError):
            validate_metric_registry(bad)
        bad = copy.deepcopy(self.registry)
        bad["metrics"][0]["evidence"][0]["artifact"]["path"] = "../escape.json"
        with self.assertRaises(LayoutMetricRegistryError):
            validate_metric_registry(bad)

    def test_launch_preflight_negotiates_all_requirements(self):
        result = validate_requirements_for_launch(self.request, self.registry)
        self.assertEqual(result.consumer_kind, "autorouter")
        self.assertEqual(len(result.decisions), 2)
        self.assertEqual(result.decisions[0].validation_state, "qualified")

    def test_unknown_metric_and_capability_mismatches_fail_closed(self):
        for field, value in (
            ("metric_id", "thermal.unknown"),
            ("evaluator", "custom"),
            ("result_key", "wrong_key"),
            ("dimension", [1, 0, 0, 0, 0, 0, 0]),
            ("relation", "ge"),
        ):
            bad = copy.deepcopy(self.request)
            bad["requirements"][0][field] = value
            with self.assertRaises(LayoutMetricRegistryError):
                validate_requirements_for_launch(bad, self.registry)

    def test_hard_constraint_rejects_insufficient_validation(self):
        registry = copy.deepcopy(self.registry)
        registry["metrics"][0]["validation_state"] = "experimental"
        with self.assertRaises(LayoutMetricRegistryError) as caught:
            negotiate_layout_requirements(self.request, registry)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-REGISTRY-0007")
        allowed = negotiate_layout_requirements(
            self.request, registry,
            accepted_hard_validation_states=("experimental", "cad_drc"),
        )
        self.assertEqual(len(allowed.decisions), 2)

    def test_batch_and_incremental_limits_are_negotiated_per_metric(self):
        accepted = negotiate_layout_requirements(
            self.request, self.registry, batch_size=8, incremental=True, change_kind="routing",
        )
        self.assertEqual(accepted.batch_size, 8)
        self.assertTrue(accepted.incremental)
        with self.assertRaises(LayoutMetricRegistryError) as caught:
            negotiate_layout_requirements(self.request, self.registry, batch_size=9)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-REGISTRY-0008")
        with self.assertRaises(LayoutMetricRegistryError):
            negotiate_layout_requirements(self.request, self.registry, incremental=True, change_kind="material")

    def test_json_schema_accepts_golden_and_rejects_unknown_field_when_available(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        from pathlib import Path

        schema_path = Path(__file__).resolve().parents[1] / "schemas" / "layout-metric-registry-v1.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(self.registry)
        bad = copy.deepcopy(self.registry)
        bad["metrics"][0]["command"] = "not allowed"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(bad)


if __name__ == "__main__":
    unittest.main()
