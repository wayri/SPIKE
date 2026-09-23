"""Offline-first dependency inventory and runtime discovery.

The desktop application owns this inventory. It never installs packages into a
user's global environment and never downloads a solver implicitly.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Iterable

from .acceleration import acceleration_catalog
from .external_engines import external_engine_catalog


MANIFEST_VERSION = "spike/dependencies/v1"


def _app_root() -> Path:
    configured = os.environ.get("SPIKE_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def _find(names: Iterable[str], bundled: Path) -> str:
    common_roots = [
        Path(os.environ.get("ProgramFiles", "C:/Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")),
        Path(os.environ.get("LOCALAPPDATA", "")),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
    ]
    for name in names:
        candidate = bundled / name
        if candidate.exists():
            return str(candidate)
        found = shutil.which(name)
        if found:
            return found
        for root in common_roots:
            if not str(root):
                continue
            candidates = [root / "Blender Foundation" / "Blender" / name, root / "FreeCAD" / "bin" / name, root / "FreeCAD" / name]
            for match in candidates:
                if match.exists():
                    return str(match)
            for pattern in (f"Blender Foundation/Blender */{name}", f"FreeCAD*/{name}", f"FreeCAD*/bin/{name}"):
                matches = list(root.glob(pattern)) if root.exists() else []
                if matches:
                    return str(matches[0])
    return ""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dependency_status() -> Dict[str, Any]:
    root = _app_root()
    bin_dir = root / "runtime" / "bin"
    worker = root / "runtime" / "worker" / "spike_worker.exe"
    manifest_file = root / "dependencies.lock.json"
    accelerator_by_id = {item["id"]: item for item in acceleration_catalog()["backends"]}
    engine_by_id = {item["id"]: item for item in external_engine_catalog()["engines"]}
    numba = accelerator_by_id["numba"]
    mumps = accelerator_by_id["petsc-mumps"]
    openems = engine_by_id["external.openems"]
    ngspice = engine_by_id["external.ngspice"]
    openfoam = engine_by_id["external.openfoam"]
    flotherm = engine_by_id["external.flotherm"]
    entries = [
        {"id": "frontend", "kind": "bundled", "required": True, "status": "bundled", "path": "app assets"},
        {"id": "worker", "kind": "bundled", "required": True, "status": "ready" if worker.exists() else "development_source", "path": str(worker) if worker.exists() else "python/spike_core/service.py"},
        {"id": "python-runtime", "kind": "bundled", "required": True, "status": "ready" if (bin_dir / "python.exe").exists() else "development_host", "path": _find(("python.exe", "python"), bin_dir)},
        {"id": "numba", "kind": "optional_accelerator", "required": False, "status": numba["state"], "path": "python module" if numba["state"] == "available" else ""},
        {"id": "petsc-mumps", "kind": "optional_accelerator", "required": False, "status": mumps["state"], "path": "petsc4py module" if mumps["state"] == "available" else ""},
        {"id": "openems", "kind": "optional_solver", "required": False, "status": openems["state"], "path": openems["executable"] or ("configured Python interface" if openems["state"] == "experimental" else "")},
        {"id": "ngspice", "kind": "optional_solver", "required": False, "status": "ready" if ngspice["state"] == "available" else ngspice["state"], "path": ngspice["executable"]},
        {"id": "openfoam", "kind": "optional_solver", "required": False, "status": openfoam["state"], "path": openfoam["executable"]},
        {"id": "flotherm", "kind": "optional_licensed_connector", "required": False, "status": flotherm["state"], "path": flotherm["executable"]},
        {"id": "freecad", "kind": "optional_converter", "required": False, "status": "ready" if _find(("FreeCADCmd.exe", "freecadcmd.exe", "FreeCADCmd", "freecadcmd"), bin_dir) else "unavailable", "path": _find(("FreeCADCmd.exe", "freecadcmd.exe", "FreeCADCmd", "freecadcmd"), bin_dir)},
        {"id": "blender", "kind": "optional_converter", "required": False, "status": "ready" if _find(("blender.exe", "blender"), bin_dir) else "unavailable", "path": _find(("blender.exe", "blender"), bin_dir)},
    ]
    return {
        "manifest": MANIFEST_VERSION,
        "offline": True,
        "app_root": str(root),
        "manifest_file": str(manifest_file),
        "python": sys.version.split()[0],
        "dependencies": entries,
        "required_ready": all(item["status"] in {"ready", "bundled", "development_source", "development_host"} for item in entries if item["required"]),
        "update_policy": "manual_signed_bundle",
    }


def verify_lockfile(path: str | Path | None = None) -> Dict[str, Any]:
    lockfile = Path(path) if path else _app_root() / "dependencies.lock.json"
    if not lockfile.exists():
        return {"valid": False, "status": "missing", "path": str(lockfile)}
    try:
        payload = json.loads(lockfile.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"valid": False, "status": "invalid", "path": str(lockfile), "error": str(exc)}
    valid = payload.get("manifest") == MANIFEST_VERSION and isinstance(payload.get("dependencies"), list)
    return {"valid": valid, "status": "valid" if valid else "invalid", "path": str(lockfile), "manifest": payload.get("manifest"), "sha256": _file_sha256(lockfile)}
