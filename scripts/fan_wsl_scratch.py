# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Opt-in local study staging; generated cases only, not a general launcher."""
import re
from pathlib import Path
from python.spike_core.openfoam_multiregion_execution import load_verified_runnable_case
from python.spike_core.openfoam_runtime import detect_openfoam_runtime
from python.spike_core.sparselizard_process import run_adapter_process


class ScratchRunner:
    def __init__(self, case, runner):
        self.case, self.manifest = load_verified_runnable_case(case)
        self.runner = runner
        runtime = detect_openfoam_runtime()
        if runtime.get("transport") != "wsl_process":
            raise ValueError("Native scratch staging requires the admitted WSL runtime")
        self.prefix = [runtime["launcher"], "-d", runtime["distribution"], "--"]
        drive = self.case.drive.rstrip(":").lower()
        if len(drive) != 1 or not drive.isalpha():
            raise ValueError("Study case must be Windows drive-backed")
        self.mounted = "/mnt/" + drive + self.case.as_posix()[2:]
        self.remote = self._transfer(["/usr/bin/mktemp", "-d", "/tmp/spike-fan-XXXXXXXXXX"])["stdout"].strip()
        if not re.fullmatch(r"/tmp/spike-fan-[A-Za-z0-9]{10}", self.remote):
            raise ValueError("Unexpected scratch path")
        self._transfer(["/usr/bin/cp", "-r", "--", self.mounted + "/.", self.remote + "/"])

    def _transfer(self, args):
        result = run_adapter_process(self.prefix + args, cwd=self.case, timeout_s=120,
            memory_limit_mb=512, output_limit_bytes=8*1024**3, stream_limit_bytes=1024**2,
            windows_active_process_limit=64)
        if result["return_code"] != 0:
            raise RuntimeError("WSL scratch transfer failed: " + result.get("stderr", ""))
        return result

    def __call__(self, command, **kwargs):
        command = list(command)
        if "-help" in command:
            return self.runner(command, **kwargs)
        index = command.index("-case") + 1
        if command[index] != self.mounted:
            raise ValueError("Scratch worker received an unexpected case path")
        command[index] = self.remote
        result = self.runner(command, **kwargs)
        # Copy after a complete command, never read live history as evidence.
        self._transfer(["/usr/bin/cp", "-r", "--", self.remote + "/.", self.mounted + "/"])
        load_verified_runnable_case(self.case)
        return result
