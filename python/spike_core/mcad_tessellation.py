"""Bounded optional STEP/STP-to-GLB visual tessellation.

The original STEP bytes remain authoritative source geometry.  The generated
GLB is independently validated and is never described as topology, a solver
mesh, a material region, or production-qualified physics geometry.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict

from .dependencies import dependency_status
from .importers import ImportPolicy
from .mcad_importer import McadImportError, validate_step_mcad_artifact, validate_visual_mcad_artifact
from .sparselizard_process import SparseLizardAdapterError, run_adapter_process


STEP_TESSELLATION_CONTRACT = "spike/mcad-step-tessellation/v1"
FREECAD_EXECUTABLE_NAMES = {"freecadcmd", "freecadcmd.exe"}


class McadTessellationError(RuntimeError):
    """Raised when optional visual tessellation cannot satisfy its bounds."""


@dataclass(frozen=True)
class StepTessellationPolicy:
    max_source_bytes: int = 64 * 1024**2
    max_output_bytes: int = 64 * 1024**2
    max_vertices: int = 2_000_000
    max_triangles: int = 2_000_000
    timeout_s: int = 300
    memory_limit_mb: int = 2048
    stream_limit_bytes: int = 1024**2
    linear_deflection_mm: float = 0.1

    def __post_init__(self) -> None:
        integer_values = (
            self.max_source_bytes, self.max_output_bytes, self.max_vertices,
            self.max_triangles, self.timeout_s, self.memory_limit_mb, self.stream_limit_bytes,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in integer_values):
            raise ValueError("STEP tessellation resource limits must be positive integers.")
        if self.max_source_bytes > 256 * 1024**2 or self.max_output_bytes > 256 * 1024**2:
            raise ValueError("STEP tessellation source and output limits cannot exceed 256 MiB.")
        if self.max_vertices > 5_000_000 or self.max_triangles > 5_000_000:
            raise ValueError("STEP tessellation mesh limits cannot exceed five million entities.")
        if self.timeout_s > 300 or self.memory_limit_mb > 4096 or self.stream_limit_bytes > 4 * 1024**2:
            raise ValueError("STEP tessellation process limits exceed the reviewed adapter ceiling.")
        if not math.isfinite(self.linear_deflection_mm) or not 0.001 <= self.linear_deflection_mm <= 10.0:
            raise ValueError("linear_deflection_mm must be within 0.001 through 10 mm.")


@dataclass(frozen=True)
class StepTessellationResult:
    source_sha256: str
    artifact_name: str
    artifact_sha256: str
    artifact_bytes: bytes
    freecad_version: str
    shape_count: int
    vertex_count: int
    triangle_count: int
    linear_deflection_mm: float
    visual_only: bool = True
    solver_ready: bool = False
    contract: str = STEP_TESSELLATION_CONTRACT

    def to_dict(self) -> Dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if key != "artifact_bytes"}


def _freecad_path(explicit: str | Path | None = None) -> Path:
    candidate = explicit
    if candidate is None:
        candidate = next(
            (item.get("path") for item in dependency_status()["dependencies"] if item.get("id") == "freecad" and item.get("status") == "ready"),
            "",
        )
    try:
        path = Path(str(candidate)).resolve(strict=True)
    except OSError as exc:
        raise McadTessellationError("FreeCADCmd is unavailable; STEP remains retained but not visualizable.") from exc
    if not path.is_file() or path.name.lower() not in FREECAD_EXECUTABLE_NAMES:
        raise McadTessellationError("Only the discovered FreeCADCmd executable may run the bounded STEP tessellator.")
    if os.name != "nt" and not os.access(path, os.X_OK):
        raise McadTessellationError("The discovered FreeCADCmd executable is not executable.")
    return path


def tessellate_step_to_glb(
    payload: bytes,
    *,
    source_name: str = "source.step",
    policy: StepTessellationPolicy | None = None,
    freecad_executable: str | Path | None = None,
    cancellation_event: threading.Event | None = None,
) -> StepTessellationResult:
    """Run the fixed SPIKE FreeCAD helper and independently validate its GLB."""

    policy = policy or StepTessellationPolicy()
    if not isinstance(payload, bytes) or not payload:
        raise McadTessellationError("STEP tessellation requires non-empty source bytes.")
    if len(payload) > policy.max_source_bytes:
        raise McadTessellationError("STEP source exceeds the configured visual tessellation budget.")
    try:
        validate_step_mcad_artifact(payload)
    except McadImportError as exc:
        raise McadTessellationError(str(exc)) from exc
    suffix = Path(source_name).suffix.lower()
    if suffix not in {".step", ".stp"}:
        suffix = ".step"
    executable = _freecad_path(freecad_executable)
    helper = Path(__file__).with_name("freecad_step_to_glb.py").resolve(strict=True)
    source_sha256 = hashlib.sha256(payload).hexdigest()

    with tempfile.TemporaryDirectory(prefix="spike-step-tessellation-") as directory:
        root = Path(directory)
        source = root / f"source{suffix}"
        output = root / "output.glb"
        report_path = root / "report.json"
        helper_copy = root / "convert.py"
        source.write_bytes(payload)
        helper_copy.write_bytes(helper.read_bytes())
        command = [
            str(executable), "--console",
            "--user-cfg", str(root / "user.cfg"), "--system-cfg", str(root / "system.cfg"),
        ]
        conversion_arguments = [
            str(source), str(output), str(report_path), f"{policy.linear_deflection_mm:.12g}",
            str(policy.max_vertices), str(policy.max_triangles), str(policy.max_output_bytes),
        ]
        stdin_payload = (
            "scope={'__name__':'spike_freecad_tessellator'}\n"
            "exec(compile(open('convert.py',encoding='utf-8').read(),'convert.py','exec'),scope)\n"
            f"scope['convert']({conversion_arguments!r})\n"
            "raise SystemExit(0)\n"
        ).encode("utf-8")
        try:
            execution = run_adapter_process(
                command, cwd=root, timeout_s=policy.timeout_s,
                memory_limit_mb=policy.memory_limit_mb,
                output_limit_bytes=policy.max_output_bytes,
                stream_limit_bytes=policy.stream_limit_bytes,
                cancellation_event=cancellation_event,
                stdin_payload=stdin_payload,
            )
        except (OSError, SparseLizardAdapterError) as exc:
            raise McadTessellationError(str(exc).replace("SparseLizard adapter", "STEP tessellation")) from exc
        if execution["return_code"] != 0:
            diagnostic = str(execution.get("stderr") or execution.get("stdout") or "FreeCAD conversion failed.")[-4000:]
            raise McadTessellationError(f"FreeCAD STEP tessellation failed: {diagnostic}")
        if not output.is_file() or not report_path.is_file():
            diagnostic = str(execution.get("stderr") or execution.get("stdout") or "No converter diagnostics were returned.")[-4000:]
            raise McadTessellationError(f"FreeCAD did not produce the required GLB and report files: {diagnostic}")
        if output.stat().st_size <= 0 or output.stat().st_size > policy.max_output_bytes:
            raise McadTessellationError("FreeCAD GLB output violates the configured byte budget.")
        artifact = output.read_bytes()
        try:
            validate_visual_mcad_artifact("glb", artifact)
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (McadImportError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise McadTessellationError("FreeCAD output failed independent GLB/report validation.") from exc
        if not isinstance(report, dict) or report.get("contract") != "spike/freecad-step-tessellation-report/v1":
            raise McadTessellationError("FreeCAD tessellation report contract is invalid.")
        if report.get("visual_only") is not True or report.get("solver_ready") is not False:
            raise McadTessellationError("FreeCAD tessellation report must preserve visual-only qualification.")
        counts = []
        for key in ("shape_count", "vertex_count", "triangle_count"):
            value = report.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise McadTessellationError(f"FreeCAD tessellation report {key} is invalid.")
            counts.append(value)
        if counts[1] > policy.max_vertices or counts[2] > policy.max_triangles:
            raise McadTessellationError("FreeCAD tessellation report exceeds the configured mesh budget.")
        artifact_sha256 = hashlib.sha256(artifact).hexdigest()
        artifact_name = f"{Path(source_name).stem or 'model'}-{source_sha256[:12]}-{artifact_sha256[:12]}.glb"
        return StepTessellationResult(
            source_sha256=source_sha256, artifact_name=artifact_name,
            artifact_sha256=artifact_sha256, artifact_bytes=artifact,
            freecad_version=str(report.get("freecad_version", "")),
            shape_count=counts[0], vertex_count=counts[1], triangle_count=counts[2],
            linear_deflection_mm=policy.linear_deflection_mm,
        )
