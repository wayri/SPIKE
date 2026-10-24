# SPDX-License-Identifier: Apache-2.0
"""Non-executing, bounded AMI parameter/package inventory; not an AMI host.

Independently authored against IBIS 8.0 sections 10.1, 10.3 and 10.4.
This intentionally supports only scalar Value/Range/List/Corner descriptors.
No library is loaded, no path is opened, and no simulation input is generated.
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re
from typing import Any

MAX_TEXT_BYTES = 1_048_576
MAX_TOKENS = 65_536
MAX_TOKEN_CHARS = 4096
MAX_DEPTH = 32
MAX_NODES = 8192
MAX_PARAMETERS = 2048
MAX_BINARY_BYTES = 4_194_304
MAX_RESULT_BYTES = 4_194_304
PARAMETER_CONTRACT = "spike/si-ami-parameter-inventory/v1"
PACKAGE_CONTRACT = "spike/si-ami-package-inventory/v1"
PACKAGE_REQUEST_CONTRACT = "spike/si-ami-package-request/v1"
_FORMATS = {"Value", "Range", "List", "Corner"}
_PARAMETER_DESCRIPTORS = {"Usage", "Type", "Format", "Default", "List_Tip"} | _FORMATS
_TYPES = {"Float", "UI", "Integer", "String", "Boolean", "Tap"}
_VERSIONS = {"5.1", "6.0", "6.1", "7.0", "7.1", "7.2", "8.0"}
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z", re.ASCII)
_INTEGER = re.compile(r"([+-]?\d+)(?:[eE]\+?(\d+))?\Z", re.ASCII)
_KNOWN_RESERVED = {"AMI_Version", "Init_Returns_Impulse", "GetWave_Exists", "Resolve_Exists"}


class SiAmiInventoryError(ValueError):
    """Malformed, unsupported or over-budget inventory input."""


@dataclass(frozen=True)
class _Atom:
    text: str
    quoted: bool = False


def _fail(message: str) -> None:
    raise SiAmiInventoryError(message)


def _bounded_result(result: dict[str, Any]) -> dict[str, Any]:
    # Repeated deep paths can expand relative to source text. Count incrementally
    # rather than allocating an unbounded serialized copy for future IPC.
    size = 0
    for fragment in json.JSONEncoder(ensure_ascii=True, allow_nan=False, separators=(",", ":")).iterencode(result):
        size += len(fragment)
        if size > MAX_RESULT_BYTES:
            _fail("AMI inventory result exceeds the 4 MiB response budget.")
    return result


def _text_bytes(text: Any) -> bytes:
    if not isinstance(text, str) or not text or len(text) > MAX_TEXT_BYTES:
        _fail("AMI text must be nonempty and at most 1 MiB.")
    if any(ord(char) > 126 or (ord(char) < 32 and char not in "\t\r\n") for char in text):
        _fail("AMI text must contain printable ASCII, tab or line termination characters.")
    return text.encode("ascii")


def _tree(text: str) -> list[Any]:
    # Iterative construction bounds memory and nesting before semantic descent.
    stack: list[list[Any]] = []
    roots: list[Any] = []
    index = count = nodes = 0
    while index < len(text):
        char = text[index]
        if char in " \t\r\n":
            index += 1
            continue
        if char == "|":
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        count += 1
        if count > MAX_TOKENS:
            _fail("AMI token limit exceeded.")
        if char == "(":
            nodes += 1
            if len(stack) >= MAX_DEPTH or nodes > MAX_NODES:
                _fail("AMI depth or node limit exceeded.")
            branch: list[Any] = []
            (stack[-1] if stack else roots).append(branch)
            stack.append(branch)
            index += 1
        elif char == ")":
            if not stack:
                _fail("Unexpected closing parenthesis.")
            stack.pop()
            index += 1
        else:
            quoted = char == '"'
            start = index + int(quoted)
            index = start
            if quoted:
                while index < len(text) and text[index] != '"':
                    index += 1
                if index == len(text):
                    _fail("Unterminated AMI string.")
                value = text[start:index]
                index += 1
                if index < len(text) and text[index] not in " \t\r\n()|":
                    _fail("AMI tokens require a delimiter after a string.")
            else:
                while index < len(text) and text[index] not in ' \t\r\n()|"':
                    index += 1
                value = text[start:index]
                if index < len(text) and text[index] == '"':
                    _fail("Unexpected quote in an unquoted token.")
            if len(value) > MAX_TOKEN_CHARS:
                _fail("AMI token length limit exceeded.")
            (stack[-1] if stack else roots).append(_Atom(value, quoted))
    if stack or len(roots) != 1 or not isinstance(roots[0], list):
        _fail("AMI requires exactly one balanced root branch.")
    return roots[0]


def _branches(node: list[Any]) -> tuple[str, dict[str, list[Any]]]:
    if not node or not isinstance(node[0], _Atom) or not node[0].text.strip():
        _fail("Every AMI branch requires a nonempty name.")
    name = node[0].text
    if len(name) > 256:
        _fail("AMI branch names are limited to 256 characters.")
    children: dict[str, list[Any]] = {}
    for child in node[1:]:
        if not isinstance(child, list) or not child or not isinstance(child[0], _Atom):
            _fail(f"{name}: expected named child branches.")
        key = child[0].text
        if key in children:
            _fail(f"{name}: duplicate branch or descriptor {key!r}.")
        children[key] = child
    return name, children


def _atoms(node: list[Any]) -> list[_Atom]:
    if any(not isinstance(value, _Atom) for value in node[1:]):
        _fail("Nested descriptor data is unsupported (including Table and ignore blocks).")
    return node[1:]


def _one(node: list[Any]) -> _Atom:
    values = _atoms(node)
    if len(values) != 1:
        _fail(f"{node[0].text} requires exactly one value.")
    return values[0]


def _value(atom: _Atom, kind: str) -> Any:
    value = atom.text
    if kind == "String":
        if not atom.quoted:
            _fail("AMI String values must be double quoted.")
        return value
    if atom.quoted:
        _fail(f"AMI {kind} values cannot be quoted.")
    if kind == "Boolean":
        if value not in {"True", "False"}:
            _fail("AMI Boolean values are exactly True or False.")
        return value == "True"
    if kind == "Integer":
        match = _INTEGER.fullmatch(value)
        if not match or len(match[1].lstrip("+-")) > 10 or len(match[2] or "") > 2:
            _fail("AMI Integer requires a bounded integer with nonnegative exponent.")
        exponent = int(match[2] or "0")
        if exponent > 10:
            _fail("AMI Integer exceeds signed 32-bit range.")
        result = int(match[1]) * 10 ** exponent
        if not -2147483648 <= result <= 2147483647:
            _fail("AMI Integer exceeds signed 32-bit range.")
        return result
    if not _NUMBER.fullmatch(value):
        _fail("AMI numeric values forbid suffixes and nonfinite literals.")
    result = float(value)
    if not math.isfinite(result) or (result == 0 and any(c in "123456789" for c in value.split("e")[0].split("E")[0])):
        _fail("AMI numeric value overflows or underflows finite binary64 inventory.")
    return result


def _description(children: dict[str, list[Any]]) -> str | None:
    return _value(_one(children["Description"]), "String") if "Description" in children else None


def _parameter(node: list[Any], path: list[str]) -> dict[str, Any]:
    name, children = _branches(node)
    allowed = _PARAMETER_DESCRIPTORS | {"Description"}
    if set(children) - allowed or not {"Usage", "Type"} <= children.keys():
        _fail(f"{name}: unsupported descriptor or missing Usage/Type.")
    usage_atom, type_atom = _one(children["Usage"]), _one(children["Type"])
    usage, kind = usage_atom.text, type_atom.text
    if usage_atom.quoted or usage not in {"In", "Out", "InOut", "Info", "Dep"}:
        _fail(f"{name}: invalid Usage.")
    if type_atom.quoted or kind not in _TYPES:
        _fail(f"{name}: unsupported Type.")
    formats = [(key, _atoms(value)) for key, value in children.items() if key in _FORMATS]
    if "Format" in children:
        items = _atoms(children["Format"])
        if not items or items[0].quoted or items[0].text not in _FORMATS:
            _fail(f"{name}: unsupported Format.")
        formats.append((items[0].text, items[1:]))
    if not formats and "Default" in children:
        formats = [("Value", [_one(children["Default"])])]
    elif "Default" in children and any(item[0] == "Value" for item in formats):
        _fail(f"{name}: Value and Default are mutually exclusive.")
    if len(formats) != 1:
        _fail(f"{name}: exactly one supported format is required.")
    form, atoms = formats[0]
    if not atoms or (form == "Value" and len(atoms) != 1) or (form in {"Range", "Corner"} and len(atoms) != 3):
        _fail(f"{name}: incorrect format value count.")
    if usage == "Out" and ("Default" in children or form == "Corner"):
        _fail(f"{name}: Usage Out forbids Default and Corner.")
    if form == "Range" and kind not in {"Float", "UI", "Integer", "Tap"}:
        _fail(f"{name}: Range requires a numeric type.")
    values = [_value(atom, kind) for atom in atoms]
    default = _value(_one(children["Default"]), kind) if "Default" in children else values[0]
    if form == "Range" and not values[1] <= values[0] <= values[2]:
        _fail(f"{name}: Range requires min <= typ <= max.")
    if (form == "Range" and not values[1] <= default <= values[2]) or (form in {"List", "Corner"} and default not in values):
        _fail(f"{name}: Default is outside the declared values.")
    tips: list[str] | None = None
    if "List_Tip" in children:
        tips = [_value(atom, "String") for atom in _atoms(children["List_Tip"])]
        if form != "List" or len(tips) != len(values) or any(not tip for tip in tips):
            _fail(f"{name}: List_Tip must match a nonempty List.")
        value_to_tip: dict[Any, str] = {}
        tip_to_value: dict[str, Any] = {}
        for value, tip in zip(values, tips):
            if (value in value_to_tip and value_to_tip[value] != tip) or (tip in tip_to_value and tip_to_value[tip] != value):
                _fail(f"{name}: List_Tip identities must match List identities.")
            value_to_tip[value], tip_to_value[tip] = tip, value
    return {"path": path, "usage": usage, "type": kind, "format": form,
            "values": values, "default": default if usage != "Out" else None,
            "description": _description(children), "list_tips": tips}


def parse_ami_parameters(text: str, name: str = "model.ami") -> dict[str, Any]:
    """Inspect a strict scalar subset. Admission never authorizes execution."""
    encoded = _text_bytes(text)
    if not isinstance(name, str) or not name or len(name) > 256 or any(not 32 <= ord(c) <= 126 for c in name):
        _fail("AMI source name must be nonempty ASCII of at most 256 characters.")
    root, children = _branches(_tree(text))
    if set(children) - {"Reserved_Parameters", "Model_Specific", "Description"} or "Reserved_Parameters" not in children:
        _fail("AMI root requires Reserved_Parameters and only supported root branches.")
    keys = list(children)
    if "Model_Specific" in keys and keys.index("Reserved_Parameters") > keys.index("Model_Specific"):
        _fail("Reserved_Parameters must precede Model_Specific.")
    parameters: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []

    def visit(node: list[Any], path: list[str]) -> None:
        branch, entries = _branches(node)
        # Description alone can annotate a group. Any other supported leaf
        # identifies a parameter, even when its required descriptors are absent.
        if _PARAMETER_DESCRIPTORS.intersection(entries):
            if len(path) == 1:
                _fail(f"{branch} is a container and cannot contain parameter descriptor leaves.")
            parameters.append(_parameter(node, path))
            if len(parameters) > MAX_PARAMETERS:
                _fail("AMI parameter limit exceeded.")
            return
        groups.append({"path": path, "description": _description(entries)})
        for key, entry in entries.items():
            if key != "Description":
                visit(entry, path + [key])

    for section in ("Reserved_Parameters", "Model_Specific"):
        if section in children:
            visit(children[section], [section])
    reserved = {item["path"][1]: item for item in parameters if len(item["path"]) == 2 and item["path"][0] == "Reserved_Parameters"}
    if not {"AMI_Version", "Init_Returns_Impulse", "GetWave_Exists"} <= reserved.keys():
        _fail("This subset requires AMI_Version, Init_Returns_Impulse and GetWave_Exists.")
    _, reserved_children = _branches(children["Reserved_Parameters"])
    if next((key for key in reserved_children if key != "Description"), None) != "AMI_Version":
        _fail("AMI_Version must be the first reserved parameter.")
    for key in _KNOWN_RESERVED & reserved.keys():
        item = reserved[key]
        if item["usage"] != "Info" or item["format"] != "Value" or item["type"] != ("String" if key == "AMI_Version" else "Boolean"):
            _fail(f"Invalid declaration for {key}.")
    version = reserved["AMI_Version"]["default"]
    if version not in _VERSIONS:
        _fail("AMI version is outside the explicit 5.1 through 8.0 subset.")
    if not reserved["Init_Returns_Impulse"]["default"] and not reserved["GetWave_Exists"]["default"]:
        _fail("GetWave_Exists must be True when Init_Returns_Impulse is False.")
    dependent = any(item["usage"] == "Dep" for item in parameters)
    if (dependent or "Resolve_Exists" in reserved) and tuple(map(int, version.split("."))) < (6, 1):
        _fail("Dependent parameters require AMI 6.1 or later.")
    if dependent and reserved.get("Resolve_Exists", {}).get("default") is not True:
        _fail("Usage Dep requires an explicit Resolve_Exists True declaration.")
    unknown = [item["path"] for item in parameters if item["path"][0] == "Reserved_Parameters" and (len(item["path"]) != 2 or item["path"][1] not in _KNOWN_RESERVED)]
    return _bounded_result({"contract": PARAMETER_CONTRACT, "name": name, "sha256": sha256(encoded).hexdigest(),
            "size_bytes": len(encoded), "root_name": root, "ami_version": version,
            "description": _description(children), "parameters": parameters, "groups": groups,
            "unvalidated_reserved_parameters": unknown, "status": "inventory_only",
            "execution_admitted": False, "abi_verified": False,
            "limitations": ["Scalar syntax subset only; not full IBIS conformance or a simulation result.",
                            "Reserved-parameter semantics beyond the four checked declarations are unvalidated.",
                            "No AMI function, dependency resolution, channel, protocol or executable is run."]})


def _record(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        _fail(f"{label} requires exactly {sorted(keys)}.")
    return value


def _member_name(value: Any) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 256 or not value.isascii():
        _fail("Package member path must be bounded ASCII.")
    if any(char in value for char in '\\:*?"<>|') or any(not 32 <= ord(char) <= 126 for char in value):
        _fail("Package member path contains unsafe characters.")
    for part in value.split("/"):
        stem = part.split(".")[0].upper()
        if part in {"", ".", ".."} or part.endswith((".", " ")) or stem in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(?:COM|LPT)[0-9]", stem):
            _fail("Package member path must be a safe relative member name.")
    return value


def _digest(data: bytes, expected: Any) -> str:
    actual = sha256(data).hexdigest()
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected) or actual != expected:
        _fail("Package member SHA-256 does not match supplied bytes.")
    return actual


def inspect_ami_package(request: dict[str, Any]) -> dict[str, Any]:
    """Hash supplied bytes; paths/platform/direction are declarations, not authority.

    This does not parse .ibs association, inspect executable headers/exports,
    resolve dependencies, extract an archive or access a filesystem path.
    """
    _record(request, {"contract", "direction", "platform", "parameter_file", "executable_file"}, "AMI package")
    if request["contract"] != PACKAGE_REQUEST_CONTRACT or request["direction"] not in ("tx", "rx"):
        _fail("AMI package contract or declared direction is invalid.")
    platform = request["platform"]
    if not isinstance(platform, str) or len(platform) > 128 or not re.fullmatch(r"[A-Za-z0-9.-]+_[A-Za-z0-9.-]+_(?:32|64)", platform):
        _fail("Platform must declare OS_compiler_32 or OS_compiler_64.")
    parameter = _record(request["parameter_file"], {"path", "text", "sha256"}, "Parameter file")
    executable = _record(request["executable_file"], {"path", "base64", "sha256"}, "Executable file")
    parameter_path, executable_path = _member_name(parameter["path"]), _member_name(executable["path"])
    if not parameter_path.endswith(".ami") or parameter_path.casefold() == executable_path.casefold():
        _fail("Parameter file must end in .ami and differ from executable member.")
    parameter_bytes = _text_bytes(parameter["text"])
    _digest(parameter_bytes, parameter["sha256"])
    encoded = executable["base64"]
    if not isinstance(encoded, str) or not encoded or len(encoded) > 4 * ((MAX_BINARY_BYTES + 2) // 3):
        _fail("Executable bytes must be bounded nonempty base64 (4 MiB decoded maximum).")
    try:
        binary = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise SiAmiInventoryError("Invalid executable base64.") from exc
    if not binary or len(binary) > MAX_BINARY_BYTES or base64.b64encode(binary).decode("ascii") != encoded:
        _fail("Executable base64 must be canonical and within 4 MiB.")
    binary_digest = _digest(binary, executable["sha256"])
    inventory = parse_ami_parameters(parameter["text"], parameter_path)
    os_name, compiler, bits = platform.split("_")
    return _bounded_result({"contract": PACKAGE_CONTRACT, "status": "inventory_only", "execution_admitted": False,
            "abi_verified": False, "declared_direction": request["direction"],
            "declared_platform": {"os": os_name, "compiler": compiler, "bits": int(bits)},
            "parameters": inventory,
            "members": [{"path": parameter_path, "sha256": inventory["sha256"], "size_bytes": len(parameter_bytes)},
                        {"path": executable_path, "sha256": binary_digest, "size_bytes": len(binary)}],
            "limitations": ["Caller declarations only: no .ibs binding, binary ABI, exports or dependency verification.",
                            "No file is opened, extracted or executed; hashes grant neither trust nor redistribution rights."]})
