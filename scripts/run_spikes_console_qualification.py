#!/usr/bin/env python3
"""Qualify a compiled SPIKES console against the checked-in live dashboard."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "spikes/native-console-qualification/v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--console", type=Path, required=True)
    parser.add_argument(
        "--project", type=Path,
        default=ROOT / "examples/spikes/electrothermal_dashboard.spkc",
    )
    parser.add_argument(
        "--commands", type=Path,
        default=ROOT / "examples/spikes/dashboard_commands.txt",
    )
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    console = arguments.console.resolve(strict=True)
    project = arguments.project.resolve(strict=True)
    commands = arguments.commands.resolve(strict=True)
    completed = subprocess.run(
        [str(console), str(project), "--script", str(commands), "--capacity", "32"],
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )
    version = subprocess.run(
        [str(console), "--version"], cwd=ROOT, capture_output=True, text=True,
        timeout=10, check=False,
    )
    required_markers = {
        "dashboard_rendered": "SPIKES DASHBOARD" in completed.stdout,
        "control_toggled": "control a toggled" in completed.stdout,
        "checkpoint_restored": "checkpoint restored" in completed.stdout,
        "runtime_probe_attached": (
            "probe attached" in completed.stdout and "VLOAD" in completed.stdout
        ),
        "health_probe_present": "HEALTH" in completed.stdout,
        "temperature_probe_present": "TEMP" in completed.stdout,
        "history_rendered": "time_s,value" in completed.stdout,
    }
    passed = (
        completed.returncode == 0
        and version.returncode == 0
        and all(required_markers.values())
    )
    report = {
        "contract": CONTRACT,
        "status": "passed" if passed else "failed",
        "claims": {
            "native_console_executable": passed,
            "persistent_interactive_dashboard": passed,
            "scripted_controls_and_probes": passed,
            "bounded_rolling_capture": passed,
            "hard_realtime": False,
            "physical_hil": False,
        },
        "inputs": {
            "console": {"path": str(console), "sha256": sha256(console)},
            "project": {"path": str(project), "sha256": sha256(project)},
            "commands": {"path": str(commands), "sha256": sha256(commands)},
        },
        "version": version.stdout.strip(),
        "return_code": completed.returncode,
        "checks": required_markers,
        "stdout_sha256": hashlib.sha256(completed.stdout.encode("utf-8")).hexdigest(),
        "stderr": completed.stderr[-2000:],
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8",
    )
    print(f"SPIKES console qualification: {report['status']}")
    print(arguments.output.resolve())
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
