# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Pinned local-development Gmsh OCC process, never a packaged solver claim.

Uses the existing administrator-installed Gmsh API/DLL without copying vendor
code. Only those two entry artifacts are hash-admitted; this is not a complete
transitive-DLL allowlist or redistributable dependency qualification.
"""
from __future__ import annotations

import ctypes.util
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

from .sparselizard_process import run_adapter_process

API = Path("C:/msys64/ucrt64/lib/gmsh.py")
DLL = Path("C:/msys64/ucrt64/bin/libgmsh.dll")
ARTIFACTS = {
    API: "f4b0935cebde899750293d87a643090e5ea33c9b18d249267f507db68a0e01c3",
    DLL: "a43b4c96644b3c7dc57f79285cd68814ecb3995e582939378a27d238533ed599",
}
MAX_REQUEST = 8 * 1024**2
MAX_RESULT = 256 * 1024**2


def _sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024**2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_installation():
    if sys.platform != "win32" or sys.version_info[:2] != (3, 11):
        raise ValueError("GMSH_RUNTIME: this local development runner supports Windows CPython 3.11 only")
    for path, expected in ARTIFACTS.items():
        if not path.is_file() or path.is_symlink() or _sha(path) != expected:
            raise ValueError("GMSH_HASH: installed entry artifact does not match the development pin: " + str(path))
    return {"version": "4.15.2", "entry_artifacts": {str(p): h for p, h in ARTIFACTS.items()},
            "approval": "local-development-only", "redistribution_approved": False,
            "transitive_dll_admission": "not_qualified"}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate control-file key")
        result[key] = value
    return result


def worker(request_sha256):
    """Only called inside the fixed-argument isolated process."""
    from .gmsh_occ_mesher import build_occ_mesh, validate_request
    provenance = verify_installation()
    path = Path("request.json")
    if path.is_symlink() or path.stat().st_size > MAX_REQUEST:
        raise ValueError("GMSH_REQUEST: invalid request file")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != request_sha256:
        raise ValueError("GMSH_REQUEST_HASH: control file changed after admission")
    request = json.loads(payload, object_pairs_hook=_unique)
    validate_request(request)
    # Accommodate this installation's libgmsh.dll name without changing gmsh.py.
    with os.add_dll_directory(str(DLL.parent)):
        previous = ctypes.util.find_library
        try:
            ctypes.util.find_library = lambda name: str(DLL) if name in ("gmsh", "gmsh-4.15") else previous(name)
            spec = importlib.util.spec_from_file_location("gmsh", API)
            gmsh = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gmsh)
        finally:
            ctypes.util.find_library = previous
        gmsh.initialize(["gmsh", "-nopopup"], readConfigFiles=False)
        try:
            result = build_occ_mesh(gmsh, request)
            result["runtime_provenance"] = provenance
            result["request_sha256"] = request_sha256
            gmsh.write("mesh.msh")
        finally:
            gmsh.finalize()
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > MAX_RESULT:
        raise ValueError("GMSH_RESULT: result control limit exceeded")
    Path("result.tmp").write_bytes(encoded)
    os.replace("result.tmp", "result.json")


def run_occ_case(request, output_dir, *, timeout_s=180, memory_limit_mb=2048, cancellation_event=None):
    """Run a typed OCC mesh job in an OS resource-limited separate process.

    No caller-supplied executable, Python, GEO text, CAD path or shell argument
    is accepted. Existing output directories are refused. Not a filesystem or
    network sandbox, and not a general signed release worker.
    """
    from .gmsh_occ_mesher import validate_request
    validate_request(request)
    provenance = verify_installation()
    if type(timeout_s) is not int or not 1 <= timeout_s <= 600:
        raise ValueError("GMSH_RESOURCE: timeout must be 1..600 seconds")
    if type(memory_limit_mb) is not int or not 256 <= memory_limit_mb <= 8192:
        raise ValueError("GMSH_RESOURCE: memory must be 256..8192 MiB")
    payload = json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(payload) > MAX_REQUEST:
        raise ValueError("GMSH_RESOURCE: request exceeds 8 MiB")
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output/"request.json").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    root = Path(__file__).resolve().parents[2]
    source = ("import sys; sys.path.insert(0," + repr(str(root)) + "); "
              "from python.spike_core.gmsh_occ_runtime import worker; worker(" + repr(digest) + ")")
    process = run_adapter_process([sys.executable, "-I", "-"], cwd=output,
        timeout_s=timeout_s, memory_limit_mb=memory_limit_mb, output_limit_bytes=512*1024**2,
        stream_limit_bytes=4*1024**2, cancellation_event=cancellation_event,
        stdin_payload=source.encode(), windows_active_process_limit=1)
    (output/"worker.log").write_text(process["stdout"]+process["stderr"], encoding="utf-8")
    (output/"process.json").write_text(json.dumps({
        "return_code": process["return_code"], "timeout_s": timeout_s,
        "memory_limit_mb": memory_limit_mb,
        "memory_limit_enforced": process.get("memory_limit_enforced", False),
        "job_assignment_race_closed": process.get("job_assignment_race_closed", False),
        "filesystem_sandbox": False, "redistribution_approved": False,
    }, indent=2), encoding="utf-8")
    if process["return_code"] != 0:
        raise RuntimeError("GMSH_EXECUTION: mesher failed; inspect " + str(output/"worker.log"))
    result_path = output/"result.json"
    if result_path.is_symlink() or not result_path.is_file() or result_path.stat().st_size > MAX_RESULT:
        raise ValueError("GMSH_RESULT: invalid result artifact")
    result = json.loads(result_path.read_bytes(), object_pairs_hook=_unique)
    if result.get("request_sha256") != digest or result.get("runtime_provenance") != provenance:
        raise ValueError("GMSH_RESULT: provenance binding mismatch")
    manifest = {p.name: _sha(p) for p in output.iterdir() if p.is_file()}
    (output/"SHA256.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return result
