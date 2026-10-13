# SPDX-License-Identifier: Apache-2.0
"""Bounded fresh-process execution for independent local analysis jobs."""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Sequence

from .acceleration import acceleration_catalog
from .compute_policy import cpu_thread_budget
from .parallel_child import ALLOWED_METHODS
from . import __version__


BATCH_CONTRACT = "spike/parallel-batch/v1"
RESULT_CONTRACT = "spike/parallel-batch-result/v1"
CATALOG_CONTRACT = "spike/parallel-pool-catalog/v1"
MAX_JOBS = 64
MAX_CONCURRENCY = 8
MAX_THREADS_PER_JOB = 32
MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_JOB_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_BATCH_OUTPUT_BYTES = 6 * 1024 * 1024
MAX_STDOUT_BYTES = MAX_JOB_OUTPUT_BYTES + 1024
MAX_STDERR_BYTES = 64 * 1024
MAX_TIMEOUT_S = 180.0
MAX_BATCH_TIMEOUT_S = 900.0
MAX_JSON_NODES = 100_000
MAX_LIST_ITEMS = 100_000
MAX_OBJECT_KEYS = 4096
MAX_NESTING = 32
MAX_STRING_BYTES = 256 * 1024
MAX_TOTAL_STRING_BYTES = 2 * 1024 * 1024
MAX_JOB_INPUT_BYTES = 1024 * 1024
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_BATCH_LOCK = threading.Lock()
_PREFIX_LOCK = threading.Lock()
_worker_prefix: tuple[str, ...] | None = None


def configure_worker_prefix(prefix: Sequence[str] | None) -> None:
    """Set a trusted host-owned child argv prefix, or reset to the default.

    The batch request has no executable field.  This hook is intended for a
    packaged host and tests; every item is passed directly to ``Popen`` with
    ``shell=False``.
    """
    global _worker_prefix
    if prefix is not None:
        if (not isinstance(prefix, (list, tuple)) or not prefix
                or any(not isinstance(item, str) or not item for item in prefix)):
            raise ValueError("Worker prefix must be a nonempty string argument array.")
        value: tuple[str, ...] | None = tuple(prefix)
    else:
        value = None
    with _PREFIX_LOCK:
        _worker_prefix = value


def _command() -> list[str]:
    with _PREFIX_LOCK:
        prefix = _worker_prefix
    default = ((sys.executable, "--parallel-child") if getattr(sys, "frozen", False)
               else (sys.executable, "-m", "python.spike_core.parallel_child"))
    return list(prefix or default)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _validate_json(value: Any) -> None:
    stack: list[tuple[Any, int]] = [(value, 0)]
    nodes = 0
    string_bytes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_NESTING:
            raise ValueError("Parallel batch JSON exceeds the structural limit.")
        if item is None or isinstance(item, (str, bool)):
            if isinstance(item, str):
                size = len(item.encode("utf-8"))
                string_bytes += size
                if size > MAX_STRING_BYTES or string_bytes > MAX_TOTAL_STRING_BYTES:
                    raise ValueError("Parallel batch string dimensions exceed the admitted limits.")
            continue
        if isinstance(item, int):
            if item.bit_length() > 1024:
                raise ValueError("Parallel batch integer is outside the supported range.")
            continue
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("Parallel batch numbers must be finite.")
            continue
        if isinstance(item, list):
            if len(item) > MAX_LIST_ITEMS:
                raise ValueError("Parallel batch array exceeds the item limit.")
            stack.extend((child, depth + 1) for child in item)
            continue
        if isinstance(item, dict):
            if len(item) > MAX_OBJECT_KEYS:
                raise ValueError("Parallel batch object exceeds the field limit.")
            if any(not isinstance(key, str) for key in item):
                raise ValueError("Parallel batch object keys must be strings.")
            string_bytes += sum(len(key.encode("utf-8")) for key in item)
            if string_bytes > MAX_TOTAL_STRING_BYTES:
                raise ValueError("Parallel batch string dimensions exceed the admitted limits.")
            stack.extend((child, depth + 1) for child in item.values())
            continue
        raise ValueError(f"Parallel batch contains unsupported JSON type: {type(item).__name__}.")


def _admit(request: Any, *, cpu_budget: int | None = None) -> tuple[list[dict[str, Any]], int, int, float, int, str]:
    _validate_json(request)
    if not isinstance(request, dict) or set(request) != {
        "contract", "jobs", "concurrency", "threads_per_job", "timeout_s",
    }:
        raise ValueError("Parallel batch requires exactly contract, jobs, concurrency, threads_per_job, and timeout_s.")
    if request["contract"] != BATCH_CONTRACT:
        raise ValueError("Unsupported parallel batch contract.")
    jobs = request["jobs"]
    if not isinstance(jobs, list) or not 1 <= len(jobs) <= MAX_JOBS:
        raise ValueError(f"Parallel batch jobs must contain 1..{MAX_JOBS} entries.")
    concurrency = request["concurrency"]
    threads = request["threads_per_job"]
    timeout_s = request["timeout_s"]
    if type(concurrency) is not int or not 1 <= concurrency <= min(MAX_CONCURRENCY, len(jobs)):
        raise ValueError("Parallel batch concurrency is outside the admitted range.")
    if type(threads) is not int or not 1 <= threads <= MAX_THREADS_PER_JOB:
        raise ValueError("Parallel batch threads_per_job is outside the admitted range.")
    if type(timeout_s) not in (int, float) or not math.isfinite(float(timeout_s)) or not 0 < float(timeout_s) <= MAX_TIMEOUT_S:
        raise ValueError(f"Parallel batch timeout_s must be finite and in (0, {MAX_TIMEOUT_S:g}].")
    budget = cpu_thread_budget() if cpu_budget is None else cpu_budget
    if concurrency * threads > budget:
        raise ValueError(
            f"Parallel batch requests {concurrency * threads} CPU threads; the worker budget is {budget}."
        )
    seen: set[str] = set()
    for job in jobs:
        if not isinstance(job, dict) or set(job) != {"id", "method", "params"}:
            raise ValueError("Each parallel job requires exactly id, method, and params.")
        job_id = job["id"]
        if not isinstance(job_id, str) or _ID_PATTERN.fullmatch(job_id) is None:
            raise ValueError("Parallel job ids must be bounded portable identifiers.")
        if job_id in seen:
            raise ValueError(f"Duplicate parallel job id: {job_id}")
        seen.add(job_id)
        if job["method"] not in ALLOWED_METHODS:
            raise ValueError(f"Parallel method is not allowed: {job['method']}")
        if not isinstance(job["params"], dict):
            raise ValueError("Parallel job params must be an object.")
        field = "scenario" if job["method"] == "estimate_thermal" else "request"
        if set(job["params"]) != {field} or not isinstance(job["params"][field], dict):
            raise ValueError(f"Parallel job {job_id} requires exactly one inline {field} object.")
        if len(_canonical_bytes(job)) > MAX_JOB_INPUT_BYTES:
            raise ValueError(f"Parallel job {job_id} exceeds the 1 MiB inline job limit.")
    encoded = _canonical_bytes(request)
    if len(encoded) > MAX_INPUT_BYTES:
        raise ValueError("Parallel batch request exceeds the 4 MiB inline JSON limit.")
    return jobs, concurrency, threads, float(timeout_s), budget, hashlib.sha256(encoded).hexdigest()


def validate_batch(request: Any, *, cpu_budget: int | None = None) -> dict[str, Any]:
    """Validate every job and return an independent canonical JSON copy.

    Callers may use this as a complete preflight before scheduling any local or
    remote work.  No executable or host configuration is accepted here.
    """
    _admit(request, cpu_budget=cpu_budget)
    return json.loads(_canonical_bytes(request).decode("utf-8"))


def pool_catalog() -> dict[str, Any]:
    budget = cpu_thread_budget()
    return {
        "contract": CATALOG_CONTRACT,
        "batch_contract": BATCH_CONTRACT,
        "result_contract": RESULT_CONTRACT,
        "worker_version": __version__,
        "cpu_budget": budget,
        "methods": sorted(ALLOWED_METHODS),
        "allowed_methods": sorted(ALLOWED_METHODS),
        "limits": {
            "max_jobs": MAX_JOBS,
            "max_concurrency": min(MAX_CONCURRENCY, budget),
            "max_threads_per_job": min(MAX_THREADS_PER_JOB, budget),
            "max_total_cpu_threads": budget,
            "max_inline_request_bytes": MAX_INPUT_BYTES,
            "max_job_stdout_bytes": MAX_STDOUT_BYTES,
            "max_retained_job_output_bytes": MAX_JOB_OUTPUT_BYTES,
            "max_retained_batch_output_bytes": MAX_BATCH_OUTPUT_BYTES,
            "max_job_stderr_bytes": MAX_STDERR_BYTES,
            "max_timeout_s": MAX_TIMEOUT_S,
            "max_batch_timeout_s": MAX_BATCH_TIMEOUT_S,
            "max_job_input_bytes": MAX_JOB_INPUT_BYTES,
            "max_json_nodes": MAX_JSON_NODES,
            "max_array_items": MAX_LIST_ITEMS,
            "max_object_fields": MAX_OBJECT_KEYS,
            "max_nesting": MAX_NESTING,
            "max_string_bytes": MAX_STRING_BYTES,
            "max_total_string_bytes": MAX_TOTAL_STRING_BYTES,
            "memory_limit": "unsupported_by_portable_process_pool",
            "batch_admission": "one_active_batch_per_host_process",
        },
        "execution": {
            "isolation": "fresh_process_per_job",
            "transport": "single_bounded_inline_json_request_response",
            "network_required": False,
            "client_executable_selection": False,
            "trusted_worker_prefix_hook": "configure_worker_prefix(argv)",
            "timeout_scope": "per_job_from_process_start",
        },
        "acceleration": acceleration_catalog(),
    }


class _BoundedReader:
    def __init__(self, stream: Any, limit: int) -> None:
        self._stream = stream
        self._limit = limit
        self.data = bytearray()
        self.overflow = threading.Event()
        self.thread = threading.Thread(target=self._read, daemon=True)

    def _read(self) -> None:
        try:
            while True:
                chunk = self._stream.read(65536)
                if not chunk:
                    return
                remaining = self._limit - len(self.data)
                if len(chunk) > remaining:
                    self.data.extend(chunk[:max(0, remaining)])
                    self.overflow.set()
                    return
                self.data.extend(chunk)
        except (OSError, ValueError):
            return


class _InputWriter:
    """Write one bounded payload without blocking the supervision thread."""

    def __init__(self, stream: Any, payload: bytes) -> None:
        self._stream = stream
        self._payload = payload
        self.error: BaseException | None = None
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._write, daemon=True)

    def _write(self) -> None:
        try:
            self._stream.write(self._payload)
            self._stream.flush()
        except (BrokenPipeError, OSError, ValueError) as exc:
            self.error = exc
        finally:
            try:
                self._stream.close()
            except OSError as exc:
                if self.error is None:
                    self.error = exc
            self.done.set()


class _OutputBudget:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.retained = 0
        self._reservations: dict[str, int] = {}
        self._lock = threading.Lock()

    def reserve(self, job_id: str, size: int) -> bool:
        with self._lock:
            if size > MAX_JOB_OUTPUT_BYTES or self.retained + size > self.limit:
                return False
            self._reservations[job_id] = size
            self.retained += size
            return True

    def release(self, job_id: str) -> None:
        with self._lock:
            self.retained -= self._reservations.pop(job_id, 0)


def _structure_within_transport(value: Any) -> bool:
    """Check the node transport's aggregate node and nesting envelope."""
    stack: list[tuple[Any, int]] = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_NESTING:
            return False
        if isinstance(item, dict):
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
    return True


def _error_outcome(job: dict[str, Any], code: str, message: str, *,
                   worker_pid: int | None, started: float, threads: int,
                   detail: str = "") -> dict[str, Any]:
    error = {"code": code, "type": "ParallelJobError", "message": message}
    if detail:
        error["detail"] = detail[:4096]
    return {
        "id": job["id"], "method": job["method"], "ok": False,
        "status": "cancelled" if code == "PARALLEL_JOB_CANCELLED" else
                  "timed_out" if code in {"PARALLEL_JOB_TIMEOUT", "PARALLEL_BATCH_TIMEOUT"} else "failed",
        "error": error,
        "provenance": {
            "request_sha256": _digest(job), "worker_pid": worker_pid,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "threads": threads, "memory_limit_enforced": False,
        },
    }


def _child_environment(threads: int) -> dict[str, str]:
    environment = dict(os.environ)
    value = str(threads)
    for name in (
        "SPIKE_CPU_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
        "BLIS_NUM_THREADS",
    ):
        environment[name] = value
    return environment


def _run_job(job: dict[str, Any], timeout_s: float, threads: int,
             worker_command: Sequence[str],
             cancel_event: threading.Event,
             batch_timeout_event: threading.Event,
             output_budget: _OutputBudget,
             active_changed: Callable[[int], None]) -> dict[str, Any]:
    started = time.monotonic()
    if batch_timeout_event.is_set():
        return _error_outcome(job, "PARALLEL_BATCH_TIMEOUT", "Batch exceeded its 900 second node limit.",
                              worker_pid=None, started=started, threads=threads)
    if cancel_event.is_set():
        return _error_outcome(job, "PARALLEL_JOB_CANCELLED", "Batch cancellation was requested.",
                              worker_pid=None, started=started, threads=threads)
    payload = _canonical_bytes(job)
    process: subprocess.Popen[bytes] | None = None
    stdout_reader: _BoundedReader | None = None
    stderr_reader: _BoundedReader | None = None
    input_writer: _InputWriter | None = None
    counted = False
    try:
        process = subprocess.Popen(
            list(worker_command), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=_child_environment(threads), shell=False,
        )
        active_changed(1)
        counted = True
        assert process.stdin is not None and process.stdout is not None and process.stderr is not None
        stdout_reader = stdout = _BoundedReader(process.stdout, MAX_STDOUT_BYTES)
        stderr_reader = stderr = _BoundedReader(process.stderr, MAX_STDERR_BYTES)
        stdout.thread.start()
        stderr.thread.start()
        input_writer = _InputWriter(process.stdin, payload)
        input_writer.thread.start()
        stop_code = ""
        while process.poll() is None:
            if batch_timeout_event.is_set():
                stop_code = "PARALLEL_BATCH_TIMEOUT"
                break
            if cancel_event.is_set():
                stop_code = "PARALLEL_JOB_CANCELLED"
                break
            if stdout.overflow.is_set() or stderr.overflow.is_set():
                stop_code = "PARALLEL_JOB_OUTPUT_LIMIT"
                break
            if input_writer.done.is_set() and input_writer.error is not None:
                stop_code = "PARALLEL_JOB_TRANSPORT"
                break
            if time.monotonic() - started >= timeout_s:
                stop_code = "PARALLEL_JOB_TIMEOUT"
                break
            time.sleep(0.01)
        if stop_code:
            process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        stdout.thread.join(timeout=1)
        stderr.thread.join(timeout=1)
        input_writer.thread.join(timeout=1)
        if stop_code == "PARALLEL_JOB_CANCELLED":
            return _error_outcome(job, stop_code, "Batch cancellation was requested.",
                                  worker_pid=process.pid, started=started, threads=threads)
        if stop_code == "PARALLEL_JOB_TIMEOUT":
            return _error_outcome(job, stop_code, f"Job exceeded its {timeout_s:g} second timeout.",
                                  worker_pid=process.pid, started=started, threads=threads)
        if stop_code == "PARALLEL_BATCH_TIMEOUT":
            return _error_outcome(job, stop_code, "Batch exceeded its 900 second node limit.",
                                  worker_pid=process.pid, started=started, threads=threads)
        if stop_code == "PARALLEL_JOB_TRANSPORT" or input_writer.error is not None:
            return _error_outcome(
                job, "PARALLEL_JOB_TRANSPORT", "Child did not accept the complete request.",
                worker_pid=process.pid, started=started, threads=threads,
                detail=str(input_writer.error or "input transport stopped"),
            )
        if stop_code or stdout.overflow.is_set() or stderr.overflow.is_set():
            return _error_outcome(job, "PARALLEL_JOB_OUTPUT_LIMIT", "Child output exceeded a transport limit.",
                                  worker_pid=process.pid, started=started, threads=threads)
        stderr_text = bytes(stderr.data).decode("utf-8", errors="replace").strip()
        if process.returncode != 0:
            return _error_outcome(job, "PARALLEL_JOB_EXIT", f"Child exited with code {process.returncode}.",
                                  worker_pid=process.pid, started=started, threads=threads, detail=stderr_text)
        response_bytes = bytes(stdout.data)
        if len(response_bytes) > MAX_JOB_OUTPUT_BYTES:
            return _error_outcome(
                job, "PARALLEL_JOB_OUTPUT_LIMIT",
                "Child response exceeds the retained job output budget.",
                worker_pid=process.pid, started=started, threads=threads,
            )
        try:
            lines = [line for line in response_bytes.splitlines() if line.strip()]
            if len(lines) != 1:
                raise ValueError("Child must return exactly one nonempty JSON response line.")
            response = json.loads(
                lines[0].decode("utf-8", errors="strict"), parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(f"Non-finite response number: {value}")),
                object_pairs_hook=lambda pairs: _response_object(pairs),
            )
            if not isinstance(response, dict) or response.get("id") != job["id"]:
                raise ValueError("Child response id does not match the job id.")
            if not isinstance(response.get("ok"), bool):
                raise ValueError("Child response requires a boolean ok field.")
            meta = response.get("meta")
            if not isinstance(meta, dict) or meta.get("method") != job["method"]:
                raise ValueError("Child response method does not match the job method.")
            response_digest = _digest(response)
        except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError) as exc:
            return _error_outcome(job, "PARALLEL_JOB_PROTOCOL", "Child returned an invalid response.",
                                  worker_pid=process.pid, started=started, threads=threads,
                                  detail=f"{exc}; stderr={stderr_text}" if stderr_text else str(exc))
        provenance = {
            "request_sha256": _digest(job), "response_sha256": response_digest,
            "worker_pid": process.pid,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "threads": threads, "memory_limit_enforced": False,
        }
        if response["ok"]:
            outcome = {
                "id": job["id"], "method": job["method"], "ok": True,
                "status": "completed", "result": response.get("result"),
                "worker_meta": meta, "provenance": provenance,
            }
        else:
            error = response.get("error")
            if not isinstance(error, dict):
                error = {"code": "PARALLEL_CHILD_REJECTED", "type": "ParallelChildError",
                         "message": str(error)[:4096]}
            outcome = {
                "id": job["id"], "method": job["method"], "ok": False,
                "status": "failed", "error": error, "worker_meta": meta,
                "provenance": provenance,
            }
        if not _structure_within_transport(outcome):
            return _error_outcome(
                job, "PARALLEL_JOB_STRUCTURE_LIMIT",
                "Child response exceeds the node transport structural limit.",
                worker_pid=process.pid, started=started, threads=threads,
            )
        if not output_budget.reserve(job["id"], len(response_bytes)):
            return _error_outcome(
                job, "PARALLEL_JOB_BATCH_OUTPUT_LIMIT",
                "Child response exceeds the remaining batch output budget.",
                worker_pid=process.pid, started=started, threads=threads,
            )
        return outcome
    except (OSError, subprocess.SubprocessError) as exc:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        return _error_outcome(job, "PARALLEL_JOB_START", "Could not start or supervise the child process.",
                              worker_pid=process.pid if process else None, started=started,
                              threads=threads, detail=str(exc))
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            for reader in (stdout_reader, stderr_reader):
                if reader is not None:
                    reader.thread.join(timeout=1)
            if input_writer is not None:
                input_writer.thread.join(timeout=1)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass
            if input_writer is not None and input_writer.thread.is_alive():
                input_writer.thread.join(timeout=1)
        if counted:
            active_changed(-1)


def _response_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate response key: {key}")
        result[key] = value
    return result


def run_parallel_batch(request: Any, *, cancel_check: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Run admitted jobs in ordered, fresh, isolated child processes."""
    normalized = validate_batch(request)
    jobs, concurrency, threads, timeout_s, budget, request_digest = _admit(normalized)
    if not _BATCH_LOCK.acquire(blocking=False):
        raise RuntimeError("A parallel batch is already active in this host process.")
    batch_started = time.monotonic()
    worker_command = _command()
    cancel_event = threading.Event()
    batch_timeout_event = threading.Event()
    output_budget = _OutputBudget(MAX_BATCH_OUTPUT_BYTES)
    active = 0
    peak_active = 0
    active_lock = threading.Lock()

    def active_changed(delta: int) -> None:
        nonlocal active, peak_active
        with active_lock:
            active += delta
            peak_active = max(peak_active, active)

    def build_result(items: list[dict[str, Any]]) -> dict[str, Any]:
        cancelled = any(item["status"] == "cancelled" for item in items)
        failed = any(not item["ok"] for item in items)
        return {
            "contract": RESULT_CONTRACT,
            "status": "cancelled" if cancelled else "completed_with_errors" if failed else "completed",
            "outcomes": items,
            "provenance": {
                "request_sha256": request_digest,
                "executor": "spike.parallel_pool/fresh-process-v1",
                "job_order_preserved": True,
                "concurrency": concurrency,
                "peak_concurrency_observed": peak_active,
                "threads_per_job": threads,
                "cpu_thread_budget": budget,
                "memory_limit_enforced": False,
                "retained_child_output_bytes": output_budget.retained,
                "duration_ms": round((time.monotonic() - batch_started) * 1000, 3),
            },
        }

    try:
        # Small placeholders reserve the complete result envelope before any
        # child output is retained. Each completed outcome replaces its slot
        # only if the aggregate still fits the node transport structure.
        outcomes = [
            _error_outcome(
                job, "PARALLEL_JOB_INTERNAL", "Job has not completed.",
                worker_pid=None, started=batch_started, threads=threads,
            )
            for job in jobs
        ]
        with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="spike-parallel") as executor:
            pending: dict[Future[dict[str, Any]], int] = {
                executor.submit(
                    _run_job, job, timeout_s, threads, worker_command, cancel_event,
                    batch_timeout_event, output_budget, active_changed,
                ): index
                for index, job in enumerate(jobs)
            }
            while pending:
                if time.monotonic() - batch_started >= MAX_BATCH_TIMEOUT_S:
                    batch_timeout_event.set()
                if cancel_check is not None and not cancel_event.is_set():
                    try:
                        if bool(cancel_check()):
                            cancel_event.set()
                    except Exception:
                        cancel_event.set()
                done, _ = wait(tuple(pending), timeout=0.02, return_when=FIRST_COMPLETED)
                for future in done:
                    index = pending.pop(future)
                    try:
                        item = future.result()
                    except Exception as exc:
                        item = _error_outcome(
                            jobs[index], "PARALLEL_JOB_INTERNAL", "Pool supervision failed.",
                            worker_pid=None, started=batch_started, threads=threads, detail=str(exc),
                        )
                    candidate = list(outcomes)
                    candidate[index] = item
                    if _structure_within_transport(build_result(candidate)):
                        outcomes[index] = item
                    else:
                        output_budget.release(item["id"])
                        outcomes[index] = _error_outcome(
                            jobs[index], "PARALLEL_JOB_STRUCTURE_LIMIT",
                            "Aggregate result exceeds the node transport structural limit.",
                            worker_pid=item.get("provenance", {}).get("worker_pid"),
                            started=batch_started, threads=threads,
                        )
        result = build_result(outcomes)
        if not _structure_within_transport(result):
            raise RuntimeError("Parallel result envelope exceeds its invariant structural limit.")
        return result
    finally:
        _BATCH_LOCK.release()


__all__ = [
    "ALLOWED_METHODS", "BATCH_CONTRACT", "RESULT_CONTRACT",
    "configure_worker_prefix", "pool_catalog", "run_parallel_batch", "validate_batch",
]
