"""Verify a returned Wave 1 clean-machine harness record and its SHA-256 ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path


SHA256 = re.compile(r"^[0-9a-f]{64}$")
ISOLATED_PROVIDERS = {"windows-sandbox", "hyperv-vm", "external-clean-vm", "physical-clean-machine"}
ATTESTATION_CONTRACT = "spike/wave1-environment-attestation/v1"
ATTESTATION_FIELDS = {
    "contract", "provider", "run_id", "inputs_sha256", "attestor",
    "issued_at", "environment_id", "isolation_claim",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _rfc3339_with_timezone(value: object) -> bool:
    if not isinstance(value, str) or not 20 <= len(value) <= 64:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def verify(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    required = ("inputs_sha256", "installer_sha256", "before_manifest_payload_sha256", "after_manifest_payload_sha256")
    if raw.get("contract") != "spike/wave1-clean-machine-harness/v2":
        raise ValueError("legacy or unsupported harness contract; v2 is required for qualification")
    provider = raw.get("provider")
    if provider not in ISOLATED_PROVIDERS or raw.get("eligible_for_human_review") is not True:
        raise ValueError("harness run is not eligible for human review")
    if any(SHA256.fullmatch(str(raw.get(key, "")).lower()) is None for key in required):
        raise ValueError("harness hash identity is invalid")
    run_id = raw.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("harness run identity is invalid")
    environment = raw.get("environment")
    required_environment = {"provider", "os", "gpu", "webview2_version", "display_scale_percent", "process_path_entries", "pre_install_spike_residue"}
    residue = environment.get("pre_install_spike_residue") if isinstance(environment, dict) else None
    if (
        not isinstance(environment, dict) or not required_environment.issubset(environment)
        or environment.get("provider") != provider or not isinstance(environment.get("os"), dict) or not environment["os"]
        or not isinstance(environment.get("gpu"), list) or not environment["gpu"]
        or not isinstance(residue, dict) or set(residue) != {"uninstall_products", "install_paths", "file_association"}
        or not isinstance(residue["file_association"], dict) or not residue["file_association"]
    ):
        raise ValueError("harness environment is incomplete; it is not a clean-machine assertion")
    mechanics = raw.get("mechanics")
    required_mechanics = {"staged_hashes_verified", "installer_started", "installer_exit_code", "installed_product", "spike_association", "launched_process_id", "after_project_supplied"}
    if not isinstance(mechanics, dict) or not required_mechanics.issubset(mechanics) or mechanics.get("staged_hashes_verified") is not True:
        raise ValueError("harness mechanics are incomplete")
    attestation = raw.get("environment_attestation")
    required_attestation = {"status", "cryptographically_verified", "eligible_for_human_review", "note", "contract", "provider", "run_id", "inputs_sha256", "attestor", "issued_at", "environment_id", "isolation_claim", "artifact"}
    if (
        not isinstance(attestation, dict) or set(attestation) != required_attestation
        or attestation.get("status") != "supplied_for_human_review" or attestation.get("cryptographically_verified") is not False
        or attestation.get("eligible_for_human_review") is not True or attestation.get("contract") != ATTESTATION_CONTRACT
        or attestation.get("provider") != provider or attestation.get("run_id") != run_id
        or str(attestation.get("inputs_sha256", "")).lower() != str(raw["inputs_sha256"]).lower()
        or any(not isinstance(attestation.get(key), str) or not attestation[key].strip() for key in ("attestor", "issued_at", "environment_id", "isolation_claim", "note"))
        or not _rfc3339_with_timezone(attestation.get("issued_at"))
    ):
        raise ValueError("harness environment attestation is missing, unbound, or not eligible for human review")
    ledger = raw.get("artifacts")
    if not isinstance(ledger, list) or not ledger:
        raise ValueError("harness artifact ledger is missing")
    verified: dict[str, str] = {}
    for item in ledger:
        relative = str(item.get("path", "")) if isinstance(item, dict) else ""
        candidate = (path.parent / relative).resolve()
        if not relative or "\\" in relative or ":" in relative or candidate.parent != path.parent.resolve() or not candidate.is_file():
            raise ValueError("harness artifact path is unsafe or missing")
        if digest(candidate) != str(item.get("sha256", "")).lower():
            raise ValueError(f"harness artifact hash mismatch: {relative}")
        if relative in verified:
            raise ValueError(f"harness artifact ledger has duplicate path: {relative}")
        verified[relative] = str(item["sha256"]).lower()
    required_ledger = {"after-project.spike", "mechanics.json", "preflight.json", "review-required.json", "inputs.json", "executing-runner.ps1", "environment-attestation.json"}
    if not required_ledger.issubset(verified):
        raise ValueError("harness artifact ledger is incomplete")
    staged_inputs = path.parent / "inputs.json"
    if digest(staged_inputs) != str(raw["inputs_sha256"]).lower():
        raise ValueError("record inputs SHA-256 does not bind the copied inputs.json")
    inputs = json.loads(staged_inputs.read_text(encoding="utf-8"))
    runner = inputs.get("runner") if isinstance(inputs, dict) else None
    if (
        not isinstance(runner, dict) or inputs.get("run_id") != run_id
        or str(runner.get("sha256", "")).lower() != digest(path.parent / "executing-runner.ps1")
    ):
        raise ValueError("copied inputs.json does not bind the executing runner")
    attestation_file = path.parent / "environment-attestation.json"
    supplied = json.loads(attestation_file.read_text(encoding="utf-8"))
    artifact = attestation.get("artifact")
    if (
        not isinstance(artifact, dict) or artifact.get("path") != "environment-attestation.json"
        or str(artifact.get("sha256", "")).lower() != digest(attestation_file)
        or not isinstance(supplied, dict) or set(supplied) != ATTESTATION_FIELDS
        or any(supplied.get(key) != attestation.get(key) for key in ATTESTATION_FIELDS - {"inputs_sha256"})
        or str(supplied.get("inputs_sha256", "")).lower() != str(attestation.get("inputs_sha256", "")).lower()
    ):
        raise ValueError("copied environment attestation does not bind this harness run")
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    record = verify(args.record)
    print(f"Verified a structurally bound review input for harness run {record['run_id']}; this is not proof that the machine is clean or isolated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
