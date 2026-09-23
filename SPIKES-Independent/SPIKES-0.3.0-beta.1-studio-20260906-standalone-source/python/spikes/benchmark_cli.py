"""Standalone JSON CLI for the bounded SPIKES benchmark harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from .benchmark import ExternalJsonCommandAdapter, NativeDcAdapter, run_benchmark_suite


EXIT_OK = 0
EXIT_INPUT = 2
EXIT_FAILED = 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spikes-benchmark",
        description="Run accuracy-gated SPIKES analytical DC micro-benchmarks.",
    )
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--timeout", type=float, default=30.0, help="External wrapper timeout in seconds.")
    parser.add_argument("--external-id", help="Label for an explicitly supplied external wrapper command.")
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument(
        "--external-command",
        nargs=argparse.REMAINDER,
        metavar="ARGV",
        help="Execute this argv directly; place this option last. No shell is used.",
    )
    return parser


def _emit(value: Any, output: Path | None) -> None:
    rendered = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if output is None:
        sys.stdout.write(rendered)
    else:
        output.write_text(rendered, encoding="utf-8")


def main(argv: Iterable[str] | None = None) -> int:
    arguments = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        command = tuple(arguments.external_command or ())
        if bool(command) != bool(arguments.external_id):
            raise ValueError("--external-id and --external-command must be supplied together.")
        adapter = (
            ExternalJsonCommandAdapter(arguments.external_id, command, timeout_s=arguments.timeout)
            if command
            else NativeDcAdapter()
        )
        report = run_benchmark_suite(
            adapter,
            warmups=arguments.warmups,
            repetitions=arguments.repetitions,
        )
        _emit(report, arguments.output)
        return EXIT_OK if report["status"] == "passed" else EXIT_FAILED
    except (OSError, UnicodeError, ValueError) as exc:
        payload = {
            "contract": "spikes/benchmark-cli-error/v1",
            "status": "error",
            "issues": [{
                "code": "SPIKES_BENCHMARK_INPUT_INVALID",
                "severity": "error",
                "message": str(exc),
            }],
        }
        try:
            _emit(payload, arguments.output)
        except OSError:
            _emit(payload, None)
        return EXIT_INPUT


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["EXIT_FAILED", "EXIT_INPUT", "EXIT_OK", "main"]
