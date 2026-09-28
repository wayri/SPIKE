# SPDX-License-Identifier: Apache-2.0
"""Worker request handlers for locally managed extension packages."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Callable

from .extensions import ExtensionPackageManager, ExtensionRegistry


def _catalog_collision(preview: dict[str, Any], registry: ExtensionRegistry, packages: ExtensionPackageManager) -> bool:
    expected = (packages.install_root / preview["manifest"]["id"]).resolve()
    return any(
        entry["id"] == preview["manifest"]["id"] and Path(entry["path"]).resolve() != expected
        for entry in registry.catalog()
    )


def handle_extension_package_request(
    method: str,
    params: dict[str, Any],
    registry: ExtensionRegistry,
    packages: ExtensionPackageManager,
    refresh: Callable[..., None],
) -> dict[str, Any] | None:
    if method not in {"list_extensions", "browse_extensions", "inspect_extension_package", "install_extension", "remove_extension"}:
        return None
    try:
        if method == "list_extensions":
            browser = packages.browse(registry)
            return {"ok": True, "result": {
                "contract": "spike/extension-catalog/v1",
                "extensions": browser["extensions"],
                "diagnostics": registry.diagnostics(),
            }}
        if method == "browse_extensions":
            path = params.get("path") or params.get("package_path")
            browser = packages.browse(registry, path)
            if "candidate" in browser and _catalog_collision(browser["candidate"], registry, packages):
                browser["candidate"]["can_install"] = False
            return {"ok": True, "result": browser}
        if method == "inspect_extension_package":
            path = params.get("path") or params.get("package_path")
            if not isinstance(path, str) or not path.strip():
                raise ValueError("A local extension package path is required.")
            preview = packages.preview(path)
            if _catalog_collision(preview, registry, packages):
                preview["can_install"] = False
            return {"ok": True, "result": preview}
        if method == "install_extension":
            path = params.get("path") or params.get("package_path")
            if not isinstance(path, str) or not path.strip():
                raise ValueError("A local extension package path is required.")
            if _catalog_collision(packages.preview(path), registry, packages):
                raise FileExistsError("An extension with this ID is already loaded from another location.")
            result = packages.install(path, replace=bool(params.get("replace", False)))
            refresh(revoke_trust={result["extension_id"]})
            installed = next(
                (entry for entry in packages.browse(registry)["extensions"] if entry["id"] == result["extension_id"]),
                None,
            )
            return {"ok": True, "result": {**result, "extension": installed}}
        result = packages.remove(str(params.get("extension_id", "")))
        refresh()
        return {"ok": True, "result": result}
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        return {"ok": False, "error": str(exc), "type": type(exc).__name__}
