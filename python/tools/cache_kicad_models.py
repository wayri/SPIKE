"""Build an offline, allowlisted VRML cache for a KiCad board.

The cache is a generated runtime dependency. It is not a replacement for the
source model library and must retain the source library's license notice.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


MODEL_PATTERN = re.compile(r'\(model\s+"([^"]+)"')
VARIABLE_PATTERN = re.compile(r"^\$\{([^}]+)\}(?:[/\\](.*))?$")
KICAD_MODEL_LICENSE = "CC-BY-SA-4.0 with KiCad library exception"


def installed_model_roots() -> dict[str, Path]:
    roots: dict[str, Path] = {}
    program_files = Path(r"C:\Program Files\KiCad")
    for version in ("10.99", "10.0", "9.0", "8.0"):
        root = program_files / version / "share" / "kicad" / "3dmodels"
        if root.is_dir():
            major = version.split(".")[0]
            roots[f"KICAD{major}_3DMODEL_DIR"] = root
    return roots


def resolve_reference(reference: str, board_dir: Path, roots: dict[str, Path]) -> tuple[Path | None, str]:
    match = VARIABLE_PATTERN.match(reference)
    base_candidates: list[Path]
    if match:
        variable, remainder = match.groups()
        if variable == "KIPRJMOD":
            base_candidates = [board_dir]
            source_kind = "project"
        elif variable.endswith("_3DMODEL_DIR"):
            preferred = roots.get(variable)
            base_candidates = ([preferred] if preferred else []) + [root for root in roots.values() if root != preferred]
            source_kind = "kicad-library"
        else:
            return None, "unsupported-variable"
        if not base_candidates:
            return None, source_kind
        candidates = [base / Path(remainder or "") for base in base_candidates]
    else:
        candidate = Path(reference)
        if not candidate.is_absolute():
            candidate = board_dir / candidate
        candidates = [candidate]
        source_kind = "project"

    expanded: list[Path] = []
    for candidate in candidates:
        expanded.append(candidate)
        if candidate.suffix.lower() in {".step", ".stp"}:
            expanded.extend([candidate.with_suffix(".wrl"), candidate.with_suffix(".WRL")])
    for path in expanded:
        if path.is_file() and path.suffix.lower() == ".wrl":
            return path.resolve(), source_kind
    return None, source_kind


def cache_models(board: Path, output: Path, url_prefix: str) -> dict[str, object]:
    source = board.read_text(encoding="utf-8")
    references = sorted(set(MODEL_PATTERN.findall(source)))
    roots = installed_model_roots()
    output.mkdir(parents=True, exist_ok=True)
    models: dict[str, dict[str, object]] = {}
    unresolved: list[dict[str, str]] = []

    for reference in references:
        resolved, source_kind = resolve_reference(reference, board.parent, roots)
        if resolved is None:
            unresolved.append({"reference": reference, "reason": source_kind})
            continue
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        target_name = f"{digest[:20]}.wrl"
        target = output / target_name
        if not target.exists():
            shutil.copy2(resolved, target)
        models[reference] = {
            "url": f"{url_prefix.rstrip('/')}/{target_name}",
            "sha256": digest,
            "format": "vrml",
            "source_kind": source_kind,
            "license": KICAD_MODEL_LICENSE if source_kind == "kicad-library" else "project-supplied",
        }

    manifest = {
        "contract": "spike/model-cache/v1",
        "offline": True,
        "board": board.name,
        "models": models,
        "unresolved": unresolved,
        "notice": (
            "KiCad library models retain their CC-BY-SA-4.0 license and KiCad library exception. "
            "See https://gitlab.com/kicad/libraries/kicad-packages3D/-/blob/master/LICENSE.md"
        ),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("board", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--url-prefix", default="/demo/models")
    args = parser.parse_args()
    manifest = cache_models(args.board.resolve(), args.output.resolve(), args.url_prefix)
    print(json.dumps({
        "resolved": len(manifest["models"]),
        "unresolved": len(manifest["unresolved"]),
        "manifest": str((args.output / "manifest.json").resolve()),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
