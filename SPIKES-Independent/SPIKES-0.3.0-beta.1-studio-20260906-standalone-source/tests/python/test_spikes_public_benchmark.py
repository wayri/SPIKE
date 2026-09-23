from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from python.spikes.public_benchmark import (
    EngineAdapterManifest,
    EngineCaseEvidence,
    JsonProcessBenchmarkAdapter,
    MetricTolerance,
    PublicBenchmarkCase,
    PublicBenchmarkError,
    PublicBenchmarkManifest,
    PublicSource,
    qualify_public_benchmark,
)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _source(deck: bytes) -> PublicSource:
    return PublicSource(
        source_id="public.example", title="Public reference deck",
        canonical_url="https://example.org/reference.cir", license_spdx="CC0-1.0",
        license_url="https://creativecommons.org/publicdomain/zero/1.0/",
        retrieved_at_utc="2026-08-30T00:00:00Z", artifact_sha256=_sha(deck),
        redistribution_approved=True,
        approval_evidence_sha256=_sha(b"license review"), reviewer="test reviewer",
    )


def _case(case_id: str, tier: str, deck: bytes = b"R1 1 0 1k\n.end\n") -> PublicBenchmarkCase:
    return PublicBenchmarkCase(
        case_id=case_id, tier=tier, analysis="op",
        deck_relative_path=f"{case_id}.cir", deck_sha256=_sha(deck),
        model_bundle_sha256=_sha(b"no external models"), source=_source(deck),
        metrics=(MetricTolerance(
            metric_id="vout", vector="v(1)", reduction="scalar", reference=1.0,
            absolute_tolerance=1e-9, relative_tolerance=1e-6,
        ),),
    )


def _manifest() -> PublicBenchmarkManifest:
    return PublicBenchmarkManifest.create(
        manifest_id="public.equal-model", version="1",
        required_engines=("spikes", "ngspice"),
        cases=(_case("small", "small"), _case("medium", "medium"), _case("large", "large")),
    )


def _evidence(manifest: PublicBenchmarkManifest, engine: str, case: PublicBenchmarkCase) -> EngineCaseEvidence:
    fast = engine == "spikes"
    return EngineCaseEvidence(
        engine_id=engine, case_id=case.case_id,
        manifest_sha256=manifest.manifest_sha256, deck_sha256=case.deck_sha256,
        model_bundle_sha256=case.model_bundle_sha256,
        host_fingerprint=_sha(b"pinned host"), timing_scope="process_inclusive",
        observed={"vout": 1.0},
        cold_elapsed_ns=(10, 11, 9, 10, 10) if fast else (20, 21, 19, 20, 20),
        warm_elapsed_ns=(5, 6, 4, 5, 5) if fast else (9, 10, 8, 9, 9),
        peak_memory_bytes=100 if fast else 200,
    )


class PublicBenchmarkTests(unittest.TestCase):
    def test_manifest_binds_exact_deck_and_public_license_review(self) -> None:
        case = _case("small", "small")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deck = root / "small.cir"
            deck.write_bytes(b"R1 1 0 1k\n.end\n")
            self.assertEqual(case.verify_deck(root), deck.resolve())
            deck.write_bytes(b"changed")
            with self.assertRaisesRegex(PublicBenchmarkError, "digest"):
                case.verify_deck(root)
        with self.assertRaisesRegex(PublicBenchmarkError, "approval"):
            replace(case.source, redistribution_approved=False)

    def test_performance_claim_is_derived_only_from_complete_equal_evidence(self) -> None:
        manifest = _manifest()
        complete = [
            _evidence(manifest, engine, case)
            for engine in manifest.required_engines for case in manifest.cases
        ]
        report = qualify_public_benchmark(manifest, complete)
        self.assertEqual(report["status"], "passed")
        self.assertTrue(report["performance_claim_eligible"])
        blocked = qualify_public_benchmark(manifest, complete[:-1])
        self.assertEqual(blocked["status"], "blocked")
        self.assertFalse(blocked["performance_claim_eligible"])
        self.assertTrue(any(str(item).startswith("missing_evidence:") for item in blocked["blockers"]))

    def test_accuracy_or_equal_model_attestation_failure_blocks_claim(self) -> None:
        manifest = _manifest()
        records = [
            _evidence(manifest, engine, case)
            for engine in manifest.required_engines for case in manifest.cases
        ]
        records[0] = replace(records[0], observed={"vout": 2.0})
        report = qualify_public_benchmark(manifest, records)
        self.assertFalse(report["accuracy_passed"])
        self.assertFalse(report["performance_claim_eligible"])
        records[0] = replace(records[0], deck_sha256=_sha(b"different deck"))
        report = qualify_public_benchmark(manifest, records)
        self.assertIn("deck_mismatch:spikes:small", report["blockers"])

    def test_digest_bound_json_adapter_attests_exact_deck_and_model(self) -> None:
        case = _case("small", "small")
        manifest = PublicBenchmarkManifest.create(
            manifest_id="adapter.test", version="1",
            required_engines=("spikes", "peer"), cases=(case,),
        )
        code = (
            "import json,sys,hashlib,base64; r=json.loads(sys.stdin.readline()); c=r['case']; "
            "o={'contract':'spikes/public-benchmark-adapter-result/v1',"
            "'engine_id':r['engine_id'],'case_id':c['case_id'],"
            "'benchmark_manifest_sha256':r['benchmark_manifest_sha256'],"
            "'executed_deck_sha256':hashlib.sha256(base64.b64decode(r['deck_base64'])).hexdigest(),"
            "'model_bundle_sha256':c['model_bundle_sha256'],"
            f"'host_fingerprint':'{_sha(b'host')}',"
            "'timing_scope':'process_inclusive','observed':{'vout':1.0},"
            "'cold_elapsed_ns':[1,1,1,1,1],'warm_elapsed_ns':[1,1,1,1,1],"
            "'peak_memory_bytes':1}; print(json.dumps(o))"
        )
        adapter_manifest = EngineAdapterManifest.create(
            engine_id="spikes", engine_version="test", executable=sys.executable,
            arguments=("-c", code),
        )
        evidence = JsonProcessBenchmarkAdapter(adapter_manifest, sys.executable).run_case(
            manifest, case, b"R1 1 0 1k\n.end\n",
        )
        self.assertEqual(evidence.deck_sha256, case.deck_sha256)
        self.assertEqual(evidence.model_bundle_sha256, case.model_bundle_sha256)

    def test_adapter_rejects_extra_or_duplicate_result_fields(self) -> None:
        case = _case("small", "small")
        manifest = PublicBenchmarkManifest.create(
            manifest_id="adapter.strict", version="1",
            required_engines=("spikes", "peer"), cases=(case,),
        )
        for response in (
            "{'contract':'spikes/public-benchmark-adapter-result/v1','extra':1}",
            "'{\"contract\":\"spikes/public-benchmark-adapter-result/v1\",\"contract\":\"x\"}'",
        ):
            code = f"print({response})"
            adapter_manifest = EngineAdapterManifest.create(
                engine_id="spikes", engine_version="test", executable=sys.executable,
                arguments=("-c", code),
            )
            with self.subTest(response=response), self.assertRaisesRegex(
                RuntimeError, "adapter_result_invalid",
            ):
                JsonProcessBenchmarkAdapter(adapter_manifest, sys.executable).run_case(
                    manifest, case, b"R1 1 0 1k\n.end\n",
                )


if __name__ == "__main__":
    unittest.main()
