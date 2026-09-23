# SPDX-License-Identifier: MIT
"""Build and smoke-test the dedicated owned-SPICE process without downloading tools."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESOURCE_ROOT = ROOT / "app" / "src-tauri" / "resources" / "worker"
BUILD_ROOT = ROOT / "build" / "packaged-circuit-worker"
EXPECTED_PYINSTALLER_VERSION = "6.21.0"
BUILD_LOCK = ROOT / "requirements-build-circuit-windows-x64.txt"
PROCESS_CONTRACT = "spike/owned-spice-process-job/v1"
CAPABILITY_CONTRACT = "spike/owned-spice-process-capability/v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _library() -> Path:
    name = "spikes_c_api.dll" if os.name == "nt" else "libspikes_c_api.so"
    path = ROOT / "build-spikes-hybrid" / name
    if not path.is_file():
        raise RuntimeError(f"the release-owned circuit library is missing: {path}")
    return path


def _require_builder() -> str:
    try:
        version = importlib.metadata.version("pyinstaller")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError(
            f"PyInstaller {EXPECTED_PYINSTALLER_VERSION} is required; this builder never installs it"
        ) from exc
    if version != EXPECTED_PYINSTALLER_VERSION:
        raise RuntimeError(
            f"PyInstaller {EXPECTED_PYINSTALLER_VERSION} is required, found {version}"
        )
    return version


def _remove_managed(path: Path, parent: Path) -> None:
    resolved = path.resolve()
    if resolved.parent != parent.resolve():
        raise RuntimeError(f"refusing to remove unmanaged path: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)


def _smoke_job() -> dict[str, Any]:
    return {
        "contract": PROCESS_CONTRACT,
        "design": {
            "contract": "spike/v1",
            "design_id": "packaged-circuit-smoke",
            "name": "Packaged circuit smoke",
            "source_format": "generated",
            "source_path": "",
            "units": "mm",
            "layers": [], "nets": [], "tracks": [], "vias": [],
            "pads": [
                {"id": "src-p", "ref": "VSRC", "name": "1", "net_name": "PWR"},
                {"id": "src-n", "ref": "VSRC", "name": "2", "net_name": "GND"},
                {"id": "load-p", "ref": "RLOAD", "name": "1", "net_name": "PWR"},
                {"id": "load-n", "ref": "RLOAD", "name": "2", "net_name": "GND"},
            ],
            "zones": [],
            "components": [
                {"id": "src", "reference": "VSRC"},
                {"id": "load", "reference": "RLOAD"},
            ],
            "component_bonds": [], "connectors": [], "stackup": [],
            "technology": "rigid", "regions": [], "bends": [], "issues": [], "metadata": {},
        },
        "circuit_request": {
            "contract": "spike/owned-spice-workspace-request/v1",
            "request_id": "packaged-circuit-smoke",
            "workspace": {
                "contract": "spike/spice-workspace/v1",
                "name": "Owned process smoke",
                "domain": "pi",
                "ground_node": "GND",
                "models": [
                    {"id": "supply", "kind": "primitive", "primitive": "voltage_source",
                     "pins": ["p", "n"], "value": "1", "origin": "built_in",
                     "parameters": {"dc_value": 1.0}},
                    {"id": "load", "kind": "primitive", "primitive": "resistor",
                     "pins": ["p", "n"], "value": "100", "origin": "built_in",
                     "parameters": {"resistance_ohm": 100.0}},
                ],
                "assignments": [
                    {"id": "supply-map", "component_ref": "VSRC", "model_id": "supply",
                     "enabled": True, "pin_bindings": [
                         {"model_pin": "p", "pad_id": "src-p", "circuit_node": "PWR"},
                         {"model_pin": "n", "pad_id": "src-n", "circuit_node": "GND"},
                     ]},
                    {"id": "load-map", "component_ref": "RLOAD", "model_id": "load",
                     "enabled": True, "pin_bindings": [
                         {"model_pin": "p", "pad_id": "load-p", "circuit_node": "PWR"},
                         {"model_pin": "n", "pad_id": "load-n", "circuit_node": "GND"},
                     ]},
                ],
                "parasitics": [],
                "analysis": {"mode": "operating_point"},
            },
            "probes": ["V(PWR)"],
            "resource_limits": {
                "maximum_netlist_bytes": 2 * 1024 * 1024,
                "maximum_result_bytes": 4 * 1024 * 1024,
                "maximum_probes": 8,
            },
        },
    }


def _smoke(executable: Path) -> dict[str, Any]:
    capability = subprocess.run(
        [str(executable), "--capabilities"], capture_output=True, text=True,
        timeout=30, check=False,
    )
    if capability.returncode != 0:
        raise RuntimeError(f"circuit capability probe failed: {capability.stderr.strip()}")
    manifest = json.loads(capability.stdout)
    if (
        manifest.get("contract") != CAPABILITY_CONTRACT
        or manifest.get("validation_state") != "experimental"
        or manifest.get("structured_workspace_only") is not True
        or manifest.get("raw_netlist_accepted") is not False
        or manifest.get("caller_selected_library") is not False
        or manifest.get("owned_engine", {}).get("available") is not True
    ):
        raise RuntimeError("packaged circuit capability manifest widened or is unavailable")

    with tempfile.TemporaryDirectory(prefix="spike-circuit-smoke-") as temporary:
        root = Path(temporary)
        job = root / "job"
        job.mkdir()
        (job / "request.json").write_text(
            json.dumps(_smoke_job(), sort_keys=True, separators=(",", ":")), encoding="utf-8",
        )
        solved = subprocess.run(
            [str(executable), "--request", "job/request.json", "--result", "job/result.json"],
            cwd=root, capture_output=True, text=True, timeout=30, check=False,
        )
        if solved.returncode != 0:
            raise RuntimeError(f"packaged circuit solve failed: {solved.stderr.strip()}")
        result = json.loads((job / "result.json").read_text(encoding="utf-8"))
        if result.get("status") != "completed":
            raise RuntimeError("packaged circuit solve did not complete")
    return manifest


def build(*, keep_work: bool = False) -> tuple[Path, Path]:
    pyinstaller_version = _require_builder()
    library = _library()
    RESOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    artifact = RESOURCE_ROOT / "spike-circuit-worker"
    _remove_managed(artifact, RESOURCE_ROOT)
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--noupx", "--onedir",
        "--name", "spike-circuit-worker", "--distpath", str(RESOURCE_ROOT),
        "--workpath", str(BUILD_ROOT / "work"), "--specpath", str(BUILD_ROOT / "spec"),
        "--paths", str(ROOT), "--add-binary", f"{library}{os.pathsep}spikes",
        str(ROOT / "scripts" / "spike_circuit_worker_entry.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    executable = artifact / ("spike-circuit-worker.exe" if os.name == "nt" else "spike-circuit-worker")
    if not executable.is_file():
        raise RuntimeError(f"PyInstaller did not produce {executable}")
    capability = _smoke(executable)
    files = [
        {"path": item.relative_to(artifact).as_posix(), "bytes": item.stat().st_size,
         "sha256": _sha256(item)}
        for item in sorted(artifact.rglob("*")) if item.is_file()
    ]
    manifest = RESOURCE_ROOT / "spike-circuit-worker.manifest.json"
    manifest.write_text(json.dumps({
        "contract": "spike/owned-spice-process-package/v1",
        "validation_state": "experimental",
        "product_qualified": False,
        "pyinstaller": pyinstaller_version,
        "build_lock": BUILD_LOCK.name,
        "build_lock_sha256": _sha256(BUILD_LOCK),
        "source_library_sha256": _sha256(library),
        "capability": capability,
        "files": files,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not keep_work:
        _remove_managed(BUILD_ROOT / "work", BUILD_ROOT)
        _remove_managed(BUILD_ROOT / "spec", BUILD_ROOT)
    return executable, manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-work", action="store_true")
    args = parser.parse_args()
    executable, manifest = build(keep_work=args.keep_work)
    print(f"Verified packaged circuit worker: {executable}")
    print(f"Integrity manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
