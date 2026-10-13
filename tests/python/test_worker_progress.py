# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import io
import json
import unittest
from unittest.mock import patch

from python.spike_core.worker_progress import (
    MAX_PROGRESS_LINE_BYTES,
    PROGRESS_PREFIX,
    emit_worker_progress,
)


class _FlushTrackingText(io.StringIO):
    def __init__(self):
        super().__init__()
        self.flush_count = 0

    def flush(self):
        self.flush_count += 1
        super().flush()


class WorkerProgressTests(unittest.TestCase):
    def test_emits_one_compact_correlated_stderr_line_and_flushes(self):
        stream = _FlushTrackingText()
        with patch("sys.stderr", stream):
            emit_worker_progress("thermal-17", "run_assembly_field_transient", {"step": 3, "time_s": 0.25})
        line = stream.getvalue()
        self.assertTrue(line.startswith(PROGRESS_PREFIX))
        self.assertEqual(line.count("\n"), 1)
        self.assertEqual(stream.flush_count, 1)
        self.assertEqual(
            json.loads(line[len(PROGRESS_PREFIX):]),
            {
                "operation_id": "thermal-17",
                "method": "run_assembly_field_transient",
                "frame": {"step": 3, "time_s": 0.25},
            },
        )

    def test_rejects_unbounded_or_non_object_frames_before_writing(self):
        stream = _FlushTrackingText()
        with patch("sys.stderr", stream):
            with self.assertRaises(TypeError):
                emit_worker_progress("thermal-17", "run_assembly_field_transient", [1, 2])
            with self.assertRaises(ValueError):
                emit_worker_progress(
                    "thermal-17",
                    "run_assembly_field_transient",
                    {"payload": "x" * MAX_PROGRESS_LINE_BYTES},
                )
        self.assertEqual(stream.getvalue(), "")
        self.assertEqual(stream.flush_count, 0)


if __name__ == "__main__":
    unittest.main()
