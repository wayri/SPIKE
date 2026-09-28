#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Report whether a Python environment has source-qualification prerequisites.

This is an inventory check only.  A passing result does not qualify numerical
results or promote any solver capability.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import platform
import sys
import warnings
from pathlib import Path
from typing import Any, Callable


DEPENDENCIES = ("numpy", "scipy", "jsonschema", "pyarrow", "nanobind")
NATIVE_MODULE = "python.spike_peec_native"
REQUIRED_NATIVE_APIS = (
    "canonicalize_planar_region",
    "canonicalize_simple_planar_ring",
    "exact_quantized_planar_incircle",
    "PlanarPoint2",
    "QuantizedPlanarPoint2",
    "VolumeMatrixAssembler",
    "VolumeMatrixIntegrationOptions",
    "VolumeRectangularBasis",
    "VolumeCoaxialAnnulusBasis",
)
ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _version(module: Any) -> str | None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        value = getattr(module, "__version__", None)
    return str(value) if value is not None else None


def collect_preflight(import_module: Callable[[str], Any] = importlib.import_module) -> dict[str, Any]:
    """Collect only import and ABI-surface evidence; never alter the environment."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    dependencies: dict[str, dict[str, str | None]] = {}
    passed = True
    for name in DEPENDENCIES:
        try:
            dependencies[name] = {"version": _version(import_module(name)), "error": None}
        except Exception as error:  # Import failures are qualification evidence.
            dependencies[name] = {"version": None, "error": f"{type(error).__name__}: {error}"}
            passed = False

    native: dict[str, Any] = {
        "loaded_file": None,
        "sha256": None,
        "error": None,
        "apis": {name: False for name in REQUIRED_NATIVE_APIS},
    }
    try:
        module = import_module(NATIVE_MODULE)
        native["apis"] = {name: hasattr(module, name) for name in REQUIRED_NATIVE_APIS}
        loaded_file = getattr(module, "__file__", None)
        if not loaded_file:
            raise RuntimeError("native module has no loaded file")
        path = Path(loaded_file).resolve(strict=True)
        native["loaded_file"] = str(path)
        native["sha256"] = sha256(path)
        passed = passed and all(native["apis"].values())
    except Exception as error:  # A missing extension or unreadable artifact is a failure.
        native["error"] = f"{type(error).__name__}: {error}"
        passed = False

    return {
        "kind": "spike/solver-source-qualification-preflight/v1",
        "status": "passed" if passed else "failed",
        "scope": "environment and native API inventory only; not numerical qualification",
        "interpreter": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "dependencies": dependencies,
        "native": native,
    }


def main() -> int:
    report = collect_preflight()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
