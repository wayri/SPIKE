"""Bounded exact STEP-to-package-shape extraction through FreeCAD/OCC."""

from __future__ import annotations

import hashlib
import json
import tempfile
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict

from .assembly_package_shapes import MAX_TOTAL_ENTITIES, TOPOLOGY_KINDS
from .mcad_importer import McadImportError, validate_step_mcad_artifact
from .mcad_tessellation import _freecad_path
from .package_shape_geometry import PackageShapeGeometryError, canonicalize_selector_geometry
from .sparselizard_process import SparseLizardAdapterError, run_adapter_process


STEP_PACKAGE_SHAPE_CONTRACT = "spike/mcad-step-package-shape/v1"
_REPORT_CONTRACT = "spike/freecad-step-package-shape-report/v2"


class McadPackageShapeError(RuntimeError):
    """Raised when exact package-shape extraction cannot satisfy its contract."""


@dataclass(frozen=True)
class StepPackageShapePolicy:
    max_source_bytes: int = 64 * 1024**2
    max_output_bytes: int = 256 * 1024**2
    max_report_bytes: int = 256 * 1024**2
    max_entities: int = MAX_TOTAL_ENTITIES
    timeout_s: int = 300
    memory_limit_mb: int = 4096
    stream_limit_bytes: int = 1024**2

    def __post_init__(self) -> None:
        values = (
            self.max_source_bytes, self.max_output_bytes, self.max_report_bytes,
            self.max_entities, self.timeout_s, self.memory_limit_mb, self.stream_limit_bytes,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in values):
            raise ValueError("STEP package-shape resource limits must be positive integers.")
        if (
            self.max_source_bytes > 256 * 1024**2
            or self.max_output_bytes > 512 * 1024**2
            or self.max_report_bytes > 512 * 1024**2
        ):
            raise ValueError("STEP package-shape byte limits exceed the reviewed ceiling.")
        if self.max_entities > MAX_TOTAL_ENTITIES or self.timeout_s > 300 or self.memory_limit_mb > 4096 or self.stream_limit_bytes > 4 * 1024**2:
            raise ValueError("STEP package-shape process or selector limits exceed the reviewed ceiling.")


@dataclass(frozen=True)
class StepPackageShapeResult:
    source_sha256: str
    artifact_name: str
    artifact_sha256: str
    artifact_bytes: bytes
    kernel_id: str
    kernel_version: str
    freecad_version: str
    shape_count: int
    entity_count: int
    entities: tuple[Dict[str, Any], ...]
    topology_ready: bool = True
    solver_ready: bool = False
    contract: str = STEP_PACKAGE_SHAPE_CONTRACT

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value.pop("artifact_bytes")
        value["entities"] = [dict(item) for item in self.entities]
        return value


def _canonical_entity(raw: Any, position: int) -> Dict[str, Any]:
    fields = {"native_persistent_id", "kind", "fingerprint_sha256", "support", "geometry"}
    if not isinstance(raw, dict) or set(raw) != fields:
        raise McadPackageShapeError(f"Package-shape selector {position} has an invalid record shape.")
    native_id, kind, fingerprint = raw["native_persistent_id"], raw["kind"], raw["fingerprint_sha256"]
    if not isinstance(native_id, str) or not native_id or len(native_id) > 256 or native_id != native_id.strip():
        raise McadPackageShapeError(f"Package-shape selector {position} has an invalid persistent identity.")
    if kind not in TOPOLOGY_KINDS:
        raise McadPackageShapeError(f"Package-shape selector {position} has an invalid topology kind.")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64 or any(character not in "0123456789abcdef" for character in fingerprint):
        raise McadPackageShapeError(f"Package-shape selector {position} has an invalid fingerprint.")
    support = raw["support"]
    if not isinstance(support, dict) or set(support) != {"surface_kind", "curve_kind", "axis_native_persistent_id"}:
        raise McadPackageShapeError(f"Package-shape selector {position} has invalid support metadata.")
    if support["surface_kind"] not in {None, "plane", "cylinder", "cone", "sphere", "torus", "nurbs", "other"}:
        raise McadPackageShapeError(f"Package-shape selector {position} has an invalid surface kind.")
    if support["curve_kind"] not in {None, "line", "circle", "ellipse", "bspline", "other"}:
        raise McadPackageShapeError(f"Package-shape selector {position} has an invalid curve kind.")
    axis_id = support["axis_native_persistent_id"]
    if axis_id is not None and (not isinstance(axis_id, str) or not axis_id or len(axis_id) > 256):
        raise McadPackageShapeError(f"Package-shape selector {position} has an invalid support axis identity.")
    try:
        geometry = canonicalize_selector_geometry(raw["geometry"], kind, f"Package-shape selector {position} geometry")
    except PackageShapeGeometryError as exc:
        raise McadPackageShapeError(str(exc)) from exc
    return {"native_persistent_id": native_id, "kind": kind, "fingerprint_sha256": fingerprint, "support": dict(support), "geometry": geometry}


def extract_step_package_shape(
    payload: bytes,
    *,
    source_name: str = "source.step",
    policy: StepPackageShapePolicy | None = None,
    freecad_executable: str | Path | None = None,
    cancellation_event: threading.Event | None = None,
) -> StepPackageShapeResult:
    """Run the fixed helper and independently validate its exact BREP/report envelope."""

    policy = policy or StepPackageShapePolicy()
    if not isinstance(payload, bytes) or not payload or len(payload) > policy.max_source_bytes:
        raise McadPackageShapeError("STEP source is empty or exceeds the exact package-shape budget.")
    try:
        validate_step_mcad_artifact(payload)
    except McadImportError as exc:
        raise McadPackageShapeError(str(exc)) from exc
    source_sha256 = hashlib.sha256(payload).hexdigest()
    suffix = Path(source_name).suffix.lower() if Path(source_name).suffix.lower() in {".step", ".stp"} else ".step"
    executable = _freecad_path(freecad_executable)
    helper = Path(__file__).with_name("freecad_step_to_package_shape.py").resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="spike-step-package-shape-") as directory:
        root = Path(directory)
        source, output, report_path = root / f"source{suffix}", root / "output.spkshape", root / "report.json"
        helper_copy = root / "extract.py"
        source.write_bytes(payload); helper_copy.write_bytes(helper.read_bytes())
        command = [str(executable), "--console", "--user-cfg", str(root / "user.cfg"), "--system-cfg", str(root / "system.cfg")]
        arguments = [str(source), str(output), str(report_path), str(policy.max_entities), str(policy.max_output_bytes)]
        stdin_payload = (
            "scope={'__name__':'spike_freecad_package_shape'}\n"
            "exec(compile(open('extract.py',encoding='utf-8').read(),'extract.py','exec'),scope)\n"
            f"scope['extract']({arguments!r})\n"
            "raise SystemExit(0)\n"
        ).encode("utf-8")
        try:
            execution = run_adapter_process(
                command, cwd=root, timeout_s=policy.timeout_s, memory_limit_mb=policy.memory_limit_mb,
                output_limit_bytes=policy.max_output_bytes, stream_limit_bytes=policy.stream_limit_bytes,
                cancellation_event=cancellation_event, stdin_payload=stdin_payload,
            )
        except (OSError, SparseLizardAdapterError) as exc:
            raise McadPackageShapeError(str(exc).replace("SparseLizard adapter", "STEP package-shape extraction")) from exc
        if execution["return_code"] != 0:
            diagnostic = str(execution.get("stderr") or execution.get("stdout") or "FreeCAD extraction failed.")[-4000:]
            raise McadPackageShapeError(f"FreeCAD STEP package-shape extraction failed: {diagnostic}")
        if not output.is_file() or not report_path.is_file() or output.stat().st_size <= 0 or output.stat().st_size > policy.max_output_bytes:
            raise McadPackageShapeError("FreeCAD package-shape output is missing or violates its byte budget.")
        artifact = output.read_bytes()
        if b"CASCADE Topology V" not in artifact[:4096]:
            raise McadPackageShapeError("FreeCAD package-shape output is not an Open CASCADE BREP artifact.")
        if report_path.stat().st_size <= 0 or report_path.stat().st_size > policy.max_report_bytes:
            raise McadPackageShapeError("FreeCAD package-shape report violates its byte budget.")
        try:
            report = json.loads(report_path.read_bytes().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise McadPackageShapeError("FreeCAD package-shape report is not valid JSON.") from exc
        if not isinstance(report, dict) or report.get("contract") != _REPORT_CONTRACT:
            raise McadPackageShapeError("FreeCAD package-shape report contract is invalid.")
        artifact_sha256 = hashlib.sha256(artifact).hexdigest()
        if report.get("source_sha256") != source_sha256 or report.get("artifact_sha256") != artifact_sha256:
            raise McadPackageShapeError("FreeCAD package-shape report digest identity is invalid.")
        if report.get("topology_ready") is not True or report.get("solver_ready") is not False:
            raise McadPackageShapeError("FreeCAD package-shape report qualification is invalid.")
        entities_raw = report.get("entities")
        if not isinstance(entities_raw, list) or not entities_raw or len(entities_raw) > policy.max_entities:
            raise McadPackageShapeError("FreeCAD package-shape selector inventory is empty or exceeds its limit.")
        if report.get("entity_count") != len(entities_raw):
            raise McadPackageShapeError("FreeCAD package-shape selector count does not match its inventory.")
        entities = tuple(_canonical_entity(item, position) for position, item in enumerate(entities_raw))
        identities = {(item["kind"], item["native_persistent_id"]) for item in entities}
        if len(identities) != len(entities):
            raise McadPackageShapeError("FreeCAD package-shape selector identities are duplicated.")
        axis_ids = {item["native_persistent_id"] for item in entities if item["kind"] == "axis"}
        if any(item["support"]["axis_native_persistent_id"] not in axis_ids for item in entities if item["support"]["axis_native_persistent_id"] is not None):
            raise McadPackageShapeError("FreeCAD package-shape selector inventory contains an unresolved axis.")
        shape_count = report.get("shape_count")
        if isinstance(shape_count, bool) or not isinstance(shape_count, int) or shape_count <= 0:
            raise McadPackageShapeError("FreeCAD package-shape report shape_count is invalid.")
        kernel_id, kernel_version, freecad_version = report.get("kernel_id"), report.get("kernel_version"), report.get("freecad_version")
        if not all(isinstance(value, str) and value.strip() for value in (kernel_id, kernel_version, freecad_version)):
            raise McadPackageShapeError("FreeCAD package-shape kernel/version identity is missing.")
        artifact_name = f"{Path(source_name).stem or 'shape'}-{source_sha256[:12]}-{artifact_sha256[:12]}.spkshape"
        return StepPackageShapeResult(
            source_sha256=source_sha256, artifact_name=artifact_name, artifact_sha256=artifact_sha256,
            artifact_bytes=artifact, kernel_id=kernel_id, kernel_version=kernel_version,
            freecad_version=freecad_version, shape_count=shape_count, entity_count=len(entities), entities=entities,
        )
