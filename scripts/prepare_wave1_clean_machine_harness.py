"""Stage hash-bound inputs for a Wave 1 clean-Windows acceptance run.

This prepares evidence; it neither provisions nor asserts a clean machine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import uuid
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.wave1_packaged_acceptance import verify_installer_manifest  # noqa: E402


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer-manifest", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--installer", required=True, help="Exact MSI or NSIS file named by the manifest.")
    parser.add_argument("--fixture", type=Path, default=ROOT / "artifacts/wave1-assembly-acceptance/wave1-assembly-acceptance.spike")
    parser.add_argument("--fixture-summary", type=Path, default=ROOT / "artifacts/wave1-assembly-acceptance/wave1-assembly-acceptance.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    raw = json.loads(args.installer_manifest.read_text(encoding="utf-8-sig"))
    if raw.get("contract") not in {
        "spike/windows-installer-manifest/v1",
        "spike/windows-installer-manifest/v2",
    }:
        raise SystemExit("The installer manifest contract is unsupported.")
    if Path(args.installer).name != args.installer or Path(args.installer).suffix.lower() not in {".msi", ".exe"}:
        raise SystemExit("The installer name must be one safe MSI or EXE basename.")
    manifest_checks, _candidate = verify_installer_manifest(args.installer_manifest, args.artifact_dir)
    failed_checks = [check["id"] for check in manifest_checks if check.get("status") != "passed"]
    if failed_checks:
        raise SystemExit(f"Installer manifest verification failed: {', '.join(failed_checks)}")
    record = next((item for item in raw.get("files", []) if item.get("file") == args.installer), None)
    if not isinstance(record, dict):
        raise SystemExit("The requested installer is not named by the installer manifest.")
    artifact_dir = args.artifact_dir.resolve()
    installer = (artifact_dir / args.installer).resolve()
    if installer.parent != artifact_dir or not installer.is_file():
        raise SystemExit("Installer escapes the declared artifact directory or is missing.")
    try:
        expected_size = int(record.get("size", -1))
    except (TypeError, ValueError):
        expected_size = -1
    if digest(installer) != str(record.get("sha256", "")).lower() or installer.stat().st_size != expected_size:
        raise SystemExit("Installer does not match its manifest SHA-256 and size.")
    fixture_summary = json.loads(args.fixture_summary.read_text(encoding="utf-8"))
    fixture_digest = str(fixture_summary.get("manifest_payload_sha256", "")).lower()
    if len(fixture_digest) != 64 or any(character not in "0123456789abcdef" for character in fixture_digest) or not args.fixture.is_file():
        raise SystemExit("Fixture summary or fixture is invalid.")
    try:
        with zipfile.ZipFile(args.fixture) as archive:
            info = archive.getinfo("manifest.json")
            if info.file_size > 16 * 1024 * 1024:
                raise SystemExit("Fixture manifest exceeds the 16 MiB control-plane limit.")
            fixture_manifest = json.loads(archive.read(info).decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        raise SystemExit("Fixture is not a readable SPIKE package.") from error
    if not isinstance(fixture_manifest, dict) or fixture_manifest.get("manifest_payload_sha256") != fixture_digest:
        raise SystemExit("Fixture summary does not bind the package manifest identity.")

    output = args.output.resolve()
    if output.exists():
        raise SystemExit("Harness output must not already exist; use a new staging directory for every run.")
    payload = output / "payload"
    payload.mkdir(parents=True)
    copied = {
        "installer": payload / installer.name,
        "fixture": payload / args.fixture.name,
        "fixture_summary": payload / args.fixture_summary.name,
        "installer_manifest": payload / args.installer_manifest.name,
    }
    for source, destination in ((installer, copied["installer"]), (args.fixture, copied["fixture"]),
                                (args.fixture_summary, copied["fixture_summary"]), (args.installer_manifest, copied["installer_manifest"])):
        shutil.copy2(source, destination)
    runner_source = ROOT / "scripts/run_wave1_clean_machine_harness.ps1"
    runner = output / runner_source.name
    shutil.copy2(runner_source, runner)
    inputs = {
        "contract": "spike/wave1-clean-machine-inputs/v1",
        "run_id": str(uuid.uuid4()),
        "installer": {"path": f"payload/{copied['installer'].name}", "sha256": digest(copied["installer"]), "size": copied["installer"].stat().st_size},
        "fixture": {"path": f"payload/{copied['fixture'].name}", "sha256": digest(copied["fixture"]), "manifest_payload_sha256": fixture_digest},
        "fixture_summary": {"path": f"payload/{copied['fixture_summary'].name}", "sha256": digest(copied["fixture_summary"])},
        "installer_manifest": {"path": f"payload/{copied['installer_manifest'].name}", "sha256": digest(copied["installer_manifest"])},
        "runner": {"path": runner.name, "sha256": digest(runner)},
    }
    target = output / "inputs.json"
    target.write_text(json.dumps(inputs, indent=2) + "\n", encoding="utf-8")
    (output / "inputs.sha256").write_text(f"{digest(target)}  inputs.json\n", encoding="ascii")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
