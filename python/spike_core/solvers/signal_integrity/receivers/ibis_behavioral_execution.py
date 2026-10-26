# SPDX-License-Identifier: Apache-2.0
"""Explicit trusted ngspice execution of SPIKE-generated IBIS circuits only."""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import re
import tempfile
from typing import Callable

from ....circuit_worker_supervisor import SupervisorInitializationError, supervise_process
from ...external_engines.circuits.ngspice_plugin import _find_ngspice

MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_EXECUTABLE_BYTES = 128 * 1024 * 1024
MAX_SAMPLES = 32768
PROBES = {"v(driver_pad)": "driver_pad_v", "v(receiver_pad)": "receiver_pad_v",
          "v(driver_die)": "driver_die_v", "v(receiver_die)": "receiver_die_v",
          "i(vdriver_probe)": "driver_current_a"}


def _identity(executable: str | Path, expected_sha256: str | None = None) -> tuple[Path, str]:
    path = Path(executable)
    if not path.is_absolute() or not path.is_file() or path != path.resolve(strict=True):
        raise ValueError("ngspice executable must be an absolute normalized regular file")
    for member in (path, *path.parents):
        state = member.lstat()
        if member.is_symlink() or getattr(state, "st_file_attributes", 0) & 0x400:
            raise ValueError("ngspice executable path cannot contain links or reparse points")
    if not 0 < path.stat().st_size <= MAX_EXECUTABLE_BYTES:
        raise ValueError("ngspice executable exceeds the identity size limit")
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if expected_sha256 is not None and (not isinstance(expected_sha256, str) or
            not re.fullmatch(r"[0-9a-f]{64}", expected_sha256) or expected_sha256 != actual):
        raise ValueError("ngspice executable SHA-256 admission failed")
    return path, actual


def inspect_ibis_behavioral_runtime(executable: str | None = None) -> dict:
    """Read executable identity; never load it or invoke a version command."""
    selected = executable if executable is not None else _find_ngspice()
    result = {"contract": "spike/ibis-behavioral-runtime/v1", "status": "unavailable",
              "executable": None, "executable_sha256": None, "executed": False,
              "version": None, "trusted_native_code_required": True, "sandboxed": False}
    if selected:
        path, digest = _identity(selected)
        result.update(status="available", executable=str(path), executable_sha256=digest)
    return result


def _read_raw(path: Path, stop_time_s: float) -> dict:
    """Reject partial, complex, duplicate, nonfinite and extra raw vectors/plots."""
    if not path.is_file() or path.stat().st_size > MAX_OUTPUT_BYTES:
        raise ValueError("ngspice raw output is absent or exceeds 4 MiB")
    lines = path.read_text(encoding="ascii").splitlines()
    try:
        variables_at, values_at = lines.index("Variables:"), lines.index("Values:")
        headers = {}
        for line in lines[:variables_at]:
            key, separator, value = line.partition(":")
            if not separator or key in headers:
                raise ValueError("malformed or duplicate raw header")
            headers[key] = value.strip()
        count, points = int(headers["No. Variables"]), int(headers["No. Points"])
        if headers.get("Flags") != "real" or "Transient" not in headers.get("Plotname", ""):
            raise ValueError("expected one real transient plot")
        if count != len(PROBES) + 1 or not 2 <= points <= MAX_SAMPLES:
            raise ValueError("raw output dimensions are outside the admitted range")
        variables = []
        for index, line in enumerate(lines[variables_at + 1:values_at]):
            fields = line.split()
            if len(fields) != 3 or int(fields[0]) != index:
                raise ValueError("malformed raw variable inventory")
            variables.append(fields[1].lower())
        if len(variables) != count or variables[0] != "time" or set(variables[1:]) != set(PROBES):
            raise ValueError("raw probe inventory does not match the compiled circuit")
        data = lines[values_at + 1:]
        if len(data) != count * points:
            raise ValueError("raw output has incomplete or extra samples")
        vectors = {name: [] for name in variables}
        for point in range(points):
            for column, name in enumerate(variables):
                fields = data[point * count + column].split()
                if len(fields) != (2 if column == 0 else 1) or (column == 0 and int(fields[0]) != point):
                    raise ValueError("raw point indices or column counts are malformed")
                value = float(fields[-1])
                if not math.isfinite(value):
                    raise ValueError("raw output contains nonfinite samples")
                vectors[name].append(value)
        times = vectors.pop("time")
        if times[0] != 0 or any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError("raw time samples must start at zero and increase strictly")
        if not math.isclose(times[-1], stop_time_s, rel_tol=1e-7, abs_tol=1e-18):
            raise ValueError("raw output did not reach the requested stop time")
        return {"time_s": times, "probes": {PROBES[key]: values for key, values in vectors.items()}}
    except (KeyError, IndexError, UnicodeError, OverflowError) as error:
        raise ValueError("malformed ngspice transient raw output") from error


def run_ibis_behavioral(request: dict, *, executable: str, executable_sha256: str,
                        execution_requested: bool = False, timeout_seconds: float = 30,
                        memory_limit_mib: int = 512, cancelled: Callable[[], bool] = lambda: False) -> dict:
    """Recompile and admit exact executable bytes before one supervised launch."""
    from .ibis_behavioral import compile_ibis_behavioral

    if execution_requested is not True:
        raise ValueError("IBIS execution requires explicit execution_requested=true and trusted native runtime consent")
    if not isinstance(executable_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", executable_sha256):
        raise ValueError("IBIS execution requires an explicit lowercase 64-hex executable SHA-256")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 30:
        raise ValueError("IBIS execution timeout must be positive and at most 30 seconds")
    if isinstance(memory_limit_mib, bool) or not isinstance(memory_limit_mib, int) or not 16 <= memory_limit_mib <= 512:
        raise ValueError("IBIS execution memory budget must be 16..512 MiB")
    compiled = compile_ibis_behavioral(request)
    result = {"contract": "spike/ibis-behavioral-result/v1", "status": "unsupported",
              "model_status": "experimental", "production_qualified": False, "time_s": [], "probes": {},
              "request_sha256": sha256(json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
              "compile_sha256": compiled.get("netlist_sha256"), "diagnostics": compiled["diagnostics"],
              "provenance": {"sandboxed": False, "trusted_native_code": True, "execution_requested": True,
                             "timeout_seconds": timeout_seconds, "memory_limit_mib": memory_limit_mib,
                             "output_admission_bytes": MAX_OUTPUT_BYTES}}
    if compiled["status"] != "ready":
        return result
    program, digest = _identity(executable, executable_sha256)
    result["provenance"].update(executable_sha256=digest, compiler=compiled["contract"],
                                endpoints=compiled.get("endpoints", {}))
    with tempfile.TemporaryDirectory(prefix="spike-ibis-") as directory:
        root = Path(directory).resolve()
        netlist, raw, log = root / "circuit.cir", root / "result.raw", root / "ngspice.log"
        netlist.write_text(compiled["netlist"], encoding="ascii")
        output_exceeded = False

        def stop_requested():
            nonlocal output_exceeded
            output_exceeded = sum(path.stat().st_size for path in (raw, log) if path.is_file()) > MAX_OUTPUT_BYTES
            return output_exceeded or cancelled()

        try:
            outcome = supervise_process(program, ["-n", "-b", "-o", str(log), "-r", str(raw), str(netlist)],
                                        cwd=root, timeout_seconds=timeout_seconds, memory_limit_mib=memory_limit_mib,
                                        cancelled=stop_requested)
        except SupervisorInitializationError:
            result.update(status="failed", diagnostics=[{"code": "IBIS_SUPERVISOR_INITIALIZATION_FAILED",
                          "message": "Required OS resource enforcement was not established; execution was not retried."}])
            return result
        result["provenance"].update(os_enforcement=outcome.os_enforcement, elapsed_seconds=outcome.elapsed_seconds,
                                    returncode=outcome.returncode)
        if log.is_file() and log.stat().st_size <= MAX_OUTPUT_BYTES:
            result["provenance"]["engine_log_sha256"] = sha256(log.read_bytes()).hexdigest()
        if output_exceeded or sum(path.stat().st_size for path in (raw, log) if path.is_file()) > MAX_OUTPUT_BYTES:
            result.update(status="failed", diagnostics=[{"code": "IBIS_OUTPUT_LIMIT", "message": "Output exceeded the 4 MiB admission limit."}])
        elif outcome.status != "completed" or outcome.returncode != 0:
            result.update(status=outcome.status if outcome.status in {"cancelled", "timeout"} else "failed",
                          diagnostics=[{"code": "IBIS_ENGINE_FAILED", "message": "Supervised ngspice did not complete successfully."}])
            if log.is_file() and log.stat().st_size <= MAX_OUTPUT_BYTES:
                result["engine_log_tail"] = log.read_text(encoding="utf-8", errors="replace")[-4096:]
        else:
            try:
                parsed = _read_raw(raw, request["analysis"]["stop_time_s"])
                for role in ("driver", "receiver"):
                    lower, upper = compiled["endpoints"][role]["die_voltage_domain_v"]
                    if any(value < lower or value > upper for value in parsed["probes"][f"{role}_die_v"]):
                        raise ValueError(f"{role} die voltage exceeded the admitted IBIS I/V source domain; continuation output rejected")
                result.update(status="completed", **parsed)
                result["provenance"]["raw_sha256"] = sha256(raw.read_bytes()).hexdigest()
            except (ValueError, OSError) as error:
                result.update(status="failed", diagnostics=[{"code": "IBIS_RAW_INVALID", "message": str(error)}])
        return result
