"""Shared helper functions for the JSON-line worker service."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

from .errors import error_envelope
from .external_engines import external_engine_catalog
from .models import export_kicad_visual_bundle, export_kicad_visual_bundle_path_payload, export_kicad_visual_bundle_payload


def build_solver_catalog(registry: Any, *, refresh_external: bool = False) -> list[Dict[str, Any]]:
    """Return one truthful catalog for built-in and relevant external solvers."""
    catalog = registry.catalog()
    discovery_error = ""
    try:
        external = {
            item["id"]: item
            for item in external_engine_catalog(refresh=refresh_external).get("engines", [])
        }
    except (OSError, RuntimeError, ValueError) as exc:
        external = {}
        discovery_error = f"External engine detection failed: {exc}"
    external_tiers = {
        "external.sparselizard": {
            "analyses": ["dc", "ac", "broadband_hf", "thermal", "emi_emc"],
            "formulations": ["fem_3d"],
        },
        "external.elmer": {
            "analyses": ["dc", "ac", "broadband_hf", "thermal", "emi_emc"],
            "formulations": ["fem_3d"],
        },
        "external.fasthenry": {
            "analyses": ["ac", "broadband_hf"],
            "formulations": ["volume_rl_extraction"],
        },
    }
    for engine_id, tier in external_tiers.items():
        engine = external.get(engine_id, {
            "id": engine_id,
            "name": {
                "external.sparselizard": "sparseLizard FEM 3D",
                "external.elmer": "Elmer FEM 3D",
                "external.fasthenry": "FastHenry 3D R/L",
            }[engine_id],
            "state": "detection_unavailable",
            "model_status": "unsupported",
            "reason": discovery_error or "External engine detection returned no descriptor.",
        })
        catalog.append({
            "id": engine_id,
            "name": engine.get("name", engine_id),
            "version": engine.get("version", ""),
            "provider": "External engine",
            "analyses": tier["analyses"],
            "formulations": tier["formulations"],
            "capabilities": engine.get("capabilities", []),
            "candidate_capabilities": engine.get("candidate_capabilities", []),
            "state": engine.get("state", "unavailable"),
            "model_status": engine.get("model_status", "unsupported"),
            "validation": engine.get("validation", ""),
            "reason": engine.get("reason", "External solver adapter is unavailable."),
            "execution": "external_process",
            "runnable": False,
        })
    return catalog


def operation_id(value: Any) -> str | None:
    token = str(value or "").strip()
    return token if token and len(token) <= 128 and all(character.isalnum() or character in "._:-" for character in token) else None


def prepare_visual_bundle(params: Dict[str, Any]) -> Dict[str, Any]:
    options = {key: params[key] for key in ("stage", "lightweight_board", "model_overrides") if key in params}
    if params.get("board_path"):
        return export_kicad_visual_bundle_path_payload(
            str(params.get("board_path", "")),
            int(params.get("timeout_seconds", 180)),
            int(params.get("max_artifact_bytes", 96 * 1024 * 1024)),
            **options,
        )
    if params.get("source_board") is not None:
        return export_kicad_visual_bundle_payload(
            str(params.get("source_board", "")),
            str(params.get("source_file", "imported.kicad_pcb")),
            int(params.get("timeout_seconds", 180)),
            int(params.get("max_artifact_bytes", 96 * 1024 * 1024)),
            **options,
        )
    return export_kicad_visual_bundle(
        params.get("board_path", ""),
        params.get("output_directory", ""),
        int(params.get("timeout_seconds", 180)),
    )


def error_response(
    code: str,
    message: str,
    *,
    operation_id: str | None = None,
    detail: str | None = None,
    context: Dict[str, Any] | None = None,
    error_type: str = "SpikeError",
) -> Dict[str, Any]:
    envelope = error_envelope(
        code,
        message=message,
        detail=detail,
        context=context,
        operation_id=operation_id,
    )
    return {
        "ok": False,
        "error": envelope["message"],
        "type": error_type,
        "error_code": envelope["code"],
        "error_detail": envelope,
    }


def find_kicad_cli() -> str:
    executable = shutil.which("kicad-cli") or shutil.which("kicad-cli.exe")
    if executable:
        return executable
    if sys.platform == "win32":
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        for version in ("10.0", "9.0", "8.0"):
            candidate = program_files / "KiCad" / version / "bin" / "kicad-cli.exe"
            if candidate.is_file():
                return str(candidate)
    return ""


def export_step(source_board: str, source_file: str, options: Dict[str, Any]) -> Dict[str, Any]:
    executable = find_kicad_cli()
    if not executable:
        raise RuntimeError("KiCad CLI is not installed or discoverable; STEP export is unavailable.")
    if not source_board.strip():
        raise ValueError("The SPIKE project does not contain an embedded KiCad board.")
    timeout = max(10, min(int(options.get("timeout_seconds", 300)), 1800))
    with tempfile.TemporaryDirectory(prefix="spike-step-") as directory:
        root = Path(directory)
        board_name = Path(source_file or "board.kicad_pcb").name
        if not board_name.lower().endswith(".kicad_pcb"):
            board_name = "board.kicad_pcb"
        board_path = root / board_name
        output_path = root / "board.step"
        board_path.write_text(source_board, encoding="utf-8")
        arguments = [
            executable, "pcb", "export", "step", "--force", "--subst-models",
            "--include-tracks", "--include-pads", "--include-zones", "--include-inner-copper",
            "--include-silkscreen", "--include-soldermask", "--output", str(output_path), str(board_path),
        ]
        if bool(options.get("board_only", False)):
            arguments.insert(-2, "--board-only")
        process = subprocess.run(
            arguments,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        diagnostics = (process.stdout + "\n" + process.stderr).strip()
        if process.returncode != 0 or not output_path.is_file():
            raise RuntimeError(f"KiCad STEP export failed: {diagnostics[-4000:]}")
        if output_path.stat().st_size > 256 * 1024 * 1024:
            raise RuntimeError("The generated STEP file exceeds the 256 MiB desktop transfer limit.")
        return {
            "contract": "spike/cad-export/v1",
            "format": "step",
            "file_name": f"{Path(source_file or 'board').stem}.step",
            "content": output_path.read_text(encoding="utf-8", errors="replace"),
            "bytes": output_path.stat().st_size,
            "status": "completed",
            "diagnostics": diagnostics.splitlines()[-40:],
            "provenance": {
                "exporter": "kicad-cli pcb export step",
                "components": not bool(options.get("board_only", False)),
                "copper_geometry": True,
            },
            "warnings": [
                "Project-relative 3D models resolve only when their files are available through KiCad library variables."
            ],
        }
