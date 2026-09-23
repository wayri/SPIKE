"""Compose machine-readable Wave 1 packaged assembly acceptance evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.wave1_packaged_acceptance import (  # noqa: E402
    compose_report,
    probe_packaged_worker_health,
    probe_packaged_worker_fixture,
    probe_packaged_worker_mutation_roundtrip,
    validate_human_evidence,
    verify_acceptance_fixture,
    verify_installer_manifest,
    verify_packaged_worker_manifest,
    verify_runtime_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer-manifest", type=Path, default=ROOT / "artifacts/windows/installer/SPIKE-0.2.1-preview-installers.json")
    parser.add_argument("--artifact-dir", type=Path, default=ROOT / "artifacts/windows/installer")
    parser.add_argument(
        "--extracted-root",
        type=Path,
        required=True,
        help="Root of the exact MSI/NSIS extracted SPIKE image being qualified.",
    )
    parser.add_argument("--fixture", type=Path, default=ROOT / "artifacts/wave1-assembly-acceptance/wave1-assembly-acceptance.spike")
    parser.add_argument("--runtime-report", type=Path, default=ROOT / "build/release-runtime-qualification.json")
    parser.add_argument("--human-evidence", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "build/wave1-packaged-assembly-acceptance.json")
    parser.add_argument("--require-human", action="store_true")
    args = parser.parse_args()

    package_metadata = json.loads((ROOT / "app/package.json").read_text(encoding="utf-8"))
    installer_checks, candidate = verify_installer_manifest(
        args.installer_manifest,
        args.artifact_dir,
        expected_application_version=str(package_metadata["version"]),
    )
    worker_manifest = args.extracted_root / "bundled/spike-worker.manifest.json"
    worker_root = args.extracted_root / "bundled/spike-worker"
    worker_executable = worker_root / "spike-worker.exe"
    worker_checks, worker = verify_packaged_worker_manifest(worker_manifest, worker_root)
    health_check, health = probe_packaged_worker_health(worker_executable, cwd=ROOT)
    worker["health"] = health
    runtime_check, runtime = verify_runtime_report(args.runtime_report)
    fixture_checks, fixture = verify_acceptance_fixture(args.fixture)
    packaged_fixture_check = probe_packaged_worker_fixture(
        worker_executable,
        cwd=ROOT,
        fixture=args.fixture,
        manifest_payload_sha256=str(fixture["manifest_payload_sha256"]),
        model_ids=fixture["model_ids"],
        shape_ids=fixture["shape_ids"],
    )
    packaged_mutation_check = probe_packaged_worker_mutation_roundtrip(
        worker_executable, cwd=ROOT, fixture=args.fixture,
    )
    human_checks, human = validate_human_evidence(args.human_evidence)
    report = compose_report(
        automated_checks=[*installer_checks, *worker_checks, health_check, runtime_check, *fixture_checks, packaged_fixture_check, packaged_mutation_check],
        human_checks=human_checks, candidate=candidate, worker=worker, fixture=fixture,
        runtime=runtime, human=human,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    automated = report["automated"]["summary"]
    print(f"Wave 1 automated packaged acceptance: {report['automated']['status']} ({automated['passed']}/{automated['total']})")
    print(f"Overall status: {report['status']}")
    print(f"Report: {args.output.resolve()}")
    if report["automated"]["status"] != "passed":
        return 1
    if args.require_human and report["status"] != "passed":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
