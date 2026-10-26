# SPDX-License-Identifier: Apache-2.0
"""Verify final installed resource bytes and supervised circuit execution.

Never repairs manifests or signatures. Reports contain identities and versions,
not local source, installation or temporary-directory paths.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.beta_runtime_readiness import _read_object
from python.spike_core.circuit_worker_supervisor import run_circuit_worker, sha256_file
from python.spike_core.spikes_runtime import _library_name
from python.spike_core.wave1_packaged_acceptance import verify_packaged_worker_manifest
from scripts.build_packaged_circuit_worker import _smoke_job


def _inventory(root: Path, manifest: dict, size_key: str) -> int:
    files = manifest.get("files")
    if not isinstance(files, list) or not 0 < len(files) <= 4096:
        raise ValueError("Invalid payload file inventory")
    declared = set()
    for item in files:
        name = item.get("path") if isinstance(item, dict) else None
        parts = PurePosixPath(name).parts if isinstance(name, str) else ()
        if (not parts or PurePosixPath(name).is_absolute() or "\\" in name
                or ":" in name or any(part in {".", ".."} for part in parts) or name in declared):
            raise ValueError("Unsafe or duplicate payload member")
        path = root.joinpath(*parts)
        if not path.resolve().is_relative_to(root):
            raise ValueError("Payload member escapes its artifact")
        size, digest = item.get(size_key), item.get("sha256")
        if (type(size) is not int or size < 0 or not isinstance(digest, str)
                or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
                or not path.is_file() or path.stat().st_size != size or sha256_file(path) != digest):
            raise ValueError("Payload member integrity mismatch")
        declared.add(name)
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual != declared:
        raise ValueError("Payload file inventory is incomplete or stale")
    return len(declared)


def _admit(resources: Path) -> tuple[dict, dict, list[dict]]:
    bundled = resources / "bundled"
    worker = _read_object(bundled / "spike-worker.manifest.json", "worker manifest")
    circuit = _read_object(bundled / "spike-circuit-worker.manifest.json", "circuit manifest")
    _inventory((bundled / "spike-worker").resolve(strict=True), worker, "size")
    _inventory((bundled / "spike-circuit-worker").resolve(strict=True), circuit, "bytes")
    checks, _ = verify_packaged_worker_manifest(
        bundled / "spike-worker.manifest.json", bundled / "spike-worker")
    if not checks or any(check.get("status") != "passed" for check in checks):
        raise ValueError("Packaged worker acceptance checks failed")
    expected = {"engine": "spike-circuit-worker", "validation_state": "experimental",
                "structured_workspace_only": True, "raw_netlist_accepted": False,
                "shell_invoked": False, "trusted_host_supervision_required": True,
                "binary_and_library_sha256_admission": True}
    capability = circuit.get("capability", {})
    if (circuit.get("contract") != "spike/owned-spice-process-package/v1"
            or circuit.get("product_qualified") is not False or not isinstance(capability, dict)
            or any(capability.get(key) != value for key, value in expected.items())):
        raise ValueError("Circuit package capability claims differ")
    return worker, circuit, checks


def verify(resources: Path) -> dict:
    resources = resources.resolve(strict=True)
    worker, circuit, checks = _admit(resources)
    bundled = resources / "bundled"
    circuit_root = bundled / "spike-circuit-worker"
    executable = circuit_root / ("spike-circuit-worker.exe" if os.name == "nt" else "spike-circuit-worker")
    library = circuit_root / "_internal" / "spikes" / _library_name()
    executable_digest, library_digest = sha256_file(executable), sha256_file(library)
    manifest_digests = {name: sha256_file(bundled / name) for name in (
        "spike-worker.manifest.json", "spike-circuit-worker.manifest.json")}
    with tempfile.TemporaryDirectory(prefix="spike-unix-payload-") as directory:
        job_root = Path(directory).resolve(strict=True)
        (job_root / "job").mkdir()
        (job_root / "job/request.json").write_text(json.dumps(_smoke_job()), encoding="utf-8")
        outcome = run_circuit_worker(
            worker_executable=executable, worker_sha256=executable_digest,
            library_path=library, library_sha256=library_digest, job_root=job_root,
            request="job/request.json", result="job/result.json", timeout_seconds=30,
            memory_limit_mib=4096)
        if outcome.status != "completed" or outcome.returncode != 0:
            raise ValueError("Supervised packaged circuit smoke did not complete")
        result = _read_object(job_root / "job/result.json", "circuit smoke result")
        if (result.get("contract") != "spike/owned-spice-process-result/v1"
                or result.get("status") != "completed" or result.get("validation_state") != "experimental"
                or result.get("circuit", {}).get("status") != "completed"):
            raise ValueError("Packaged circuit smoke returned an invalid result")
    _admit(resources)
    if any(sha256_file(bundled / name) != digest for name, digest in manifest_digests.items()):
        raise ValueError("Payload manifests changed during verification")
    versions = {key: worker.get(key) for key in ("worker_version", "python", "pyinstaller", "machine")}
    if any(not isinstance(value, str) or not value or "/" in value or "\\" in value
           for value in versions.values()):
        raise ValueError("Payload version identities are missing or invalid")
    return {"contract": "spike/unix-release-payload-verification/v1", "status": "passed",
            "production_qualified": False, "versions": versions,
            "worker_checks": [{"id": check["id"], "status": check["status"]} for check in checks],
            "worker_members": len(worker["files"]), "circuit_members": len(circuit["files"]),
            "manifest_sha256": manifest_digests,
            "circuit_worker_sha256": executable_digest, "circuit_library_sha256": library_digest,
            "supervised_circuit": {"status": outcome.status, "returncode": outcome.returncode,
                                   "os_enforcement": outcome.os_enforcement}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", required=True, type=Path,
                        help="Installed resource root containing bundled/")
    parser.add_argument("--output", type=Path, default=ROOT / "build/qualification/unix-payload.json")
    args = parser.parse_args(argv)
    report = verify(args.resources)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
