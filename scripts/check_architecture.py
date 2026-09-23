#!/usr/bin/env python3
"""Fail fast when source dependencies bypass SPIKE's architectural boundaries."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = ROOT / "app" / "src"
WORKER_SOURCE = ROOT / "python" / "spike_core"
CORE_SOURCE = ROOT / "python" / "core"

PRODUCT_SOURCE_ROOTS = (
    ROOT / "app" / "src",
    ROOT / "app" / "src-tauri" / "src",
    ROOT / "python",
    ROOT / "src",
    ROOT / "solver_sdk",
    ROOT / "extension_sdk",
    ROOT / "kicad_plugin",
    ROOT / "integrations",
    ROOT / "wx_desktop",
)

# A new implementation language requires an ADR and an explicit guard update.
PROHIBITED_IMPLEMENTATION_SUFFIXES = {
    ".cs",
    ".dart",
    ".ex",
    ".exs",
    ".fs",
    ".fsx",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".lua",
    ".php",
    ".rb",
    ".scala",
    ".swift",
}

FROZEN_PYTHON_UI_IMPORTS = (
    "python.gui",
    "python.ui",
    "python.viz",
)

REQUIRED_DOCUMENTS = (
    "ARCHITECTURE.md",
    "CONTRIBUTING.md",
    "docs/CONTRACTS.md",
    "docs/DEVELOPER_GUIDE.md",
    "docs/DESIGN_PRINCIPLES.md",
    "docs/IMPORTER_ARCHITECTURE.md",
    "docs/LANGUAGE_POLICY.md",
    "docs/STABILITY_AND_RECOVERY.md",
    "docs/SUBSYSTEM_INDEX.md",
    "docs/EMI_WORKFLOW.md",
    "docs/adr/0001-normalized-design-ir.md",
    "docs/adr/0002-worker-process-isolation.md",
    "docs/adr/0003-importer-registry.md",
    "docs/adr/0007-language-budget-and-runtime-boundaries.md",
    "docs/adr/0008-parallel-native-wxwidgets-client.md",
    "docs/adr/0018-portable-results-and-board-visuals.md",
    "docs/adr/0019-freecad-collaboration-sessions.md",
)

CONTRACT_SCHEMAS = (
    "schemas/design-ir-v1.schema.json",
    "schemas/analysis-spec-v1.schema.json",
    "schemas/analysis-result-v1.schema.json",
    "schemas/emi-setup-v1.schema.json",
    "schemas/mcad-session-v1.schema.json",
    "schemas/mcad-feedback-v1.schema.json",
)

# These are known composition roots. They are tracked debt, not size examples.
LEGACY_LARGE_MODULES = {
    "app/src/App.tsx",
    "app/src/BoardViewport.tsx",
    "app/src/LayoutViewport.tsx",
    "python/spike_core/cli.py",
    "python/spike_core/hybrid_mesh.py",
    "python/spike_core/transient_peec.py",
}
MAX_NEW_MODULE_LINES = 800


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def source_files(root: Path, suffixes: set[str]) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix in suffixes)


def main() -> int:
    errors: list[str] = []
    typescript = source_files(APP_SOURCE, {".ts", ".tsx"})
    python = source_files(WORKER_SOURCE, {".py"})
    supported_python = [*python, *source_files(CORE_SOURCE, {".py"})]

    for root in PRODUCT_SOURCE_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in PROHIBITED_IMPLEMENTATION_SUFFIXES:
                errors.append(
                    f"{relative(path)}: implementation language is outside the accepted language budget"
                )

    ipc_boundaries = {
        "app/src/workerBridge.ts",
        "app/src/resourceMonitor.ts",
        "app/src/licenseBridge.ts",
        "app/src/detachedToolWindows.tsx",
    }
    for path in typescript:
        name = relative(path)
        text = path.read_text(encoding="utf-8")
        if "@tauri-apps/api" in text and name not in ipc_boundaries:
            errors.append(f"{name}: native IPC must be wrapped by a desktop bridge module")
        if "parseKicadBoard" in text and name not in {
            "app/src/boardParser.ts",
            "app/src/designSourceRegistry.ts",
        }:
            errors.append(f"{name}: EDA-specific parsing must go through designSourceRegistry")
        if re.search(r"Math\.(?:min|max)\s*\(\s*\.\.\.", text):
            errors.append(f"{name}: spread extrema can overflow on large result arrays; use numericRange")

    for path in python:
        name = relative(path)
        text = path.read_text(encoding="utf-8")
        if re.search(r"(?:from|import)\s+python\.core\..*parser", text) and name != "python/spike_core/kicad_importer.py":
            errors.append(f"{name}: source parser imports belong in a registered importer adapter")

    for path in supported_python:
        name = relative(path)
        text = path.read_text(encoding="utf-8")
        for legacy_import in FROZEN_PYTHON_UI_IMPORTS:
            if re.search(rf"(?:from|import)\s+{re.escape(legacy_import)}(?:\.|\s|$)", text):
                errors.append(
                    f"{name}: supported services must not depend on frozen legacy module {legacy_import}"
                )

    for path in [*typescript, *python]:
        name = relative(path)
        if name in LEGACY_LARGE_MODULES:
            continue
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > MAX_NEW_MODULE_LINES:
            errors.append(
                f"{name}: {line_count} lines exceeds the {MAX_NEW_MODULE_LINES}-line module guard; split responsibilities"
            )

    for document in REQUIRED_DOCUMENTS:
        if not (ROOT / document).is_file():
            errors.append(f"{document}: required architecture document is missing")

    for schema in CONTRACT_SCHEMAS:
        path = ROOT / schema
        if not path.is_file():
            errors.append(f"{schema}: required contract schema is missing")
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            errors.append(f"{schema}: invalid JSON schema document: {error}")

    tauri_config_path = ROOT / "app" / "src-tauri" / "tauri.conf.json"
    try:
        tauri_config = json.loads(tauri_config_path.read_text(encoding="utf-8"))
        resources = tauri_config["bundle"]["resources"]
        for required_resource in ("../../python/core", "../../python/spike_core", "../../extensions"):
            if required_resource not in resources:
                errors.append(
                    f"app/src-tauri/tauri.conf.json: packaged worker is missing {required_resource}"
                )
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        errors.append(f"app/src-tauri/tauri.conf.json: invalid bundle configuration: {error}")

    if errors:
        print("SPIKE architecture check failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(
        "SPIKE architecture check passed: importer, IPC, numeric, module-size, "
        "language-budget, legacy-UI, and documentation boundaries are intact."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
