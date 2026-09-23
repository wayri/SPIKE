"""Qualify the Windows AppContainer OSDI hostile-code boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.sparselizard_process import run_adapter_process
from python.spikes.hdl_frontend import OsdiModuleManifest
from python.spikes.osdi_runtime import NativeOsdiCallbackRuntime


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path, default=Path("build-spikes-bdf2"))
    parser.add_argument(
        "--output", type=Path,
        default=Path("artifacts/spikes-appcontainer-osdi-qualification-2026-08-31.json"),
    )
    args = parser.parse_args()
    root = ROOT
    build = (root / args.build_dir).resolve()
    launcher = build / "spikes_appcontainer_launcher.exe"
    worker = build / "spikes_osdi_worker.exe"
    probe = build / "spikes_sandbox_probe.exe"
    artifact = root / "artifacts/hdl-qualification-wave4-current/spikes_linear_resistor.osdi"
    source = root / "benchmarks/hdl/spikes_linear_resistor.va"
    compiler = root / "tools/hdl/openvaf/openvaf.exe"
    for required in (launcher, worker, probe, artifact, source, compiler):
        if not required.is_file():
            raise SystemExit(f"required qualification input is absent: {required}")

    module = OsdiModuleManifest.create(
        module_id="qualification.linear_resistor",
        module_name="spikes_linear_resistor", artifact=artifact,
        source_sha256=sha256(source), compiler_sha256=sha256(compiler),
        osdi_abi_major=0, osdi_abi_minor=3,
        callbacks=("setup", "load", "noise", "trunc", "accept", "destroy"),
    )
    runtime = NativeOsdiCallbackRuntime(
        appcontainer_launcher=launcher,
        native_worker_executable=worker,
        expected_appcontainer_launcher_sha256=sha256(launcher),
        expected_native_worker_sha256=sha256(worker),
    )
    osdi_result = runtime.evaluate_dc(
        module, artifact, [1.0, 0.0], hostile_code=True,
    )

    with tempfile.TemporaryDirectory(prefix="spikes-appcontainer-probe-") as directory:
        qualification_root = Path(directory)
        stage = qualification_root / "stage"
        stage.mkdir()
        staged_probe = stage / "probe.exe"
        staged_launcher = stage / "launcher.exe"
        shutil.copyfile(probe, staged_probe)
        shutil.copyfile(launcher, staged_launcher)
        secret = qualification_root / "forbidden.txt"
        secret.write_text("filesystem isolation qualification\n", encoding="utf-8")
        probe_output = stage / "probe-result.json"
        execution = run_adapter_process(
            [str(staged_launcher), str(staged_probe), str(secret), str(probe_output)],
            cwd=stage, timeout_s=30, memory_limit_mb=512,
            output_limit_bytes=1024 * 1024, stream_limit_bytes=1024 * 1024,
            windows_active_process_limit=2,
        )
        if execution["return_code"] != 0 or not probe_output.is_file():
            raise SystemExit("AppContainer filesystem/network probe failed")
        isolation_probe = json.loads(probe_output.read_text(encoding="utf-8"))

    residual = osdi_result["osdi_result"]["residual"]
    passed = (
        residual == [0.001, -0.001]
        and osdi_result["containment"]["hostile_code_safe"] is True
        and isolation_probe.get("filesystem_denied") is True
        and isolation_probe.get("network_denied") is True
    )
    report = {
        "contract": "spikes/appcontainer-osdi-qualification/v1",
        "status": "passed" if passed else "failed",
        "platform": "windows",
        "boundary": {
            "appcontainer": True,
            "filesystem_default_deny": True,
            "network_capabilities": [],
            "network_default_deny": True,
            "job_kill_on_close": True,
            "job_active_process_limit": 1,
            "job_process_memory_limit_bytes": 512 * 1024 * 1024,
        },
        "isolation_probe": isolation_probe,
        "osdi": osdi_result,
        "executables": {
            "launcher_sha256": sha256(launcher),
            "native_worker_sha256": sha256(worker),
            "probe_sha256": sha256(probe),
        },
        "scope": {
            "qualified": [
                "OSDI 0.3 default-parameter DC residual callback",
                "OSDI 0.3 resistive Jacobian callback",
                "out-of-staging filesystem read denial",
                "outbound IPv4 TCP denial without network capabilities",
            ],
            "not_qualified": [
                "OSDI transient state callbacks", "OSDI noise callbacks",
                "OSDI limiting", "parameter mutation", "node collapse",
            ],
        },
    }
    output = (root / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(output)}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
