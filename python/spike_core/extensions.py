"""General-purpose SPIKE extension discovery and isolated command execution."""

from __future__ import annotations

import json
import os
import hashlib
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, List

from .extension_analysis_results import admit_analysis_result, design_binding
from .extension_mesh_exchange import build_extension_mesh_exchange
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
    "mesh.read",
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
    "mesh_spec": "mesh.read",
    "project": "project.read",
    "selection": "selection.read",
    "results": "results.read",
    "source": "filesystem.workspace",
    "harness": "harness.read",
}
MAX_EXTENSION_RESULT_BYTES = 64 * 1024 * 1024
MAX_EXTENSION_REQUEST_BYTES = 64 * 1024 * 1024
MANAGED_EXTENSION_CONTRACT = "spike/managed-extension/v1"
EXTENSION_BROWSER_CONTRACT = "spike/extension-browser/v1"
MAX_PACKAGE_FILES = 4096
MAX_PACKAGE_FILE_BYTES = 64 * 1024 * 1024
MAX_PACKAGE_BYTES = 256 * 1024 * 1024
MANAGED_RECEIPT = ".spike-managed.json"


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
    ui: Dict[str, Any] = field(default_factory=dict)

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
        if "mesh.read" in self.permissions and "design.read" not in self.permissions:
            raise ValueError("mesh.read requires design.read permission.")
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
                if point == "analyses" and entry.get("output_contract") == "spike/v1":
                    if not {"design.read", "results.write"}.issubset(self.permissions):
                        raise ValueError("Analysis result contributions require design.read and results.write permissions.")
        if not isinstance(self.ui, dict) or set(self.ui) - {"menu_bar", "title_bar", "menu_items"}:
            raise ValueError("Extension UI settings contain unsupported fields.")
        for key in ("menu_bar", "title_bar"):
            if key in self.ui and not isinstance(self.ui[key], bool):
                raise ValueError(f"Extension UI {key} must be boolean.")
        items = self.ui.get("menu_items", [])
        if (not isinstance(items, list) or len(items) > 20
                or any(not isinstance(item, str) or item not in contribution_ids for item in items)
                or len(items) != len(set(items))):
            raise ValueError("Extension UI menu_items must reference up to 20 declared contributions.")

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
        analysis_contribution = next((item for item in self.manifest.contributes.get("analyses", [])
                                      if item["id"] == contribution_id and item.get("output_contract") == "spike/v1"), None)
        binding = design_binding(context.get("design")) if analysis_contribution else None
        if any(key in context for key in ("mesh", "mesh_preview", "mesh_binding", "solver_geometry")):
            raise ValueError("Mesh and solver geometry context are generated by the SPIKE host.")
        filtered_context: Dict[str, Any] = {}
        for key, value in context.items():
            required = CONTEXT_PERMISSIONS.get(key)
            if required and required not in self.manifest.permissions:
                raise PermissionError(f"Extension lacks permission {required} for context field {key}.")
            if key in CONTEXT_PERMISSIONS or key == "parameters":
                filtered_context[key] = value.to_dict() if key == "design" and hasattr(value, "to_dict") else value
        if binding is not None:
            filtered_context["design_binding"] = binding
        mesh_binding = None
        if analysis_contribution and "mesh.read" in self.manifest.permissions:
            parameters = context.get("parameters") or {}
            if not isinstance(parameters, dict):
                raise ValueError("Extension parameters must be an object.")
            mesh_spec = context.get("mesh_spec", parameters.get("mesh_spec"))
            exchange = build_extension_mesh_exchange(filtered_context["design"], mesh_spec, binding)
            filtered_context.update(exchange)
            mesh_binding = exchange["mesh_binding"]
        timeout_seconds = max(1, min(int(self.manifest.limits.get("timeout_seconds", 300)), timeout_seconds or 3600, 3600))
        max_result_bytes = max(1024, min(int(self.manifest.limits.get("max_result_bytes", MAX_EXTENSION_RESULT_BYTES)), 1024 * 1024 * 1024))
        if analysis_contribution:
            max_result_bytes = min(max_result_bytes, MAX_EXTENSION_RESULT_BYTES)
        with tempfile.TemporaryDirectory(prefix="spike-extension-") as directory:
            job = Path(directory)
            request_path = job / "request.json"
            result_path = job / "result.json"
            diagnostic_path = job / "extension.log"
            request_data = json.dumps({
                "contract": EXTENSION_CONTRACT,
                "api_version": EXTENSION_API_VERSION,
                "request_id": str(uuid.uuid4()),
                "extension": self.manifest.to_dict(),
                "contribution_id": contribution_id,
                "context": filtered_context,
            }, ensure_ascii=False, allow_nan=False, default=str).encode("utf-8")
            if len(request_data) > MAX_EXTENSION_REQUEST_BYTES:
                raise ValueError("Extension request exceeds the 64 MB exchange limit.")
            request_path.write_bytes(request_data)
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
            for key in ("USERPROFILE", "LOCALAPPDATA", "APPDATA", "ProgramFiles", "ProgramFiles(x86)", "HOME", "XDG_STATE_HOME", "XDG_DATA_HOME", "SPIKE_STATE_HOME", "OPENEMS_INSTALL_PATH", "SPIKE_OPENEMS_PYTHON"):
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
            if binding is not None:
                if payload.get("status") not in {"completed", "completed_with_warnings"}:
                    raise ValueError("Analysis extension did not complete successfully.")
                data = payload.get("data")
                if not isinstance(data, dict):
                    raise ValueError("Analysis extension must return data.analysis_result.")
                admitted = admit_analysis_result(data.get("analysis_result"), binding,
                    extension_id=self.manifest.id,
                    expected_mesh_digest=mesh_binding["mesh_digest_sha256"] if mesh_binding else None,
                    expected_spec_digest=mesh_binding["analysis_spec_digest_sha256"] if mesh_binding else None)
                payload = {**payload, "data": {**data, "analysis_result": admitted,
                                                "input_design_sha256": binding["digest_sha256"]}}
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
                if manifest_path.parent.name.startswith("."):
                    continue
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

    def reset(self) -> None:
        """Forget discovered packages while retaining no executable state."""
        self._extensions.clear()
        self._diagnostics.clear()

    def trust(self, extension_id: str) -> Dict[str, Any]:
        """Trust one already discovered local package for this worker session."""
        extension = self._extensions.get(extension_id)
        if extension is None:
            raise ValueError(f"Extension is not installed: {extension_id}")
        if extension.manifest.state == "disabled":
            raise ValueError("Disabled extensions cannot be trusted for execution.")
        extension.trusted = True
        return extension.catalog_entry()

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
    roots = [Path(__file__).resolve().parents[2] / "extensions", user_extension_root()]
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


def user_extension_root() -> Path:
    """Return SPIKE's private directory for extension-manager installations."""
    configured = os.environ.get("SPIKE_STATE_HOME", "").strip()
    if configured:
        state = Path(configured).expanduser().resolve()
    elif os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        state = Path(os.environ["LOCALAPPDATA"]) / "SPIKE" / "state"
    elif sys.platform == "darwin":
        state = Path.home() / "Library" / "Application Support" / "SPIKE" / "state"
    else:
        xdg = os.environ.get("XDG_STATE_HOME", "").strip()
        state = (Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state") / "spike"
    return state / "extensions"


def _managed_receipt(directory: Path) -> Dict[str, Any] | None:
    path = directory / MANAGED_RECEIPT
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (not isinstance(value, dict) or value.get("contract") != MANAGED_EXTENSION_CONTRACT
            or value.get("extension_id") != directory.name):
        return None
    return value


def _safe_package_files(root: Path) -> List[tuple[Path, Path]]:
    root = root.resolve()
    files: List[tuple[Path, Path]] = []
    total = 0
    for candidate in root.rglob("*"):
        relative = candidate.relative_to(root)
        if candidate.is_symlink():
            raise ValueError(f"Extension packages cannot contain symbolic links: {relative.as_posix()}")
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f"Extension package member escapes its root: {relative.as_posix()}")
        if candidate.is_dir():
            continue
        if not candidate.is_file() or not stat.S_ISREG(candidate.stat().st_mode):
            raise ValueError(f"Extension package member is not a regular file: {relative.as_posix()}")
        if relative.as_posix() == MANAGED_RECEIPT:
            raise ValueError(f"Extension packages cannot provide the reserved {MANAGED_RECEIPT} file.")
        size = candidate.stat().st_size
        if size > MAX_PACKAGE_FILE_BYTES:
            raise ValueError(f"Extension package member exceeds the 64 MB limit: {relative.as_posix()}")
        total += size
        files.append((candidate, relative))
        if len(files) > MAX_PACKAGE_FILES or total > MAX_PACKAGE_BYTES:
            raise ValueError("Extension package exceeds the 4096-file or 256 MB installation limit.")
    return files


def _locate_package_root(directory: Path) -> Path:
    direct = directory / "spike-extension.json"
    if direct.is_file():
        return directory
    children = [item for item in directory.iterdir() if item.is_dir() and not item.is_symlink()]
    if len(children) == 1 and (children[0] / "spike-extension.json").is_file():
        return children[0]
    raise ValueError("An extension package must contain spike-extension.json at its root.")


def _read_package_manifest(root: Path) -> ExtensionManifest:
    path = root / "spike-extension.json"
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Extension manifest exceeds the 1 MB limit.")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Extension manifest must be a JSON object.")
    manifest = ExtensionManifest.from_dict(raw)
    if manifest.bundled:
        raise ValueError("Locally installed extensions cannot declare themselves bundled.")
    ProcessExtension(manifest, root, False)
    return manifest


def _package_digest(files: Iterable[tuple[Path, Path]]) -> str:
    digest = hashlib.sha256()
    for source, relative in sorted(files, key=lambda item: item[1].as_posix()):
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        with source.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def _extract_zip(package: Path, destination: Path) -> None:
    total = 0
    seen: set[str] = set()
    with zipfile.ZipFile(package) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_PACKAGE_FILES:
            raise ValueError("Extension package exceeds the 4096-file installation limit.")
        for info in infos:
            name = info.filename
            normalized = PurePosixPath(name)
            if (not name or "\\" in name or normalized.is_absolute()
                    or any(part in {"", ".", ".."} for part in normalized.parts)):
                raise ValueError(f"Unsafe extension archive member: {name!r}")
            key = normalized.as_posix().casefold()
            if key in seen:
                raise ValueError(f"Duplicate extension archive member: {name}")
            seen.add(key)
            mode = info.external_attr >> 16
            if stat.S_IFMT(mode) == stat.S_IFLNK:
                raise ValueError(f"Extension archives cannot contain symbolic links: {name}")
            if info.flag_bits & 0x1:
                raise ValueError("Encrypted extension archives are not supported.")
            if info.is_dir():
                (destination / Path(*normalized.parts)).mkdir(parents=True, exist_ok=True)
                continue
            if info.file_size > MAX_PACKAGE_FILE_BYTES:
                raise ValueError(f"Extension package member exceeds the 64 MB limit: {name}")
            total += info.file_size
            if total > MAX_PACKAGE_BYTES:
                raise ValueError("Extension package exceeds the 256 MB installation limit.")
            target = destination / Path(*normalized.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with archive.open(info) as source, target.open("wb") as output:
                while True:
                    block = source.read(min(1024 * 1024, MAX_PACKAGE_FILE_BYTES + 1 - written))
                    if not block:
                        break
                    written += len(block)
                    if written > MAX_PACKAGE_FILE_BYTES:
                        raise ValueError(f"Extension package member exceeds the 64 MB limit: {name}")
                    output.write(block)
            if written != info.file_size:
                raise ValueError(f"Extension archive member size is inconsistent: {name}")


class ExtensionPackageManager:
    """Install and remove only bounded local extension packages owned by SPIKE."""

    def __init__(self, install_root: str | Path | None = None) -> None:
        self.install_root = Path(install_root).expanduser().resolve() if install_root else user_extension_root()

    def _materialize(self, package_path: str | Path, temporary: Path) -> Path:
        source = Path(package_path).expanduser().resolve()
        if source.is_dir():
            return _locate_package_root(source)
        if not source.is_file() or source.suffix.lower() not in {".zip", ".spike-extension"}:
            raise ValueError("Choose a local extension directory, .zip, or .spike-extension package.")
        _extract_zip(source, temporary)
        return _locate_package_root(temporary)

    def preview(self, package_path: str | Path) -> Dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="spike-extension-preview-") as directory:
            root = self._materialize(package_path, Path(directory))
            files = _safe_package_files(root)
            manifest = _read_package_manifest(root)
            destination = self.install_root / manifest.id
            receipt = _managed_receipt(destination) if destination.is_dir() else None
            return {
                "contract": "spike/extension-package-preview/v1",
                "manifest": manifest.to_dict(),
                "package_sha256": _package_digest(files),
                "file_count": len(files),
                "installed": destination.is_dir(),
                "managed": receipt is not None,
                "can_install": not destination.exists() or receipt is not None,
            }

    def install(self, package_path: str | Path, *, replace: bool = False) -> Dict[str, Any]:
        self.install_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="spike-extension-source-") as source_directory:
            source_root = self._materialize(package_path, Path(source_directory))
            files = _safe_package_files(source_root)
            manifest = _read_package_manifest(source_root)
            package_sha256 = _package_digest(files)
            destination = (self.install_root / manifest.id).resolve()
            if destination.parent != self.install_root:
                raise ValueError("Extension ID resolves outside the managed installation directory.")
            previous = _managed_receipt(destination) if destination.is_dir() else None
            if destination.exists() and previous is None:
                raise FileExistsError("The destination exists but is not owned by SPIKE's extension manager.")
            if destination.exists() and not replace:
                raise FileExistsError("The extension is already installed; enable replace to update it.")
            stage: Path | None = Path(tempfile.mkdtemp(prefix=".install-", dir=self.install_root))
            backup: Path | None = None
            try:
                for source, relative in files:
                    target = stage / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target, follow_symlinks=False)
                receipt = {
                    "contract": MANAGED_EXTENSION_CONTRACT,
                    "extension_id": manifest.id,
                    "version": manifest.version,
                    "package_sha256": package_sha256,
                }
                (stage / MANAGED_RECEIPT).write_text(
                    json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
                )
                ProcessExtension(manifest, stage, False)
                if destination.exists():
                    backup = self.install_root / f".replace-{manifest.id}-{uuid.uuid4().hex}"
                    os.replace(destination, backup)
                os.replace(stage, destination)
                stage = None
                if backup is not None:
                    shutil.rmtree(backup, ignore_errors=True)
                return {
                    "contract": "spike/extension-install-result/v1",
                    "action": "updated" if previous else "installed",
                    "extension_id": manifest.id,
                    "version": manifest.version,
                    "package_sha256": package_sha256,
                    "managed": True,
                    "trusted": False,
                }
            except Exception:
                if backup is not None and backup.exists() and not destination.exists():
                    os.replace(backup, destination)
                raise
            finally:
                if stage is not None and stage.exists():
                    shutil.rmtree(stage, ignore_errors=True)

    def remove(self, extension_id: str) -> Dict[str, Any]:
        if not extension_id or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for character in extension_id):
            raise ValueError("A valid extension ID is required.")
        destination = (self.install_root / extension_id).resolve()
        if destination.parent != self.install_root or not destination.is_dir():
            raise ValueError(f"Managed extension is not installed: {extension_id}")
        receipt = _managed_receipt(destination)
        if receipt is None:
            raise PermissionError("Only extensions installed by SPIKE's extension manager can be removed.")
        tombstone = self.install_root / f".remove-{extension_id}-{uuid.uuid4().hex}"
        os.replace(destination, tombstone)
        # The rename removes the extension from discovery atomically. A locked
        # file may leave an inert tombstone for a later cleanup, but must not
        # restore a partially deleted executable package.
        shutil.rmtree(tombstone, ignore_errors=True)
        return {
            "contract": "spike/extension-remove-result/v1",
            "extension_id": extension_id,
            "removed": True,
        }

    def browse(self, registry: ExtensionRegistry, package_path: str | Path | None = None) -> Dict[str, Any]:
        managed_root = self.install_root
        entries = []
        for entry in registry.catalog():
            path = Path(str(entry.get("path", ""))).resolve()
            receipt = _managed_receipt(path) if path.parent == managed_root else None
            bundled = bool(entry.get("bundled"))
            entries.append({
                **entry,
                "install_state": "bundled" if bundled else "installed",
                "managed": receipt is not None,
                "can_remove": receipt is not None and not bundled,
            })
        result: Dict[str, Any] = {
            "contract": EXTENSION_BROWSER_CONTRACT,
            "install_root": str(managed_root),
            "extensions": entries,
            "diagnostics": registry.diagnostics(),
        }
        if package_path:
            result["candidate"] = self.preview(package_path)
        return result


def _tail_text(path: Path, limit: int) -> str:
    if not path.is_file():
        return ""
    with path.open("rb") as stream:
        size = stream.seek(0, 2)
        stream.seek(max(0, size - limit))
        return stream.read(limit).decode("utf-8", errors="replace")
