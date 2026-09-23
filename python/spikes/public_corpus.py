"""Deterministic first-party equal-model corpus and local evidence runner.

The corpus is CC0-staged but has no canonical public repository URL in this
workspace.  Local cross-engine evidence is therefore useful engineering data,
not claim-eligible public benchmark evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


PUBLIC_LADDER_SIZES = {"small": 16, "medium": 500, "large": 2_000}
STAGED_CORPUS_CONTRACT = "spikes/staged-public-equal-model-corpus/v1"
LOCAL_EVIDENCE_CONTRACT = "spikes/local-equal-model-evidence/v1"
_NUMBER = re.compile(r"^[ \t]*\d+[ \t]+([^ \t]+)", re.MULTILINE)


class PublicCorpusError(RuntimeError):
    pass


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_ladder_deck(tier: str, sections: int) -> bytes:
    if tier not in PUBLIC_LADDER_SIZES or PUBLIC_LADDER_SIZES[tier] != sections:
        raise PublicCorpusError("ladder tier and section count do not match policy")
    lines = [
        f"SPIKES public {tier} {sections}-section unit-resistor ladder",
        "* SPDX-License-Identifier: CC0-1.0",
        "* First-party deterministic sparse-MNA scale fixture",
        f"IIN 0 n{sections - 1} 1",
        "R0 n0 0 1",
    ]
    lines.extend(
        f"R{index} n{index} n{index - 1} 1"
        for index in range(1, sections)
    )
    lines.extend((".op", ".end"))
    return ("\n".join(lines) + "\n").encode("ascii")


def validate_staged_corpus(root: str | Path) -> dict[str, Any]:
    corpus = Path(root).resolve(strict=True)
    license_path = corpus / "LICENSE.txt"
    provenance_path = corpus / "PROVENANCE.md"
    if not license_path.is_file() or "CC0-1.0" not in license_path.read_text(encoding="utf-8"):
        raise PublicCorpusError("corpus CC0 license declaration is missing")
    if not provenance_path.is_file():
        raise PublicCorpusError("corpus provenance review is missing")
    cases = []
    for tier, sections in PUBLIC_LADDER_SIZES.items():
        path = corpus / f"ladder_{tier}_{sections}.cir"
        expected = render_ladder_deck(tier, sections)
        if not path.is_file() or path.read_bytes() != expected:
            raise PublicCorpusError(f"{tier} deck does not match deterministic source")
        cases.append({
            "case_id": f"public.ladder.{tier}", "tier": tier,
            "sections": sections, "deck": path.name,
            "deck_sha256": _sha256_file(path), "analysis": "op",
            "probe": f"v(n{sections - 1})", "expected": float(sections),
            "absolute_tolerance": max(2.0e-8, sections * 1.0e-9),
            "license_spdx": "CC0-1.0",
        })
    source_digest = _sha256_bytes(b"".join(
        (corpus / item["deck"]).read_bytes() for item in cases
    ))
    return {
        "contract": STAGED_CORPUS_CONTRACT,
        "status": "staged_not_publicly_published",
        "corpus_root": str(corpus),
        "source_bundle_sha256": source_digest,
        "license": {"path": str(license_path), "sha256": _sha256_file(license_path), "spdx": "CC0-1.0"},
        "provenance": {"path": str(provenance_path), "sha256": _sha256_file(provenance_path)},
        "cases": cases,
        "publication": {
            "canonical_https_url": "",
            "publicly_retrievable": False,
            "blocker": "No repository remote or authorized publication destination is configured.",
        },
        "performance_claim_eligible": False,
    }


def _peak_working_set(process: subprocess.Popen[bytes]) -> tuple[int | None, str]:
    if os.name != "nt":
        return None, "child_peak_working_set_not_implemented_on_this_host"
    try:
        import ctypes
        from ctypes import wintypes

        class COUNTERS(ctypes.Structure):
            _fields_ = (
                ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            )
        counters = COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(COUNTERS), wintypes.DWORD)
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        if psapi.GetProcessMemoryInfo(
            wintypes.HANDLE(process._handle), ctypes.byref(counters), ctypes.sizeof(counters)
        ):
            return int(counters.PeakWorkingSetSize), "windows_process_peak_working_set"
    except (AttributeError, OSError, ValueError):
        pass
    return None, "windows_peak_working_set_unavailable"


def _run_measured_process(
    command: Sequence[str], *, cwd: Path, timeout_s: float,
) -> dict[str, Any]:
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        started = time.perf_counter_ns()
        process = subprocess.Popen(
            list(command), cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=stdout_file, stderr=stderr_file, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        peak = 0
        peak_scope = "unavailable"
        deadline = time.monotonic() + timeout_s
        while process.poll() is None:
            measured, scope = _peak_working_set(process)
            peak_scope = scope
            if measured is not None:
                peak = max(peak, measured)
            if time.monotonic() >= deadline:
                process.kill()
                process.wait(timeout=5)
                raise PublicCorpusError("benchmark process timed out")
            time.sleep(0.002)
        elapsed = time.perf_counter_ns() - started
        measured, scope = _peak_working_set(process)
        peak_scope = scope
        if measured is not None:
            peak = max(peak, measured)
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read(16 * 1024 * 1024)
        stderr = stderr_file.read(4 * 1024 * 1024)
    if process.returncode != 0:
        raise PublicCorpusError(
            f"benchmark process exited {process.returncode}: {stderr[-2000:].decode(errors='replace')}"
        )
    return {
        "elapsed_ns": elapsed, "peak_working_set_bytes": peak or None,
        "peak_memory_scope": peak_scope, "stdout": stdout, "stderr": stderr,
    }


def _spikes_command(deck: Path, library: Path, probe: str) -> list[str]:
    return [
        sys.executable, "-m", "python.spikes.public_corpus", "--worker",
        "--deck", str(deck), "--library", str(library), "--probe", probe,
    ]


def _observe_spikes(result: Mapping[str, Any], probe: str) -> float:
    try:
        payload = json.loads(result["stdout"].decode("utf-8"))
        if payload.get("status") != "completed" or payload.get("probe") != probe:
            raise ValueError(payload)
        return float(payload["observed"])
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicCorpusError("SPIKES benchmark result is invalid") from exc


def _ngspice_command(deck: Path, executable: Path, root: Path) -> list[str]:
    return [
        str(executable), "-n", "-b", "-o", str(root / "ngspice.log"),
        "-r", str(root / "result.raw"), str(deck),
    ]


def _observe_ngspice(result: Mapping[str, Any], raw: Path, probe: str) -> float:
    if not raw.is_file() or raw.stat().st_size > 64 * 1024 * 1024:
        raise PublicCorpusError("ngspice raw result is missing or exceeds the bound")
    text = raw.read_text(encoding="utf-8", errors="strict")
    target = probe.lower()
    variable_match = re.search(r"(?m)^Variables:\s*$", text)
    value_match = re.search(r"(?m)^Values:\s*$", text)
    if variable_match is None or value_match is None:
        raise PublicCorpusError("ngspice raw result is not ASCII")
    variables = variable_match.start()
    values = value_match.start()
    names = []
    for line in text[variable_match.end():values].splitlines():
        parts = line.split()
        if len(parts) >= 3:
            names.append(parts[1].lower())
    try:
        target_index = names.index(target)
    except ValueError as exc:
        raise PublicCorpusError(f"ngspice omitted {probe}") from exc
    rows = [line.split() for line in text[value_match.end():].splitlines() if line.strip()]
    values_by_index: list[float] = []
    current = 0
    for parts in rows:
        if len(parts) >= 2 and parts[0].isdigit():
            current = 0
            value = parts[1]
        else:
            value = parts[-1]
        if current == target_index:
            values_by_index.append(float(value))
        current += 1
    if not values_by_index:
        raise PublicCorpusError(f"ngspice emitted no values for {probe}")
    return values_by_index[-1]


def _run_engine_case(
    *, engine_id: str, case: Mapping[str, Any], deck: Path,
    command_factory: Callable[[Path], tuple[list[str], Path | None]],
    observer: Callable[[Mapping[str, Any], Path | None, str], float],
    repetitions: int, cwd: Path, timeout_s: float,
) -> dict[str, Any]:
    runs = []
    # Every observation is process-inclusive.  The first cohort records fresh
    # process launches before the measured warm cohort; the second cohort is
    # collected only after the host executable/deck/model pages have been
    # exercised.  Keeping both full cohorts avoids the former one-cold-sample
    # ambiguity and satisfies the public evidence contract's 5/5 minimum.
    for _ in range(repetitions * 2):
        command, output = command_factory(deck)
        measured = _run_measured_process(command, cwd=cwd, timeout_s=timeout_s)
        try:
            measured["observed"] = observer(measured, output, str(case["probe"]))
        finally:
            if output is not None and output.parent.name.startswith("spikes-ngspice-public-"):
                shutil.rmtree(output.parent, ignore_errors=True)
        runs.append(measured)
    errors = [abs(float(run["observed"]) - float(case["expected"])) for run in runs]
    passed = max(errors) <= float(case["absolute_tolerance"])
    return {
        "engine_id": engine_id, "case_id": case["case_id"],
        "status": "passed" if passed else "failed",
        "deck_sha256": case["deck_sha256"], "timing_scope": "process_inclusive",
        "observed": [run["observed"] for run in runs],
        "maximum_absolute_error": max(errors),
        "absolute_tolerance": case["absolute_tolerance"],
        "cold_elapsed_ns": [run["elapsed_ns"] for run in runs[:repetitions]],
        "warm_elapsed_ns": [run["elapsed_ns"] for run in runs[repetitions:]],
        "cold_median_ns": int(statistics.median(run["elapsed_ns"] for run in runs[:repetitions])),
        "warm_median_ns": int(statistics.median(run["elapsed_ns"] for run in runs[repetitions:])),
        "peak_working_set_bytes": max(
            (int(run["peak_working_set_bytes"]) for run in runs if run["peak_working_set_bytes"] is not None),
            default=None,
        ),
        "peak_memory_scope": runs[0]["peak_memory_scope"],
    }


def _spikes_worker(deck: Path, library: Path, probe: str) -> dict[str, Any]:
    """Parse the exact deck and solve only its declared scalar through native MNA."""
    from .contracts import ProbeDescriptor
    from .native_abi import load_native_library
    from .native_runner import _populate
    from .netlist import parse_netlist

    deck_bytes = deck.read_bytes()
    descriptor = ProbeDescriptor.parse(probe)
    project = parse_netlist(
        deck_bytes.decode("ascii"), source_name=str(deck), probes=(descriptor,),
        native_extensions=True,
    )
    if project.analysis.mode != "operating_point" or descriptor.quantity != "node_voltage":
        raise PublicCorpusError("public ladder worker accepts one operating-point voltage probe")
    native = load_native_library(library)
    with native.circuit() as circuit:
        _populate(circuit, project)
        with circuit.solve_operating_point(
            # Equal-model ladder cases are sparse MNA systems.  Use the native
            # symbolic-ordering/SparseLU path instead of the older CG harness,
            # which repeated thousands of iterations and measured the wrong
            # production solver route for this topology.
            linear_solver="sparse_lu", linear_threads=1,
            max_linear_iterations=max(100, len(project.elements) * 4),
        ) as result:
            if result.status != "converged":
                raise PublicCorpusError(f"SPIKES solve failed: {result.status}: {result.message}")
            observed = result.node_voltage(descriptor.targets[0])
            if len(descriptor.targets) == 2:
                observed -= result.node_voltage(descriptor.targets[1])
            return {
                "contract": "spikes/public-corpus-worker/v1", "status": "completed",
                "deck_sha256": _sha256_bytes(deck_bytes), "probe": probe,
                "observed": observed, "diagnostics": result.diagnostics(),
            }


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--deck", type=Path)
    parser.add_argument("--library", type=Path)
    parser.add_argument("--probe")
    arguments = parser.parse_args()
    if not arguments.worker or arguments.deck is None or arguments.library is None or not arguments.probe:
        parser.error("this entry point is reserved for bounded public-corpus workers")
    try:
        payload = _spikes_worker(
            arguments.deck.resolve(strict=True), arguments.library.resolve(strict=True),
            arguments.probe,
        )
        print(json.dumps(payload, allow_nan=False))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({
            "contract": "spikes/public-corpus-worker/v1", "status": "failed",
            "issue": str(exc)[:4096],
        }))
        return 2


def run_local_equal_model_evidence(
    corpus_root: str | Path, *, spikes_library: str | Path,
    ngspice_executable: str | Path | None = None, repetitions: int = 5,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    if not 5 <= repetitions <= 20:
        raise PublicCorpusError("repetitions must be from 5 through 20")
    corpus = validate_staged_corpus(corpus_root)
    root = Path(corpus_root).resolve(strict=True)
    library = Path(spikes_library).resolve(strict=True)
    ngspice = Path(ngspice_executable).resolve(strict=True) if ngspice_executable else None
    engines = [{
        "engine_id": "spikes", "executable": str(Path(sys.executable).resolve()),
        "executable_sha256": _sha256_file(Path(sys.executable).resolve()),
        "implementation": str(library), "implementation_sha256": _sha256_file(library),
        "status": "available",
    }]
    if ngspice:
        engines.append({
            "engine_id": "ngspice", "executable": str(ngspice),
            "executable_sha256": _sha256_file(ngspice), "status": "available",
        })
    else:
        engines.append({"engine_id": "ngspice", "status": "blocked", "reason": "not configured"})
    records = []
    for case in corpus["cases"]:
        deck = root / case["deck"]
        records.append(_run_engine_case(
            engine_id="spikes", case=case, deck=deck,
            command_factory=lambda selected: (_spikes_command(selected, library, str(case["probe"])), None),
            observer=lambda result, _output, probe: _observe_spikes(result, probe),
            repetitions=repetitions, cwd=Path(__file__).resolve().parents[2], timeout_s=timeout_s,
        ))
        if ngspice:
            # Each run gets a separate result directory so no stale raw file can pass.
            def factory(selected: Path) -> tuple[list[str], Path]:
                run_root = Path(tempfile.mkdtemp(prefix="spikes-ngspice-public-"))
                return _ngspice_command(selected, ngspice, run_root), run_root / "result.raw"

            records.append(_run_engine_case(
                engine_id="ngspice", case=case, deck=deck, command_factory=factory,
                observer=lambda result, output, probe: _observe_ngspice(result, output, probe),
                repetitions=repetitions, cwd=Path(__file__).resolve().parents[2], timeout_s=timeout_s,
            ))
    passed = all(record["status"] == "passed" for record in records)
    host = {
        "system": platform.system(), "release": platform.release(),
        "machine": platform.machine(), "python": platform.python_version(),
    }
    return {
        "contract": LOCAL_EVIDENCE_CONTRACT,
        "generated_at_epoch_s": time.time(), "status": "passed" if passed else "failed",
        "host": host, "host_fingerprint": _sha256_bytes(json.dumps(host, sort_keys=True).encode()),
        "corpus": corpus, "engines": engines, "records": records,
        "accuracy_passed": passed, "cold_warm_separated": True,
        "peak_memory_complete": all(record["peak_working_set_bytes"] is not None for record in records),
        "performance_claim_eligible": False,
        "claim_blockers": [
            "Corpus is locally staged under CC0 but has no canonical public HTTPS publication URL.",
            "Only SPIKES and locally vendored ngspice are available; LTspice/QSPICE/PSIM/SIMPLIS are absent.",
            "Three transparent resistor ladders establish sparse scaling, not application or analysis breadth.",
        ],
    }


__all__ = [
    "LOCAL_EVIDENCE_CONTRACT", "PUBLIC_LADDER_SIZES", "PublicCorpusError",
    "render_ladder_deck", "run_local_equal_model_evidence", "validate_staged_corpus",
]


if __name__ == "__main__":
    raise SystemExit(_main())
