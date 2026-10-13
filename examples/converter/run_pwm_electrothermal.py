"""Retain original PWM inputs, native outputs and independent reference evidence.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Yawar B (wayri) and SPIKE contributors.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from python.spike_core.pwm_electrothermal import REQUEST, run_pwm_electrothermal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    benchmark = ROOT / "build-peec-native" / ("test_spikes_pwm_electrothermal.exe" if sys.platform == "win32" else "test_spikes_pwm_electrothermal")
    check = subprocess.run([str(benchmark)], capture_output=True, text=True, timeout=60, check=True)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {}
    def retain(name, data):
        content = data if isinstance(data, str) else json.dumps(data, indent=2, allow_nan=False)+"\n"
        (args.output_dir/name).write_text(content, encoding="utf-8", newline="\n")
        artifacts[name] = hashlib.sha256(content.encode()).hexdigest()
    retain("native-independent-reference.txt", check.stdout)
    summaries = []
    for index, dt in enumerate((2e-6, 1e-6, 0.5e-6)):
        request = {"contract": REQUEST, "parameters": {"maximum_step_s": dt}}
        result = run_pwm_electrothermal(request)
        retain(f"request-{index}.json", request)
        retain(f"result-{index}.json", result)
        summaries.append({"maximum_step_s": dt, "endpoint": result["windows"][-1],
                          "quality": result["quality"], "energy": result["energy"],
                          "library_sha256": result["runtime"]["library_sha256"]})
    sources = ["python/spike_core/pwm_electrothermal.py", "src/spikes/transient_solver.cpp", "src/spikes/transient_session.cpp",
               "tests/test_spikes_pwm_electrothermal.cpp", "tests/python/test_pwm_electrothermal.py",
               "schemas/pwm-electrothermal-request-v1.schema.json", "schemas/pwm-electrothermal-result-v1.schema.json",
               "examples/converter/run_pwm_electrothermal.py"]
    report = {"contract": "spike/pwm-electrothermal-evidence/v1", "status": "reference_passed",
              "python": platform.python_version(), "platform": platform.platform(),
              "artifacts": artifacts, "source_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
              "native_benchmark_sha256": hashlib.sha256(benchmark.read_bytes()).hexdigest(),
              "cases": summaries, "limits": ["synthetic behavioral-switch/winding-only thermal reference",
                  "not semiconductor switching loss, measured hardware or release qualification"]}
    retain("evidence.json", report)
    print(json.dumps({"output_dir": str(args.output_dir.resolve()), "cases": len(summaries), "status": report["status"]}))


if __name__ == "__main__":
    main()
