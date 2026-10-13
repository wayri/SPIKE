# SPDX-License-Identifier: Apache-2.0
"""Bounded adapter for KLayout's read-only database inspection.

The adapter requires an explicit local executable and invokes the checked-in
probe in batch mode.  It does not download KLayout, open interactive windows,
modify layouts, or claim DRC/LVS/PEX capability.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


LAYOUT_INSPECTION_CONTRACT = "spikes/klayout-layout-inspection/v1"
_SUPPORTED_LAYOUT_SUFFIXES = frozenset({
    ".cif", ".dxf", ".gds", ".gds2", ".oas", ".oasis",
})
_MAX_CONFIGURABLE_INPUT_BYTES = 1024**3


class KLayoutBridgeError(ValueError):
    """Invalid inspection request or invalid KLayout report."""


class KLayoutExecutionError(RuntimeError):
    """Stable failure from the KLayout child process."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail[:4096]
        super().__init__(code if not self.detail else f"{code}: {self.detail}")


@dataclass(frozen=True, slots=True)
class KLayoutInspectionLimits:
    max_input_bytes: int = 1024**3
    max_cells: int = 4096
    max_layers: int = 1024
    max_instances: int = 100_000
    max_shapes: int = 10_000_000
    max_cell_layer_pairs: int = 250_000
    max_report_bytes: int = 8 * 1024 * 1024
    max_process_output_bytes: int = 1024 * 1024

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise KLayoutBridgeError(f"{name} must be a positive integer.")
        if self.max_input_bytes > _MAX_CONFIGURABLE_INPUT_BYTES:
            raise KLayoutBridgeError("max_input_bytes must be at most 1 GiB.")


DEFAULT_KLAYOUT_LIMITS = KLayoutInspectionLimits()

Runner = Callable[
    [Sequence[str], Path, float],
    subprocess.CompletedProcess[bytes],
]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checked_file(value: str | Path, role: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise KLayoutBridgeError(f"{role} must be an existing file.") from exc
    if not path.is_file():
        raise KLayoutBridgeError(f"{role} must be an existing file.")
    return path


def _probe_script() -> Path:
    path = Path(__file__).resolve().parents[2] / "scripts" / "klayout" / "spikes_layout_probe.py"
    if not path.is_file():
        raise KLayoutBridgeError("the checked-in KLayout probe script is missing.")
    return path


def _default_runner(
    arguments: Sequence[str], working_directory: Path, timeout_s: float,
    output_limit_bytes: int = DEFAULT_KLAYOUT_LIMITS.max_process_output_bytes,
) -> subprocess.CompletedProcess[bytes]:
    """Run KLayout with a hard aggregate stdout/stderr memory bound."""

    process = subprocess.Popen(
        list(arguments), cwd=working_directory,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert process.stdout is not None and process.stderr is not None
    captured = [bytearray(), bytearray()]
    captured_total = [0]
    capture_lock = threading.Lock()
    overflow = threading.Event()

    def drain(stream: Any, destination: bytearray) -> None:
        try:
            while chunk := stream.read(64 * 1024):
                with capture_lock:
                    remaining = output_limit_bytes - captured_total[0]
                    if remaining > 0:
                        accepted = chunk[:remaining]
                        destination.extend(accepted)
                        captured_total[0] += len(accepted)
                    if len(chunk) > remaining:
                        overflow.set()
                if overflow.is_set():
                    try:
                        process.kill()
                    except OSError:
                        pass
                    break
        finally:
            stream.close()

    readers = [
        threading.Thread(target=drain, args=(process.stdout, captured[0]), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, captured[1]), daemon=True),
    ]
    for reader in readers:
        reader.start()
    try:
        return_code = process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        for reader in readers:
            reader.join(timeout=1.0)
        raise
    for reader in readers:
        reader.join(timeout=1.0)
    stdout = bytes(captured[0])
    stderr = bytes(captured[1])
    if overflow.is_set():
        # Preserve the Runner contract while making the downstream bounded
        # diagnostic check distinguish overflow from exact-limit output.
        stdout += b"\x00"
    return subprocess.CompletedProcess(list(arguments), return_code, stdout, stderr)


def _bounded_text(completed: subprocess.CompletedProcess[bytes], limit: int) -> str:
    stdout = completed.stdout or b""
    stderr = completed.stderr or b""
    if len(stdout) + len(stderr) > limit:
        raise KLayoutExecutionError("process_output_limit_exceeded")
    return (stdout + b"\n" + stderr).decode("utf-8", errors="replace")[-4096:]


def _bounded_name(value: object, field: str) -> str:
    if not isinstance(value, str) or len(value) > 1024 or "\x00" in value:
        raise KLayoutExecutionError("invalid_probe_report", f"{field} is invalid")
    return value


def _integer(value: object, field: str, maximum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise KLayoutExecutionError("invalid_probe_report", f"{field} must be a nonnegative integer")
    if maximum is not None and value > maximum:
        raise KLayoutExecutionError("probe_limit_exceeded", field)
    return value


def _validate_bbox(record: Mapping[str, object], dbu_um: float, field: str) -> None:
    integer_box = record.get("bbox_dbu")
    physical_box = record.get("bbox_um")
    if integer_box is None or physical_box is None:
        if integer_box is not None or physical_box is not None:
            raise KLayoutExecutionError("invalid_probe_report", f"{field} bbox units disagree")
        return
    if (
        not isinstance(integer_box, list) or len(integer_box) != 4
        or any(not isinstance(item, int) or isinstance(item, bool) for item in integer_box)
        or integer_box[0] > integer_box[2] or integer_box[1] > integer_box[3]
        or not isinstance(physical_box, list) or len(physical_box) != 4
    ):
        raise KLayoutExecutionError("invalid_probe_report", f"{field} bbox is invalid")
    for integer, physical in zip(integer_box, physical_box, strict=True):
        if (
            not isinstance(physical, (int, float)) or isinstance(physical, bool)
            or not math.isfinite(float(physical))
            or not math.isclose(float(physical), integer * dbu_um, rel_tol=1e-12, abs_tol=1e-15)
        ):
            raise KLayoutExecutionError("invalid_probe_report", f"{field} bbox unit conversion is invalid")


def _validate_report(
    value: object, limits: KLayoutInspectionLimits,
) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("contract") != LAYOUT_INSPECTION_CONTRACT:
        raise KLayoutExecutionError("invalid_probe_report", "contract mismatch")
    if value.get("status") == "failed":
        error = value.get("error")
        detail = error.get("detail", "") if isinstance(error, dict) else ""
        raise KLayoutExecutionError("klayout_probe_failed", str(detail))
    if value.get("status") != "inspected" or value.get("model_status") != "read_only_inspection":
        raise KLayoutExecutionError("invalid_probe_report", "status mismatch")

    units = value.get("units")
    if not isinstance(units, dict):
        raise KLayoutExecutionError("invalid_probe_report", "units are missing")
    dbu_um = units.get("dbu_um")
    if (
        not isinstance(dbu_um, (int, float)) or isinstance(dbu_um, bool)
        or not math.isfinite(float(dbu_um)) or float(dbu_um) <= 0.0
    ):
        raise KLayoutExecutionError("invalid_probe_report", "dbu_um is invalid")
    dbu_um = float(dbu_um)

    engine = value.get("engine")
    if not isinstance(engine, dict) or engine.get("id") != "klayout":
        raise KLayoutExecutionError("invalid_probe_report", "engine identity is invalid")
    _bounded_name(engine.get("version"), "engine.version")

    cells = value.get("cells")
    layers = value.get("layers")
    top_cells = value.get("top_cells")
    if not isinstance(cells, list) or not isinstance(layers, list) or not isinstance(top_cells, list):
        raise KLayoutExecutionError("invalid_probe_report", "layout collections are invalid")
    if len(cells) > limits.max_cells or len(layers) > limits.max_layers or len(top_cells) > len(cells):
        raise KLayoutExecutionError("probe_limit_exceeded", "layout collection count")
    if len(cells) * len(layers) > limits.max_cell_layer_pairs:
        raise KLayoutExecutionError("probe_limit_exceeded", "cell/layer matrix")

    cell_indices: set[int] = set()
    shape_total = 0
    edge_total = 0
    occurrence_total = 0
    for cell in cells:
        if not isinstance(cell, dict):
            raise KLayoutExecutionError("invalid_probe_report", "cell record is invalid")
        index = _integer(cell.get("index"), "cell.index")
        if index in cell_indices:
            raise KLayoutExecutionError("invalid_probe_report", "duplicate cell index")
        cell_indices.add(index)
        _bounded_name(cell.get("name"), "cell.name")
        if not isinstance(cell.get("is_top"), bool):
            raise KLayoutExecutionError("invalid_probe_report", "cell.is_top is invalid")
        count = _integer(cell.get("direct_shape_count"), "cell.direct_shape_count", limits.max_shapes)
        shape_total += count
        direct_shapes = cell.get("direct_shapes")
        children = cell.get("children")
        if not isinstance(direct_shapes, list) or not isinstance(children, list):
            raise KLayoutExecutionError("invalid_probe_report", "cell members are invalid")
        if sum(_integer(item.get("count"), "direct shape count", limits.max_shapes)
               for item in direct_shapes if isinstance(item, dict)) != count:
            raise KLayoutExecutionError("invalid_probe_report", "cell shape count mismatch")
        if any(not isinstance(item, dict) for item in direct_shapes):
            raise KLayoutExecutionError("invalid_probe_report", "direct shape record is invalid")
        edge_total += len(children)
        for child in children:
            if not isinstance(child, dict):
                raise KLayoutExecutionError("invalid_probe_report", "child record is invalid")
            _bounded_name(child.get("child_name"), "child.name")
            occurrence_total += _integer(
                child.get("occurrence_count"), "child.occurrence_count", limits.max_instances,
            )
            _validate_bbox(child, dbu_um, "child")
        _validate_bbox(cell, dbu_um, "cell")
    if shape_total > limits.max_shapes or edge_total > limits.max_instances or occurrence_total > limits.max_instances:
        raise KLayoutExecutionError("probe_limit_exceeded", "layout content count")

    layer_shape_total = 0
    for layer in layers:
        if not isinstance(layer, dict):
            raise KLayoutExecutionError("invalid_probe_report", "layer record is invalid")
        _integer(layer.get("index"), "layer.index")
        _integer(layer.get("layer"), "layer.number")
        _integer(layer.get("datatype"), "layer.datatype")
        _bounded_name(layer.get("name"), "layer.name")
        layer_shape_total += _integer(
            layer.get("defined_shape_count"), "layer.defined_shape_count", limits.max_shapes,
        )
        _validate_bbox(layer, dbu_um, "layer")
    if layer_shape_total != shape_total:
        raise KLayoutExecutionError("invalid_probe_report", "layer and cell shape totals disagree")
    for top in top_cells:
        if not isinstance(top, dict) or top.get("index") not in cell_indices:
            raise KLayoutExecutionError("invalid_probe_report", "top cell record is invalid")
        _bounded_name(top.get("name"), "top cell name")
        _validate_bbox(top, dbu_um, "top cell")

    summary = value.get("summary")
    expected_summary = {
        "cell_count": len(cells),
        "top_cell_count": len(top_cells),
        "layer_count": len(layers),
        "defined_shape_count": shape_total,
        "hierarchy_edge_count": edge_total,
        "hierarchy_occurrence_count": occurrence_total,
    }
    if not isinstance(summary, dict) or any(summary.get(key) != item for key, item in expected_summary.items()):
        raise KLayoutExecutionError("invalid_probe_report", "summary count mismatch")

    capabilities = value.get("capabilities")
    if not isinstance(capabilities, dict) or capabilities != {
        "layout_inspection": True, "layout_modification": False,
        "drc": False, "lvs": False, "pex": False,
    }:
        raise KLayoutExecutionError("invalid_probe_report", "capability claim mismatch")
    return value


def inspect_layout(
    executable: str | Path,
    layout_path: str | Path,
    *,
    timeout_s: float = 30.0,
    limits: KLayoutInspectionLimits = DEFAULT_KLAYOUT_LIMITS,
    runner: Runner | None = None,
) -> dict[str, Any]:
    """Inspect one layout with an explicitly selected KLayout executable.

    The original layout is opened read-only and all generated data is staged in
    a temporary directory.  KLayout is a separate child process but is not a
    security sandbox for hostile layout files.
    """

    executable_path = _checked_file(executable, "KLayout executable")
    source_path = _checked_file(layout_path, "layout_path")
    if not isinstance(limits, KLayoutInspectionLimits):
        raise KLayoutBridgeError("limits must be KLayoutInspectionLimits.")
    if source_path.suffix.lower() not in _SUPPORTED_LAYOUT_SUFFIXES:
        raise KLayoutBridgeError("layout_path has an unsupported layout suffix.")
    if source_path.stat().st_size > limits.max_input_bytes:
        raise KLayoutBridgeError("layout_path exceeds the input size limit.")
    timeout = float(timeout_s)
    if not math.isfinite(timeout) or not 0.0 < timeout <= 300.0:
        raise KLayoutBridgeError("timeout_s must be positive and at most 300 seconds.")
    script_path = _probe_script()
    executable_sha256 = _sha256_file(executable_path)
    layout_sha256 = _sha256_file(source_path)
    script_sha256 = _sha256_file(script_path)
    selected_runner = runner or (
        lambda arguments, working_directory, timeout: _default_runner(
            arguments, working_directory, timeout, limits.max_process_output_bytes,
        )
    )

    with tempfile.TemporaryDirectory(prefix="spikes-klayout-") as directory:
        staging = Path(directory)
        report_path = staging / "layout-report.json"
        arguments = [
            str(executable_path), "-b", "-r", str(script_path),
            "-rd", f"input_layout={source_path}",
            "-rd", f"report_path={report_path}",
            "-rd", f"max_cells={limits.max_cells}",
            "-rd", f"max_layers={limits.max_layers}",
            "-rd", f"max_instances={limits.max_instances}",
            "-rd", f"max_shapes={limits.max_shapes}",
            "-rd", f"max_cell_layer_pairs={limits.max_cell_layer_pairs}",
        ]
        try:
            completed = selected_runner(arguments, staging, timeout)
        except subprocess.TimeoutExpired as exc:
            raise KLayoutExecutionError("klayout_timeout", f"timeout_s={timeout:g}") from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise KLayoutExecutionError("klayout_process_failed", type(exc).__name__) from exc
        diagnostic = _bounded_text(completed, limits.max_process_output_bytes)
        if not report_path.is_file():
            raise KLayoutExecutionError(
                "klayout_report_missing",
                f"return_code={completed.returncode}\n{diagnostic}",
            )
        size = report_path.stat().st_size
        if size <= 0 or size > limits.max_report_bytes:
            raise KLayoutExecutionError("klayout_report_size_invalid", f"bytes={size}")
        try:
            raw_report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise KLayoutExecutionError("invalid_probe_report", "report is not UTF-8 JSON") from exc
        if completed.returncode != 0 and not (
            isinstance(raw_report, dict) and raw_report.get("status") == "failed"
        ):
            raise KLayoutExecutionError(
                "klayout_process_failed",
                f"return_code={completed.returncode}\n{diagnostic}",
            )
        report = _validate_report(raw_report, limits)

    if _sha256_file(source_path) != layout_sha256:
        raise KLayoutExecutionError("layout_changed_during_inspection")
    if _sha256_file(executable_path) != executable_sha256:
        raise KLayoutExecutionError("executable_changed_during_inspection")
    if _sha256_file(script_path) != script_sha256:
        raise KLayoutExecutionError("probe_script_changed_during_inspection")
    result = dict(report)
    result["provenance"] = {
        "executable_path": str(executable_path),
        "executable_sha256": executable_sha256,
        "layout_path": str(source_path),
        "layout_sha256": layout_sha256,
        "probe_script_path": str(script_path),
        "probe_script_sha256": script_sha256,
    }
    return result


__all__ = [
    "DEFAULT_KLAYOUT_LIMITS",
    "KLayoutBridgeError",
    "KLayoutExecutionError",
    "KLayoutInspectionLimits",
    "LAYOUT_INSPECTION_CONTRACT",
    "inspect_layout",
]
