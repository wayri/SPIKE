"""Build and verify the offline SPIKE worker artifact.

This script never installs or downloads build dependencies. Release builders must
prepare an isolated environment containing the pinned PyInstaller version first.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.runtime_qualification import (
    canonical_digest,
    collect_runtime_snapshot,
    qualify_runtime_snapshots,
)
from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.geometry_arrow import GEOMETRY_ARROW_CONTRACT_V4, canonical_geometry_rows
from python.spike_core.project_package import read_geometry_arrow_artifact, read_spike_package


EXPECTED_PYINSTALLER_VERSION = "6.21.0"
EXPECTED_WINDOWS_BUILD_PACKAGES = {
    "pyinstaller": "6.21.0",
    "altgraph": "0.17.5",
    "packaging": "26.0",
    "pefile": "2024.8.26",
    "pyinstaller-hooks-contrib": "2026.6",
    "pyarrow": "25.0.1",
    "pywin32-ctypes": "0.2.3",
    "setuptools": "84.0.0",
}
RESOURCE_ROOT = ROOT / "app" / "src-tauri" / "resources" / "worker"
BUILD_ROOT = ROOT / "build" / "packaged-worker"
RUNTIME_QUALIFICATION_PATH = ROOT / "build" / "release-runtime-qualification.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_runtime_qualification(qualification: dict[str, Any]) -> Path:
    """Keep the bundled and repository release-gate reports identical."""

    payload = json.dumps(qualification, indent=2) + "\n"
    qualification_path = RESOURCE_ROOT / "release-runtime-qualification.json"
    qualification_path.parent.mkdir(parents=True, exist_ok=True)
    qualification_path.write_text(payload, encoding="utf-8")
    RUNTIME_QUALIFICATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_QUALIFICATION_PATH.write_text(payload, encoding="utf-8")
    return qualification_path


def _remove_managed_tree(path: Path, parent: Path) -> None:
    resolved = path.resolve()
    if resolved.parent != parent.resolve():
        raise RuntimeError(f"Refusing to remove unmanaged build path: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)


def _native_extension() -> Path:
    suffix = sysconfig.get_config_var("EXT_SUFFIX")
    if not suffix:
        raise RuntimeError("The active Python runtime does not expose EXT_SUFFIX")
    extension = ROOT / "python" / f"spike_peec_native{suffix}"
    if not extension.is_file():
        raise RuntimeError(
            "The ABI-matched native PEEC extension is missing: "
            f"{extension}. Build the native binding with this Python runtime first."
        )
    return extension


def _spikes_library() -> Path:
    names = {
        "win32": "spikes_c_api.dll",
        "darwin": "libspikes_c_api.dylib",
    }
    library = ROOT / "build-spikes-hybrid" / names.get(sys.platform, "libspikes_c_api.so")
    if not library.is_file():
        raise RuntimeError(
            "The owned SPIKES C ABI library is missing: "
            f"{library}. Build the native circuit engine before packaging."
        )
    return library


def _require_pyinstaller() -> str:
    try:
        version = importlib.metadata.version("pyinstaller")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError(
            f"PyInstaller {EXPECTED_PYINSTALLER_VERSION} is required in the active "
            "release environment. This script does not download dependencies."
        ) from exc
    if version != EXPECTED_PYINSTALLER_VERSION:
        raise RuntimeError(
            f"Expected PyInstaller {EXPECTED_PYINSTALLER_VERSION}, found {version}."
        )
    if os.name == "nt":
        mismatches = []
        for package, expected in EXPECTED_WINDOWS_BUILD_PACKAGES.items():
            try:
                installed = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                installed = "missing"
            if installed != expected:
                mismatches.append(f"{package}={installed} (expected {expected})")
        if mismatches:
            raise RuntimeError(
                "The Windows worker build environment does not match "
                "requirements-build-windows-x64.txt: " + "; ".join(mismatches)
            )
    return version


def _request(
    executable: Path, method: str, params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = json.dumps({"id": f"package-{method}", "method": method, "params": params or {}})
    environment = os.environ.copy()
    environment.update(
        {
            "SPIKE_HOME": str(ROOT),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
        }
    )
    process = subprocess.run(
        [str(executable)],
        input=request + "\n",
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
        env=environment,
    )
    if process.returncode != 0:
        raise RuntimeError(
            f"Packaged worker {method} check failed with exit code "
            f"{process.returncode}: {process.stderr.strip()}"
        )
    lines = [line for line in process.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError(
            f"Packaged worker emitted {len(lines)} protocol lines during {method}; expected one."
        )
    response = json.loads(lines[0])
    if response.get("ok") is not True:
        raise RuntimeError(f"Packaged worker rejected {method}: {response}")
    return response


def _verify_geometry_arrow_package(executable: Path) -> dict[str, Any]:
    """Prove that the frozen worker can generate and persist canonical Arrow."""
    design = DesignIRV2.from_v1(DesignIR(
        design_id="packaged-arrow-probe",
        name="Packaged Arrow probe",
        source_format="ipc-2581",
        layers=[
            {"id": "L1", "name": "TOP", "type": "copper"},
            {"id": "L2", "name": "BOTTOM", "type": "copper"},
        ],
        nets=[{"id": "N1", "name": "VCC"}],
        tracks=[
            {"id": "T1", "net_id": "N1", "layer": "TOP",
             "start": [0, 0], "end": [5, 0], "width": 0.25},
            {"id": "T2", "net_id": "N1", "layer": "TOP",
             "start": [5, 0], "end": [5, 5], "width": 0.25},
        ],
        zones=[{
            "id": "Z1", "net_id": "N1", "layer": "TOP",
            "boundary_rings": [{
                "role": "outer", "start_mm": [0, 0], "segments": [
                    {"kind": "line", "end_mm": [1, 0]},
                    {"kind": "line", "end_mm": [1, 1]},
                    {"kind": "line", "end_mm": [0, 1]},
                    {"kind": "line", "end_mm": [0, 0]},
                ],
            }],
            "fill_style_id": "SOLID_FILL", "fill_property": "FILL",
        }],
        vias=[{
            "id": "V1", "net_id": "N1", "at": [5, 0], "diameter": 0.8,
            "drill": 0.4, "layers": ["TOP", "BOTTOM"],
            "land_profiles": [
                {"layer_id": "TOP", "use": "regular", "shape": "circle",
                 "size_mm": [0.8, 0.8], "offset_mm": [0, 0],
                 "source_primitive_id": "VIA-TOP"},
                {"layer_id": "BOTTOM", "use": "regular", "shape": "circle",
                 "size_mm": [0.6, 0.6], "offset_mm": [0, 0],
                 "source_primitive_id": "VIA-BOTTOM"},
            ],
        }],
        metadata={
            "source_sha256": "a" * 64,
            "geometry_solver_ready": False,
            "ipc2581_retained_nonregular_padstack_geometry": {
                "contract": "spike/retained-padstack-geometry/v1",
                "user_primitives": [{
                    "id": "USER-SPECIAL-1", "kind": "user_special",
                    "source_index": 5, "source_units": "mm",
                    "contours": [{"boundary_rings": [{
                        "role": "outer", "fill_style_id": "SOLID_FILL",
                        "start_mm": [0, 0], "segments": [
                            {"kind": "line", "end_mm": [2, 0]},
                            {"kind": "line", "end_mm": [2, 2]},
                            {"kind": "line", "end_mm": [0, 2]},
                            {"kind": "line", "end_mm": [0, 0]},
                        ],
                    }]}],
                }],
                "occurrences": [{
                    "source_index": 17, "source_id": "PADSTACK-17",
                    "kind": "retained_padstack_nonregular_occurrence",
                    "status": "retained_unresolved",
                    "reason": "negative_plane_user_primitive_semantics_pending",
                    "padstack_ref": "PTH-1", "layer_id": "TOP",
                    "layer_polarity": "negative", "raw_net_ref": "VCC",
                    "resolved_net_id": "VCC", "occurrence_pad_usage": "via",
                    "matched_profile_use": "thermal", "at_mm": [3, 4],
                    "xform": {"rotation_deg": 90, "mirror": False},
                    "primitive_ref": "USER-SPECIAL-1",
                }],
            },
        },
    ), source_digest="a" * 64)
    snapshot = {
        "project": {"id": "packaged-arrow-probe", "name": "Packaged Arrow probe"},
        "design_ir": design.to_dict(),
    }
    with tempfile.TemporaryDirectory(prefix="spike-packaged-arrow-") as directory:
        package_path = Path(directory) / "packaged-arrow-probe.spike"
        response = _request(
            executable, "write_project_package",
            {"path": str(package_path), "snapshot": snapshot},
        )
        manifest = response.get("result", {}).get("manifest", {})
        manifest_digest = str(manifest.get("manifest_payload_sha256", ""))
        opened = read_spike_package(package_path)
        tables = opened.payload.get("geometry", {}).get("tables", [])
        if not isinstance(tables, list) or len(tables) != 1:
            raise RuntimeError("Packaged worker did not persist exactly one geometry table.")
        table = tables[0]
        decoded = read_geometry_arrow_artifact(
            package_path, str(table.get("path", "")),
            expected_manifest_payload_sha256=manifest_digest,
        )
        rows = decoded.get("rows", [])
        retained = design.retained_nonregular_padstack_geometry
        retained_count = len(retained.occurrences) if retained is not None else 0
        if table.get("schema") != GEOMETRY_ARROW_CONTRACT_V4 or len(rows) != 4:
            raise RuntimeError("Packaged worker Arrow probe did not persist the canonical Arrow contract.")
        if retained_count != 1:
            raise RuntimeError("Packaged worker Arrow probe lost its retained unresolved occurrence.")
        if rows != canonical_geometry_rows(design):
            raise RuntimeError("Packaged worker Arrow probe did not decode canonical DesignIR rows.")
        return {
            "contract": "spike/packaged-arrow-probe/v1",
            "status": "passed",
            "table_contract": table.get("schema"),
            "rows": len(rows),
            "retained_unresolved_occurrences": retained_count,
            "artifact_sha256": table.get("sha256"),
            "design_id": opened.payload.get("design_ir", {}).get("design_id"),
        }


def _verify_spikes_engine(executable: Path) -> dict[str, Any]:
    environment = os.environ.copy()
    environment.update({
        "SPIKE_HOME": str(ROOT),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
    })
    process = subprocess.Popen(
        [str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, env=environment,
    )
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("Unable to open the packaged worker protocol streams.")

    def request(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        process.stdin.write(json.dumps({
            "id": f"interactive-{method}", "method": method, "params": params or {},
        }) + "\n")
        process.stdin.flush()
        line = process.stdout.readline()
        if not line:
            stderr = process.stderr.read().strip() if process.stderr is not None else ""
            raise RuntimeError(f"Packaged worker stopped during {method}: {stderr}")
        response = json.loads(line)
        if response.get("ok") is not True:
            raise RuntimeError(f"Packaged worker rejected {method}: {response}")
        return response["result"]

    status = request("spikes_engine_status")
    if status.get("status") != "ready" or not status.get("features", {}).get("persistent_sessions"):
        raise RuntimeError(f"Packaged owned SPIKES engine is not session-ready: {status}")
    netlist = """* Packaged interactive RC probe
Vdrive in 0 0
R1 in out 1k
C1 out 0 1u
.tran 100u 2m
.end
"""
    created = request(
        "spikes_session_create",
        {"netlist": netlist, "probes": ["V(out)"], "integration_method": "backward_euler"},
    )
    session_id = created["session_id"]
    try:
        stepped = request(
            "spikes_session_step",
            {"session_id": session_id, "source_values": {"Vdrive": 1.0}, "steps": 10},
        )
        observed = float(stepped["samples"][-1]["values"]["V(out)"])
        expected = 1.0 - (1.0 / 1.1) ** 10
        error = abs(observed - expected)
        if stepped.get("status") != "converged" or error > 2.0e-12:
            raise RuntimeError(
                "Packaged interactive stepping failed its analytical RC check: "
                f"observed={observed}, expected={expected}, error={error}"
            )
        checkpoint = request(
            "spikes_session_checkpoint", {"session_id": session_id}
        )
        request(
            "spikes_session_step",
            {"session_id": session_id, "source_values": {"Vdrive": -1.0}, "steps": 3},
        )
        restored = request(
            "spikes_session_restore",
            {"session_id": session_id, "checkpoint_id": checkpoint["checkpoint_id"]},
        )
        restored_value = float(restored["sample"]["values"]["V(out)"])
        if restored_value != observed:
            raise RuntimeError("Packaged interactive checkpoint replay was not bit-exact.")
        return {
            "contract": "spikes/packaged-interactive-probe/v1",
            "status": "passed",
            "steps": 10,
            "observed_voltage_v": observed,
            "expected_voltage_v": expected,
            "absolute_error_v": error,
            "checkpoint_replay_bit_exact": restored_value == observed,
            "execution_class": "soft_realtime",
            "hard_realtime_qualified": False,
            "hil_qualified": False,
        }
    finally:
        try:
            request("spikes_session_close", {"session_id": session_id})
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)


def _verify(executable: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    runtime_environment = {"SPIKE_HOME": str(ROOT)}
    source = collect_runtime_snapshot(
        [sys.executable, "-m", "python.spike_core.service"],
        cwd=ROOT,
        environment_overrides=runtime_environment,
    )
    packaged = collect_runtime_snapshot(
        [str(executable)], cwd=ROOT, environment_overrides=runtime_environment
    )
    if packaged.get("health", {}).get("status") != "ready":
        raise RuntimeError(f"Packaged worker health is not ready: {packaged.get('health')}")
    plugins = packaged.get("solver_plugins", [])
    peec = next((item for item in plugins if item.get("id") == "spike.peec_2_5d"), None)
    runnable_states = {"available", "experimental", "reference_validated", "validated"}
    if not peec or peec.get("state") not in runnable_states:
        raise RuntimeError(
            "The packaged worker did not load the ABI-matched native PEEC extension."
        )
    benchmark_result = packaged.get("benchmarks", {})
    summary = benchmark_result.get("summary", {})
    if benchmark_result.get("status") != "passed" or summary.get("failed") or summary.get("skipped"):
        raise RuntimeError(f"Packaged worker benchmark gate did not pass cleanly: {benchmark_result}")
    qualification = qualify_runtime_snapshots(source, packaged)
    if qualification["status"] != "passed":
        failures = ", ".join(
            check["id"] for check in qualification["checks"] if check["status"] == "failed"
        )
        raise RuntimeError(
            "Packaged worker differs from the qualified source runtime: " + failures
        )
    geometry_arrow_probe = _verify_geometry_arrow_package(executable)
    spikes_engine_probe = _verify_spikes_engine(executable)
    from scripts.verify_extension_runtime import verify_extension_runtime
    extension_probe = verify_extension_runtime(executable, _request)
    return packaged, qualification, geometry_arrow_probe, spikes_engine_probe, extension_probe


def _write_manifest(
    artifact_dir: Path,
    native_extension: Path,
    pyinstaller_version: str,
    packaged_snapshot: dict[str, Any],
    qualification: dict[str, Any],
    geometry_arrow_probe: dict[str, Any],
    spikes_library: Path,
    spikes_engine_probe: dict[str, Any],
    extension_probe: dict[str, Any],
) -> Path:
    files = []
    for path in sorted(item for item in artifact_dir.rglob("*") if item.is_file()):
        files.append(
            {
                "path": path.relative_to(artifact_dir).as_posix(),
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    manifest = {
        "contract": "spike/packaged-worker-manifest/v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "pyinstaller": pyinstaller_version,
        "worker_version": packaged_snapshot.get("health", {}).get("worker_version"),
        "benchmark_summary": packaged_snapshot.get("benchmarks", {}).get("summary", {}),
        "runtime_snapshot_digest": canonical_digest(packaged_snapshot),
        "runtime_qualification": {
            "contract": qualification["contract"],
            "status": qualification["status"],
            "summary": qualification["summary"],
            "source_snapshot_digest": qualification["source_snapshot_digest"],
            "packaged_snapshot_digest": qualification["packaged_snapshot_digest"],
            "report": "release-runtime-qualification.json",
        },
        "geometry_arrow_probe": geometry_arrow_probe,
        "extension_execution_probe": extension_probe,
        "owned_spikes_engine": {
            "source_name": spikes_library.name,
            "sha256": _sha256(spikes_library),
            "interactive_probe": spikes_engine_probe,
        },
        "native_extension": {
            "source_name": native_extension.name,
            "sha256": _sha256(native_extension),
        },
        "files": files,
    }
    destination = RESOURCE_ROOT / "spike-worker.manifest.json"
    destination.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return destination


def build(*, keep_work: bool = False) -> tuple[Path, Path]:
    pyinstaller_version = _require_pyinstaller()
    native_extension = _native_extension()
    spikes_library = _spikes_library()
    RESOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    artifact_dir = RESOURCE_ROOT / "spike-worker"
    _remove_managed_tree(artifact_dir, RESOURCE_ROOT)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--noupx",
        "--onedir",
        "--name",
        "spike-worker",
        "--distpath",
        str(RESOURCE_ROOT),
        "--workpath",
        str(BUILD_ROOT / "work"),
        "--specpath",
        str(BUILD_ROOT / "spec"),
        "--paths",
        str(ROOT),
        "--add-binary",
        f"{native_extension}{os.pathsep}python",
        "--add-binary",
        f"{spikes_library}{os.pathsep}spikes",
        "--add-data",
        (
            f"{ROOT / 'python' / 'spike_core' / 'validation_data'}"
            f"{os.pathsep}python/spike_core/validation_data"
        ),
        "--hidden-import",
        "python.spike_peec_native",
        "--hidden-import",
        "pyarrow",
        "--hidden-import",
        "pyarrow.ipc",
        "--hidden-import",
        "python.spike_core.odb_importer",
        "--hidden-import",
        "python.spike_core.harness",
        "--hidden-import",
        "python.spike_core.mcad_export",
        "--hidden-import",
        "python.spike_core.mcad_export_design",
        "--add-data",
        f"{ROOT / 'python' / 'spike_core' / 'freecad_assembly_export.py'}{os.pathsep}python/spike_core",
        "--add-data",
        f"{ROOT / 'extensions'}{os.pathsep}extensions",
        "--add-data",
        f"{ROOT / 'schemas'}{os.pathsep}schemas",
        str(ROOT / "scripts" / "spike_worker_entry.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)

    executable = artifact_dir / ("spike-worker.exe" if os.name == "nt" else "spike-worker")
    if not executable.is_file():
        raise RuntimeError(f"PyInstaller did not produce the expected worker: {executable}")
    packaged_snapshot, qualification, geometry_arrow_probe, spikes_engine_probe, extension_probe = _verify(executable)
    _write_runtime_qualification(qualification)
    manifest = _write_manifest(
        artifact_dir,
        native_extension,
        pyinstaller_version,
        packaged_snapshot,
        qualification,
        geometry_arrow_probe,
        spikes_library,
        spikes_engine_probe,
        extension_probe,
    )
    if not keep_work:
        work = BUILD_ROOT / "work"
        spec = BUILD_ROOT / "spec"
        _remove_managed_tree(work, BUILD_ROOT)
        _remove_managed_tree(spec, BUILD_ROOT)
    return executable, manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-work", action="store_true", help="Retain PyInstaller work/spec directories")
    args = parser.parse_args()
    executable, manifest = build(keep_work=args.keep_work)
    print(f"Verified packaged worker: {executable}")
    print(f"Integrity manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
