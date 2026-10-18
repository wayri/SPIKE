# SPDX-License-Identifier: Apache-2.0
"""Package member classification, separate from archive trust and persistence."""
from pathlib import Path


def media_type(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".json": "application/json",
        ".jsonl": "application/x-ndjson",
        ".arrow": "application/vnd.apache.arrow.file",
        ".html": "text/html",
        ".pdf": "application/pdf",
        ".csv": "text/csv",
        ".step": "model/step",
        ".stp": "model/step",
        ".gltf": "model/gltf+json",
        ".glb": "model/gltf-binary",
        ".spkshape": "application/vnd.spike.package-shape",
    }.get(suffix, "application/octet-stream")


def member_role(path: str) -> str:
    return path.split("/", 1)[0]
