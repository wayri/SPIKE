# SPDX-License-Identifier: Apache-2.0
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
import sysconfig

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


def _worker_interpreter():
    """Bypass the Windows venv redirector, retaining a one-process Job limit.

    Paths come solely from the running trusted interpreter configuration.
    Package directories are inserted, not processed with site.addsitedir:
    their .pth files are never executed by this bootstrap.
    """
    executable = Path(sys.executable).resolve()
    packages = list(dict.fromkeys(str(Path(sysconfig.get_path(kind)).resolve())
                                 for kind in ('purelib', 'platlib')))
    if sys.platform == 'win32' and sys.prefix != sys.base_prefix:
        executable = Path(sys._base_executable).resolve()
        configuration = Path(sys.prefix)/'pyvenv.cfg'
        if configuration.is_symlink():
            raise ValueError('GMSH_RUNTIME: linked virtual environment configuration is not admitted')
        if configuration.is_file():
            if configuration.stat().st_size > 8192:
                raise ValueError('GMSH_RUNTIME: oversized virtual environment configuration')
            flags = [line.split('=', 1)[1].strip().lower()
                     for line in configuration.read_text(encoding='utf-8').splitlines()
                     if '=' in line and line.split('=', 1)[0].strip().lower() == 'include-system-site-packages']
            if len(flags) > 1 or any(flag not in ('true', 'false') for flag in flags):
                raise ValueError('GMSH_RUNTIME: ambiguous package inheritance declaration')
            if flags == ['true']:
                packages = list(dict.fromkeys(packages + [
                    str(Path(sysconfig.get_path(kind, vars={'base': sys.base_prefix,
                                                          'platbase': sys.base_exec_prefix})).resolve())
                    for kind in ('purelib', 'platlib')]))
    if not executable.is_file() or any(not Path(path).is_dir() for path in packages):
        raise ValueError('GMSH_RUNTIME: trusted interpreter or package directories unavailable')
    return executable, packages


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
    executable, packages = _worker_interpreter()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output/"request.json").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    root = Path(__file__).resolve().parents[2]
    from .gmsh_environment import isolated_preflight_source
    source = isolated_preflight_source(root, packages) + (
              "\nfrom python.spike_core.gmsh_occ_runtime import worker\nworker(" + repr(digest) + ")\n")
    process = run_adapter_process([str(executable), "-I", "-S", "-"], cwd=output,
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
        "worker_interpreter": str(executable), "worker_interpreter_sha256": _sha(executable),
        "configured_package_directories": packages,
        "dependency_preflight": json.loads((output/'environment.json').read_text(encoding='utf-8'))
            if (output/'environment.json').is_file() else {'status': 'missing'},
    }, indent=2), encoding="utf-8")
    if process["return_code"] != 0:
        raise RuntimeError("GMSH_EXECUTION: mesher failed; inspect " + str(output/"worker.log"))
    environment_path = output/'environment.json'
    if not environment_path.is_file() or environment_path.is_symlink() or environment_path.stat().st_size > 65536:
        raise ValueError('GMSH_DEPENDENCY: missing or invalid isolated environment evidence')
    environment = json.loads(environment_path.read_text(encoding='utf-8'), object_pairs_hook=_unique)
    if environment.get('status') != 'passed' or environment.get('isolated') is not True or environment.get('site_disabled') is not True:
        raise ValueError('GMSH_DEPENDENCY: isolated dependency preflight did not pass')
    result_path = output/"result.json"
    if result_path.is_symlink() or not result_path.is_file() or result_path.stat().st_size > MAX_RESULT:
        raise ValueError("GMSH_RESULT: invalid result artifact")
    result = json.loads(result_path.read_bytes(), object_pairs_hook=_unique)
    if result.get("request_sha256") != digest or result.get("runtime_provenance") != provenance:
        raise ValueError("GMSH_RESULT: provenance binding mismatch")
    result['runtime_environment'] = environment
    manifest = {p.name: _sha(p) for p in output.iterdir() if p.is_file()}
    (output/"SHA256.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return result
