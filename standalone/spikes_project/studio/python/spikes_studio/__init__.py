"""SPIKES Studio document, library, and workbench contracts."""

from __future__ import annotations

from typing import Any

__all__ = [
    "AI_DRAFT_CONTRACT",
    "DatasheetEvidence",
    "LocalAIError",
    "LocalModelAssistant",
    "MODEL_IMPORT_CONTRACT",
    "STUDIO_PART_CONTRACT",
    "ModelImportError",
    "convert_model_statement",
    "parse_model_statement",
]


def __getattr__(name: str) -> Any:
    if name in {"AI_DRAFT_CONTRACT", "DatasheetEvidence", "LocalAIError", "LocalModelAssistant"}:
        from . import local_ai
        return getattr(local_ai, name)
    if name in __all__:
        from . import model_import
        return getattr(model_import, name)
    raise AttributeError(name)
