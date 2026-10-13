# SPDX-License-Identifier: Apache-2.0
"""Fixed-entry, hash-admitted resource-bounded assembly air meshing worker."""
import ctypes.util
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from . import gmsh_occ_runtime as runtime
from .assembly_airflow_mesh import validate_geometry, build_air_mesh


def worker(digest):
    provenance = runtime.verify_installation()
    payload = Path('request.json').read_bytes()
    if len(payload) > runtime.MAX_REQUEST or hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError('AIRFLOW_REQUEST: changed or oversized control')
    job = json.loads(payload, object_pairs_hook=runtime._unique)
    validate_geometry(job)
    with os.add_dll_directory(str(runtime.DLL.parent)):
        previous = ctypes.util.find_library
        try:
            ctypes.util.find_library = lambda name: str(runtime.DLL) if name in ('gmsh', 'gmsh-4.15') else previous(name)
            spec = importlib.util.spec_from_file_location('gmsh', runtime.API)
            gmsh = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gmsh)
        finally:
            ctypes.util.find_library = previous
        gmsh.initialize(['gmsh', '-nopopup'], readConfigFiles=False)
        try:
            result = build_air_mesh(gmsh, job)
            gmsh.write('mesh.msh')
        finally:
            gmsh.finalize()
    result.update(request_sha256=digest, runtime_provenance=provenance)
    encoded = json.dumps(result, allow_nan=False).encode()
    if len(encoded) > runtime.MAX_RESULT:
        raise ValueError('AIRFLOW_RESOURCE: mesh result too large')
    Path('result.json').write_bytes(encoded)


def run_air_mesh(job, output_dir, *, cancellation_event=None, timeout_s=180, memory_limit_mb=2048):
    validate_geometry(job)
    # Parent desktop workers may use another Python; only the isolated admitted
    # child loads the Gmsh DLL. Pin the same local development interpreter.
    executable = Path('C:/Users/yawar/AppData/Local/Programs/Python/Python311/python.exe')
    if not executable.is_file() or runtime._sha(executable) != '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec':
        raise ValueError('AIRFLOW_RUNTIME: pinned development Python 3.11 unavailable')
    for path, expected in runtime.ARTIFACTS.items():
        if not path.is_file() or path.is_symlink() or runtime._sha(path) != expected:
            raise ValueError('AIRFLOW_RUNTIME: Gmsh entry artifact changed')
    provenance = {'version': '4.15.2', 'entry_artifacts': {str(p):h for p,h in runtime.ARTIFACTS.items()},
        'approval': 'local-development-only', 'redistribution_approved': False, 'transitive_dll_admission': 'not_qualified'}
    if type(timeout_s) is not int or not 1 <= timeout_s <= 600 or type(memory_limit_mb) is not int or not 256 <= memory_limit_mb <= 8192:
        raise ValueError('AIRFLOW_RESOURCE: invalid meshing budget')
    payload = json.dumps(job, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if len(payload) > runtime.MAX_REQUEST:
        raise ValueError('AIRFLOW_RESOURCE: request too large')
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output/'request.json').write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    packages = [str(executable.parent/'Lib/site-packages')]
    source = ('import sys; sys.path.insert(0,' + repr(str(Path(__file__).resolve().parents[2]))
        + '); sys.path.extend(' + repr(packages) + '); '
        'from python.spike_core.assembly_airflow_runtime import worker; worker(' + repr(digest) + ')')
    process = runtime.run_adapter_process([str(executable), '-I', '-S', '-'], cwd=output,
        timeout_s=timeout_s, memory_limit_mb=memory_limit_mb, output_limit_bytes=512*1024**2,
        stream_limit_bytes=4*1024**2, cancellation_event=cancellation_event,
        stdin_payload=source.encode(), windows_active_process_limit=1)
    (output/'worker.log').write_text(process['stdout']+process['stderr'], encoding='utf-8')
    (output/'process.json').write_text(json.dumps({
        'return_code': process['return_code'], 'timeout_s': timeout_s,
        'memory_limit_mb': memory_limit_mb,
        'memory_limit_enforced': process.get('memory_limit_enforced', False),
        'job_assignment_race_closed': process.get('job_assignment_race_closed', False),
        'worker_interpreter': str(executable), 'worker_interpreter_sha256': runtime._sha(executable),
        'filesystem_sandbox': False, 'redistribution_approved': False}, indent=2), encoding='utf-8')
    if process['return_code'] != 0:
        raise RuntimeError('AIRFLOW_MESH: mesher failed; inspect '+str(output/'worker.log'))
    target = output/'result.json'
    if target.is_symlink() or target.stat().st_size > runtime.MAX_RESULT:
        raise ValueError('AIRFLOW_RESULT: invalid result artifact')
    result = json.loads(target.read_bytes(), object_pairs_hook=runtime._unique)
    if result.get('request_sha256') != digest or result.get('runtime_provenance') != provenance:
        raise ValueError('AIRFLOW_RESULT: provenance binding mismatch')
    return result
