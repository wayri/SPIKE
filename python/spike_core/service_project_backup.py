# SPDX-License-Identifier: Apache-2.0
"""Bounded local recovery packages; never writes the user's active project."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from .project_package import ProjectPackageError, read_project
from .service_helpers import error_response, operation_id

CONTRACT = "spike/project-backup/v1"
METHODS = {"write_project_backup", "list_project_backups", "open_project_backup"}
KEEP_PER_SESSION = 10
MAX_BACKUP_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_RECORDS = 1000
_ID = re.compile(r"^[0-9a-f]{32}$")


def _plain(path):
    return not path.is_symlink() and not getattr(path, "is_junction", lambda: False)()


def _root(params):
    value = params.get("_backup_root")
    if not isinstance(value, str) or not value:
        raise ProjectPackageError("The native host must supply the recovery directory.")
    root = Path(value)
    if not root.is_absolute() or any(not _plain(p) for p in (root, *root.parents)):
        raise ProjectPackageError("Recovery directory must be an absolute local directory without links.")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not root.is_dir():
        raise ProjectPackageError("Recovery directory is unavailable.")
    return root


def _record(root, path):
    if not _plain(path) or path.stat().st_size > 16384:
        raise ProjectPackageError("Recovery metadata is invalid; no backups were pruned.")
    row = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(row, dict):
        raise ProjectPackageError("Recovery metadata must be an object.")
    identifier = row.get("id", "")
    if row.get("contract") != CONTRACT or not _ID.fullmatch(identifier) or path.name != identifier + ".json":
        raise ProjectPackageError("Recovery metadata identity is invalid.")
    if not _ID.fullmatch(row.get("session_id", "")) or not isinstance(row.get("project_name"), str):
        raise ProjectPackageError("Recovery session metadata is invalid.")
    datetime.fromisoformat(row["created_at"])
    if not re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", "")):
        raise ProjectPackageError("Recovery package digest is invalid.")
    package = root / (identifier + ".spike")
    if not _plain(package) or not package.is_file() or package.stat().st_size != row.get("bytes"):
        raise ProjectPackageError("Recovery package is missing or changed; no backups were pruned.")
    if not 0 < row["bytes"] <= MAX_BACKUP_BYTES:
        raise ProjectPackageError("Recovery package exceeds its size bound.")
    return {**row, "path": str(package)}


def _records(root):
    metadata = list(root.glob("*.json"))
    if len(metadata) > MAX_RECORDS:
        raise ProjectPackageError("Recovery metadata count exceeds its bound.")
    return sorted((_record(root, p) for p in metadata), key=lambda r: (r["created_at"], r["id"]), reverse=True)


def _digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@contextmanager
def _lock(root):
    lock = root / ".backup-lock"
    if not _plain(lock):
        raise ProjectPackageError("Recovery storage lock must not be a link.")
    with lock.open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ProjectPackageError("Recovery storage is busy; retry after the active write.") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def handle_backup_request(method, params, *, request_id, application_version):
    if method not in METHODS:
        return None
    try:
        if any(key in params for key in ("path", "root", "backup_root", "directory", "project_path")):
            raise ProjectPackageError("Recovery paths are controlled by the native host.")
        root = _root(params)
        with _lock(root):
            rows = _records(root)
            if method == "list_project_backups":
                return {"ok": True, "result": {"contract": "spike/project-backups/v1", "backups": rows}}
            if method == "open_project_backup":
                identifier = params.get("id", "")
                if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
                    raise ProjectPackageError("A valid recovery identifier is required.")
                row = next((r for r in rows if r["id"] == identifier), None)
                if row is None or _digest(Path(row["path"])) != row["sha256"]:
                    raise ProjectPackageError("Recovery package is missing or failed its integrity check.")
                read_project(row["path"])
                return {"ok": True, "result": row}
            try:
                session_id = uuid.UUID(str(params.get("session_id", ""))).hex
            except ValueError as exc:
                raise ProjectPackageError("A recovery session UUID is required.") from exc
            snapshot = params.get("snapshot")
            if not isinstance(snapshot, dict):
                raise ProjectPackageError("A project snapshot is required for recovery.")
            base = params.get("base_package_path")
            expected = params.get("expected_base_manifest_sha256")
            if base and (not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected)):
                raise ProjectPackageError("Backups of opened packages require the expected base manifest identity.")
            if len(rows) >= MAX_RECORDS:
                raise ProjectPackageError("Recovery metadata capacity reached; review existing backups.")
            identifier = uuid.uuid4().hex
            package = root / (identifier + ".spike")
            metadata = root / (identifier + ".json")
            temporary_metadata = root / (identifier + ".pending")
            from .service_project_handlers import handle_project_request
            save_params = {"path": str(package), "snapshot": snapshot, "profile": "portable_project", "generate_geometry_tables": False}
            for key in ("visuals", "base_package_path", "expected_base_manifest_sha256"):
                if key in params and params[key] is not None:
                    save_params[key] = params[key]
            try:
                saved = handle_project_request("write_project_package", save_params, request_id=request_id, application_version=application_version)
                if not saved.get("ok"):
                    package.unlink(missing_ok=True)
                    return saved
                size = package.stat().st_size
                session_rows = [r for r in rows if r["session_id"] == session_id]
                excess = max(0, len(session_rows) + 1 - KEEP_PER_SESSION)
                protected_base = Path(base).resolve() if base else None
                candidates = [r for r in reversed(session_rows) if Path(r["path"]).resolve() != protected_base]
                old = candidates[:excess]
                # Include orphaned/unknown files left by interrupted writes in the
                # storage bound, but never treat them as pruning candidates.
                stored_bytes = sum(p.stat().st_size for p in root.iterdir() if p.is_file() and _plain(p))
                if size > MAX_BACKUP_BYTES or stored_bytes - sum(r["bytes"] for r in old) > MAX_TOTAL_BYTES:
                    raise ProjectPackageError("Recovery storage size limit reached; the active project was not changed.")
                # Validate pruning candidates before publishing a new record.
                for row in old:
                    if _digest(Path(row["path"])) != row["sha256"]:
                        raise ProjectPackageError("An older backup changed; no backups were pruned.")
                project = snapshot.get("project") or {}
                row = {"contract": CONTRACT, "id": identifier, "session_id": session_id,
                       "created_at": datetime.now(timezone.utc).isoformat(),
                       "project_name": str(project.get("name") or params.get("source_name") or "Untitled project")[:256],
                       "source_name": str(params.get("source_name") or "")[:256],
                       "bytes": size, "sha256": _digest(package)}
                with temporary_metadata.open("x", encoding="utf-8") as stream:
                    json.dump(row, stream, ensure_ascii=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_metadata, metadata)
            except BaseException:
                if not metadata.exists():
                    package.unlink(missing_ok=True)
                temporary_metadata.unlink(missing_ok=True)
                raise
            for previous in old:
                # Only exact, digest-checked files belonging to this recovery session.
                Path(previous["path"]).unlink()
                (root / (previous["id"] + ".json")).unlink()
            return {"ok": True, "result": {**row, "path": str(package)}}
    except (OSError, ValueError, TypeError, KeyError, ProjectPackageError) as exc:
        return error_response("SPIKE-BE-PACKAGE-E-0002", str(exc), error_type=type(exc).__name__, operation_id=operation_id(request_id))
