"""General-purpose SPIKE extension discovery and isolated command execution."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .si_protocol_suites import canonical_si_protocol_suite


EXTENSION_CONTRACT = "spike/extension/v1"
EXTENSION_RESULT_CONTRACT = "spike/extension-result/v1"
EXTENSION_API_VERSION = 1
EXTENSION_POINTS = {
    "applications",
    "commands",
    "analyses",
    "importers",
    "exporters",
    "reports",
    "panels",
    "validators",
    "protocol_suites",
    "schemas",
    "harness_engines",
}
EXTENSION_PERMISSIONS = {
    "design.read",
    "project.read",
    "selection.read",
    "results.read",
    "results.write",
    "project.write",
    "harness.read",
    "filesystem.workspace",
    "network",
}
CONTEXT_PERMISSIONS = {
    "design": "design.read",
    "project": "project.read",
    "selection": "selection.read",
    "results": "results.read",
    "source": "filesystem.workspace",
    "harness": "harness.read",
}
MAX_EXTENSION_RESULT_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class ExtensionManifest:
    id: str
    name: str
    version: str
    provider: str
    description: str
    contributes: Dict[str, List[Dict[str, Any]]]
    permissions: List[str] = field(default_factory=list)
    contract: str = EXTENSION_CONTRACT
    api_version: int = EXTENSION_API_VERSION
    execution: str = "process"
    runtime: str = "native"
    entrypoint: str = ""
    state: str = "available"
    license: str = "proprietary"
    bundled: bool = False
    limits: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "ExtensionManifest":
        allowed = {item.name for item in cls.__dataclass_fields__.values()}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"Unknown extension manifest fields: {', '.join(sorted(unknown))}")
        manifest = cls(**{key: value[key] for key in value if key in allowed})
        manifest.validate()
        return manifest

    def validate(self) -> None:
        if self.contract != EXTENSION_CONTRACT or self.api_version != EXTENSION_API_VERSION:
            raise ValueError("Unsupported extension contract or API version.")
        if not self.id or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for character in self.id):
            raise ValueError("Extension IDs must use lowercase ASCII letters, numbers, dot, underscore, or dash.")
        if self.execution != "process" or self.runtime not in {"native", "python"}:
            raise ValueError("Extensions must use a native or Python isolated process.")
        if self.state not in {"available", "experimental", "disabled"}:
            raise ValueError("Extension state is not supported.")
        if not self.entrypoint:
            raise ValueError("Process extensions must declare an entrypoint.")
        if not isinstance(self.contributes, dict) or not self.contributes:
            raise ValueError("Extensions must declare at least one contribution.")
        unknown_points = set(self.contributes) - EXTENSION_POINTS
        if unknown_points:
            raise ValueError(f"Unknown extension points: {', '.join(sorted(unknown_points))}")
        unknown_permissions = set(self.permissions) - EXTENSION_PERMISSIONS
        if unknown_permissions:
            raise ValueError(f"Unknown extension permissions: {', '.join(sorted(unknown_permissions))}")
        contribution_ids: set[str] = set()
        for point, entries in self.contributes.items():
            if not isinstance(entries, list) or not entries:
                raise ValueError(f"Extension point {point} must contain at least one contribution.")
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
                    raise ValueError(f"Every {point} contribution requires an ID.")
                if entry["id"] in contribution_ids:
                    raise ValueError(f"Duplicate extension contribution ID: {entry['id']}")
                contribution_ids.add(entry["id"])
                if not isinstance(entry.get("name"), str) or not entry["name"]:
                    raise ValueError(f"Extension contribution {entry['id']} requires a name.")
                if point == "protocol_suites":
                    definition = entry.get("definition")
                    if not isinstance(definition, dict):
                        raise ValueError(f"Protocol-suite contribution {entry['id']} requires a definition.")
                    canonical = canonical_si_protocol_suite(definition)
                    if canonical["id"] != entry["id"]:
                        raise ValueError(f"Protocol-suite contribution {entry['id']} must match definition.id.")
                if point == "importers" and entry.get("output_contract") == "spike/v1":
                    for key in ("source_formats", "extensions"):
                        if not isinstance(entry.get(key), list) or not entry[key] or any(not isinstance(v, str) or not v for v in entry[key]):
                            raise ValueError(f"Design importer {entry['id']} requires {key}.")
                    if any(not suffix.startswith(".") for suffix in entry["extensions"]):
                        raise ValueError("Importer extensions must start with a dot.")
                    if not isinstance(entry.get("accepts_directories", False), bool):
                        raise ValueError("accepts_directories must be boolean.")
                    if "filesystem.workspace" not in self.permissions:
                        raise ValueError("Design importer requires filesystem.workspace permission.")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProcessExtension:
    def __init__(self, manifest: ExtensionManifest, directory: Path, trusted: bool) -> None:
        manifest.validate()
        root = directory.resolve()
        entrypoint = (root / manifest.entrypoint).resolve()
        if not entrypoint.is_relative_to(root) or not entrypoint.is_file():
            raise ValueError("Extension entrypoint must be a file inside its extension directory.")
        self.manifest = manifest
        self.directory = root
        self.entrypoint = entrypoint
        self.trusted = trusted

    def catalog_entry(self) -> Dict[str, Any]:
        return {
            **self.manifest.to_dict(),
            "trusted": self.trusted,
            "path": str(self.directory),
            "execution_boundary": "isolated_process",
        }

    def invoke(self, contribution_id: str, context: Dict[str, Any], *, timeout_seconds: int | None = None) -> Dict[str, Any]:
        declared = {
            contribution["id"]
            for entries in self.manifest.contributes.values()
            for contribution in entries
        }
        if contribution_id not in declared:
            raise ValueError(f"Extension contribution is not declared: {contribution_id}")
        if self.manifest.state == "disabled":
            raise PermissionError("Disabled extensions cannot execute.")
        if not self.trusted:
            raise PermissionError("Extension execution requires explicit trust.")
        filtered_context: Dict[str, Any] = {}
        for key, value in context.items():
            required = CONTEXT_PERMISSIONS.get(key)
            if required and required not in self.manifest.permissions:
                raise PermissionError(f"Extension lacks permission {required} for context field {key}.")
            if key in CONTEXT_PERMISSIONS or key == "parameters":
                filtered_context[key] = value
        timeout_seconds = max(1, min(int(self.manifest.limits.get("timeout_seconds", 300)), timeout_seconds or 3600, 3600))
        max_result_bytes = max(1024, min(int(self.manifest.limits.get("max_result_bytes", MAX_EXTENSION_RESULT_BYTES)), 1024 * 1024 * 1024))
        with tempfile.TemporaryDirectory(prefix="spike-extension-") as directory:
            job = Path(directory)
            request_path = job / "request.json"
            result_path = job / "result.json"
            diagnostic_path = job / "extension.log"
            request_path.write_text(json.dumps({
                "contract": EXTENSION_CONTRACT,
                "api_version": EXTENSION_API_VERSION,
                "request_id": str(uuid.uuid4()),
                "extension": self.manifest.to_dict(),
                "contribution_id": contribution_id,
                "context": filtered_context,
            }, default=str), encoding="utf-8")
            command = [str(self.entrypoint)]
            if self.manifest.runtime == "python":
                command = ([sys.executable, "--extension-host", str(self.entrypoint)]
                           if getattr(sys, "frozen", False) else [sys.executable, str(self.entrypoint)])
            command.extend(["--request", str(request_path), "--result", str(result_path)])
            environment = {
                "PATH": os.environ.get("PATH", ""),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                "TEMP": str(job),
                "TMP": str(job),
                "SPIKE_EXTENSION_JOB": str(job),
                "PYTHONNOUSERSITE": "1",
            }
            # Standard OS locations allow installed optional runtimes and SPIKE
            # registrations to be discovered. Do not copy arbitrary environment
            # variables (tokens, Python paths, or application credentials).
            for key in ("USERPROFILE", "LOCALAPPDATA", "APPDATA", "ProgramFiles", "ProgramFiles(x86)", "HOME", "XDG_STATE_HOME", "XDG_DATA_HOME"):
                if os.environ.get(key):
                    environment[key] = os.environ[key]
            try:
                with diagnostic_path.open("wb") as diagnostic:
                    process = subprocess.run(
                        command,
                        cwd=job,
                        env=environment,
                        stdout=diagnostic,
                        stderr=subprocess.STDOUT,
                        timeout=timeout_seconds,
                        shell=False,
                    )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"Extension exceeded the {timeout_seconds}-second limit.") from exc
            if process.returncode != 0 or not result_path.is_file():
                detail = _tail_text(diagnostic_path, 2000)
                cause = detail.strip().splitlines()[-1] if detail.strip() else "No diagnostic output."
                raise RuntimeError(f"Extension exited with code {process.returncode}: {cause}\n{detail}".strip())
            if result_path.stat().st_size > max_result_bytes:
                raise RuntimeError(f"Extension result exceeds the {max_result_bytes}-byte limit.")
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("contract") != EXTENSION_RESULT_CONTRACT:
                raise ValueError(f"Extension must return {EXTENSION_RESULT_CONTRACT}.")
            return payload


class ExtensionRegistry:
    def __init__(self) -> None:
        self._extensions: Dict[str, ProcessExtension] = {}
        self._diagnostics: List[Dict[str, Any]] = []

    def discover(
        self,
        roots: Iterable[str | Path],
        trusted_ids: Iterable[str] = (),
        trusted_roots: Iterable[str | Path] = (),
    ) -> List[Dict[str, Any]]:
        trusted = set(trusted_ids)
        trusted_root_paths = tuple(Path(item).expanduser().resolve() for item in trusted_roots)
        diagnostics: List[Dict[str, Any]] = []
        for root_value in roots:
            root = Path(root_value).expanduser().resolve()
            if not root.is_dir():
                continue
            for manifest_path in root.glob("*/spike-extension.json"):
                try:
                    manifest = ExtensionManifest.from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
                    resolved_directory = manifest_path.parent.resolve()
                    trusted_by_distribution = any(
                        resolved_directory == trusted_root or resolved_directory.is_relative_to(trusted_root)
                        for trusted_root in trusted_root_paths
                    )
                    if manifest.bundled and not trusted_by_distribution:
                        raise ValueError("An external manifest cannot self-assert bundled trust.")
                    if manifest.id in self._extensions:
                        raise ValueError(f"Duplicate extension ID is already registered: {manifest.id}")
                    extension = ProcessExtension(manifest, manifest_path.parent, trusted_by_distribution or manifest.id in trusted)
                    self._extensions[manifest.id] = extension
                    diagnostics.append({"id": manifest.id, "status": "loaded", "trusted": extension.trusted, "path": str(manifest_path)})
                except Exception as exc:
                    diagnostics.append({"id": manifest_path.parent.name, "status": "rejected", "path": str(manifest_path), "error": str(exc)})
        self._diagnostics = diagnostics
        return diagnostics

    def catalog(self) -> List[Dict[str, Any]]:
        return [
            extension.catalog_entry()
            for extension in sorted(self._extensions.values(), key=lambda item: item.manifest.id)
        ]

    def diagnostics(self) -> List[Dict[str, Any]]:
        return list(self._diagnostics)

    def design_importers(self):
        from .extension_importers import ExtensionDesignImporter
        return [ExtensionDesignImporter(extension, contribution)
                for extension in self._extensions.values()
                if extension.trusted and extension.manifest.state != "disabled"
                for contribution in extension.manifest.contributes.get("importers", [])
                if contribution.get("output_contract") == "spike/v1"]

    def invoke(self, extension_id: str, contribution_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        extension = self._extensions.get(extension_id)
        if extension is None:
            raise ValueError(f"Extension is not installed: {extension_id}")
        return extension.invoke(contribution_id, context)


def default_extension_roots() -> List[Path]:
    roots = [Path(__file__).resolve().parents[2] / "extensions"]
    workspace = os.environ.get("SPIKE_WORKSPACE", "")
    if workspace:
        roots.append(Path(workspace) / "extensions")
    configured = os.environ.get("SPIKE_EXTENSION_PATH", "")
    roots.extend(Path(value) for value in configured.split(os.pathsep) if value)
    output: List[Path] = []
    seen = set()
    for root in roots:
        key = os.path.normcase(str(root.expanduser().resolve()))
        if key not in seen:
            seen.add(key)
            output.append(root)
    return output


def _tail_text(path: Path, limit: int) -> str:
    if not path.is_file():
        return ""
    with path.open("rb") as stream:
        size = stream.seek(0, 2)
        stream.seek(max(0, size - limit))
        return stream.read(limit).decode("utf-8", errors="replace")
