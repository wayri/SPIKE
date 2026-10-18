# SPDX-License-Identifier: Apache-2.0
"""Check process survival only; this does not establish frontend readiness."""
import os
import signal
import subprocess
import sys
import tempfile

command = sys.argv[1:]
if not command:
    raise SystemExit('Supply the installed desktop command.')
with tempfile.TemporaryFile() as log:
    process = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
    try:
        result = process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        print('Desktop process survival check passed; frontend readiness remains unverified.')
    else:
        log.seek(0)
        raise SystemExit(f'Desktop exited during startup ({result}):\n{log.read().decode(errors="replace")}')
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=10)
