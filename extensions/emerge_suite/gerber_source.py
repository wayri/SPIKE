# SPDX-License-Identifier: Apache-2.0
"""Bounded native-Gerber source package admission and SpiDeR projection."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import tempfile

from python.spike_core.contracts import SpiDeR, ValidationIssue
from python.spike_core.importers import FunctionImporter, ImportPolicy, ImporterDescriptor, ImporterRegistry


CONTRACT = "spike/emerge-gerber-source/v1"
MAX_FILES = 8
MAX_LAYERS = 16
MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024
MAX_PACKAGE_JSON_BYTES = 16 * 1024 * 1024
_LAYER_NAME = re.compile(r"^(?:F\.Cu|B\.Cu|In[1-9][0-9]*\.Cu)$")


def _number(value: object, label: str, *, low: float = -math.inf,
            high: float = math.inf, low_inclusive: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number.")
    result = float(value)
    if not math.isfinite(result) or result > high or (result < low if low_inclusive else result <= low):
        raise ValueError(f"{label} is outside its supported range.")
    return result


def _text(value: object, label: str, *, maximum: int = 128) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} must be a non-empty string of at most {maximum} characters.")
    return value.strip()


def _file_name(value: object, label: str) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise ValueError(f"{label} must be a portable plain file name.")
    name = _text(value, label, maximum=160)
    if (name in {".", ".."} or name.endswith((".", " "))
            or any(character in name for character in '<>:"/\\|?*')
            or any(ord(character) < 32 or ord(character) == 127 for character in name)):
        raise ValueError(f"{label} must be a portable plain file name without reserved characters.")
    device = name.split(".", 1)[0].rstrip(" ").upper()
    if device in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(?:COM|LPT)[1-9¹²³]", device):
        raise ValueError(f"{label} uses a reserved Windows device name.")
    return name


def _source_file(row: object, label: str) -> dict:
    if not isinstance(row, dict) or set(row) - {"name", "file_name", "content", "sha256", "size_bytes"}:
        raise ValueError(f"{label} must contain only its declared source fields.")
    name = _file_name(row.get("file_name"), f"{label}.file_name")
    content = row.get("content")
    if not isinstance(content, str) or not content or "\x00" in content:
        raise ValueError(f"{label}.content must be non-empty text without NUL characters.")
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_FILE_BYTES:
        raise ValueError(f"{label} exceeds the 512 KiB per-file limit.")
    digest = hashlib.sha256(encoded).hexdigest()
    if row.get("sha256") not in (None, digest) or row.get("size_bytes") not in (None, len(encoded)):
        raise ValueError(f"{label} retained hash or size does not match its content.")
    return {"file_name": name, "content": content,
            "sha256": digest, "size_bytes": len(encoded)}


def normalize_gerber_source(source: object) -> dict:
    """Validate and canonicalize the user-authored native Gerber package."""
    if not isinstance(source, dict) or source.get("contract") != CONTRACT:
        raise ValueError(f"Gerber source must use {CONTRACT}.")
    allowed = {"contract", "name", "bounds_mm", "layers", "dielectrics", "ports",
               "resolution_mm", "drills"}
    unknown = set(source) - allowed
    if unknown:
        raise ValueError("Gerber source contains unsupported fields: " + ", ".join(sorted(unknown)))
    name = _text(source.get("name"), "Gerber source name")
    bounds_value = source.get("bounds_mm")
    if not isinstance(bounds_value, list) or len(bounds_value) != 4:
        raise ValueError("bounds_mm must contain xmin, ymin, xmax, and ymax in millimetres.")
    bounds = [_number(value, f"bounds_mm[{index}]", low=-1e6, high=1e6)
              for index, value in enumerate(bounds_value)]
    if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        raise ValueError("bounds_mm must have increasing x and y coordinates.")
    if (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]) > 40_000:
        raise ValueError("Gerber bounds exceed the 40000 mm2 adapter limit.")

    rows = source.get("layers")
    if not isinstance(rows, list) or not 2 <= len(rows) <= MAX_LAYERS:
        raise ValueError("Gerber source needs 2-16 copper layers.")
    layers = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) - {"name", "file_name", "content", "sha256", "size_bytes"}:
            raise ValueError(f"layers[{index}] must contain name, file_name, and content only.")
        layer_name = _text(row.get("name"), f"layers[{index}].name", maximum=32)
        if not _LAYER_NAME.fullmatch(layer_name):
            raise ValueError(f"Unsupported Gerber copper layer name: {layer_name}.")
        layers.append({"name": layer_name, **_source_file(row, f"layers[{index}]")})
    expected_names = ["F.Cu", *[f"In{index}.Cu" for index in range(1, len(layers) - 1)], "B.Cu"]
    if [row["name"] for row in layers] != expected_names:
        raise ValueError("Gerber layers must be ordered F.Cu, sequential inner copper layers, then B.Cu.")

    dielectric_rows = source.get("dielectrics")
    if not isinstance(dielectric_rows, list) or len(dielectric_rows) != len(layers) - 1:
        raise ValueError("Gerber source needs one dielectric definition per copper-layer gap.")
    dielectrics = []
    for index, row in enumerate(dielectric_rows):
        if not isinstance(row, dict) or set(row) - {"thickness_mm", "epsilon_r", "loss_tangent"}:
            raise ValueError(f"dielectrics[{index}] has unsupported fields.")
        dielectrics.append({
            "thickness_mm": _number(row.get("thickness_mm"), "dielectric thickness",
                                     low=0.01, high=10),
            "epsilon_r": _number(row.get("epsilon_r"), "relative permittivity", low=1.01, high=30),
            "loss_tangent": _number(row.get("loss_tangent", 0), "loss tangent", low=0, high=1),
        })
    if sum(row["thickness_mm"] for row in dielectrics) > 10:
        raise ValueError("Total dielectric thickness exceeds 10 mm.")

    ports_value = source.get("ports")
    if not isinstance(ports_value, list) or not 1 <= len(ports_value) <= 2:
        raise ValueError("Gerber source needs one or two explicit ports.")
    ports = []
    for index, row in enumerate(ports_value):
        if not isinstance(row, dict) or set(row) - {
                "id", "x_mm", "y_mm", "width_mm", "signal_layer", "return_layer"}:
            raise ValueError(f"ports[{index}] has unsupported fields.")
        port_id = _text(row.get("id"), f"ports[{index}].id", maximum=32)
        expected_id = f"P{index + 1}"
        if port_id != expected_id:
            raise ValueError(f"Gerber ports must be ordered and named {expected_id}.")
        x = _number(row.get("x_mm"), f"{port_id} x", low=bounds[0], high=bounds[2])
        y = _number(row.get("y_mm"), f"{port_id} y", low=bounds[1], high=bounds[3])
        width = _number(row.get("width_mm"), f"{port_id} width", low=0.01,
                        high=max(bounds[2] - bounds[0], bounds[3] - bounds[1]))
        if x - width / 2 < bounds[0] or x + width / 2 > bounds[2]:
            raise ValueError(f"{port_id} width extends outside the declared Gerber bounds.")
        signal = _text(row.get("signal_layer"), f"{port_id} signal layer", maximum=32)
        returned = _text(row.get("return_layer"), f"{port_id} return layer", maximum=32)
        names = [item["name"] for item in layers]
        if signal not in names or returned not in names or names.index(returned) != names.index(signal) + 1:
            raise ValueError(f"{port_id} must connect a signal layer to the adjacent copper layer below it.")
        ports.append({"id": port_id, "x_mm": x, "y_mm": y, "width_mm": width,
                      "signal_layer": signal, "return_layer": returned})
    locations = [(row["x_mm"], row["y_mm"], row["signal_layer"], row["return_layer"])
                 for row in ports]
    if len(locations) != len(set(locations)):
        raise ValueError("Gerber ports must have distinct coordinates and layer pairs.")

    drills_value = source.get("drills", [])
    if not isinstance(drills_value, list):
        raise ValueError("drills must be an array of retained Excellon source files.")
    drills = [_source_file(row, f"drills[{index}]") for index, row in enumerate(drills_value)]
    files = [*layers, *drills]
    if len(files) > MAX_FILES:
        raise ValueError("Gerber source exceeds the eight-file limit.")
    file_names = [row["file_name"].casefold() for row in files]
    if len(file_names) != len(set(file_names)):
        raise ValueError("Gerber and drill file names must be unique.")
    if sum(row["size_bytes"] for row in files) > MAX_TOTAL_BYTES:
        raise ValueError("Gerber source exceeds the 2 MiB retained-content limit.")
    resolution = _number(source.get("resolution_mm", 0.01), "Gerber outline resolution",
                         low=0.001, high=1)
    return {"contract": CONTRACT, "name": name, "bounds_mm": bounds, "layers": layers,
            "dielectrics": dielectrics, "ports": ports, "resolution_mm": resolution,
            "drills": drills}


def source_digest(source: dict) -> str:
    payload = json.dumps(source, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def design_from_source(source: object) -> SpiDeR:
    package = normalize_gerber_source(source)
    digest = source_digest(package)
    identity = digest[:16]
    stackup = []
    for index, layer in enumerate(package["layers"]):
        stackup.append({"id": f"gerber-{identity}-layer-{index}", "name": layer["name"],
                        "type": "copper", "thickness": 0.0})
        if index < len(package["dielectrics"]):
            dielectric = package["dielectrics"][index]
            stackup.append({"id": f"gerber-{identity}-dielectric-{index + 1}",
                            "name": f"Dielectric {index + 1}", "type": "dielectric",
                            "thickness": dielectric["thickness_mm"],
                            "epsilon_r": dielectric["epsilon_r"],
                            "loss_tangent": dielectric["loss_tangent"]})
    issues = [
        ValidationIssue(
            code="EMERGE_GERBER_NATIVE_ONLY", severity="warning",
            message="Gerber artwork is retained for the native EMerge loader; SPIKE has not inferred nets, pads, copper polygons, or connectivity."),
        ValidationIssue(
            code="EMERGE_GERBER_MANUAL_PORTS", severity="warning",
            message="Port coordinates and adjacent-layer assignments are manual annotations and are not verified against source pads."),
    ]
    if package["drills"]:
        issues.append(ValidationIssue(
            code="EMERGE_GERBER_DRILLS_RETAINED_UNSUPPORTED", severity="warning",
            message="Excellon files are retained, but native drill execution is blocked until via semantics are integrated and verified."))
    metadata = {
        "board_bounds_mm": package["bounds_mm"],
        "emerge_gerber_source": package,
        "emerge_gerber_source_sha256": digest,
        "emerge_gerber_port_markers": package["ports"],
        "semantic_net_labels": ["GerberRF", "GerberReturn"],
        "source_artwork_retained_only": True,
        "geometry_normalized": False,
        "geometry_solver_ready": False,
        "native_solver_readiness": {
            "emerge_native_gerber": {"ready": not package["drills"],
                                      "reasons": (["Retained Excellon drill files are not yet admitted for execution."]
                                                  if package["drills"] else [])}},
    }
    return SpiDeR(
        design_id=f"emerge-gerber-{digest}", name=package["name"],
        source_format="emerge-gerber", units="mm",
        layers=[{"id": f"gerber-{identity}-layer-{index}", "name": row["name"], "type": "copper"}
                for index, row in enumerate(package["layers"])],
        nets=[{"id": f"gerber-{identity}-rf", "name": "GerberRF", "class": "semantic_annotation"},
              {"id": f"gerber-{identity}-return", "name": "GerberReturn", "class": "semantic_annotation"}],
        stackup=stackup, issues=issues, metadata=metadata,
    )


def import_gerber_design(path: str) -> SpiDeR:
    source_path = Path(path)
    if not source_path.is_file() or source_path.stat().st_size > MAX_PACKAGE_JSON_BYTES:
        raise ValueError("Gerber package JSON is missing or exceeds the 16 MiB parser limit.")
    try:
        raw = json.loads(source_path.read_text(encoding="utf-8"),
                         parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Gerber package must be finite UTF-8 JSON.") from error
    return design_from_source(raw)


def _registry(*, max_source_bytes: int = 8 * 1024 * 1024) -> ImporterRegistry:
    descriptor = ImporterDescriptor(
        importer_id="emerge-gerber-design", display_name="EMerge native Gerber package",
        source_formats=("emerge-gerber",), extensions=(".spike-gerber.json",),
    )
    return ImporterRegistry([FunctionImporter(descriptor, import_gerber_design)],
                            policy=ImportPolicy(max_source_bytes=max_source_bytes))


def snapshot_from_source(source: object) -> dict:
    """Use the normal importer outcome path for an in-memory application source."""
    package = normalize_gerber_source(source)
    payload = json.dumps(package, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    with tempfile.TemporaryDirectory(prefix="spike-gerber-import-") as directory:
        path = Path(directory) / "source.spike-gerber.json"
        path.write_bytes(payload)
        outcome = _registry(max_source_bytes=max(8 * 1024 * 1024, len(payload) + 1)).import_outcome(
            str(path), "emerge-gerber")
    report = outcome.report.to_dict()
    native = outcome.design.metadata["native_solver_readiness"]
    report["solver_readiness"].update(native)
    outcome.design.metadata["import_report"] = report
    design = design_from_source(package).to_dict()
    design["metadata"]["import_report"] = report
    return {"contract": "spike/design-snapshot/v1", "design": design,
            "canonical_design": outcome.design.to_dict(), "report": report}
