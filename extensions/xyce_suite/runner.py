# SPDX-License-Identifier: Apache-2.0
"""Fixed native Xyce process calls; no shell, MPI launcher or plugin loading."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import sys
from python.spike_core.circuit_worker_supervisor import supervise_process
from .cases import artifacts, file_digest, regular, verify_case, waveform


def runtime(options) -> dict:
    if not isinstance(options, dict) or set(options) - {'executable', 'timeout_seconds', 'memory_limit_mib'}:
        raise ValueError('XYCE_RUNTIME: only executable, timeout_seconds and memory_limit_mib are supported.')
    explicit = options.get('executable')
    if explicit is not None and (not isinstance(explicit, str) or not explicit.strip()):
        raise ValueError('XYCE_RUNTIME: executable must be a nonempty absolute path.')
    configured = explicit or os.environ.get('SPIKE_XYCE_EXECUTABLE')
    candidate = Path(configured).expanduser() if configured else None
    if candidate is None:
        found = shutil.which('Xyce') or shutil.which('Xyce.exe')
        candidate = Path(found) if found else None
    if candidate is not None:
        if not candidate.is_absolute():
            raise ValueError('XYCE_RUNTIME: select an absolute native executable path.')
        regular(candidate)
        candidate = candidate.resolve()
        if candidate.suffix.lower() in {'.bat', '.cmd', '.ps1', '.py', '.sh'}:
            raise ValueError('XYCE_RUNTIME: scripts and shell wrappers are not admitted.')
    available = candidate is not None and candidate.is_file()
    if available and candidate.stat().st_size > 256 * 1024 * 1024:
        raise ValueError('XYCE_RUNTIME: native executable exceeds 256 MiB admission limit.')
    if available and os.name == 'nt' and candidate.suffix.lower() != '.exe':
        raise ValueError('XYCE_RUNTIME: select a native .exe, not a library or script.')
    if available and os.name != 'nt' and (candidate.stat().st_mode & 0o6000 or not os.access(candidate, os.X_OK)):
        raise ValueError('XYCE_RUNTIME: executable must be runnable without setuid/setgid privilege changes.')
    return {'available': available, 'executable': str(candidate) if candidate else None,
            'sha256': file_digest(candidate) if available else None,
            'selection': 'explicit' if explicit else 'configured_or_path',
            'plugins_supported': False, 'mpi_supported': False}


def budgets(options) -> tuple[float, int]:
    timeout, memory = options.get('timeout_seconds', 120), options.get('memory_limit_mib', 2048)
    if isinstance(timeout, bool) or not isinstance(timeout, (float, int)) or not 1 <= timeout <= 300:
        raise ValueError('XYCE_LIMIT: timeout must be between 1 and 300 seconds.')
    if isinstance(memory, bool) or not isinstance(memory, int) or not 64 <= memory <= 8192:
        raise ValueError('XYCE_LIMIT: memory must be an integer between 64 and 8192 MiB.')
    return float(timeout), memory


def diagnostics(path: Path) -> list[dict]:
    log = path / 'xyce.log'
    regular(log)
    if not log.is_file():
        return []
    if log.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('XYCE_OUTPUT: log exceeds resource budget.')
    lines = log.read_text(encoding='utf-8', errors='replace').splitlines()
    messages = []
    for line in lines:
        if any(word in line.lower() for word in ('error', 'warning', 'failed', 'fatal')):
            messages.append({'code': 'XYCE_NATIVE', 'severity': 'warning' if 'warning' in line.lower() else 'error',
                             'message': line[:1200]})
    return messages[:100]


def inspect_case(path: Path) -> dict:
    verify_case(path)
    record = path / 'result.json'
    regular(record)
    if not record.is_file():
        return {'status': 'prepared', 'solved': False, 'diagnostics': [], 'waveforms': [],
                'artifacts': artifacts(path)}
    if record.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('XYCE_OUTPUT: result record exceeds budget.')
    result = json.loads(record.read_text(encoding='utf-8'))
    admitted_artifacts = artifacts(path)
    # Never turn stale files or a nonzero native exit into a solved result.
    waves = []
    if result.get('status') == 'completed' and result.get('returncode') == 0:
        expected = result.get('output_digests', {})
        current = {item.name: file_digest(item)
                   for item in path.glob('wave*.csv') if item.is_file() and item.stat().st_size <= 4 * 1024 * 1024}
        if not expected or expected != current:
            raise ValueError('XYCE_OUTPUT: saved solver waveforms changed after execution.')
        waves = [waveform(item) for item in sorted(path.glob('wave*.csv'))]
    return {**result, 'solved': bool(waves) and result.get('status') == 'completed',
            'waveforms': waves, 'artifacts': admitted_artifacts}


def run(path: Path, selected: dict, options: dict, validate: bool) -> dict:
    verify_case(path)
    timeout, memory = budgets(options)
    lock = path / 'active.lock'
    regular(lock)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise ValueError('XYCE_BUSY: case already active or interrupted; prepare a fresh case.') from error
    os.close(descriptor)
    result = {'status': 'failed', 'solved': False, 'diagnostics': [], 'waveforms': []}
    exceeded = False
    try:
        # Repeat runs cannot admit waveforms from an earlier successful solve.
        for item in list(path.glob('wave*')) + [path / 'xyce.log', path / 'result.json', path / 'cancel.flag']:
            regular(item)
            if item.is_file():
                item.unlink()
        program = Path(selected['executable'])
        regular(program)
        if file_digest(program) != selected['sha256']:
            raise ValueError('XYCE_RUNTIME: executable changed during admission.')
        arguments = ['-l', 'xyce.log', '-o', 'wave']
        if validate:
            arguments.append('-syntax')
        arguments.append('circuit.cir')
        if os.name != 'nt':
            if sys.platform != 'linux' or getattr(sys, 'frozen', False):
                raise ValueError('XYCE_CONTAINMENT: execution requires Windows or source Python on Linux.')
            arguments = ['-I', '-S', str(Path(__file__).with_name('guardian.py').resolve()),
                         str(os.getpid()), str(program), selected['sha256'],
                         'validate' if validate else 'run']
            program = Path(sys.executable).resolve()
        def cancelled():
            nonlocal exceeded
            entries = list(path.iterdir())
            total = 0
            for item in entries:
                try:
                    regular(item)
                except (ValueError, OSError):
                    exceeded = True
                    return True
                if item.is_file():
                    size = item.stat().st_size
                    total += size
                    if size > 8 * 1024 * 1024:
                        exceeded = True
            if len(entries) > 96 or total > 32 * 1024 * 1024:
                exceeded = True
            return exceeded or (path / 'cancel.flag').exists()
        outcome = supervise_process(program, arguments, cwd=path.resolve(),
            timeout_seconds=timeout, memory_limit_mib=memory, cancelled=cancelled)
        artifacts(path)
        notes = diagnostics(path)
        status = outcome.status
        if exceeded:
            status = 'resource_limit'
        elif status == 'completed':
            if outcome.returncode != 0 or any(d['severity'] == 'error' for d in notes):
                status = 'failed'
            elif validate:
                status = 'validated_syntax'
        waves = []
        if status == 'completed':
            waves = [waveform(item) for item in sorted(path.glob('wave*.csv'))]
            if not waves:
                status = 'completed_without_waveforms'
                notes.append({'code': 'XYCE_NO_WAVEFORMS', 'severity': 'warning',
                              'message': 'Xyce returned no admitted CSV waveform; use native .PRINT FORMAT=CSV.'})
        result = {'status': status, 'solved': status == 'completed' and bool(waves),
                  'returncode': outcome.returncode, 'elapsed_seconds': outcome.elapsed_seconds,
                  'os_enforcement': outcome.os_enforcement, 'diagnostics': notes,
                  'waveforms': waves, 'runtime': selected}
        result['output_digests'] = {item.name: file_digest(item)
                                    for item in path.glob('wave*.csv')}
        (path / 'result.json').write_text(json.dumps({k: v for k, v in result.items() if k != 'waveforms'},
                                                   allow_nan=False), encoding='utf-8')
        result['artifacts'] = artifacts(path)
        return result
    finally:
        lock.unlink(missing_ok=True)
