# SPDX-License-Identifier: Apache-2.0
"""Stage current release source and generated workers without local caches."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


REPOSITORY = Path(__file__).resolve().parents[1]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))


def source_files(root: Path) -> set[str]:
    snapshot = root / "RELEASE_SOURCE_MANIFEST.json"
    if snapshot.is_file():
        return {entry["path"] for entry in json.loads(snapshot.read_text(encoding="utf-8"))["files"]}
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root,
    )
    return set(output.decode("utf-8").split("\0")) - {""}


def _stage_location(root: Path, stage_root: Path | None) -> tuple[Path, bool]:
    build = (root / "build").resolve()
    if stage_root is None:
        stage = (build / "release-resources").resolve()
        if stage.parent != build:
            raise RuntimeError("Refusing to reset an unmanaged resource directory")
        return stage, True
    candidate = Path(stage_root)
    stage = (candidate if candidate.is_absolute() else root / candidate).resolve()
    try:
        relative = stage.relative_to(build)
    except ValueError as exc:
        raise RuntimeError("Custom resource stage must be strictly under the repository build directory") from exc
    if not relative.parts:
        raise RuntimeError("Custom resource stage must be strictly under the repository build directory")
    if stage.exists():
        raise RuntimeError("Custom resource stage must be fresh; refusing to remove or merge it")
    return stage, False


def _verify_worker_package(artifact: Path, manifest: Path, executable_name: str) -> tuple[Path | None, Path | None]:
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    files = raw.get("files") if isinstance(raw, dict) else None
    if not isinstance(files, list) or not any(
            isinstance(item, dict) and item.get("path") == executable_name for item in files):
        raise RuntimeError("Worker manifest does not bind the expected executable")
    from python.spike_core.wave1_packaged_acceptance import verify_packaged_worker_manifest
    checks, _ = verify_packaged_worker_manifest(manifest, artifact)
    failures = [str(check.get("id", "unknown")) for check in checks if check.get("status") != "passed"]
    if failures:
        raise RuntimeError("Worker override failed packaged-manifest verification: " + ", ".join(failures))
    report = report_relative = None
    qualification = raw.get("runtime_qualification")
    if isinstance(qualification, dict) and isinstance(qualification.get("report"), str):
        report_relative = Path(qualification["report"])
        if report_relative.is_absolute() or ".." in report_relative.parts:
            raise RuntimeError("Worker runtime qualification report path is unsafe")
        report = manifest.parent / report_relative
        if not report.is_file():
            raise RuntimeError("Worker runtime qualification report is missing")
    return report, report_relative


def _verified_worker(worker_root: Path | None) -> tuple[Path, Path, Path | None, Path | None] | None:
    if worker_root is None:
        return None
    supplied = Path(worker_root).resolve()
    executable_name = "spike-worker.exe" if os.name == "nt" else "spike-worker"
    if (supplied / executable_name).is_file():
        artifact, manifest = supplied, supplied.parent / "spike-worker.manifest.json"
    elif (supplied / "spike-worker" / executable_name).is_file():
        artifact, manifest = supplied / "spike-worker", supplied / "spike-worker.manifest.json"
    else:
        raise RuntimeError(f"Worker override is missing spike-worker/{executable_name}")
    if not manifest.is_file():
        raise RuntimeError("Worker override is missing sibling spike-worker.manifest.json")
    report, report_relative = _verify_worker_package(artifact, manifest, executable_name)
    return artifact, manifest, report, report_relative


def _copy_worker(source: Path, target: Path,
                 override: tuple[Path, Path, Path | None, Path | None] | None) -> None:
    if override is None:
        shutil.copytree(source, target, symlinks=True, dirs_exist_ok=True)
        return
    artifact, manifest, report, report_relative = override
    shutil.copytree(source, target, symlinks=True, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("spike-worker", "spike-worker.manifest.json",
                                                  "release-runtime-qualification.json"))
    shutil.copytree(artifact, target / "spike-worker", symlinks=True)
    shutil.copy2(manifest, target / "spike-worker.manifest.json")
    if report is not None:
        report_target = target / report_relative
        report_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(report, report_target)
    executable_name = "spike-worker.exe" if os.name == "nt" else "spike-worker"
    _verify_worker_package(target / "spike-worker", target / "spike-worker.manifest.json",
                           executable_name)


def prepare(root: Path, output: Path | None = None, *, stage_root: Path | None = None,
            worker_root: Path | None = None) -> Path:
    root = root.resolve()
    included = source_files(root)
    config_path = root / "app/src-tauri/tauri.conf.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    stage, reset_managed_stage = _stage_location(root, stage_root)
    worker_override = _verified_worker(worker_root)
    sources = [(str(src), (config_path.parent / src).resolve(), str(dst)) for src, dst in config["bundle"]["resources"].items()]
    if any(source == stage for _, source, _ in sources):
        raise RuntimeError("Use the original Tauri configuration when staging resources")
    if stage.exists():
        if not reset_managed_stage:
            raise RuntimeError("Custom resource stage must be fresh; refusing to remove or merge it")
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for _, source, dst in sources:
        source.relative_to(root)
        if source == root / "app/src-tauri/resources/worker":
            _copy_worker(source, stage / dst, worker_override)
            continue
        files = source.rglob("*") if source.is_dir() else [source]
        for file in files:
            if not file.is_file() or "__pycache__" in file.parts or file.suffix in {".pyc", ".pyo"}:
                continue
            if file.relative_to(root).as_posix() not in included:
                continue
            target = stage / dst / file.relative_to(source) if source.is_dir() else stage / dst
            target.resolve().relative_to(stage)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target)
    staged_resource = Path(os.path.relpath(stage, config_path.parent)).as_posix().rstrip("/") + "/"
    config["bundle"]["resources"] = {staged_resource: "./"}
    if sys.platform == "win32":
        name = "spike-em" if config["identifier"] == "org.spike.em" else "spike"
        (stage / f"{name}.cmd").write_text(
            '@echo off\nset "SPIKE_HOME=%~dp0"\nset "SPIKE_WORKSPACE=%~dp0"\n'
            '"%~dp0bundled\\spike-worker\\spike-worker.exe" --cli %*\nexit /b %errorlevel%\n', encoding="utf-8",
        )
    if sys.platform == "darwin":
        config["bundle"]["macOS"] = {"minimumSystemVersion": "15.0", "signingIdentity": "-"}
    destination = output or config_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-output", type=Path, help="Preserve source config and emit a build config here")
    parser.add_argument("--stage-root", type=Path,
                        help="Fresh resource stage strictly below this repository's build directory")
    parser.add_argument("--worker-root", type=Path,
                        help="Verified spike-worker artifact directory (or its package parent) to stage")
    args = parser.parse_args()
    print(prepare(Path(__file__).resolve().parents[1], args.config_output,
                  stage_root=args.stage_root, worker_root=args.worker_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
