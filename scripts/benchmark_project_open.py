# SPDX-License-Identifier: Apache-2.0
"""Bounded source-worker project-open timing, with exact response fingerprints."""
from __future__ import annotations

import argparse
import cProfile
import gc
import hashlib
import importlib.util
import io
import json
import platform
import pstats
import statistics
import sys
import time
from pathlib import Path
from contextlib import nullcontext, ExitStack
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--reference-dir", type=Path, help="retained predecessor validator/comparator modules for alternating comparison")
    args = parser.parse_args()
    if not 1 <= args.repeats <= 20:
        parser.error("repeats must be between 1 and 20")
    from python.spike_core.service_project_handlers import handle_project_request
    from python.spike_core import __version__
    from python.spike_core import spider_v2; from python.spike_core import assembly_designs
    project = args.project.resolve()
    params = dict(path=str(project), defer_artifacts=True,
                  compact_normalized_source=True, compact_canonical_design=True)

    def run():
        value = handle_project_request("read_project_package", params,
                                       request_id="benchmark-open", application_version=__version__)
        if not value or not value.get("ok"):
            raise RuntimeError(value)
        return value

    references = []
    reference_service_project = None
    if args.reference_dir:
        for name in ("custom_pad_geometry", "assembly_designs"):
            path = args.reference_dir / f"{name}.py"
            spec = importlib.util.spec_from_file_location(f"python.spike_core._reference_{name}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            references.append(module)
        service_path = args.reference_dir / "service_project.py"
        if service_path.is_file():
            spec = importlib.util.spec_from_file_location(
                "python.spike_core._reference_service_project", service_path,
            )
            reference_service_project = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(reference_service_project)

    def reference_context():
        context = ExitStack()
        context.enter_context(patch.object(spider_v2, "validate_custom_pad_geometries", references[0].validate_custom_pad_geometries))
        context.enter_context(patch.object(assembly_designs, "_same_json_value", references[1]._same_json_value))
        if reference_service_project is not None:
            context.enter_context(patch(
                "python.spike_core.service_project_handlers.frontend_project_payload",
                reference_service_project.frontend_project_payload,
            ))
        return context

    samples, hashes = [], []
    baseline_samples = []
    sizes = []
    for index in range(args.repeats):
        order = [False, True] if references else [False]
        if index % 2:
            order.reverse()
        for baseline in order:
            gc.collect()
            with reference_context() if baseline else nullcontext():
                start = time.perf_counter_ns()
                response = run()
                elapsed = (time.perf_counter_ns() - start) / 1e6
            (baseline_samples if baseline else samples).append(elapsed)
            encoded = json.dumps(response, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
            hashes.append(hashlib.sha256(encoded).hexdigest())
            sizes.append(len(encoded))
            del response, encoded
    if len(set(hashes)) != 1:
        raise AssertionError("project response changed between repeated reads")
    source_paths = ("service_project_handlers.py", "project_package.py", "service_project.py",
                    "service_project_persistence.py", "custom_pad_geometry.py", "assembly_designs.py")
    report = dict(project=str(project), project_sha256=file_sha256(project),
                  python=sys.version, platform=platform.platform(), params=params,
                  samples_ms=samples, median_ms=statistics.median(samples), response_sha256=hashes[0],
                  response_bytes=sizes[0], source_sha256={name: hashlib.sha256(
                      (ROOT / "python/spike_core" / name).read_bytes()).hexdigest() for name in source_paths},
                  limits="In-process deferred worker open only; numerical imports, native IPC, result/visual hydration and viewport excluded.")
    if references:
        report["reference_samples_ms"] = baseline_samples
        report["reference_median_ms"] = statistics.median(baseline_samples)
        report["reference_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in args.reference_dir.glob("*.py")}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.profile:
        gc.collect()
        profile = cProfile.Profile()
        profile.runcall(run)
        output = io.StringIO()
        pstats.Stats(profile, stream=output).sort_stats("cumulative").print_stats(35)
        args.output.with_suffix(".profile.txt").write_text(output.getvalue(), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("median_ms", "samples_ms", "response_bytes", "response_sha256")}))


if __name__ == "__main__":
    main()
