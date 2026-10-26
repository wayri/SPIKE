# SPDX-License-Identifier: Apache-2.0
"""Bounded, inert inspection of an explicit subset of SPICE model libraries.

Supports flat .subckt/.ends definitions, .param/.model cards, + continuations,
and ordinary device cards. No dialect translation, expression evaluation, file
resolution or numerical qualification is performed. Syntax reference: ngspice
43 manual, circuit description and parametric subcircuits (independent parser).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

from .spice_netlist_safety import FORBIDDEN_DIRECTIVES
from .spice_workspace import (
    IDENTIFIER, PIN_IDENTIFIER, MAX_MODELS, MAX_MODEL_SOURCE_BYTES,
    MAX_VALUE_EXPRESSION_CHARS, MODEL_ANALYSIS_DIRECTIVES, _validate_model_source,
)

INSPECTION_CONTRACT = "spike/spice-model-library-inspection/v1"
MAX_PHYSICAL_LINES = 32768
MAX_LOGICAL_LINES = 16384
MAX_LINE_CHARS = 16384
MAX_DEPENDENCY_DEPTH = 64
MAX_CALLS = 8192
MAX_INSPECTION_BYTES = 4 * 1024 * 1024
_FILE_SYNTAX = re.compile(r"\b(?:file|filename|file_name|pwlfile)\b|\b(?:read|write|load|include|source|shell)\s*\(", re.I)


class ModelLibraryError(ValueError):
    def __init__(self, message: str, line: int = 0, code: str = "SPICE_LIBRARY_REJECTED"):
        super().__init__(message)
        self.line, self.code = line, code


@dataclass
class _Subcircuit:
    name: str
    pins: list[str]
    defaults: dict[str, str]
    line: int
    lines: list[str] = field(default_factory=list)
    calls: list[tuple[str, int, dict[str, str], int]] = field(default_factory=list)
    parameters: set[str] = field(default_factory=set)
    devices: set[str] = field(default_factory=set)
    model_cards: list[tuple[list[str], int]] = field(default_factory=list)
    model_names: set[str] = field(default_factory=set)


def _tokens(text: str, line: int) -> list[str]:
    """Split only outside balanced expression groups; never interpret a value."""
    tokens, token, stack = [], [], []
    for char in text:
        if char in "({":
            stack.append(char)
            if len(stack) > 32:
                raise ModelLibraryError("Expression nesting exceeds 32 levels.", line)
        elif char in ")}":
            if not stack or stack.pop() != {"}": "{", ")": "("}[char]:
                raise ModelLibraryError("Unbalanced expression delimiters.", line)
        if not stack and (char.isspace() or char == "="):
            if token:
                tokens.append("".join(token)); token = []
            if char == "=":
                tokens.append(char)
        else:
            token.append(char)
    if stack:
        raise ModelLibraryError("Unbalanced expression delimiters.", line)
    if token:
        tokens.append("".join(token))
    return tokens


def _assignments(tokens: list[str], line: int) -> dict[str, str]:
    values, seen = {}, set()
    if not tokens or len(tokens) % 3:
        raise ModelLibraryError("Expected explicit name=value assignments; group spaced expressions in braces.", line)
    for index in range(0, len(tokens), 3):
        name, equals, value = tokens[index:index + 3]
        if (not IDENTIFIER.fullmatch(name) or equals != "=" or value == "="
                or len(value) > MAX_VALUE_EXPRESSION_CHARS or name.casefold() in seen):
            raise ModelLibraryError("Invalid, duplicate or oversized parameter assignment.", line)
        seen.add(name.casefold()); values[name] = value
    return values


def _arguments(tokens: list[str], line: int) -> tuple[list[str], dict[str, str]]:
    for index, token in enumerate(tokens):
        if token.lower().startswith("params:"):
            if token.lower() != "params:":
                raise ModelLibraryError("PARAMS: must be a separate token.", line)
            return tokens[:index], _assignments(tokens[index + 1:], line)
        if token == "=":
            if index == 0:
                raise ModelLibraryError("Missing parameter name.", line)
            return tokens[:index - 1], _assignments(tokens[index - 1:], line)
    return tokens, {}


def _logical_lines(text: str, max_bytes: int = MAX_MODEL_SOURCE_BYTES) -> list[tuple[int, str]]:
    if not isinstance(text, str) or not text.strip():
        raise ModelLibraryError("Library source must be nonempty text.")
    if len(text) > max_bytes:
        raise ModelLibraryError(f"Library source exceeds {max_bytes} bytes.")
    # No alternate line separators or command delimiters can hide a directive.
    if any(ord(char) < 32 and char not in "\r\n\t" or ord(char) > 126 for char in text):
        raise ModelLibraryError("This import subset accepts ASCII source and ordinary line endings only.")
    physical = text.splitlines()
    if len(physical) > MAX_PHYSICAL_LINES:
        raise ModelLibraryError("Library exceeds the physical line limit.")
    logical: list[tuple[int, str]] = []
    for number, raw in enumerate(physical, 1):
        if len(raw) > MAX_LINE_CHARS:
            raise ModelLibraryError("Source line exceeds the length limit.", number)
        stripped = raw.strip()
        if not stripped or stripped.startswith("*"):
            continue
        # Dollar comments are supported; quoted strings/paths and command chains are not.
        stripped = stripped.split("$", 1)[0].rstrip()
        if not stripped:
            continue
        if any(char in stripped for char in "\"'`;\\") or _FILE_SYNTAX.search(stripped):
            raise ModelLibraryError("Quoted, file-bearing or command syntax is outside the import subset.", number)
        if stripped.startswith("+"):
            if not logical or logical[-1][1].lower().startswith(".ends"):
                raise ModelLibraryError("Orphan continuation line.", number)
            start, previous = logical[-1]
            joined = previous + " " + stripped[1:].strip()
            if len(joined) > MAX_LINE_CHARS:
                raise ModelLibraryError("Continued statement exceeds the length limit.", number)
            logical[-1] = (start, joined)
        else:
            logical.append((number, stripped))
            if len(logical) > MAX_LOGICAL_LINES:
                raise ModelLibraryError("Library exceeds the logical line limit.", number)
    return logical


def _parse(text: str, *, resolve: bool = True, max_bytes: int = MAX_MODEL_SOURCE_BYTES) -> tuple[dict[str, _Subcircuit], dict[tuple[str, str], str]]:
    subcircuits, globals_, model_names = {}, {}, set()
    current = None
    calls = 0
    for line, statement in _logical_lines(text, max_bytes):
        tokens = _tokens(statement, line)
        command = tokens[0].lower()
        normalized = " ".join(tokens)
        if command in FORBIDDEN_DIRECTIVES or command in MODEL_ANALYSIS_DIRECTIVES:
            raise ModelLibraryError(f"Disallowed directive: {command}.", line)
        if command == ".subckt":
            if current is not None:
                raise ModelLibraryError("Lexically nested subcircuit definitions are unsupported.", line)
            fields, defaults = _arguments(tokens[1:], line)
            if len(fields) < 2 or not IDENTIFIER.fullmatch(fields[0]):
                raise ModelLibraryError("Subcircuit requires a name and explicit pins.", line)
            name, pins = fields[0], fields[1:]
            if (len(pins) > 512 or any(not PIN_IDENTIFIER.fullmatch(pin) for pin in pins)
                    or len({pin.casefold() for pin in pins}) != len(pins)):
                raise ModelLibraryError("Subcircuit pins must be unique bounded node identifiers.", line)
            if name.casefold() in subcircuits or len(subcircuits) + len(model_names) >= MAX_MODELS:
                raise ModelLibraryError("Duplicate subcircuit name or more than 1024 definitions.", line)
            current = _Subcircuit(name, pins, defaults, line, [normalized],
                                  parameters={key.casefold() for key in defaults})
            subcircuits[name.casefold()] = current
        elif command == ".ends":
            if (current is None or len(tokens) > 2
                    or len(tokens) == 2 and tokens[1].casefold() != current.name.casefold()):
                raise ModelLibraryError("Unmatched or mismatched .ends declaration.", line)
            current.lines.append(f".ends {current.name}")
            current = None
        elif command == ".param":
            values = _assignments(tokens[1:], line)
            for name, value in values.items():
                key = ("param", name.casefold())
                if key in globals_ and current is None or current is not None and key[1] in current.parameters:
                    raise ModelLibraryError("Duplicate parameter in the same scope.", line)
                card = f".param {name} = {value}"
                if current is None:
                    globals_[key] = card
                else:
                    current.parameters.add(key[1]); current.lines.append(card)
        elif command == ".model":
            match = re.fullmatch(r"\.model\s+(\S+)\s+([A-Za-z][A-Za-z0-9_]*)(?:\s*(\(.*\))|\s+(.*))?", statement, re.I)
            if not match or not IDENTIFIER.fullmatch(match[1]):
                raise ModelLibraryError("Unsupported .model declaration.", line)
            name = match[1]
            if name.casefold() in model_names or len(model_names) + len(subcircuits) >= MAX_MODELS:
                raise ModelLibraryError("Duplicate device model or more than 1024 definitions.", line)
            model_names.add(name.casefold())
            if current is None:
                globals_[("model", name.casefold())] = normalized
            else:
                current.model_names.add(name.casefold())
                current.lines.append(normalized)
        elif command.startswith("."):
            raise ModelLibraryError(f"Unsupported library directive: {command}.", line)
        else:
            if current is None or not IDENTIFIER.fullmatch(tokens[0]) or command[0] not in "rclvidqjmefghbkswx":
                raise ModelLibraryError("Only supported device cards inside a subcircuit are admitted.", line)
            if command in current.devices:
                raise ModelLibraryError("Duplicate device identifier in subcircuit.", line)
            current.devices.add(command)
            if len(tokens) < 4:
                raise ModelLibraryError("Incomplete device card.", line)
            if command[0] in "djmqsw":
                current.model_cards.append((tokens, line))
            if command.startswith("x"):
                fields, parameters = _arguments(tokens[1:], line)
                if len(fields) < 2 or not IDENTIFIER.fullmatch(fields[-1]) or any(not PIN_IDENTIFIER.fullmatch(pin) for pin in fields[:-1]):
                    raise ModelLibraryError("Subcircuit call requires explicit nodes followed by its target.", line)
                current.calls.append((fields[-1], len(fields) - 1, parameters, line))
                calls += 1
                if calls > MAX_CALLS:
                    raise ModelLibraryError("Library exceeds 8192 subcircuit calls.", line)
            current.lines.append(normalized)
    if current is not None:
        raise ModelLibraryError("Missing .ends declaration.", current.line)
    if not resolve:
        return subcircuits, globals_
    for block in subcircuits.values():
        available_models = {key[1] for key in globals_ if key[0] == "model"} | block.model_names
        for card, line in block.model_cards:
            indices = [4, 5] if card[0][0].lower() == "q" else [{"d": 3, "j": 4, "m": 5, "s": 5, "w": 4}[card[0][0].lower()]]
            matches = [index for index in indices if index < len(card) and card[index].casefold() in available_models]
            if len(matches) != 1:
                raise ModelLibraryError("Missing or ambiguous in-scope device model reference.", line)
        for target, pin_count, parameters, line in block.calls:
            dependency = subcircuits.get(target.casefold())
            if dependency is None:
                raise ModelLibraryError(f"Missing subcircuit dependency: {target}.", line)
            if pin_count != len(dependency.pins):
                raise ModelLibraryError(f"Wrong pin count for subcircuit: {target}.", line)
            if {key.casefold() for key in parameters} - {key.casefold() for key in dependency.defaults}:
                raise ModelLibraryError(f"Undeclared parameter on subcircuit call: {target}.", line)
    for symbol in subcircuits:
        _closure(symbol, subcircuits)
    return subcircuits, globals_


def _closure(symbol: str, blocks: dict[str, _Subcircuit]) -> list[str]:
    ordered, active, heights = [], set(), {}
    def visit(key: str, depth: int) -> int:
        if key in active:
            raise ModelLibraryError("Cyclic subcircuit dependencies are unsupported.", blocks[key].line)
        if depth > MAX_DEPENDENCY_DEPTH:
            raise ModelLibraryError("Subcircuit dependency depth exceeds 64.", blocks[key].line)
        if key in heights:
            if depth + heights[key] - 1 > MAX_DEPENDENCY_DEPTH:
                raise ModelLibraryError("Subcircuit dependency depth exceeds 64.", blocks[key].line)
            return heights[key]
        active.add(key)
        height = 1
        for target, *_ in blocks[key].calls:
            height = max(height, 1 + visit(target.casefold(), depth + 1))
        active.remove(key); heights[key] = height; ordered.append(key)
        return height
    visit(symbol, 1)
    return ordered


def _name(name: str) -> str:
    if not isinstance(name, str) or not name.strip() or len(name) > 256 or any(ord(char) < 32 for char in name):
        raise ModelLibraryError("Library display name requires 1 to 256 printable characters.")
    return name.strip()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _candidate(block: _Subcircuit, blocks: dict[str, _Subcircuit], digest: str) -> dict:
    return {"id": "imported_" + _sha(digest + ":" + block.name.casefold())[:32],
            "subcircuit_name": block.name, "pins": block.pins,
            "default_parameters": block.defaults, "line": block.line,
            "dependency_names": [blocks[key].name for key in _closure(block.name.casefold(), blocks)[:-1]],
            "required_engine": "ngspice", "source_sha256": digest}


def inspect_spice_model_library(text: str, name: str = "Imported library") -> dict:
    """Return ordered entry choices, or diagnostics with no partially admitted choices."""
    result = {"contract": INSPECTION_CONTRACT, "valid": False, "status": "rejected",
              "candidates": [], "diagnostics": [], "production_qualified": False}
    try:
        result["name"] = _name(name)
        blocks, globals_ = _parse(text)
        result["source_sha256"] = _sha(text)
        if not blocks:
            raise ModelLibraryError("No subcircuit entry points were declared.")
        candidates, output_bytes = [], 1024 + len(json.dumps(result).encode("utf-8"))
        for block in blocks.values():
            candidate = _candidate(block, blocks, result["source_sha256"])
            output_bytes += len(json.dumps(candidate).encode("utf-8")) + 2
            if output_bytes > MAX_INSPECTION_BYTES:
                raise ModelLibraryError("Inspection metadata exceeds the 4 MiB output limit.")
            candidates.append(candidate)
        result.update(valid=True, status="inspected", candidates=candidates,
                      global_definition_count=len(globals_))
        result["diagnostics"] = [{"code": "SPICE_LIBRARY_ENGINE_REVIEW_REQUIRED", "severity": "warning",
                                  "message": "Structural import only; expressions and device syntax remain unevaluated and require ngspice review. All top-level parameters and device models are retained conservatively.", "line": 0}]
    except ModelLibraryError as error:
        result["diagnostics"] = [{"code": error.code, "severity": "error", "message": str(error), "line": error.line}]
    return result


def import_spice_model(text: str, subcircuit_name: str, name: str = "Imported library") -> dict:
    """Select one inspected entry and copy its dependency closure into a workspace model."""
    label = _name(name)
    blocks, globals_ = _parse(text)
    if not isinstance(subcircuit_name, str) or subcircuit_name.casefold() not in blocks:
        raise ModelLibraryError("Select an explicitly declared subcircuit entry.")
    block = blocks[subcircuit_name.casefold()]
    source = "\n".join([*globals_.values(), *("\n".join(blocks[key].lines) for key in _closure(subcircuit_name.casefold(), blocks))]) + "\n"
    issues: list[dict] = []
    _validate_model_source(source, "source", issues)
    if issues:
        raise ModelLibraryError(issues[0]["message"])
    digest = _sha(text)
    candidate = _candidate(block, blocks, digest)
    return {**candidate, "name": block.name, "kind": "subcircuit", "origin": "imported", "source": source,
            "import_provenance": {"source_name": label, "source_sha256": digest, "normalized_source_sha256": _sha(source),
                                  "target_symbol": block.name, "default_parameters": block.defaults,
                                  "required_engine": "ngspice", "structural_inspection_only": True,
                                  "expressions_evaluated": False, "external_files_resolved": False,
                                  "production_qualified": False}}


def merge_spice_model_sources(sources: list[str]) -> str:
    """Deduplicate whole admitted definitions; never rename conflicting symbols."""
    if not isinstance(sources, list) or len(sources) > MAX_MODELS:
        raise ModelLibraryError("Expected at most 1024 model sources.")
    definitions: dict[tuple[str, str], str] = {}
    total = 0
    for source in sources:
        if not isinstance(source, str):
            raise ModelLibraryError("Model sources must be text.")
        if not source.strip():
            continue
        total += len(source.encode("utf-8"))
        if total > 10 * 1024 * 1024:
            raise ModelLibraryError("Combined model input exceeds 10 MiB.")
        blocks, globals_ = _parse(source, resolve=False)
        units = {**globals_, **{("subckt", key): "\n".join(block.lines) for key, block in blocks.items()}}
        for key, unit in units.items():
            previous = definitions.get(key)
            if previous is not None and previous != unit:
                raise ModelLibraryError(f"Conflicting {key[0]} definition: {key[1]}.")
            definitions.setdefault(key, unit)
    merged = "\n".join(definitions.values()) + ("\n" if definitions else "")
    # Cross-source collisions of local .model names and total admission limits.
    if merged:
        _parse(merged, max_bytes=10 * 1024 * 1024)
    return merged
