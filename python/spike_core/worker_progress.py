# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded stderr progress frames for the desktop worker transport."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from threading import Lock
from typing import Any

PROGRESS_PREFIX = "SPIKE_PROGRESS:"
MAX_PROGRESS_LINE_BYTES = 512 * 1024
_WRITE_LOCK = Lock()


def emit_worker_progress(
    operation_id: str,
    method: str,
    frame: Mapping[str, Any],
) -> None:
    """Write one correlated progress frame without using protocol stdout."""
    if not isinstance(operation_id, str) or not operation_id:
        raise ValueError("worker progress requires a non-empty operation_id")
    if not isinstance(method, str) or not method:
        raise ValueError("worker progress requires a non-empty method")
    if not isinstance(frame, Mapping):
        raise TypeError("worker progress frame must be an object")
    payload = json.dumps(
        {
            "operation_id": operation_id,
            "method": method,
            "frame": dict(frame),
        },
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    )
    line = f"{PROGRESS_PREFIX}{payload}\n"
    if len(line.encode("utf-8")) > MAX_PROGRESS_LINE_BYTES:
        raise ValueError("worker progress frame exceeds the 512 KiB transport limit")
    with _WRITE_LOCK:
        sys.stderr.write(line)
        sys.stderr.flush()
