# SPDX-License-Identifier: Apache-2.0
"""Linux exec guardian: retain supervisor PID and die when adapter disappears."""
import ctypes
import hashlib
import os
from pathlib import Path
import signal
import sys


def main():
    parent_pid = int(sys.argv[1])
    program = Path(sys.argv[2])
    digest = sys.argv[3]
    mode = sys.argv[4]
    if len(sys.argv) != 5 or mode not in {'run', 'validate'}:
        raise ValueError('Invalid fixed Xyce guardian ABI.')
    if sys.platform != 'linux' or os.getppid() != parent_pid:
        raise RuntimeError('Xyce adapter disappeared before guardian admission.')
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'Parent death signal unavailable.')
    if os.getppid() != parent_pid:
        raise RuntimeError('Xyce adapter disappeared during guardian admission.')
    if not program.is_absolute() or program.is_symlink() or not program.is_file():
        raise ValueError('Invalid Xyce executable.')
    if program.stat().st_size > 256 * 1024 * 1024 or program.stat().st_mode & 0o6000:
        raise ValueError('Xyce executable size or privilege mode is inadmissible.')
    identity = hashlib.sha256()
    with program.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            identity.update(block)
    if identity.hexdigest() != digest:
        raise ValueError('Xyce executable changed after admission.')
    arguments = [str(program), '-l', 'xyce.log', '-o', 'wave']
    if mode == 'validate':
        arguments.append('-syntax')
    arguments.append('circuit.cir')
    os.execv(str(program), arguments)


if __name__ == '__main__':
    main()
