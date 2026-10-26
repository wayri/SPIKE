# SPDX-License-Identifier: Apache-2.0
"""Fixed-command, bounded process adapter for separately installed CalculiX."""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import time

MAX_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_EXECUTABLE_BYTES = 256 * 1024 * 1024


def _artifact_bytes(root):
    """Count live regular files; CCX removes transient artifacts during a solve."""
    total = 0
    for path in root.iterdir():
        try:
            info = path.stat()
        except FileNotFoundError:
            # Disappearance between enumeration and stat is a normal solver
            # transition. Permission/I/O errors must still fail monitoring.
            continue
        if stat.S_ISREG(info.st_mode):
            total += info.st_size
    return total


def _executable():
    configured = os.environ.get('SPIKE_CALCULIX_EXECUTABLE')
    candidates = [configured] if configured else [shutil.which('ccx'), shutil.which('ccx.exe'),
        'C:/msys64/mingw64/bin/ccx.exe', 'C:/msys64/ucrt64/bin/ccx.exe',
        'C:/Program Files/CalculiX/ccx.exe', 'C:/Program Files/CalculiX/bin/ccx.exe',
        'C:/Program Files/bConverged/CalculiX/ccx/ccx.exe']
    for value in candidates:
        if not value:
            continue
        path = Path(value)
        if not path.is_absolute() or not path.is_file():
            continue
        path = path.resolve()
        if os.name == 'nt' and path.suffix.lower() != '.exe':
            continue
        if not 0 < path.stat().st_size <= MAX_EXECUTABLE_BYTES:
            continue
        return path
    return None


def probe_calculix_runtime():
    """Discovery only; executable identity does not establish validated physics."""
    path = _executable()
    if path is None:
        return {'available': False, 'status': 'unavailable', 'solver_id': 'external.calculix',
                'message': 'Install CalculiX separately and set SPIKE_CALCULIX_EXECUTABLE to its absolute ccx executable path, then restart SPIKE.'}
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'available': True, 'status': 'detected', 'solver_id': 'external.calculix',
            'executable': str(path), 'executable_sha256': digest,
            'message': 'Separately installed executable detected; a completed solve is required for execution evidence.'}


def parse_calculix_temperatures(text, count):
    """Read the complete final NT table at end time 1; reject partial/stale data."""
    blocks, current, current_time = [], None, None
    header = re.compile(r'temperatures(?:\s*\(.*?\))?\s+for\s+set\s+NALL\s+and\s+time\s+([^\s]+)', re.I)
    for line in text.splitlines():
        match = header.search(line)
        if match:
            if current is not None:
                blocks.append((current_time, current))
            current, current_time = {}, float(match.group(1).replace('D', 'E').replace('d', 'e'))
            continue
        if current is None or not line.strip():
            continue
        fields = line.split()
        if re.match(r'\s*(?:S T E P|INCREMENT)\s+\d+\s*$', line):
            continue
        if len(fields) != 2 or not fields[0].isdigit():
            raise ValueError('CALCULIX_OUTPUT: unexpected NT table row.')
        node, value = int(fields[0]), float(fields[1].replace('D', 'E').replace('d', 'e'))
        if node in current or not 1 <= node <= count or not math.isfinite(value) or value < 0:
            raise ValueError('CALCULIX_OUTPUT: duplicate, unknown or nonphysical nodal temperature.')
        current[node] = value
    if current is not None:
        blocks.append((current_time, current))
    if not blocks or not math.isclose(blocks[-1][0], 1., abs_tol=1e-8, rel_tol=0):
        raise ValueError('CALCULIX_INCOMPLETE: final temperature table at end time 1 is missing.')
    final = blocks[-1][1]
    if set(final) != set(range(1, count+1)):
        raise ValueError('CALCULIX_INCOMPLETE: temperature table does not cover the admitted mesh.')
    return [final[i] for i in range(1, count+1)]


def validate_calculix_options(engine_options=None):
    """Admit fixed runner controls without discovering or executing a runtime."""
    options = {} if engine_options is None else engine_options
    if not isinstance(options, dict) or set(options) - {'timeout_seconds', 'threads'}:
        raise ValueError('CALCULIX_OPTIONS: only timeout_seconds and threads are supported; no paths or commands.')
    timeout, threads = options.get('timeout_seconds', 300), options.get('threads', 1)
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 1 <= timeout <= 3300:
        raise ValueError('CALCULIX_OPTIONS: timeout_seconds must be between 1 and 3300.')
    if type(threads) is not int or not 1 <= threads <= min(32, os.cpu_count() or 1):
        raise ValueError('CALCULIX_OPTIONS: threads exceeds the available bounded CPU budget.')
    return {'timeout_seconds': timeout, 'threads': threads}


def run_calculix_deck(compiled, engine_options=None, *, cancel_check=None,
                      temperature_parser=None, completed_step_time=1.0):
    """Only a compiler-produced deck, fixed job name/argv and isolated directory."""
    options = validate_calculix_options(engine_options)
    timeout, threads = options['timeout_seconds'], options['threads']
    if cancel_check is not None and cancel_check():
        raise ValueError('CALCULIX_CANCELLED: external thermal solve cancelled.')
    runtime = probe_calculix_runtime()
    if not runtime['available']:
        raise ValueError('CALCULIX_UNAVAILABLE: ' + runtime['message'])
    executable = runtime['executable']
    environment = dict(os.environ, OMP_NUM_THREADS=str(threads), CCX_NPROC_RESULTS=str(threads),
                       CCX_NPROC_EQUATION_SOLVER=str(threads))
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='spike-calculix-') as directory:
        root = Path(directory)
        deck = compiled['deck'].encode('ascii')
        (root/'thermal.inp').write_bytes(deck)
        output_path = root/'solver.log'
        with output_path.open('wb') as log:
            process = subprocess.Popen([executable, '-i', 'thermal'], cwd=root, env=environment,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, shell=False,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                while process.poll() is None:
                    if cancel_check is not None and cancel_check():
                        raise ValueError('CALCULIX_CANCELLED: external thermal solve cancelled.')
                    if time.monotonic()-started > timeout:
                        raise ValueError('CALCULIX_TIMEOUT: bounded solver execution expired.')
                    if _artifact_bytes(root) > MAX_OUTPUT_BYTES:
                        raise ValueError('CALCULIX_OUTPUT_LIMIT: solver artifact budget exceeded.')
                    time.sleep(.05)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
        if cancel_check is not None and cancel_check():
            raise ValueError('CALCULIX_CANCELLED: external thermal solve cancelled.')
        if _artifact_bytes(root) > MAX_OUTPUT_BYTES:
            raise ValueError('CALCULIX_OUTPUT_LIMIT: solver artifact budget exceeded.')
        log_text = output_path.read_text(encoding='utf-8', errors='replace')
        if process.returncode != 0 or '*ERROR' in log_text.upper() or not re.search(r'job\s+finished', log_text, re.I):
            raise ValueError('CALCULIX_FAILED: solver did not finish successfully. ' + log_text[-3000:])
        dat_path = root/'thermal.dat'
        if not dat_path.is_file():
            raise ValueError('CALCULIX_INCOMPLETE: solver returned no temperature artifact.')
        dat = dat_path.read_bytes()
        parser = temperature_parser or parse_calculix_temperatures
        temperatures = parser(dat.decode('ascii'), compiled['nodes'])
        version = re.search(r'CalculiX\s+Version\s*:?\s*([0-9]+\.[0-9]+(?:\.[0-9]+)?)', log_text, re.I)
        return {'node_temperatures_k': temperatures, 'runtime': runtime,
                'solver_version': version.group(1) if version else 'unreported',
                'input_sha256': hashlib.sha256(deck).hexdigest(),
                'output_sha256': hashlib.sha256(dat).hexdigest(),
                'log_sha256': hashlib.sha256(log_text.encode()).hexdigest(),
                'log_tail': log_text[-3000:], 'exit_code': process.returncode,
                'elapsed_seconds': time.monotonic()-started, 'threads': threads,
                'completed_step_time': completed_step_time, 'solver_reported_finished': True}
