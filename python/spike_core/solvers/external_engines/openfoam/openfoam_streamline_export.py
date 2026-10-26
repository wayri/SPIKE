# SPDX-License-Identifier: Apache-2.0
"""Native OpenFOAM streamline and saved-frame export for admitted CHT cases."""
from __future__ import annotations

import base64
import binascii
import math
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Mapping

from .openfoam import _parse_internal_field
from .openfoam_multiregion_execution import MAX_STREAM_BYTES, _bounded_command, _windows_process_allowance
from .openfoam_runtime import detect_openfoam_runtime
from ..sparselizard.sparselizard_process import run_adapter_process


def _times(case: Path) -> list[tuple[float, Path]]:
    rows = []
    for path in case.iterdir():
        try:
            value = float(path.name)
        except ValueError:
            continue
        if math.isfinite(value) and value > 0 and (path / "air/U").is_file() and (path / "air/T").is_file():
            rows.append((value, path))
    rows.sort()
    if any(left[0] == right[0] for left, right in zip(rows, rows[1:])):
        raise ValueError("OpenFOAM field export contains duplicate numeric times")
    if len(rows) > 256:
        raise ValueError("OpenFOAM field export exceeds 256 saved frames")
    return rows


def _dictionary(start_m: list[float], end_m: list[float], line_count: int) -> str:
    point = lambda value: "(" + " ".join(format(item, ".12g") for item in value) + ")"
    return f"""FoamFile
{{
    format ascii;
    class dictionary;
    object controlDict;
}}
functions
{{
    spikeStreamlines
    {{
        type streamLine;
        libs (\"libfieldFunctionObjects.so\");
        region air;
        writeControl writeTime;
        setFormat vtk;
        direction forward;
        lifeTime 10000;
        nSubCycle 8;
        cloud spikeParticleTracks;
        fields (U T);
        seedSampleSet
        {{
            type uniform;
            axis y;
            start {point(start_m)};
            end {point(end_m)};
            nPoints {line_count};
        }}
    }}
}}
"""


def _vtk_array(node: ET.Element) -> list[float] | list[int]:
    if node.attrib.get("format") != "binary":
        raise ValueError("OpenFOAM VTP arrays must use inline binary format")
    try:
        raw = base64.b64decode("".join((node.text or "").split()), validate=True)
    except binascii.Error as exc:
        raise ValueError("OpenFOAM VTP array is not valid base64") from exc
    if len(raw) < 8:
        raise ValueError("OpenFOAM VTP array lacks its UInt64 byte count")
    count = struct.unpack("<Q", raw[:8])[0]
    if count != len(raw) - 8:
        raise ValueError("OpenFOAM VTP declared byte count does not match its payload")
    payload = raw[8:]
    kind = {"Float32": "f", "Int32": "i"}.get(node.attrib.get("type"))
    if kind is None or len(payload) % struct.calcsize(kind):
        raise ValueError("OpenFOAM VTP array type or length is unsupported")
    return list(struct.unpack("<" + kind*(len(payload)//struct.calcsize(kind)), payload))


def _curves(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or path.stat().st_size > 64*1024**2:
        raise ValueError("Native streamline VTP is missing or outside its limit")
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ValueError("Native streamline VTP XML is malformed") from exc
    if (root.tag != "VTKFile" or root.attrib.get("type") != "PolyData"
            or root.attrib.get("byte_order") != "LittleEndian" or root.attrib.get("header_type") != "UInt64"
            or root.attrib.get("compressor") is not None):
        raise ValueError("Native streamline VTP encoding is unsupported")
    piece = root.find("./PolyData/Piece")
    if piece is None:
        raise ValueError("Native streamline VTP lacks PolyData")
    arrays = {item.attrib.get("Name"): item for item in piece.findall(".//DataArray")}
    if not {"Points", "offsets", "connectivity", "T", "U"} <= set(arrays):
        raise ValueError("Native streamline VTP lacks aligned U/T tracks")
    xyz = _vtk_array(arrays["Points"]); offsets = _vtk_array(arrays["offsets"]); connectivity = _vtk_array(arrays["connectivity"])
    temperature = _vtk_array(arrays["T"]); velocity = _vtk_array(arrays["U"])
    if len(xyz) % 3 or len(velocity) % 3 or len(xyz) // 3 > 1_000_000:
        raise ValueError("Native streamline coordinates or velocity arrays are malformed or too large")
    if any(not math.isfinite(value) for value in [*xyz, *temperature, *velocity]):
        raise ValueError("Native streamline arrays contain nonfinite values")
    points = [[1000*xyz[i], 1000*xyz[i+1], 1000*xyz[i+2]] for i in range(0, len(xyz), 3)]
    speeds = [math.hypot(*velocity[i:i+3]) for i in range(0, len(velocity), 3)]
    if len(points) != len(temperature) or len(points) != len(speeds):
        raise ValueError("Native streamline point and field arrays are not aligned")
    if (not offsets or any(type(value) is not int for value in [*offsets, *connectivity])
            or any(value <= 0 for value in offsets) or any(left >= right for left, right in zip(offsets, offsets[1:]))
            or offsets[-1] != len(connectivity)
            or any(index < 0 or index >= len(points) for index in connectivity)):
        raise ValueError("Native streamline connectivity or offsets are malformed")
    declared_points = piece.attrib.get("NumberOfPoints")
    declared_lines = piece.attrib.get("NumberOfLines")
    if (not declared_points or not declared_lines or int(declared_points) != len(points) or int(declared_lines) != len(offsets)):
        raise ValueError("Native streamline VTP declared counts do not match its arrays")
    rows, start = [], 0
    for stop in offsets:
        ids = connectivity[start:stop]; start = stop
        if len(ids) >= 2:
            rows.append({"points": [points[index] for index in ids], "scalars": {
                "temperature_k": [temperature[index] for index in ids], "speed_m_s": [speeds[index] for index in ids]}})
    return rows


def export_forced_airflow_field_volume(case_dir: str | Path, result: Mapping[str, Any], *, seed_line_mm: list[list[float]],
                                       runtime: Mapping[str, Any] | None = None, line_count: int = 16,
                                       cancellation_event=None) -> dict[str, Any]:
    case = Path(case_dir).resolve()
    if result.get("status") != "completed" or not isinstance(seed_line_mm, list) or len(seed_line_mm) != 2 or any(not isinstance(row, list) or len(row) != 3 for row in seed_line_mm):
        raise ValueError("Completed result and explicit two-point seed line in mm are required")
    if type(line_count) is not int or not 2 <= line_count <= 64 or any(not math.isfinite(float(value)) for row in seed_line_mm for value in row):
        raise ValueError("Streamline seed controls are invalid")
    saved = _times(case)
    if not saved:
        raise ValueError("No written air U/T fields are available")
    control = case / "system/spikeStreamlineControlDict"
    control.write_text(_dictionary([[value/1000 for value in row] for row in seed_line_mm][0],
                                   [[value/1000 for value in row] for row in seed_line_mm][1], line_count), encoding="utf-8", newline="\n")
    active = dict(runtime or detect_openfoam_runtime())
    argv = _bounded_command(active, "postProcess", case, "-region", "air", "-dict", "system/spikeStreamlineControlDict",
        "-fields", "(U T)", "-time", ",".join(path.name for _, path in saved), timeout_s=120, memory_limit_mb=2048, output_limit_bytes=256*1024**2)
    report = run_adapter_process(argv, cwd=case, timeout_s=120, memory_limit_mb=2048, output_limit_bytes=256*1024**2,
        stream_limit_bytes=MAX_STREAM_BYTES, windows_active_process_limit=_windows_process_allowance(active),
        cancellation_event=cancellation_event)
    if report["return_code"] != 0 or "Tracks:" not in report.get("stdout", ""):
        raise RuntimeError("Native OpenFOAM streamline export failed")
    velocity_samples = [row for row in result["fields"]["velocity_m_s"]["samples"] if row.get("region") == "air"]
    centers = [row["point_mm"] for row in velocity_samples]
    if not centers or len(centers) > 1_000_000 or len(centers) * len(saved) > 2_000_000:
        raise ValueError("OpenFOAM air frame export exceeds its point budget")
    frames = []
    retained_curve_points = 0
    for value, path in saved:
        vectors = _parse_internal_field(path / "air/U", vector=True, expected_count=len(centers))
        temperature = _parse_internal_field(path / "air/T", expected_count=len(centers))
        curves = _curves(case / "postProcessing/sets/spikeStreamlines/air" / path.name / "track0.vtp")
        retained_curve_points += sum(len(curve["points"]) for curve in curves)
        if retained_curve_points > 2_000_000:
            raise ValueError("OpenFOAM streamline export exceeds its retained-point budget")
        frames.append({"timeS": value, "scalars": {"temperature_k": temperature, "speed_m_s": [math.hypot(*row) for row in vectors]},
                       "vectors": vectors, "streamlines": curves})
    return {"contract": "spike/field-volume-view/v1", "id": str(result.get("job_id") or "assembly-airflow"),
        "label": "Assembly airflow saved fields and native streamlines", "lengthUnit": "mm",
        "geometryNote": "Solver air-cell centres and OpenFOAM-native frozen-time streamlines; unstructured cells are point-only and no complete Cartesian fluid domain is asserted.",
        "cells": {"centers": centers}, "quantities": [
            {"id": "temperature_k", "label": "Air temperature", "unit": "K"},
            {"id": "speed_m_s", "label": "Air speed", "unit": "m/s"}], "frames": frames}


__all__ = ["export_forced_airflow_field_volume"]
