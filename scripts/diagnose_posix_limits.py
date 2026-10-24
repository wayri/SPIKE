# SPDX-License-Identifier: Apache-2.0
"""Bounded release diagnostics; resource limits are changed only after fork."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys


def _limits() -> dict:
    import resource

    return {name: list(resource.getrlimit(getattr(resource, name)))
            for name in ("RLIMIT_AS", "RLIMIT_CORE")}


def _memory() -> dict:
    result = subprocess.run(
        ["ps", "-o", "vsz=,rss=", "-p", str(os.getpid())],
        capture_output=True, text=True, timeout=3, check=True,
    )
    virtual, resident = (int(value) for value in result.stdout.split())
    return {"virtual_kib": virtual, "resident_kib": resident}


def _error(error: Exception) -> dict:
    # These diagnostics never retain commands, environment values or traceback paths.
    message = re.sub(r"(?:[A-Za-z]:[\\/]|/)[^\s'\";,)]*", "<path>", str(error))
    return {"type": type(error).__name__, "errno": getattr(error, "errno", None),
            "message": message[:256]}


def _emit(value: dict) -> None:
    print(json.dumps(value, sort_keys=True), flush=True)


def _parent(mode: str, memory_mib: int) -> None:
    import resource

    versions = {}
    if mode == "loaded":
        for name in ("numpy", "scipy", "shapely"):
            module = importlib.import_module(name)
            versions[name] = module.__version__
    before = _limits()
    _emit({"event": "parent", "mode": mode, "memory_mib": memory_mib,
           "limits": before, "memory": _memory(), "imports": versions})
    read_fd, write_fd = os.pipe()

    def apply_child_limits() -> None:
        records = []
        failed = False
        for name, requested in (("RLIMIT_AS", memory_mib * 1024 * 1024),
                                ("RLIMIT_CORE", 0)):
            key = getattr(resource, name)
            record = {"resource": name, "requested": [requested, requested],
                      "before": list(resource.getrlimit(key))}
            try:
                resource.setrlimit(key, (requested, requested))
                record["status"] = "applied"
            except Exception as error:
                failed = True
                record.update(status="rejected", error=_error(error))
            record["after"] = list(resource.getrlimit(key))
            records.append(record)
        os.write(write_fd, json.dumps(records).encode("utf-8"))
        if failed:
            raise RuntimeError("diagnostic child resource admission rejected")

    record = {"event": "launch"}
    try:
        child = subprocess.Popen(
            [sys.executable, "-c", "import json,resource; print(json.dumps({n:list(resource.getrlimit(getattr(resource,n))) for n in ('RLIMIT_AS','RLIMIT_CORE')}))"],
            shell=False, close_fds=True, pass_fds=(write_fd,),
            preexec_fn=apply_child_limits, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            stdout, stderr = child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            stdout, stderr = child.communicate(timeout=2)
            record["timed_out"] = True
        record.update(returncode=child.returncode, stderr_bytes=len(stderr),
                      stderr_sha256=hashlib.sha256(stderr).hexdigest())
        if child.returncode == 0:
            record["after_exec_limits"] = json.loads(stdout)
    except Exception as error:
        record["error"] = _error(error)
    finally:
        os.close(write_fd)
        data = os.read(read_fd, 8192)
        os.close(read_fd)
    record["preexec"] = json.loads(data) if data else []
    record["parent_limits_after"] = _limits()
    record["parent_limits_unchanged"] = before == record["parent_limits_after"]
    _emit(record)


def diagnose() -> dict:
    report = {"contract": "spike/posix-limit-diagnostics/v1",
              "platform": {"system": platform.system(), "release": platform.release(),
                           "machine": platform.machine(), "python": platform.python_version(),
                           "macos": platform.mac_ver()[0]},
              "probes": [], "production_configuration_changed": False}
    for mode in ("light", "loaded"):
        for memory_mib in (256, 2048, 4096):
            stage = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--parent", mode,
                 "--memory-mib", str(memory_mib)],
                start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            timed_out = False
            try:
                stdout, stderr = stage.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(stage.pid, signal.SIGKILL)
                stdout, stderr = stage.communicate(timeout=3)
            report["probes"].append({
                "mode": mode, "memory_mib": memory_mib, "returncode": stage.returncode,
                "timed_out": timed_out, "stderr_bytes": len(stderr),
                "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
                "events": [json.loads(line) for line in stdout.splitlines()],
            })
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("build/qualification/posix-limits.json"))
    parser.add_argument("--parent", choices=("light", "loaded"), help=argparse.SUPPRESS)
    parser.add_argument("--memory-mib", type=int, choices=(256, 2048, 4096), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if os.name != "posix":
        parser.error("this diagnostic requires a native POSIX runner")
    if args.parent:
        if args.memory_mib is None:
            parser.error("child probe requires --memory-mib")
        _parent(args.parent, args.memory_mib)
        return 0
    report = diagnose()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    _emit(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
