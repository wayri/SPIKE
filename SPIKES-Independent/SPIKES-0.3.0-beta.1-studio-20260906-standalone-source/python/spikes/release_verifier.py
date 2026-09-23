# SPDX-License-Identifier: MIT
"""Fail-closed verification for an offline SPIKES engine release bundle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tempfile
from typing import Any, Mapping
import zipfile


VERIFY_CONTRACT = "spikes/engine-release-verification/v1"
MAX_CONTROL_BYTES = 8 * 1024 * 1024


class ReleaseVerificationError(ValueError):
    """A bundle violated an integrity, path, identity, or launch invariant."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ReleaseVerificationError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _read_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_CONTROL_BYTES:
        raise ReleaseVerificationError(f"{label} is missing, empty, or oversized")
    try:
        result = json.loads(
            path.read_bytes().decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ReleaseVerificationError(f"non-finite JSON constant {token} is prohibited")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseVerificationError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(result, dict):
        raise ReleaseVerificationError(f"{label} must contain one JSON object")
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_member(name: str, package_name: str) -> str:
    if "\\" in name:
        raise ReleaseVerificationError("archive member uses a backslash")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ReleaseVerificationError(f"unsafe archive member {name!r}")
    if len(path.parts) < 2 or path.parts[0] != package_name:
        raise ReleaseVerificationError("archive does not have exactly one expected root")
    return PurePosixPath(*path.parts[1:]).as_posix()


def _file_records(manifest: Mapping[str, Any]) -> dict[str, tuple[int, str]]:
    raw = manifest.get("files")
    if not isinstance(raw, list) or not raw:
        raise ReleaseVerificationError("release manifest has no file inventory")
    result: dict[str, tuple[int, str]] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            raise ReleaseVerificationError("release file record is malformed")
        name, size, digest = item.get("path"), item.get("size"), item.get("sha256")
        if not isinstance(name, str):
            raise ReleaseVerificationError("release file path is not a string")
        pure = PurePosixPath(name)
        if (
            pure.is_absolute() or "\\" in name
            or any(part in {"", ".", ".."} for part in pure.parts)
            or name in result
        ):
            raise ReleaseVerificationError(f"unsafe or repeated release path {name!r}")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ReleaseVerificationError(f"invalid release size for {name!r}")
        if (
            not isinstance(digest, str) or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ReleaseVerificationError(f"invalid release digest for {name!r}")
        result[name] = (size, digest)
    return result


def verify_engine_release(
    report_path: str | Path,
    *,
    launch_smoke: bool = True,
) -> dict[str, Any]:
    """Verify, stage, launch, and remove one deterministic release archive.

    The extraction root is temporary and deleted before success is reported.
    This models side-by-side install and uninstall without modifying the system.
    """

    report_file = Path(report_path).resolve(strict=True)
    report = _read_object(report_file, "engine release report")
    if report.get("contract") != "spikes/engine-release-manifest/v1":
        raise ReleaseVerificationError("engine release report contract is incompatible")
    version = report.get("version")
    if not isinstance(version, str) or not version:
        raise ReleaseVerificationError("engine release version is missing")
    package_name = f"SPIKES-{version}-windows-x64-engineering-preview"
    archive_record = report.get("archive")
    if not isinstance(archive_record, Mapping):
        raise ReleaseVerificationError("engine release archive record is missing")
    archive_name = archive_record.get("path")
    archive = report_file.parent / str(archive_name)
    if (
        not isinstance(archive_name, str)
        or Path(archive_name).name != archive_name
        or not archive.is_file()
        or archive.stat().st_size != archive_record.get("size")
        or _sha256(archive) != archive_record.get("sha256")
    ):
        raise ReleaseVerificationError("engine release archive identity mismatch")

    expected = _file_records(report)
    seen: set[str] = set()
    manifest_bytes: bytes | None = None
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if info.is_dir():
                continue
            relative = _safe_member(info.filename, package_name)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ReleaseVerificationError("archive contains a symbolic link")
            if relative in seen:
                raise ReleaseVerificationError(f"archive repeats {relative!r}")
            seen.add(relative)
            if relative == "release.manifest.json":
                manifest_bytes = bundle.read(info)
                continue
            record = expected.get(relative)
            if record is None:
                raise ReleaseVerificationError(f"archive contains undeclared file {relative!r}")
            payload = bundle.read(info)
            if len(payload) != record[0] or hashlib.sha256(payload).hexdigest() != record[1]:
                raise ReleaseVerificationError(f"archive member identity mismatch for {relative!r}")
    if seen != set(expected) | {"release.manifest.json"}:
        raise ReleaseVerificationError("archive inventory is incomplete")
    if manifest_bytes is None or len(manifest_bytes) > MAX_CONTROL_BYTES:
        raise ReleaseVerificationError("embedded release manifest is missing or oversized")
    try:
        embedded = json.loads(
            manifest_bytes.decode("utf-8"), object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ReleaseVerificationError(f"non-finite JSON constant {token} is prohibited")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseVerificationError("embedded release manifest is invalid") from exc
    expected_embedded = dict(report)
    expected_embedded.pop("archive", None)
    if embedded != expected_embedded:
        raise ReleaseVerificationError("embedded manifest differs from the release report")

    smoke = "skipped"
    functional_smoke = "skipped"
    console_smoke = "not_present"
    with tempfile.TemporaryDirectory(prefix="spikes-release-smoke-") as directory:
        staging = Path(directory)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(staging)
        installed = staging / package_name
        if not installed.is_dir():
            raise ReleaseVerificationError("side-by-side staging root is absent")
        if launch_smoke:
            completed = subprocess.run(
                [str(installed / "spikes.cmd"), "--version"],
                cwd=installed, stdin=subprocess.DEVNULL, capture_output=True,
                text=True, shell=False, timeout=30, check=False,
            )
            if completed.returncode != 0 or completed.stderr or completed.stdout.strip() != f"SPIKES {version}":
                raise ReleaseVerificationError("staged CLI version smoke failed")
            smoke = "passed"
            fixture = installed / "examples" / "voltage_divider.cir"
            completed = subprocess.run(
                [str(installed / "spikes.cmd"), "check", str(fixture)],
                cwd=installed, stdin=subprocess.DEVNULL, capture_output=True,
                text=True, shell=False, timeout=30, check=False,
            )
            if completed.returncode != 0 or completed.stderr:
                raise ReleaseVerificationError("staged CLI functional smoke failed")
            try:
                checked = json.loads(completed.stdout, object_pairs_hook=_strict_object)
            except json.JSONDecodeError as exc:
                raise ReleaseVerificationError("staged CLI functional output is invalid") from exc
            if not isinstance(checked, dict):
                raise ReleaseVerificationError("staged CLI functional output is not an object")
            functional_smoke = "passed"
            console = installed / "bin" / "spikes_console.exe"
            if console.is_file():
                completed = subprocess.run(
                    [str(console), "--version"], cwd=installed,
                    stdin=subprocess.DEVNULL, capture_output=True, text=True,
                    shell=False, timeout=30, check=False,
                )
                if (
                    completed.returncode != 0 or completed.stderr
                    or completed.stdout.strip() != f"spikes_console {version}"
                ):
                    raise ReleaseVerificationError("staged native console version smoke failed")
                console_smoke = "passed"
    if Path(directory).exists():
        raise ReleaseVerificationError("temporary side-by-side installation was not removed")

    claims = report.get("claims")
    if not isinstance(claims, Mapping):
        raise ReleaseVerificationError("release claims are missing")
    prohibited = (
        "complete_spice3_parity", "competitive_superiority", "hard_realtime",
        "physical_hil", "hostile_code_safe", "production_signed",
    )
    if any(claims.get(name) is not False for name in prohibited):
        raise ReleaseVerificationError("release manifest widens an unqualified claim")
    return {
        "contract": VERIFY_CONTRACT,
        "status": "passed",
        "version": version,
        "archive": archive.name,
        "archive_sha256": _sha256(archive),
        "files_verified": len(expected),
        "side_by_side_install": "passed",
        "cli_launch_smoke": smoke,
        "cli_functional_smoke": functional_smoke,
        "native_console_version_smoke": console_smoke,
        "uninstall": "passed",
        "rollback_compatible": True,
        "production_qualified": False,
        "limitations": [
            "Integrity and launch verification does not establish numerical qualification.",
            "Rollback compatibility means versioned side-by-side extraction is non-destructive; installer upgrade behavior is outside this engine bundle.",
            "The verified artifact remains unsigned and marked engineering_preview.",
        ],
    }


__all__ = [
    "ReleaseVerificationError", "VERIFY_CONTRACT", "verify_engine_release",
]
