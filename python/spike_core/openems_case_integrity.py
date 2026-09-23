"""Integrity checks for prepared openEMS execution inputs.

The exported driver remains editable for inspection because SPIKE never executes
it. Job metadata and normalized geometry are authenticated with a per-user key
stored outside the case directory so edited cases must be prepared again.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any, Dict, Iterable


INTEGRITY_CONTRACT = "spike/external-case-integrity/v1"
SIGNED_FILE_KEYS = ("geometry",)
MAX_JOB_JSON_BYTES = 4 * 1024**2
MAX_SIGNED_FILE_BYTES = 512 * 1024**2
DEFAULT_JSON_LIMIT_BYTES = 256 * 1024**2


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON constant is not allowed: {value}")


def _read_bounded_bytes(path: Path, max_bytes: int, label: str) -> bytes:
    if max_bytes <= 0:
        raise ValueError(f"The {label} byte limit must be positive.")
    with path.open("rb") as stream:
        payload = stream.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError(f"The {label} exceeds its {max_bytes:,}-byte input limit.")
    return payload


def parse_strict_json_bytes(payload: bytes, *, label: str = "JSON input") -> Any:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"The {label} is not valid UTF-8.") from exc
    return json.loads(text, parse_constant=_reject_json_constant)


def load_strict_json(
    path: Path,
    *,
    max_bytes: int = DEFAULT_JSON_LIMIT_BYTES,
    label: str = "JSON input",
) -> Any:
    return parse_strict_json_bytes(_read_bounded_bytes(path, max_bytes, label), label=label)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _state_root() -> Path:
    configured = os.environ.get("SPIKE_STATE_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "SPIKE" / "state"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SPIKE" / "state"
    xdg = os.environ.get("XDG_STATE_HOME", "").strip()
    return (Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state") / "spike"


def _key_paths(case_root: Path) -> list[Path]:
    configured = os.environ.get("SPIKE_CASE_INTEGRITY_KEY", "").strip()
    if configured:
        return [Path(configured).expanduser().resolve()]
    state = _state_root()
    return [state / "external-case.key", state / "external-case-recovery.key"]


def _read_or_create_key(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.parent.chmod(0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    # Windows text-mode descriptors can translate random key bytes and change
    # their length. Integrity keys are opaque binary material on every host.
    flags |= getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        descriptor = -1
    if descriptor >= 0:
        try:
            material = secrets.token_bytes(32)
            offset = 0
            while offset < len(material):
                written = os.write(descriptor, material[offset:])
                if written <= 0:
                    raise OSError("Could not persist the external-case integrity key.")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    key = path.read_bytes()
    if len(key) != 32:
        raise ValueError("The SPIKE external-case integrity key is invalid; restore it or reinitialize application state.")
    if os.name != "nt":
        path.chmod(0o600)
    return key


def _load_or_create_key(case_root: Path) -> bytes:
    paths = _key_paths(case_root)
    explicitly_configured = bool(os.environ.get("SPIKE_CASE_INTEGRITY_KEY", "").strip())
    last_error: Exception | None = None
    for path in paths:
        try:
            return _read_or_create_key(path)
        except (OSError, ValueError) as exc:
            if explicitly_configured:
                raise
            last_error = exc
    raise ValueError(f"SPIKE could not create a private external-case integrity key: {last_error}")


def _load_matching_key(case_root: Path, key_id: str) -> bytes:
    for path in _key_paths(case_root):
        try:
            if not path.is_file():
                continue
            key = path.read_bytes()
        except OSError:
            continue
        if len(key) == 32 and hmac.compare_digest(hashlib.sha256(key).hexdigest()[:16], key_id):
            return key
    raise ValueError("The prepared case belongs to a different SPIKE installation state; prepare it again.")


def _case_file(root: Path, job: Dict[str, Any], key: str) -> tuple[str, Path]:
    files = job.get("files")
    relative = files.get(key) if isinstance(files, dict) else None
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"The external-engine job is missing its {key} path.")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"The external-engine {key} input is missing or outside the job directory.")
    return relative.replace("\\", "/"), path


def _payload(
    job: Dict[str, Any],
    root: Path,
    signed_keys: Iterable[str],
) -> tuple[Dict[str, Any], Dict[str, bytes]]:
    unsigned_job = dict(job)
    unsigned_job.pop("integrity", None)
    files: Dict[str, Any] = {}
    snapshots: Dict[str, bytes] = {}
    for key in signed_keys:
        relative, path = _case_file(root, unsigned_job, key)
        payload = _read_bounded_bytes(path, MAX_SIGNED_FILE_BYTES, f"external-engine {key} input")
        snapshots[key] = payload
        files[key] = {
            "path": relative,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    return {"job": unsigned_job, "execution_inputs": files}, snapshots


def attach_case_integrity(job: Dict[str, Any], root: Path) -> Dict[str, Any]:
    key = _load_or_create_key(root)
    payload, _ = _payload(job, root, SIGNED_FILE_KEYS)
    encoded = _canonical_json(payload)
    job["integrity"] = {
        "contract": INTEGRITY_CONTRACT,
        "signed_file_keys": list(SIGNED_FILE_KEYS),
        "payload_sha256": hashlib.sha256(encoded).hexdigest(),
        "key_id": hashlib.sha256(key).hexdigest()[:16],
        "hmac_sha256": hmac.new(key, encoded, hashlib.sha256).hexdigest(),
    }
    return job


def verify_case_integrity(job: Dict[str, Any], root: Path) -> Dict[str, bytes]:
    integrity = job.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("contract") != INTEGRITY_CONTRACT:
        raise ValueError("The prepared case has no valid execution-input integrity record; prepare it again.")
    if integrity.get("signed_file_keys") != list(SIGNED_FILE_KEYS):
        raise ValueError("The prepared case uses an unsupported execution-input integrity policy.")
    key_id = str(integrity.get("key_id", ""))
    key = _load_matching_key(root, key_id)
    payload, snapshots = _payload(job, root, SIGNED_FILE_KEYS)
    encoded = _canonical_json(payload)
    expected_payload = hashlib.sha256(encoded).hexdigest()
    expected_signature = hmac.new(key, encoded, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(str(integrity.get("payload_sha256", "")), expected_payload):
        raise ValueError("The prepared case job or geometry changed after validation; prepare it again.")
    if not hmac.compare_digest(str(integrity.get("hmac_sha256", "")), expected_signature):
        raise ValueError("The prepared case integrity signature is invalid; prepare it again.")
    return snapshots
