# SPDX-License-Identifier: Apache-2.0
"""Bounded metadata-only index of an explicitly selected local LTspice library.

Source files remain in their original directory. Model bodies are neither
returned nor executed, and discovery makes no compatibility, manufacturer,
redistribution, or qualification claim.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat
from .vendor_intake import inspect_text


EXTENSIONS = frozenset({".lib", ".sub", ".cir", ".mod", ".asy",
                        ".bjt", ".dio", ".mos", ".jft"})
MAX_FILES = 20000
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_ENTRIES = 100000
MAX_WALK_ENTRIES = 100000
_SYMATTR = re.compile(r"^\s*SYMATTR\s+(Value|SpiceModel|ModelFile|Prefix)\s*(.*?)\s*$", re.I)
_SYMBOL_TYPE = re.compile(r"^\s*SymbolType\s+(\S+)\s*$", re.I)


def index_library(path, *, max_files=MAX_FILES, max_total_bytes=MAX_TOTAL_BYTES,
                  max_file_bytes=MAX_FILE_BYTES, max_entries=MAX_ENTRIES,
                  max_walk_entries=MAX_WALK_ENTRIES):
    """Return a JSON-serializable, inert inventory of ``path``.

    The caller must supply the directory explicitly. Includes and model-file
    references are recorded as text metadata only and are never followed.
    """
    limits = (max_files, max_total_bytes, max_file_bytes, max_entries, max_walk_entries)
    if any(type(value) is not int or value < 1 for value in limits):
        raise ValueError("LTspice index limits must be positive integers")
    selected = Path(path).absolute()
    if _is_link(selected):
        raise ValueError("Select the actual LTspice library directory, not a link or junction")
    try:
        root = selected.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"Cannot open LTspice library directory: {exc}") from exc
    if not root.is_dir():
        raise ValueError("LTspice library path must be a directory")
    result = {
        "contract": "spikes/ltspice-local-library/v1",
        "root": str(root), "files": [], "models": [], "symbols": [], "diagnostics": [],
        "limits": {"files": max_files, "total_bytes": max_total_bytes,
                   "file_bytes": max_file_bytes, "entries": max_entries,
                   "walk_entries": max_walk_entries},
        "status": {"complete": True, "execution": "not_executed",
                   "compatibility": "not_qualified", "redistribution": "not_granted"},
        "notice": ("Local declaration metadata only. LTspice dialect models may not run in SPIKES; "
                   "symbol or declaration presence is not a manufacturer-part or qualification claim."),
    }
    total_bytes = walked = attempted_files = 0
    pending = [root]
    while pending and result["status"]["complete"]:
        directory = pending.pop()
        try:
            with os.scandir(directory) as listing:
                children=[]
                for child in listing:
                    children.append(child);walked+=1
                    if walked>=max_walk_entries:
                        relative=Path(child.path).relative_to(root).as_posix()
                        _truncate(result,relative,"walk_entry_limit","Directory-entry limit reached")
                        break
                children.sort(key=lambda item:item.name.casefold(),reverse=True)
        except OSError as exc:
            _diagnostic(result, directory.relative_to(root).as_posix() or ".", "directory_error", exc)
            continue
        for child in children:
            relative = Path(child.path).relative_to(root).as_posix()
            target = Path(child.path)
            if child.is_symlink():
                _diagnostic(result, relative, "link_skipped", "Links and junctions are not indexed")
                continue
            try:
                if child.is_dir(follow_symlinks=False):
                    if getattr(target,"is_junction",lambda:False)():
                        _diagnostic(result,relative,"link_skipped","Links and junctions are not indexed")
                        continue
                    pending.append(target)
                    continue
                if not child.is_file(follow_symlinks=False) or target.suffix.lower() not in EXTENSIONS:
                    continue
                if attempted_files >= max_files:
                    _truncate(result, relative, "file_limit", "Supported-file limit reached")
                    break
                attempted_files += 1
                size = child.stat(follow_symlinks=False).st_size
                if size > max_file_bytes:
                    _diagnostic(result, relative, "file_too_large",
                                f"File exceeds {max_file_bytes} byte limit")
                    continue
                if total_bytes + size > max_total_bytes:
                    _truncate(result, relative, "byte_limit", "Total byte limit reached")
                    break
                raw = _read_regular(target, max_file_bytes)
                total_bytes += len(raw)
                digest = hashlib.sha256(raw).hexdigest()
                result["files"].append({"source_path": relative, "bytes": len(raw), "sha256": digest})
                text = _decode(raw, result, relative)
                if text is None:
                    continue
                if target.suffix.lower() == ".asy":
                    if len(result["models"]) + len(result["symbols"]) >= max_entries:
                        _truncate(result, relative, "entry_limit", "Model/symbol entry limit reached")
                        break
                    result["symbols"].append(_parse_symbol(text, relative, digest))
                else:
                    try:
                        report = inspect_text(text, relative)
                    except ValueError as exc:
                        _diagnostic(result, relative, "no_declarations", exc)
                        continue
                    declarations = (("model", item) for item in report["models"])
                    declarations = (*declarations,
                                    *(("subckt", item) for item in report["subcircuits"]))
                    for kind, item in declarations:
                        if len(result["models"]) + len(result["symbols"]) >= max_entries:
                            _truncate(result, relative, "entry_limit", "Model/symbol entry limit reached")
                            break
                        identifier = hashlib.sha256(
                            f"{relative}\0{item['line']}\0{kind}\0{item['name']}".encode()).hexdigest()
                        result["models"].append(
                            {"id": identifier, "name": item["name"], "kind": kind,
                             "pins": list(item.get("pins", [])), "source_path": relative,
                             "sha256": digest, "line": item["line"]})
                    if not result["status"]["complete"]:
                        break
            except (OSError, ValueError) as exc:
                _diagnostic(result, relative, "file_error", exc)
    _join_symbol_dependencies(result)
    result["files"].sort(key=lambda item: item["source_path"].casefold())
    result["models"].sort(key=lambda item: (item["name"].casefold(), item["source_path"], item["id"]))
    result["symbols"].sort(key=lambda item: (item.get("value", "").casefold(), item["source_path"]))
    result["counts"] = {"files_attempted": attempted_files, "files": len(result["files"]), "bytes": total_bytes,
                        "models": len(result["models"]), "symbols": len(result["symbols"]),
                        "walk_entries": walked}
    return result


def _is_link(path):
    try:
        return path.is_symlink() or getattr(path, "is_junction", lambda: False)()
    except OSError:
        return True


def _read_regular(path, limit):
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("Source is not a regular file")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > limit:
        raise ValueError("File grew beyond its byte limit while reading")
    if (before.st_dev, before.st_ino, before.st_size) != (after.st_dev, after.st_ino, len(raw)):
        raise ValueError("File changed while indexing")
    return raw


def _decode(raw, result, source_path):
    try:
        text,encoding=_decode_text(raw)
    except (UnicodeDecodeError,ValueError) as exc:
        _diagnostic(result,source_path,"binary_skipped",exc);return None
    if encoding!="UTF-8":_diagnostic(result,source_path,"encoding_fallback",f"Decoded as {encoding}")
    return text


def _decode_text(raw):
    if raw.startswith((b"\xff\xfe",b"\xfe\xff")):
        text=raw.decode("utf-16",errors="strict");encoding="UTF-16 BOM"
    elif raw.startswith(b"\xef\xbb\xbf"):
        text=raw.decode("utf-8-sig",errors="strict");encoding="UTF-8"
    else:
        probe=raw[:min(len(raw),4096)];pairs=len(probe)//2
        bomless=(len(raw)%2==0 and pairs>=4
                 and sum(probe[i]==0 for i in range(1,pairs*2,2))/pairs>=.60
                 and sum(probe[i]==0 for i in range(0,pairs*2,2))/pairs<=.05)
        if bomless:text=raw.decode("utf-16-le",errors="strict");encoding="UTF-16LE (no BOM)"
        else:
            try:text=raw.decode("utf-8",errors="strict");encoding="UTF-8"
            except UnicodeDecodeError:text=raw.decode("cp1252",errors="strict");encoding="Windows-1252"
    if "\x00" in text or any(ord(char)<32 and char not in "\t\r\n" for char in text):
        raise ValueError("Decoded file contains NUL or unsupported control characters")
    return text,encoding


def _parse_symbol(text, source_path, digest):
    metadata = {"symbol_type": "", "value": "", "spice_model": "",
                "model_file": "", "prefix": ""}
    for line in text.splitlines():
        symbol = _SYMBOL_TYPE.match(line)
        if symbol:
            metadata["symbol_type"] = symbol.group(1)
            continue
        attribute = _SYMATTR.match(line)
        if attribute:
            key = {"value": "value", "spicemodel": "spice_model",
                   "modelfile": "model_file", "prefix": "prefix"}[attribute.group(1).casefold()]
            metadata[key] = attribute.group(2)
    metadata.update(id=hashlib.sha256(f"{source_path}\0symbol".encode()).hexdigest(),
                    source_path=source_path, sha256=digest)
    return metadata


def _join_symbol_dependencies(result):
    """Bind only explicit ModelFile or LTspice standard-prefix dependencies."""
    standard = {"Q": "cmp/standard.bjt", "D": "cmp/standard.dio",
                "M": "cmp/standard.mos", "J": "cmp/standard.jft"}
    declarations = {}
    for item in result["models"]:
        declarations.setdefault((item["source_path"].casefold(),item["name"].casefold()),[]).append(item["id"])
    for symbol in result["symbols"]:
        spice_model=symbol["spice_model"];declared_file=symbol["model_file"].replace("\\", "/").lstrip("/")
        if not declared_file and Path(spice_model).suffix.casefold() in EXTENSIONS:
            declared_file=spice_model;name=symbol["value"]
        else:name=spice_model or symbol["value"]
        expected = ((declared_file if declared_file.casefold().startswith(("sub/","cmp/"))
                     else "sub/"+declared_file).casefold() if declared_file else standard.get(
                         symbol["prefix"].upper(), "").casefold())
        matches=declarations.get((expected,name.casefold()),[]) if expected and name else []
        symbol["dependency"] = {"source_path": expected, "model_name": name,
                                "model_ids": list(matches)}


def read_model_file(index, model_id):
    """Revalidate and return the full selected source file without following dependencies."""
    matches=[item for item in index.get("models",[]) if item.get("id")==model_id]
    if len(matches)!=1:raise ValueError("Unknown or ambiguous LTspice model declaration")
    entry=matches[0];root=Path(index.get("root","")).absolute()
    if _is_link(root):raise ValueError("LTspice library root has become a link or junction")
    try:root=root.resolve(strict=True)
    except OSError as exc:raise ValueError(f"Cannot reopen LTspice library root: {exc}") from exc
    if not root.is_dir():raise ValueError("LTspice library root is no longer a directory")
    target=_contained_file(root,entry.get("source_path",""))
    configured=index.get("limits",{}).get("file_bytes",MAX_FILE_BYTES)
    if type(configured) is not int or configured<1:raise ValueError("Invalid recorded LTspice file limit")
    raw=_read_regular(target,min(configured,MAX_FILE_BYTES))
    if hashlib.sha256(raw).hexdigest()!=entry.get("sha256"):
        raise ValueError("LTspice model source changed since indexing; rescan before review")
    try:return _decode_text(raw)[0]
    except (UnicodeDecodeError,ValueError) as exc:
        raise ValueError(f"LTspice model source is no longer supported plain text: {exc}") from exc


def read_model_declaration(index,model_id):
    """Return one unchanged intrinsic .MODEL declaration and its continuations."""
    matches=[item for item in index.get("models",[]) if item.get("id")==model_id]
    if len(matches)!=1:raise ValueError("Unknown or ambiguous LTspice model declaration")
    entry=matches[0]
    if entry.get("kind")!="model":
        raise ValueError("SUBCKT import requires full dependency-aware source review")
    text=read_model_file(index,model_id);lines=text.splitlines(keepends=True);candidates=[]
    for position,line in enumerate(lines):
        match=re.match(r"^\s*\.model\s+(\S+)",line,re.I)
        if match and match.group(1).casefold()==entry["name"].casefold():candidates.append(position)
    if len(candidates)!=1:raise ValueError("Model name is ambiguous within its source file")
    start=candidates[0]
    if entry.get("line") is not None and entry["line"]!=start+1:
        raise ValueError("Model declaration location changed since indexing")
    end=start+1
    cursor=end
    while cursor<len(lines):
        stripped=lines[cursor].strip()
        if not stripped or stripped.startswith("*"):cursor+=1;continue
        if lines[cursor].lstrip().startswith("+"):end=cursor+1;cursor+=1;continue
        break
    return "".join(lines[start:end])


def _contained_file(root,source_path):
    relative=Path(source_path)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("LTspice model path must remain inside the indexed library")
    target=root
    for part in relative.parts:
        target=target/part
        if _is_link(target):raise ValueError("Links and junctions are not accepted in model paths")
    try:resolved=target.resolve(strict=True)
    except OSError as exc:raise ValueError(f"Cannot reopen LTspice model source: {exc}") from exc
    if not resolved.is_relative_to(root):raise ValueError("LTspice model path escapes the indexed library")
    return resolved


def _diagnostic(result, source_path, code, message):
    result["diagnostics"].append({"source_path": source_path, "code": code, "message": str(message)})


def _truncate(result, source_path, code, message):
    result["status"]["complete"] = False
    _diagnostic(result, source_path, code, message)
