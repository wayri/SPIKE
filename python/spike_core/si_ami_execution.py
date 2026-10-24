# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Explicitly trusted native AMI development runs, never in-process DLL loading.

Windows x64/system-only imports are the admitted platform. No sandbox or vendor
qualification is claimed. See docs/SI_AMI_EXECUTION.md for the security boundary.
"""
from __future__ import annotations

from hashlib import sha256
import io
import json
import math
import os
from pathlib import Path
import platform
import re
import struct
import tempfile
from typing import Callable

from .circuit_worker_supervisor import supervise_process
from .si_ami_inventory import SiAmiInventoryError, _Atom, _NUMBER, _tree, parse_ami_parameters

REQUEST_CONTRACT = "spike/si-ami-execution-request/v1"
RESULT_CONTRACT = "spike/si-ami-execution-result/v1"
MAX_SAMPLES = 65_536
MAX_OUTPUT = 4_194_304
MAX_BINARY = 33_554_432
TRUST_ACKNOWLEDGEMENT = "trusted-native-code-with-current-user-access"


class SiAmiExecutionError(ValueError):
    """Admission, lifecycle, supervision or bounded result failure."""


def _fail(message: str):
    raise SiAmiExecutionError(message)


def _exact(value, fields: set[str], label: str):
    if not isinstance(value, dict) or set(value) != fields:
        _fail(f"{label} must contain exactly {sorted(fields)}")


def _identity(member: dict, *, dll: bool) -> tuple[Path, bytes]:
    _exact(member, {"path", "sha256"}, "executable member")
    if not isinstance(member["path"], str) or not member["path"].isascii():
        _fail("executable path must be ASCII")
    path = Path(member["path"])
    if not path.is_absolute() or not path.is_file() or path != path.resolve():
        _fail("executable path must be an absolute normalized regular file")
    for part in (path, *path.parents):
        state = part.lstat()
        if part.is_symlink() or getattr(state, "st_file_attributes", 0) & 0x400:
            _fail("executable path cannot contain reparse points")
    if not isinstance(member["sha256"], str) or not re.fullmatch("[0-9a-f]{64}", member["sha256"]):
        _fail("executable SHA-256 must be lowercase hexadecimal")
    with path.open("rb") as stream:
        data = stream.read(MAX_BINARY + 1)
    if len(data) > MAX_BINARY or sha256(data).hexdigest() != member["sha256"]:
        _fail("executable size or SHA-256 admission failed")
    _pe_system_imports(data, dll=dll)
    return path, data


def _pe_system_imports(data: bytes, *, dll: bool) -> list[str]:
    """Inspect PE64 import metadata without loading code. No delay imports."""
    def u16(offset): return struct.unpack_from("<H", data, offset)[0]
    def u32(offset): return struct.unpack_from("<I", data, offset)[0]
    try:
        pe = u32(0x3c)
        if data[:2] != b"MZ" or data[pe:pe + 4] != b"PE\0\0" or u16(pe + 4) != 0x8664:
            _fail("only AMD64 PE binaries are admitted")
        optional = pe + 24
        section_count, optional_size = u16(pe + 6), u16(pe + 20)
        if not 0 < section_count <= 96 or optional_size < 240 or u16(optional) != 0x20b:
            _fail("unsupported PE headers")
        if bool(u16(pe + 22) & 0x2000) != dll:
            _fail("PE executable/library kind mismatch")
        if u32(optional + 108) < 14:
            _fail("incomplete PE data directories")
        if u32(optional + 112 + 13 * 8) or u32(optional + 116 + 13 * 8):
            _fail("delay-loaded dependencies are unsupported")
        sections = optional + optional_size

        def offset(rva):
            for index in range(section_count):
                section = sections + index * 40
                start, size, raw = u32(section + 12), u32(section + 16), u32(section + 20)
                if start <= rva < start + size and raw + rva - start < len(data):
                    return raw + rva - start
            _fail("PE import RVA outside raw sections")

        imports = []
        rva, size = u32(optional + 120), u32(optional + 124)
        if not rva and not size:
            return imports
        if not rva or not 20 <= size <= 20 * 257:
            _fail("PE import directory exceeds admission bounds")
        table = offset(rva)
        for index in range(min(size // 20, 257)):
            entry = struct.unpack_from("<5I", data, table + index * 20)
            if not any(entry):
                return imports
            start = offset(entry[3])
            end = data.find(b"\0", start, start + 260)
            if end < 0:
                _fail("unterminated PE dependency name")
            name = data[start:end].decode("ascii").lower()
            if name not in {"kernel32.dll", "msvcrt.dll", "ucrtbase.dll"} and not re.fullmatch(
                r"api-ms-win-crt-[a-z0-9-]+\.dll", name
            ):
                _fail(f"non-system or unsupported dependency: {name}")
            imports.append(name)
        _fail("unterminated PE import directory")
    except (struct.error, UnicodeError, IndexError) as error:
        raise SiAmiExecutionError("malformed PE metadata") from error


def _parameter_input(source: str) -> tuple[dict, str]:
    inventory = parse_ami_parameters(source)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", inventory["root_name"]):
        _fail("unsupported executable parameter root name")
    reserved = {}
    selected = []
    for item in inventory["parameters"]:
        path = item["path"]
        if path[0] == "Reserved_Parameters":
            if len(path) != 2 or path[1] not in {"AMI_Version", "Init_Returns_Impulse", "GetWave_Exists", "Resolve_Exists"}:
                _fail("unimplemented reserved parameter prevents execution")
            reserved[path[1]] = item["default"]
        elif item["usage"] in {"In", "InOut"}:
            if len(path) != 2 or item["default"] is None:
                _fail("execution supports flat model parameters with explicit defaults only")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", path[-1]):
                _fail("unsupported executable model parameter name")
            value = item["default"]
            if item["type"] == "UI":
                _fail("symbolic UI model parameters are unsupported")
            if isinstance(value, str):
                if any(char in value for char in '\\"\r\n'):
                    _fail("unsupported string escape in selected AMI parameter")
                encoded = '"' + value + '"'
            elif isinstance(value, bool):
                encoded = "True" if value else "False"
            else:
                encoded = str(value)
            selected.append(f"({path[-1]} {encoded})")
        elif item["usage"] == "Dep":
            _fail("AMI_Resolve is unsupported")
    if reserved.get("Resolve_Exists"):
        _fail("AMI_Resolve is unsupported")
    parameters = f"({inventory['root_name']} {' '.join(selected)})"
    if len(parameters) > 16384:
        _fail("selected parameters exceed host string budget")
    return {"inventory": inventory, "reserved": reserved}, parameters


def _vector(value, label):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_SAMPLES:
        _fail(f"{label} must contain 1..{MAX_SAMPLES} samples")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in value):
        _fail(f"{label} samples must be finite numbers")
    return [float(x) for x in value]


def _output_parameters(value: str, root: str) -> str:
    """Validate a complete bounded output tree, not its descriptor semantics."""
    quoted = False
    for character in value:
        if character == '"':
            quoted = not quoted
        elif character == '|' and not quoted:
            _fail("AMI output parameter comments are unsupported")
    try:
        tree = _tree(value)
    except SiAmiInventoryError as error:
        raise SiAmiExecutionError(f"malformed AMI output parameter tree: {error}") from error
    if not tree or not isinstance(tree[0], _Atom) or tree[0].quoted or tree[0].text != root:
        _fail("AMI output root name mismatch")
    pending = [(tree, True)]
    while pending:
        node, is_root = pending.pop()
        if (not node or not isinstance(node[0], _Atom) or node[0].quoted or
                not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", node[0].text)):
            _fail("malformed AMI output parameter name")
        children = node[1:]
        if not children and not is_root:
            _fail("malformed empty AMI output parameter group")
        if all(isinstance(child, list) for child in children):
            pending.extend((child, False) for child in children)
        elif not is_root and all(isinstance(child, _Atom) for child in children):
            for atom in children:
                if not atom.quoted and atom.text not in {"True", "False"}:
                    if not _NUMBER.fullmatch(atom.text) or not math.isfinite(float(atom.text)):
                        _fail("malformed AMI output parameter value")
        else:
            _fail("malformed AMI output parameter group")
    return value


def _decode(data: bytes, request: dict, root: str) -> dict:
    stream = io.BytesIO(data)
    def read(fmt):
        size = struct.calcsize(fmt)
        value = stream.read(size)
        if len(value) != size:
            _fail("truncated AMI host result")
        return struct.unpack(fmt, value)[0]
    def text():
        length = read("<I")
        if length > 16384:
            _fail("AMI result string exceeds budget")
        value = stream.read(length)
        if len(value) != length:
            _fail("truncated AMI result string")
        try:
            return value.decode("ascii")
        except UnicodeError as error:
            raise SiAmiExecutionError("non-ASCII AMI result") from error
    def parameters():
        return _output_parameters(text(), root)
    def array(expected=None):
        count = read("<I")
        if count > MAX_SAMPLES or (expected is not None and count != expected):
            _fail("AMI result sample count mismatch")
        values = [read("<d") for _ in range(count)]
        if any(not math.isfinite(value) for value in values):
            _fail("non-finite AMI result")
        return values
    if stream.read(8) != b"SPKAMO1\0":
        _fail("invalid AMI host result version")
    status, message = read("<I"), text()
    if status != 0:
        _fail(f"native AMI lifecycle failure: {message}")
    result = {"init_parameters_out": parameters(), "init_message": text(),
              "impulse_response": array(len(request["impulse_response"])), "blocks": []}
    if read("<I") != len(request["wave_blocks"]):
        _fail("AMI result block count mismatch")
    last = -1.0
    for source in request["wave_blocks"]:
        block = {"parameters_out": parameters(), "wave": array(len(source)), "clock_times_s": array()}
        for clock in block["clock_times_s"]:
            if clock < 0 or clock <= last:
                _fail("nonmonotonic AMI result clock")
            last = clock
        if request["direction"] == "tx" and block["clock_times_s"]:
            _fail("unexpected Tx clock output")
        result["blocks"].append(block)
    if stream.read(1):
        _fail("trailing AMI host result bytes")
    return result


def execute_ami_native(request: dict, *, host_path: str, host_sha256: str,
                       job_parent: str | None = None,
                       cancelled: Callable[[], bool] = lambda: False) -> dict:
    """Run one explicitly admitted Init / ordered GetWave blocks / Close session."""
    _exact(request, {"contract", "platform", "direction", "model_file", "dependencies", "trust",
                     "parameter_text", "sample_interval_s", "symbol_time_s", "impulse_response",
                     "wave_blocks", "timeout_s", "memory_limit_mib"}, "AMI execution request")
    if request["contract"] != REQUEST_CONTRACT:
        _fail("unsupported execution contract")
    if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64"} or request["platform"] != "windows-x86_64":
        _fail("native execution currently requires Windows x64 Job Object enforcement")
    _exact(request["trust"], {"acknowledgement", "license_reviewed", "dependency_reviewed"}, "trust admission")
    if (request["trust"]["acknowledgement"] != TRUST_ACKNOWLEDGEMENT or
            request["trust"]["license_reviewed"] is not True or request["trust"]["dependency_reviewed"] is not True):
        _fail("explicit native-code trust, license and dependency review are required")
    if request["dependencies"] != []:
        _fail("non-system dependencies are not admitted in this host revision")
    if request["direction"] not in {"tx", "rx"}:
        _fail("direction must be tx or rx")
    for key in ("sample_interval_s", "symbol_time_s", "timeout_s"):
        value = request[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            _fail(f"{key} must be positive and finite")
    if request["symbol_time_s"] < request["sample_interval_s"] or request["timeout_s"] > 300:
        _fail("sample interval or timeout exceeds development admission")
    memory = request["memory_limit_mib"]
    if isinstance(memory, bool) or not isinstance(memory, int) or not 32 <= memory <= 2048:
        _fail("memory_limit_mib must be 32..2048")
    metadata, parameters = _parameter_input(request["parameter_text"])
    impulse = _vector(request["impulse_response"], "impulse response")
    if not isinstance(request["wave_blocks"], list) or len(request["wave_blocks"]) > 64:
        _fail("wave_blocks must contain at most 64 blocks")
    waves = [_vector(block, "wave block") for block in request["wave_blocks"]]
    if sum(map(len, waves)) > MAX_SAMPLES:
        _fail("total waveform sample budget exceeded")
    if waves and not metadata["reserved"]["GetWave_Exists"]:
        _fail("parameter file declares no GetWave")
    if not waves and not metadata["reserved"]["Init_Returns_Impulse"]:
        _fail("Init-only execution requires Init_Returns_Impulse")
    host, _ = _identity({"path": host_path, "sha256": host_sha256}, dll=False)
    _, library_bytes = _identity(request["model_file"], dll=True)
    # Stage exact model bytes into the fresh job: the native loader never opens
    # the original mutable model path. Host installation remains trusted.
    with tempfile.TemporaryDirectory(prefix="spike-ami-", dir=job_parent) as directory:
        job = Path(directory).resolve()
        library = job / "model.dll"
        library.write_bytes(library_bytes)
        packet = bytearray(b"SPKAMI1\0")
        packet += struct.pack("<IIIddI", len(impulse), len(waves), int(request["direction"] == "rx"),
                              request["sample_interval_s"], request["symbol_time_s"], len(parameters))
        packet += parameters.encode("ascii")
        packet += struct.pack(f"<{len(impulse)}d", *impulse)
        for wave in waves:
            packet += struct.pack("<I", len(wave)) + struct.pack(f"<{len(wave)}d", *wave)
        (job / "request.bin").write_bytes(packet)
        outcome = supervise_process(host, [str(library), "request.bin", "result.bin"], cwd=job,
                                    timeout_seconds=request["timeout_s"], memory_limit_mib=memory,
                                    cancelled=cancelled)
        if outcome.status != "completed":
            _fail(f"AMI execution {outcome.status}")
        output = job / "result.bin"
        if not output.is_file() or output.stat().st_size > MAX_OUTPUT:
            _fail("AMI host crashed or returned an oversized/missing result")
        with output.open("rb") as stream:
            result = _decode(stream.read(MAX_OUTPUT + 1), request, metadata["inventory"]["root_name"])
        if outcome.returncode != 0:
            _fail(f"AMI host process failed: {outcome.returncode}")
    result.update({"contract": RESULT_CONTRACT, "status": "completed", "model_status": "experimental",
                   "production_qualified": False,
                   "execution_mode": "trusted_native_development", "sandboxed": False,
                   "qualification": "synthetic_abi_only", "init_returns_impulse": metadata["reserved"]["Init_Returns_Impulse"],
                   "provenance": {"model_sha256": request["model_file"]["sha256"], "host_sha256": host_sha256,
                                  "parameter_sha256": metadata["inventory"]["sha256"],
                                  "request_sha256": sha256(json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
                                  "sample_interval_s": request["sample_interval_s"], "symbol_time_s": request["symbol_time_s"],
                                  "direction": request["direction"],
                                  "os_enforcement": outcome.os_enforcement}})
    if not result["init_returns_impulse"]:
        result["impulse_response"] = None
    if len(json.dumps(result, allow_nan=False).encode()) > MAX_OUTPUT:
        _fail("AMI JSON result exceeds transport budget")
    return result
