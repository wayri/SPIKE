# SPDX-License-Identifier: Apache-2.0
"""Fixed-code bridge from desktop Python to the pinned local OCC environment."""
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess

from .gmsh_extension_api import execute

MAX_REQUEST = 64 * 1024**2
MAX_RESULT = 8 * 1024**2


def _local_appdata():
    """Windows folder identity; never inherit an executable path from the environment."""
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 0x001c, None, 0, buffer) != 0 or not buffer.value:
        raise ValueError('GMSH_RUNTIME: Windows local application folder unavailable')
    return Path(buffer.value)


def _interpreter():
    if sys.platform != 'win32':
        raise ValueError('GMSH_RUNTIME: this development integration requires Windows CPython 3.11')
    if sys.version_info[:2] == (3, 11) and not getattr(sys, 'frozen', False):
        return None
    base = _local_appdata() / 'Programs' / 'Python' / 'Python311'
    executable = base/'python.exe'
    if not executable.is_file() or executable.is_symlink() or not (base/'Lib'/'site-packages').is_dir():
        raise ValueError('GMSH_RUNTIME: install the supported local CPython 3.11 OCC dependencies; no interpreter was selected')
    return executable.resolve()


def worker():
    """Called solely by the fixed bootstrap, inside the bounded bridge process."""
    path = Path('request.json')
    if path.is_symlink() or path.stat().st_size > MAX_REQUEST:
        raise ValueError('GMSH_REQUEST: invalid bridge input')
    from .gmsh_occ_runtime import _unique
    result = execute(json.loads(path.read_bytes(), object_pairs_hook=_unique))
    encoded = json.dumps(result, allow_nan=False, separators=(',', ':')).encode()
    if len(encoded) > MAX_RESULT:
        raise ValueError('GMSH_RESULT: result exceeds 8 MiB; use a coarser mesh')
    Path('result.tmp').write_bytes(encoded)
    os.replace('result.tmp', 'result.json')


def dispatch(request):
    """No caller executable, Python/GEO source, command or shell is accepted."""
    payload = json.dumps(request, allow_nan=False, separators=(',', ':')).encode()
    if len(payload) > MAX_REQUEST:
        raise ValueError('GMSH_REQUEST: extension request exceeds 64 MiB')
    executable = _interpreter()
    if executable is None:
        return execute(request)
    root = Path(__file__).resolve().parents[2]
    packages = executable.parent/'Lib'/'site-packages'
    # Add package directories directly. Site processing and .pth execution are
    # disabled, matching the existing native OCC worker bootstrap.
    from .gmsh_environment import isolated_preflight_source
    bootstrap = isolated_preflight_source(root, [packages]) + (
                 '\nfrom python.spike_core.gmsh_extension_runtime import worker\nworker()\n')
    with tempfile.TemporaryDirectory(prefix='spike-gmsh-bridge-') as directory:
        job = Path(directory)
        (job/'request.json').write_bytes(payload)
        # Windows rejects this runtime's nested Job Objects. The fixed Python
        # bridge has a wall-clock bound; each native OCC child retains its own
        # existing memory/time/process Job limits. Killing this parent closes
        # its owned native Job handle (KILL_ON_JOB_CLOSE).
        with (job/'bridge.log').open('wb') as diagnostic:
            process = subprocess.run([str(executable), '-I', '-S', '-'], cwd=job,
                input=bootstrap.encode(), timeout=900, stdout=diagnostic, stderr=subprocess.STDOUT,
                shell=False, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        result_path = job/'result.json'
        environment_path = job/'environment.json'
        environment = None
        if environment_path.is_file() and not environment_path.is_symlink() and environment_path.stat().st_size <= 65536:
            from .gmsh_occ_runtime import _unique
            environment = json.loads(environment_path.read_bytes(), object_pairs_hook=_unique)
        if process.returncode != 0:
            with (job/'bridge.log').open('rb') as diagnostic:
                diagnostic.seek(max(0, diagnostic.seek(0, 2)-8192))
                detail = diagnostic.read(8192).decode('utf-8', errors='replace')
            raise ValueError('GMSH_BRIDGE: '+detail+'; isolated_environment='+json.dumps(environment, separators=(',', ':')))
        if not environment or environment.get('status') != 'passed' or environment.get('isolated') is not True or environment.get('site_disabled') is not True:
            raise ValueError('GMSH_DEPENDENCY: missing or failed bridge environment preflight')
        if not result_path.is_file() or result_path.is_symlink() or result_path.stat().st_size > MAX_RESULT:
            raise ValueError('GMSH_RESULT: missing or oversized complete result')
        from .gmsh_occ_runtime import _unique
        result = json.loads(result_path.read_bytes(), object_pairs_hook=_unique)
        result['data']['bridge_environment'] = environment
        return result
