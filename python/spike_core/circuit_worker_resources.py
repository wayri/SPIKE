# SPDX-License-Identifier: Apache-2.0
"""Bounded observation and provenance for experimental Darwin RSS supervision."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time

from .owned_spice_process import (
    MAX_CONTROL_BYTES, PROCESS_RESULT_CONTRACT, _atomic_publish,
    _reject_constant, _reject_reparse_components, _strict_object,
)

RSS_SAMPLE_INTERVAL_SECONDS = 0.05
RSS_OBSERVER_TIMEOUT_SECONDS = 0.5
RSS_OBSERVER_MAX_BYTES = 256 * 1024
DARWIN_RSS_ENFORCEMENT = "darwin_process_group_sampled_rss_experimental"


class ResourceObservationError(RuntimeError):
    """A required sampled memory observation failed; execution must stop."""


def _parse_group_rss(output: bytes, group: int) -> int:
    if not output or len(output) > RSS_OBSERVER_MAX_BYTES:
        raise ResourceObservationError("RSS observer returned empty or excessive output")
    seen = set()
    total_kib = 0
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 3 or any(len(field) > 20 or not field.isdigit() for field in fields):
            raise ResourceObservationError("RSS observer returned a malformed row")
        pid, pgid, rss_kib = map(int, fields)
        if pid <= 0 or pgid != group or pid in seen:
            raise ResourceObservationError("RSS observer returned an invalid process identity")
        seen.add(pid)
        total_kib += rss_kib
    if not seen:
        raise ResourceObservationError("RSS observer returned no process-group members")
    return total_kib * 1024


def _sample_group_rss_bytes(group: int, timeout_seconds: float) -> int:
    """Read a bounded /bin/ps snapshot; the caller retains its unreaped leader."""
    import select

    deadline = time.monotonic() + min(timeout_seconds, RSS_OBSERVER_TIMEOUT_SECONDS)
    observer = None
    try:
        observer = subprocess.Popen(
            ["/bin/ps", "-x", "-g", str(group), "-o", "pid=,pgid=,rss="],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            shell=False, close_fds=True, env={"LC_ALL": "C", "COMMAND_MODE": "unix2003"},
        )
        output = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ResourceObservationError("RSS observer exceeded its time budget")
            ready, _, _ = select.select([observer.stdout], [], [], remaining)
            if not ready:
                raise ResourceObservationError("RSS observer exceeded its time budget")
            chunk = os.read(observer.stdout.fileno(), min(65536, RSS_OBSERVER_MAX_BYTES + 1 - len(output)))
            if not chunk:
                if observer.wait(timeout=max(0.001, deadline - time.monotonic())) != 0:
                    raise ResourceObservationError("RSS observer returned a nonzero exit status")
                return _parse_group_rss(bytes(output), group)
            output.extend(chunk)
            if len(output) > RSS_OBSERVER_MAX_BYTES:
                raise ResourceObservationError("RSS observer exceeded its output budget")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise ResourceObservationError("RSS observer could not complete a valid observation") from error
    finally:
        if observer is not None:
            try:
                if observer.poll() is None:
                    observer.kill()
                observer.wait(timeout=RSS_OBSERVER_TIMEOUT_SECONDS)
            except (OSError, subprocess.SubprocessError) as error:
                raise ResourceObservationError("RSS observer cleanup failed") from error
            finally:
                observer.stdout.close()


def _rss_provenance(timeout_seconds: float, memory_limit_mib: int, *, termination_requested: bool = True) -> dict:
    return {
        "supervisor": "python.spike_core.circuit_worker_supervisor",
        "resource_policy": "darwin_sampled_rss",
        "memory_enforcement": DARWIN_RSS_ENFORCEMENT,
        "hard_memory_cap": False,
        "memory_metric": "sum_process_group_resident_set_bytes",
        "shared_pages_counted_per_process": True,
        "escaped_process_groups_covered": False,
        "normal_leader_exit_descendants_covered": False,
        "overshoot_between_observations_possible": True,
        "sample_interval_seconds": RSS_SAMPLE_INTERVAL_SECONDS,
        "observer_timeout_seconds": RSS_OBSERVER_TIMEOUT_SECONDS,
        "requested_timeout_seconds": timeout_seconds,
        "requested_memory_limit_mib": memory_limit_mib,
        "complete_process_tree_termination_requested": termination_requested,
    }


def _attach_rss_provenance(root: Path, relative: Path, timeout_seconds: float, memory_limit_mib: int) -> None:
    """Augment a bounded worker envelope atomically, retaining its circuit data."""
    _reject_reparse_components(root, relative)
    path = root / relative
    if not path.is_file():
        raise ValueError("sampled supervision requires an existing regular worker result")
    with path.open("rb") as stream:
        raw = stream.read(MAX_CONTROL_BYTES + 1)
    if len(raw) > MAX_CONTROL_BYTES:
        raise ValueError("worker result exceeds the control limit")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object,
                       parse_constant=_reject_constant)
    if not isinstance(value, dict) or value.get("contract") != PROCESS_RESULT_CONTRACT:
        raise ValueError("worker result has an unexpected contract")
    provenance = value.get("provenance", {})
    if not isinstance(provenance, dict):
        raise ValueError("worker result provenance must be an object")
    value["provenance"] = {**provenance, **_rss_provenance(
        timeout_seconds, memory_limit_mib, termination_requested=False)}
    _atomic_publish(path, value)
