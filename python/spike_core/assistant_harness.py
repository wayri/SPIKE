# SPDX-License-Identifier: Apache-2.0
"""Bounded, read-only evidence access for a user-selected assistant folder."""
from __future__ import annotations

import csv
import ctypes
import hashlib
import io
import itertools
import math
import os
import stat
from pathlib import Path, PureWindowsPath

MAX_FILE_BYTES = 256 * 1024
MAX_SCANNED_ENTRIES = 2000
MAX_PAGE_LIMIT = 200
DEFAULT_PAGE_LIMIT = 100
READABLE_SUFFIXES = {".txt", ".md", ".csv", ".json", ".log", ".py", ".spice", ".cir", ".net"}
_SECRET_MARKERS = {"credential", "credentials", "secret", "secrets", "token", "tokens", "apikey", "api_key"}


class HarnessError(ValueError):
    """Safe work-folder diagnostic that does not disclose host paths."""


def _integer(value, label, minimum, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        ceiling = "" if maximum is None else f" and at most {maximum}"
        raise HarnessError(f"{label} must be an integer of at least {minimum}{ceiling}.")
    return value


def _hidden_or_secret(parts):
    for part in parts:
        folded = part.casefold()
        if not part or part.startswith("."):
            return True
        stem = Path(part).stem.casefold().replace("-", "_")
        tokens = set(stem.replace(".", "_").split("_"))
        if folded in {"config", "config.json", "settings.json"} or tokens & _SECRET_MARKERS:
            return True
    return False


def _is_reparse(path):
    try:
        stat = path.lstat()
    except OSError as exc:
        raise HarnessError("Work-folder path could not be inspected.") from exc
    return bool(getattr(stat, "st_file_attributes", 0) & getattr(os.stat_result, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _final_handle_path(stream):
    """Resolve an opened file handle without trusting its pathname."""
    if os.name == "nt":
        import msvcrt
        handle = msvcrt.get_osfhandle(stream.fileno())
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        function = kernel32.GetFinalPathNameByHandleW
        function.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong]
        function.restype = ctypes.c_ulong
        size = function(handle, None, 0, 0)
        if not size or size > 32768:
            raise HarnessError("The opened work-folder file could not be verified.")
        buffer = ctypes.create_unicode_buffer(size + 1)
        written = function(handle, buffer, len(buffer), 0)
        if not written or written >= len(buffer):
            raise HarnessError("The opened work-folder file could not be verified.")
        value = buffer.value
        if value.startswith("\\\\?\\UNC\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
        return Path(value)
    descriptor = Path(f"/proc/self/fd/{stream.fileno()}")
    if descriptor.exists():
        try:
            return Path(os.readlink(descriptor)).resolve(strict=True)
        except OSError as exc:
            raise HarnessError("The opened work-folder file could not be verified.") from exc
    raise HarnessError("Opened-file path verification is unavailable on this platform.")


def _comparison_path(path):
    """Use the same Windows namespace spelling for resolved-path comparisons only."""
    value = str(path)
    if os.name == "nt":
        if value.startswith("\\\\?\\UNC\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
    return Path(value)


def _verify_open_handle(stream, expected, base):
    actual = _final_handle_path(stream)
    try:
        actual = _comparison_path(actual.resolve(strict=True))
        actual.relative_to(_comparison_path(base))
    except (OSError, ValueError) as exc:
        raise HarnessError("The opened file is outside the work folder.") from exc
    if os.path.normcase(str(actual)) != os.path.normcase(str(_comparison_path(expected))):
        raise HarnessError("The opened file does not match the requested work-folder file.")


def _target(root, relative_name, *, allow_root=False):
    if not isinstance(root, str) or not root:
        raise HarnessError("A trusted work-folder root is required.")
    try:
        base = Path(root).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise HarnessError("The work-folder root is unavailable.") from exc
    if not base.is_dir():
        raise HarnessError("The work-folder root must be a directory.")
    if not isinstance(relative_name, str):
        raise HarnessError("relativeName must be a string.")
    windows_path = PureWindowsPath(relative_name)
    if windows_path.drive or ":" in relative_name or any(ord(character) < 32 or ord(character) == 127 for character in relative_name):
        raise HarnessError("relativeName contains an unsupported drive, stream, or control character.")
    normalized = relative_name.replace("\\", "/")
    candidate_parts = Path(normalized).parts
    if (Path(normalized).is_absolute() or PureWindowsPath(relative_name).is_absolute()
            or any(part in {"", ".", ".."} for part in candidate_parts)):
        if not (allow_root and relative_name == ""):
            raise HarnessError("relativeName must be a confined relative path.")
    if relative_name == "":
        return base, "", base
    if _hidden_or_secret(candidate_parts):
        raise HarnessError("Hidden, secret, and configuration paths are unavailable.")
    current = base
    for part in candidate_parts:
        current = current / part
        if current.is_symlink() or _is_reparse(current):
            raise HarnessError("Symlinks and junctions are unavailable in assistant work folders.")
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(base)
    except (OSError, ValueError) as exc:
        raise HarnessError("relativeName does not resolve inside the work folder.") from exc
    return resolved, resolved.relative_to(base).as_posix(), base


def _source(relative_name, raw):
    return {"relativeName": relative_name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _read_bytes(path, relative_name, base):
    if path.suffix.casefold() not in READABLE_SUFFIXES:
        raise HarnessError("The requested file type is unavailable.")
    try:
        with path.open("rb") as stream:
            _verify_open_handle(stream, path, base)
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise HarnessError("The requested file type is unavailable.")
            if before.st_size > MAX_FILE_BYTES:
                raise HarnessError("Assistant work-folder files must not exceed 256 KiB.")
            raw = stream.read(MAX_FILE_BYTES + 1)
            after = os.fstat(stream.fileno())
            _verify_open_handle(stream, path, base)
    except OSError as exc:
        raise HarnessError("The requested file could not be read.") from exc
    verified, _, _ = _target(str(base), relative_name)
    if verified != path:
        raise HarnessError("The requested file changed during inspection.")
    if len(raw) != before.st_size or len(raw) > MAX_FILE_BYTES or after.st_size != before.st_size:
        raise HarnessError("The file changed while it was being read or exceeds 256 KiB.")
    if b"\0" in raw:
        raise HarnessError("Binary files are unavailable.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HarnessError("Assistant work-folder text must be valid UTF-8.") from exc
    source = _source(relative_name, raw)
    source["decodedTextSha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return raw, text, source


def _list(root, params):
    allowed = {"action", "relativeName", "offset", "limit"}
    if set(params) - allowed:
        raise HarnessError("Unsupported list parameter.")
    path, relative, _ = _target(root, params.get("relativeName", ""), allow_root=True)
    if not path.is_dir():
        raise HarnessError("list requires a directory.")
    offset = _integer(params.get("offset", 0), "offset", 0)
    limit = _integer(params.get("limit", DEFAULT_PAGE_LIMIT), "limit", 1, MAX_PAGE_LIMIT)
    try:
        with os.scandir(path) as iterator:
            scanned = list(itertools.islice(iterator, MAX_SCANNED_ENTRIES + 1))
    except OSError as exc:
        raise HarnessError("The requested directory could not be listed.") from exc
    if len(scanned) > MAX_SCANNED_ENTRIES:
        raise HarnessError("Directory exceeds the 2000-entry scan limit.")
    entries = []
    for entry in scanned:
        if _hidden_or_secret((entry.name,)):
            continue
        try:
            metadata = entry.stat(follow_symlinks=False)
        except OSError as exc:
            raise HarnessError("A directory entry could not be inspected.") from exc
        is_link = entry.is_symlink() or bool(getattr(metadata, "st_file_attributes", 0) & 0x400)
        kind = "link" if is_link else "directory" if entry.is_dir() else "file" if entry.is_file() else "other"
        name = f"{relative}/{entry.name}" if relative else entry.name
        entries.append({"name": name.replace("\\", "/"), "type": kind})
    entries.sort(key=lambda item: (item["type"], item["name"].casefold(), item["name"]))
    return {"action": "list", "relativeName": relative, "entries": entries[offset:offset + limit],
            "offset": offset, "limit": limit, "count": len(entries), "scannedCount": len(scanned)}


def _read(root, params):
    allowed = {"action", "relativeName"}
    if set(params) - allowed:
        raise HarnessError("Unsupported read parameter.")
    if not params.get("relativeName"):
        raise HarnessError("read requires relativeName.")
    path, relative, base = _target(root, params["relativeName"])
    raw, text, source = _read_bytes(path, relative, base)
    return {"action": "read", "source": source, "text": text}


def _csv_summary(root, params):
    allowed = {"action", "relativeName", "column", "units"}
    if set(params) - allowed:
        raise HarnessError("Unsupported csv_summary parameter.")
    for key in ("relativeName", "column", "units"):
        if not isinstance(params.get(key), str) or not params[key]:
            raise HarnessError(f"csv_summary requires non-empty {key}.")
    path, relative, base = _target(root, params["relativeName"])
    if path.suffix.casefold() != ".csv":
        raise HarnessError("csv_summary requires a CSV file.")
    raw, text, source = _read_bytes(path, relative, base)
    try:
        rows = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(rows)
    except (csv.Error, StopIteration) as exc:
        raise HarnessError("CSV must contain a valid header.") from exc
    if not header or any(not name or name != name.strip() for name in header) or len(set(header)) != len(header):
        raise HarnessError("CSV header names must be non-empty, exact, and unique.")
    column = params["column"]
    if column not in header:
        raise HarnessError("The requested CSV column is missing.")
    index, values = header.index(column), []
    try:
        for row_number, row in enumerate(rows, start=2):
            if len(row) != len(header) or not row[index].strip():
                raise HarnessError(f"CSV row {row_number} is missing a numeric value.")
            try:
                value = float(row[index])
            except (ValueError, OverflowError) as exc:
                raise HarnessError(f"CSV row {row_number} is not numeric.") from exc
            if not math.isfinite(value):
                raise HarnessError(f"CSV row {row_number} contains a non-finite value.")
            values.append(value)
    except csv.Error as exc:
        raise HarnessError("CSV contains malformed rows.") from exc
    if not values:
        raise HarnessError("CSV contains no numeric data rows.")
    try:
        mean = math.fsum(values) / len(values)
    except OverflowError as exc:
        raise HarnessError("CSV statistics exceed finite numeric range.") from exc
    if not math.isfinite(mean):
        raise HarnessError("CSV statistics exceed finite numeric range.")
    return {"action": "csv_summary", "source": source, "column": column,
            "units": {"value": params["units"], "provenance": "supplied"},
            "statistics": {"count": len(values), "min": min(values), "max": max(values),
                           "mean": mean}}


def handle_work_request(root: str, params: dict) -> dict:
    """Execute one bounded read-only action within a trusted work-folder root."""
    if not isinstance(params, dict):
        raise HarnessError("Assistant work request must be an object.")
    action = params.get("action")
    if action == "list":
        return _list(root, params)
    if action == "read":
        return _read(root, params)
    if action == "csv_summary":
        return _csv_summary(root, params)
    raise HarnessError("Unsupported assistant work-folder action.")
