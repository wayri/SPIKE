"""Strict parser and bounded elaborator for the owned SPIKES netlist subset."""

from __future__ import annotations

import ast
import hashlib
import itertools
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from .behavioral import compile_behavioral_expression

from .contracts import (
    AnalysisDirective,
    CircuitElement,
    CircuitProject,
    DiodeModel,
    HierarchyInstance,
    MeasureDirective,
    ProbeDescriptor,
    SourceWaveform,
    StepDirective,
    StepVariant,
    SwitchModel,
)


MAX_NETLIST_BYTES = 8 * 1024 * 1024
MAX_NETLIST_LINES = 100_000
MAX_SWEEP_POINTS = 1_000_000
MAX_TRANSIENT_POINTS = 1_000_000
MAX_SUBCIRCUITS = 4096
MAX_HIERARCHY_DEPTH = 64
MAX_EXPANDED_INSTANCES = 100_000
MAX_EXPANDED_ELEMENTS = 1_000_000
MAX_PARAMETERS = 4096
MAX_EXPRESSION_NODES = 128
MAX_INCLUDE_FILES = 64
MAX_INCLUDE_DEPTH = 16
MAX_STEP_DIRECTIVES = 8
MAX_STEP_VARIANTS = 10_000
MAX_STEPPED_WORK_POINTS = 2_000_000
MAX_MEASUREMENTS = 1024
MAX_USER_FUNCTIONS = 256
MAX_FUNCTION_ARGUMENTS = 16
MAX_FUNCTION_EXPANSIONS = 4096

_NUMBER_RE = re.compile(
    r"^(?P<number>[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?)"
    r"(?P<suffix>[A-Za-z]*)$",
    flags=re.ASCII,
)
_DESIGNATOR_RE = re.compile(r"^[A-Za-z][0-9][A-Za-z0-9_.$:+-]*$", flags=re.ASCII)
_LOCAL_NAME_RE = re.compile(r"^[A-Za-z0-9_.$+-]+$", flags=re.ASCII)
_DIODE_MODEL_RE = re.compile(
    r"(?is)^\.model\s+(?P<name>[A-Za-z0-9_.$+-]+)\s+D\s*\((?P<body>.*)\)\s*$"
)
_MODEL_ASSIGNMENT_RE = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z0-9_]*)\s*=\s*(?P<value>[^\s,()]+)",
    flags=re.ASCII,
)
_SCALE = {
    "t": 1e12,
    "g": 1e9,
    "meg": 1e6,
    "k": 1e3,
    "m": 1e-3,
    "mil": 25.4e-6,
    "u": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
    "f": 1e-15,
}
_UNITS = {
    "resistor": {"", "r", "ohm", "ohms"},
    "capacitor": {"", "f", "farad", "farads"},
    "inductor": {"", "h", "henry", "henries"},
    "voltage_source": {"", "v", "volt", "volts"},
    "current_source": {"", "a", "amp", "amps", "ampere", "amperes"},
    "sweep": {"", "v", "a"},
    "scalar": {""},
    "time": {"", "s", "sec", "secs", "second", "seconds"},
}


@dataclass(frozen=True, slots=True)
class NetlistParseError(ValueError):
    """A source-located parser diagnostic suitable for CLI JSON output."""

    code: str
    message: str
    line: int = 0
    source_name: str = "<memory>"

    def __str__(self) -> str:
        location = f"{self.source_name}:{self.line}" if self.line else self.source_name
        return f"{location}: {self.message}"

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": "error",
            "message": self.message,
            "path": self.source_name,
            "line": self.line,
        }


@dataclass(frozen=True, slots=True)
class _Statement:
    value: "_ElementSpec" | "_Diode" | "_Instance" | "_ParamStatement"
    line: int


@dataclass(frozen=True, slots=True)
class _Instance:
    name: str
    nodes: tuple[str, ...]
    definition: str
    parameter_overrides: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class _ElementSpec:
    tokens: tuple[str, ...]
    native_extensions: bool

    @property
    def name(self) -> str:
        return self.tokens[0]


@dataclass(frozen=True, slots=True)
class _ParamStatement:
    assignments: tuple[tuple[str, str], ...]

    @property
    def name(self) -> str:
        return ".param"


@dataclass(frozen=True, slots=True)
class _Diode:
    name: str
    anode: str
    cathode: str
    model_name: str


@dataclass(frozen=True, slots=True)
class _Subcircuit:
    name: str
    pins: tuple[str, ...]
    body: tuple[_Statement, ...]
    line: int
    parameter_defaults: tuple[tuple[str, str], ...] = ()


def parse_spice_number(token: str, quantity: str) -> float:
    """Parse a finite SPICE number; ``M`` means milli and ``MEG`` means mega."""

    matched = _NUMBER_RE.fullmatch(str(token).strip())
    if matched is None:
        raise ValueError(f"Invalid numeric value {token!r}.")
    tail = matched.group("suffix").lower()
    scale = 1.0
    unit = tail
    for prefix in ("meg", "mil", "t", "g", "k", "m", "u", "n", "p", "f"):
        if tail.startswith(prefix) and tail != prefix and tail[len(prefix):] in _UNITS[quantity]:
            scale = _SCALE[prefix]
            unit = tail[len(prefix):]
            break
        if tail == prefix:
            scale = _SCALE[prefix]
            unit = ""
            break
    if unit not in _UNITS[quantity]:
        raise ValueError(f"Unsupported unit suffix in {token!r}.")
    number = float(matched.group("number")) * scale
    if not math.isfinite(number):
        raise ValueError(f"Numeric value {token!r} is not finite.")
    return number


def _content(line: str) -> str:
    stripped = line.strip()
    if not stripped or stripped.startswith("*"):
        return ""
    for marker in ("$", ";"):
        if marker in stripped:
            stripped = stripped.split(marker, 1)[0].rstrip()
    return stripped


def _tokens(line: str) -> list[str]:
    """Split on whitespace while preserving one bounded brace expression."""
    result: list[str] = []
    current: list[str] = []
    brace_depth = 0
    for character in line:
        if character == "{":
            brace_depth += 1
            if brace_depth > 1:
                raise ValueError("Nested parameter-expression braces are unsupported.")
        elif character == "}":
            brace_depth -= 1
            if brace_depth < 0:
                raise ValueError("Unmatched parameter-expression brace.")
        if character.isspace() and brace_depth == 0:
            if current:
                result.append("".join(current))
                current = []
        else:
            current.append(character)
    if brace_depth:
        raise ValueError("Unterminated parameter-expression brace.")
    if current:
        result.append("".join(current))
    return result


def _error(code: str, message: str, line: int, source_name: str) -> NetlistParseError:
    return NetlistParseError(code=code, message=message, line=line, source_name=source_name)


def _parse_assignments(text: str, line: int, source_name: str) -> tuple[tuple[str, str], ...]:
    starts = list(re.finditer(r"(?i)(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)\s*=", text))
    if not starts:
        raise _error("SPIKES_NETLIST_PARAM_INVALID", "Parameter directive requires NAME=EXPR assignments.", line, source_name)
    prefix = text[:starts[0].start()]
    if prefix.strip(" \t,"):
        raise _error("SPIKES_NETLIST_PARAM_INVALID", "Malformed parameter assignment list.", line, source_name)
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index, matched in enumerate(starts):
        name = matched.group(1).lower()
        expression = text[matched.end(): starts[index + 1].start() if index + 1 < len(starts) else len(text)].strip(" \t,")
        if not expression:
            raise _error("SPIKES_NETLIST_PARAM_INVALID", f"Parameter {name} has no expression.", line, source_name)
        if name in seen:
            raise _error("SPIKES_NETLIST_PARAM_DUPLICATE", f"Parameter {name} is assigned more than once.", line, source_name)
        if "{" in expression or "}" in expression:
            if not (expression.startswith("{") and expression.endswith("}") and expression.count("{") == expression.count("}") == 1):
                raise _error("SPIKES_NETLIST_PARAM_INVALID", f"Parameter {name} has malformed braces.", line, source_name)
        seen.add(name)
        result.append((name, expression))
    return tuple(result)


_EXPRESSION_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_.])(?P<value>(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?[A-Za-z]*)(?![A-Za-z0-9_.])"
)
_BEHAVIOR_SIGNAL_RE = re.compile(
    r"(?i)\b(?P<kind>[vi])\(\s*(?P<first>[A-Za-z0-9_.$+-]+)"
    r"(?:\s*,\s*(?P<second>[A-Za-z0-9_.$+-]+))?\s*\)"
)


@dataclass(frozen=True, slots=True)
class _UserFunction:
    name: str
    arguments: tuple[str, ...]
    expression: str
    line: int


def _expand_user_functions(
    lines: list[tuple[int, str]], source_name: str
) -> list[tuple[int, str]]:
    definitions: dict[str, _UserFunction] = {}
    retained: list[tuple[int, str]] = []
    header = re.compile(
        r"(?is)^\.func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^()]*)\)\s*"
        r"(?:=\s*)?(?:\{(.*)\}|(.+))\s*$"
    )
    for line_number, line in lines:
        if not line.lower().startswith(".func"):
            retained.append((line_number, line))
            continue
        matched = header.fullmatch(line)
        if matched is None:
            raise _error(
                "SPIKES_NETLIST_FUNC_INVALID",
                ".func requires NAME(ARG,...) {EXPRESSION}.",
                line_number, source_name,
            )
        name = matched.group(1).lower()
        raw_arguments = matched.group(2).strip()
        arguments = tuple(
            argument.strip().lower()
            for argument in raw_arguments.split(",") if argument.strip()
        )
        if (
            len(arguments) > MAX_FUNCTION_ARGUMENTS
            or len(arguments) != len(set(arguments))
            or any(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item) is None for item in arguments)
        ):
            raise _error(
                "SPIKES_NETLIST_FUNC_ARGUMENTS",
                f"User functions permit at most {MAX_FUNCTION_ARGUMENTS} unique identifier arguments.",
                line_number, source_name,
            )
        expression = (matched.group(3) or matched.group(4) or "").strip()
        if not expression:
            raise _error("SPIKES_NETLIST_FUNC_INVALID", "User-function expression is empty.", line_number, source_name)
        if name in definitions:
            raise _error("SPIKES_NETLIST_FUNC_DUPLICATE", f"Function {name} is defined more than once.", line_number, source_name)
        if len(definitions) >= MAX_USER_FUNCTIONS:
            raise _error("SPIKES_NETLIST_FUNC_LIMIT", f"More than {MAX_USER_FUNCTIONS} functions are not allowed.", line_number, source_name)
        definitions[name] = _UserFunction(name, arguments, expression, line_number)

    if not definitions:
        return retained
    names = "|".join(re.escape(name) for name in sorted(definitions, key=len, reverse=True))
    call_re = re.compile(rf"(?i)\b({names})\s*\(")
    expansions = 0

    def split_arguments(text: str, line_number: int) -> tuple[str, ...]:
        if not text.strip():
            return ()
        result: list[str] = []
        start = 0
        parenthesis_depth = 0
        brace_depth = 0
        for index, character in enumerate(text):
            if character == "(":
                parenthesis_depth += 1
            elif character == ")":
                parenthesis_depth -= 1
            elif character == "{":
                brace_depth += 1
            elif character == "}":
                brace_depth -= 1
            elif character == "," and parenthesis_depth == 0 and brace_depth == 0:
                result.append(text[start:index].strip())
                start = index + 1
            if parenthesis_depth < 0 or brace_depth < 0:
                raise _error("SPIKES_NETLIST_FUNC_CALL", "Malformed user-function argument list.", line_number, source_name)
        result.append(text[start:].strip())
        if parenthesis_depth or brace_depth or any(not item for item in result):
            raise _error("SPIKES_NETLIST_FUNC_CALL", "Malformed user-function argument list.", line_number, source_name)
        return tuple(result)

    def expand(text: str, line_number: int, stack: tuple[str, ...] = ()) -> str:
        nonlocal expansions
        while (matched := call_re.search(text)) is not None:
            name = matched.group(1).lower()
            if name in stack:
                cycle = " -> ".join((*stack, name))
                raise _error("SPIKES_NETLIST_FUNC_RECURSION", f"Recursive user-function call: {cycle}.", line_number, source_name)
            opening = matched.end() - 1
            depth = 1
            closing = opening + 1
            while closing < len(text) and depth:
                if text[closing] == "(":
                    depth += 1
                elif text[closing] == ")":
                    depth -= 1
                closing += 1
            if depth:
                raise _error("SPIKES_NETLIST_FUNC_CALL", "Unterminated user-function call.", line_number, source_name)
            function = definitions[name]
            actual = split_arguments(text[opening + 1:closing - 1], line_number)
            if len(actual) != len(function.arguments):
                raise _error(
                    "SPIKES_NETLIST_FUNC_ARITY",
                    f"Function {name} expects {len(function.arguments)} arguments, got {len(actual)}.",
                    line_number, source_name,
                )
            body = function.expression
            for formal, value in zip(function.arguments, actual, strict=True):
                body = re.sub(
                    rf"(?i)(?<![A-Za-z0-9_]){re.escape(formal)}(?![A-Za-z0-9_])",
                    f"({value})", body,
                )
            body = expand(body, line_number, (*stack, name))
            text = text[:matched.start()] + f"({body})" + text[closing:]
            expansions += 1
            if expansions > MAX_FUNCTION_EXPANSIONS or len(text.encode("utf-8")) > MAX_NETLIST_BYTES:
                raise _error("SPIKES_NETLIST_FUNC_LIMIT", "User-function expansion exceeds resource limits.", line_number, source_name)
        return text

    # Validate all definition dependency paths, including functions not called
    # by an element card, so dormant recursion cannot enter a model package.
    for function in definitions.values():
        expand(function.expression, function.line, (function.name,))
    return [(line_number, expand(line, line_number)) for line_number, line in retained]


def _evaluate_expression(expression: str, parameters: dict[str, float], quantity: str) -> float:
    raw = expression.strip()
    if raw.startswith("{") and raw.endswith("}"):
        raw = raw[1:-1].strip()
    try:
        return parse_spice_number(raw, quantity)
    except ValueError:
        pass

    def replace_number(matched: re.Match[str]) -> str:
        return repr(parse_spice_number(matched.group("value"), quantity))

    try:
        normalized = _EXPRESSION_NUMBER_RE.sub(replace_number, raw)
        tree = ast.parse(normalized, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise ValueError(f"Invalid parameter expression {expression!r}.") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_EXPRESSION_NODES:
        raise ValueError("Parameter expression exceeds the complexity limit.")

    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.Name):
            name = node.id.lower()
            if name == "pi":
                return math.pi
            if name not in parameters:
                raise ValueError(f"Unknown parameter {node.id}.")
            return parameters[name]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Add):
                result = left + right
            elif isinstance(node.op, ast.Sub):
                result = left - right
            elif isinstance(node.op, ast.Mult):
                result = left * right
            elif isinstance(node.op, ast.Div):
                result = left / right
            else:
                if abs(right) > 16.0:
                    raise ValueError("Parameter exponent exceeds the bounded range.")
                result = left ** right
            if not math.isfinite(result):
                raise ValueError("Parameter expression produced a non-finite result.")
            return result
        raise ValueError("Parameter expressions permit only names, numbers, parentheses, and + - * / ** operators.")

    try:
        result = evaluate(tree)
    except (ArithmeticError, OverflowError) as exc:
        raise ValueError("Parameter expression could not be evaluated finitely.") from exc
    if not math.isfinite(result):
        raise ValueError("Parameter expression produced a non-finite result.")
    return result


def _apply_assignments(
    base: dict[str, float], assignments: tuple[tuple[str, str], ...], line: int,
    source_name: str,
) -> dict[str, float]:
    result = dict(base)
    if len(result) + len(assignments) > MAX_PARAMETERS:
        raise _error("SPIKES_NETLIST_PARAM_LIMIT", f"Parameter scope exceeds {MAX_PARAMETERS} entries.", line, source_name)
    pending = dict(assignments)
    while pending:
        progressed = False
        errors: dict[str, ValueError] = {}
        for name, expression in tuple(pending.items()):
            try:
                result[name] = _evaluate_expression(expression, result, "scalar")
            except ValueError as exc:
                errors[name] = exc
                continue
            del pending[name]
            progressed = True
        if not progressed:
            name = next(iter(pending))
            raise _error("SPIKES_NETLIST_PARAM_UNRESOLVED", f"Cannot resolve parameter {name}: {errors[name]}", line, source_name)
    return result


def _linear_step_values(start: float, stop: float, step: float) -> tuple[float, ...]:
    if step == 0.0 or (stop - start) * step < 0.0:
        raise ValueError("STEP increment must be nonzero and point toward the stop value.")
    count = int(math.floor(abs((stop - start) / step) + 1.0e-12)) + 1
    if count > MAX_STEP_VARIANTS:
        raise ValueError(f"One STEP axis exceeds {MAX_STEP_VARIANTS} values.")
    values = [start + index * step for index in range(count)]
    tolerance = max(abs(start), abs(stop), 1.0) * 1.0e-12
    if values and abs(values[-1] - stop) <= tolerance:
        values[-1] = stop
    return tuple(values)


def _measure_directive(
    tokens: list[str], parameters: dict[str, float], line: int, source_name: str
) -> MeasureDirective:
    if len(tokens) < 5:
        raise _error(
            "SPIKES_NETLIST_MEASURE_ARITY",
            ".measure requires ANALYSIS NAME OPERATION PROBE and optional FROM=/TO= or AT=.",
            line,
            source_name,
        )
    analysis, name, operation = tokens[1].lower(), tokens[2], tokens[3].lower()
    try:
        probe = ProbeDescriptor.parse(tokens[4])
    except ValueError as exc:
        raise _error("SPIKES_NETLIST_MEASURE_PROBE", str(exc), line, source_name) from exc
    options: dict[str, float] = {}
    quantity = "time" if analysis == "tran" else "sweep"
    for token in tokens[5:]:
        if "=" not in token:
            raise _error("SPIKES_NETLIST_MEASURE_OPTION", f"Malformed measurement option {token}.", line, source_name)
        key, expression = token.split("=", 1)
        key = key.lower()
        if key not in {"from", "to", "at"} or key in options:
            raise _error("SPIKES_NETLIST_MEASURE_OPTION", f"Unsupported or duplicate measurement option {key}.", line, source_name)
        try:
            options[key] = _evaluate_expression(expression, parameters, quantity)
        except ValueError as exc:
            raise _error("SPIKES_NETLIST_MEASURE_OPTION", str(exc), line, source_name) from exc
    try:
        return MeasureDirective(
            name=name, analysis=analysis, operation=operation, probe=probe,
            from_value=options.get("from"), to_value=options.get("to"),
            at_value=options.get("at"),
        )
    except ValueError as exc:
        raise _error("SPIKES_NETLIST_MEASURE_INVALID", str(exc), line, source_name) from exc


def _expand_local_includes(text: str, source_name: str) -> str:
    if not re.search(r"(?im)^\s*\.(?:include|lib)\b", text):
        return text
    main = Path(source_name)
    if source_name.startswith("<") or not main.is_file():
        raise _error("SPIKES_NETLIST_INCLUDE_CONTEXT", "Local include directives require a real top-level source file.", 0, source_name)
    main = main.resolve()
    root = main.parent
    visited: set[Path] = {main}
    total_bytes = len(text.encode("utf-8"))

    def safe_path(reference: str, current: Path, line_number: int) -> Path:
        candidate = (current.parent / reference).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise _error("SPIKES_NETLIST_INCLUDE_PATH", "Include path escapes the top-level netlist directory.", line_number, str(current)) from exc
        if not candidate.is_file():
            raise _error("SPIKES_NETLIST_INCLUDE_MISSING", f"Included file does not exist: {reference}.", line_number, str(current))
        return candidate

    def section(contents: str, section_name: str, path: Path) -> str:
        selected: list[str] = []
        active = False
        found = False
        for line_number, raw in enumerate(contents.splitlines(), 1):
            stripped = _content(raw)
            opening = re.fullmatch(r"(?i)\.lib\s+([A-Za-z0-9_.+-]+)", stripped)
            closing = re.fullmatch(r"(?i)\.endl(?:\s+([A-Za-z0-9_.+-]+))?", stripped)
            if opening:
                if active:
                    raise _error("SPIKES_NETLIST_LIB_NESTED", "Nested library sections are unsupported.", line_number, str(path))
                active = opening.group(1).lower() == section_name.lower()
                found = found or active
                continue
            if closing:
                if active and closing.group(1) and closing.group(1).lower() != section_name.lower():
                    raise _error("SPIKES_NETLIST_LIB_END_MISMATCH", "Library section terminator does not match.", line_number, str(path))
                active = False
                continue
            if active:
                selected.append(raw)
        if not found:
            raise _error("SPIKES_NETLIST_LIB_SECTION_UNKNOWN", f"Library section {section_name} was not found.", 0, str(path))
        return "\n".join(selected)

    def expand(contents: str, current: Path, stack: tuple[Path, ...], depth: int) -> str:
        nonlocal total_bytes
        if depth > MAX_INCLUDE_DEPTH:
            raise _error("SPIKES_NETLIST_INCLUDE_DEPTH", f"Include depth exceeds {MAX_INCLUDE_DEPTH}.", 0, str(current))
        output: list[str] = []
        include_re = re.compile(r"(?i)^\.include\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))\s*$")
        lib_re = re.compile(r"(?i)^\.lib\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))\s+([A-Za-z0-9_.+-]+)\s*$")
        for line_number, raw in enumerate(contents.splitlines(), 1):
            stripped = _content(raw)
            include = include_re.fullmatch(stripped)
            library = lib_re.fullmatch(stripped)
            if not include and not library:
                output.append(raw)
                continue
            reference = next(item for item in (include or library).groups()[:3] if item is not None)
            target = safe_path(reference, current, line_number)
            if target in stack:
                raise _error("SPIKES_NETLIST_INCLUDE_CYCLE", "Include cycle detected.", line_number, str(current))
            visited.add(target)
            if len(visited) > MAX_INCLUDE_FILES:
                raise _error("SPIKES_NETLIST_INCLUDE_LIMIT", f"Netlist references more than {MAX_INCLUDE_FILES} files.", line_number, str(current))
            try:
                file_bytes = target.stat().st_size
                if file_bytes > MAX_NETLIST_BYTES or total_bytes + file_bytes > MAX_NETLIST_BYTES:
                    raise _error("SPIKES_NETLIST_SIZE_LIMIT", "Aggregate included source exceeds the 8 MiB input limit.", line_number, str(current))
                loaded = target.read_text(encoding="utf-8")
                total_bytes += file_bytes
            except (OSError, UnicodeError) as exc:
                raise _error("SPIKES_NETLIST_INCLUDE_READ", f"Cannot read included file: {exc}", line_number, str(current)) from exc
            if library:
                loaded = section(loaded, library.group(4), target)
            output.append(expand(loaded, target, (*stack, target), depth + 1))
        return "\n".join(output)

    return expand(text, main, (main,), 0)


def _source_waveform(expression: str, kind: str, parameters: dict[str, float]) -> SourceWaveform:
    matched = re.fullmatch(r"(?is)\s*(pulse|pwl)\s*\((.*)\)\s*", expression)
    if matched is None:
        raise ValueError("Native source form must be PULSE(...) or PWL(...).")
    form = matched.group(1).lower()
    raw_values = _tokens(matched.group(2).replace(",", " "))
    if form == "pulse":
        if len(raw_values) != 7:
            raise ValueError("PULSE requires V1 V2 TD TR TF PW PER.")
        values = (
            _evaluate_expression(raw_values[0], parameters, kind),
            _evaluate_expression(raw_values[1], parameters, kind),
            *(_evaluate_expression(item, parameters, "time") for item in raw_values[2:]),
        )
        return SourceWaveform(kind="pulse", pulse=tuple(values))
    if len(raw_values) < 2 or len(raw_values) % 2:
        raise ValueError("PWL requires one or more TIME VALUE pairs.")
    points = tuple(
        (
            _evaluate_expression(raw_values[index], parameters, "time"),
            _evaluate_expression(raw_values[index + 1], parameters, kind),
        )
        for index in range(0, len(raw_values), 2)
    )
    return SourceWaveform(kind="pwl", points=points)


def _diode_model(line_text: str, line: int, source_name: str) -> tuple[str, DiodeModel]:
    matched = _DIODE_MODEL_RE.fullmatch(line_text)
    if matched is None:
        raise _error(
            "SPIKES_NETLIST_MODEL_UNSUPPORTED",
            "Only top-level .model NAME D(IS=... N=... TNOM=... KF=... AF=...) cards are supported.",
            line,
            source_name,
        )
    name = matched.group("name")
    if _LOCAL_NAME_RE.fullmatch(name) is None:
        raise _error("SPIKES_NETLIST_MODEL_INVALID", "Invalid diode model name.", line, source_name)
    values: dict[str, str] = {}
    body = matched.group("body")
    position = 0
    for assignment in _MODEL_ASSIGNMENT_RE.finditer(body):
        if re.fullmatch(r"[\s,]*", body[position:assignment.start()]) is None:
            raise _error("SPIKES_NETLIST_MODEL_INVALID", "Malformed diode model parameter list.", line, source_name)
        key = assignment.group("name").upper()
        if key not in {"IS", "N", "TNOM", "KF", "AF"}:
            raise _error(
                "SPIKES_NETLIST_MODEL_PARAMETER_UNSUPPORTED",
                f"Unsupported diode model parameter {key}; only IS, N, TNOM, KF, and AF are accepted.",
                line,
                source_name,
            )
        if key in values:
            raise _error("SPIKES_NETLIST_MODEL_PARAMETER_DUPLICATE", f"Diode model parameter {key} is duplicated.", line, source_name)
        values[key] = assignment.group("value")
        position = assignment.end()
    if re.fullmatch(r"[\s,]*", body[position:]) is None:
        raise _error("SPIKES_NETLIST_MODEL_INVALID", "Malformed diode model parameter list.", line, source_name)
    try:
        saturation_current = parse_spice_number(values.get("IS", "10f"), "current_source")
        emission_coefficient = parse_spice_number(values.get("N", "1"), "scalar")
        nominal_temperature_c = parse_spice_number(values.get("TNOM", "27"), "scalar")
        flicker_coefficient = parse_spice_number(values.get("KF", "0"), "scalar")
        flicker_exponent = parse_spice_number(values.get("AF", "1"), "scalar")
        model = DiodeModel(
            saturation_current_a=saturation_current,
            emission_coefficient=emission_coefficient,
            temperature_k=nominal_temperature_c + 273.15,
            flicker_noise_coefficient=flicker_coefficient,
            flicker_noise_exponent=flicker_exponent,
        )
    except ValueError as exc:
        raise _error("SPIKES_NETLIST_MODEL_INVALID", str(exc), line, source_name) from exc
    return name.upper(), model


def _diode(tokens: list[str], line: int, source_name: str) -> _Diode:
    if len(tokens) != 4:
        raise _error(
            "SPIKES_NETLIST_ELEMENT_ARITY",
            "D requires NAME ANODE CATHODE MODEL; area, OFF, and per-instance parameters are unsupported.",
            line,
            source_name,
        )
    if any(":" in token for token in tokens):
        raise _error(
            "SPIKES_NETLIST_ELEMENT_INVALID",
            "Colon is reserved for elaborated hierarchical names.",
            line,
            source_name,
        )
    if any(_LOCAL_NAME_RE.fullmatch(token) is None for token in tokens):
        raise _error("SPIKES_NETLIST_ELEMENT_INVALID", "Invalid diode name, node, or model name.", line, source_name)
    return _Diode(tokens[0].upper(), tokens[1].lower(), tokens[2].lower(), tokens[3].upper())


def _element(
    tokens: list[str], line: int, source_name: str, *, native_extensions: bool = False,
    parameters: dict[str, float] | None = None,
) -> CircuitElement:
    parameters = parameters or {}
    name = tokens[0]
    prefix = name[0].upper()
    kinds = {
        "R": "resistor",
        "C": "capacitor",
        "L": "inductor",
        "V": "voltage_source",
        "I": "current_source",
        "S": "voltage_controlled_switch",
        "E": "vcvs",
        "G": "vccs",
        "F": "cccs",
        "H": "ccvs",
    }
    kind = kinds.get(prefix, "")
    expected = (
        9 if prefix == "S" else
        6 if prefix in {"E", "G"} else
        5 if prefix in {"F", "H"} else
        None if prefix in {"B", "V", "I"} else
        (4 if prefix == "R" else (4, 5) if prefix in {"C", "L"} else (4, 5))
    )
    if prefix == "B":
        if len(tokens) < 4:
            raise _error(
                "SPIKES_NETLIST_ELEMENT_ARITY",
                "B requires NAME NODE+ NODE- V={EXPR} or I={EXPR}.", line, source_name,
            )
        try:
            if any(":" in token for token in tokens[:3]):
                raise ValueError("Colon is reserved for elaborated hierarchical names.")
            assignment = " ".join(tokens[3:]).strip()
            matched_assignment = re.fullmatch(r"(?is)([vi])\s*=\s*(.+)", assignment)
            if matched_assignment is None:
                raise ValueError("Behavioral source requires V={EXPR} or I={EXPR}.")
            output_kind = matched_assignment.group(1).lower()
            expression = matched_assignment.group(2).strip()
            if expression.startswith("{") and expression.endswith("}"):
                expression = expression[1:-1].strip()
            quantity = "voltage_source" if output_kind == "v" else "current_source"
            signal_literals: list[str] = []

            def mask_signal(matched: re.Match[str]) -> str:
                signal_literals.append(matched.group(0))
                return f"__behavior_signal_{len(signal_literals) - 1}__"

            resolved = _BEHAVIOR_SIGNAL_RE.sub(mask_signal, expression)
            for parameter_name, parameter_value in sorted(parameters.items(), key=lambda item: -len(item[0])):
                resolved = re.sub(
                    rf"(?i)(?<![A-Za-z0-9_]){re.escape(parameter_name)}(?![A-Za-z0-9_])",
                    repr(parameter_value), resolved,
                )
            resolved = _EXPRESSION_NUMBER_RE.sub(
                lambda matched: repr(parse_spice_number(matched.group("value"), quantity)), resolved
            )
            for signal_index, signal_literal in enumerate(signal_literals):
                resolved = resolved.replace(f"__behavior_signal_{signal_index}__", signal_literal)
            compiled = compile_behavioral_expression(resolved)
            stored_assignment = f"{output_kind.upper()}={{{resolved}}}"
            if len(compiled.signals) <= 1:
                try:
                    samples = {
                        point: compiled.evaluate((point,) if compiled.signals else ()).value
                        for point in (-1.0, 0.0, 1.0, 2.0)
                    }
                    offset = samples[0.0]
                    gain = 0.5 * (samples[1.0] - samples[-1.0])
                    scale = max(1.0, *(abs(value) for value in samples.values()))
                    affine = all(
                        abs(samples[point] - (offset + gain * point)) <= 1.0e-11 * scale
                        for point in (-1.0, 1.0, 2.0)
                    )
                except ValueError:
                    affine = False
                if affine and (not compiled.signals or abs(offset) <= 1.0e-13 * max(1.0, abs(gain))):
                    common = dict(
                        name=name, positive_node=tokens[1], negative_node=tokens[2],
                        value=(gain if compiled.signals else offset), behavioral_expression=stored_assignment,
                    )
                    if not compiled.signals:
                        return CircuitElement(kind=("voltage_source" if output_kind == "v" else "current_source"), **common)
                    signal = compiled.signals[0]
                    if signal.kind == "v":
                        return CircuitElement(
                            kind=("vcvs" if output_kind == "v" else "vccs"),
                            control_positive_node=signal.first, control_negative_node=signal.second, **common,
                        )
                    return CircuitElement(
                        kind=("ccvs" if output_kind == "v" else "cccs"),
                        control_source_id=signal.first, **common,
                    )
            return CircuitElement(
                name=name,
                kind=("behavioral_voltage_source" if output_kind == "v" else "behavioral_current_source"),
                positive_node=tokens[1], negative_node=tokens[2], value=0.0,
                behavioral_expression=stored_assignment,
            )
        except ValueError as exc:
            raise _error("SPIKES_NETLIST_BEHAVIORAL_INVALID", str(exc), line, source_name) from exc
    if (isinstance(expected, int) and len(tokens) != expected) or (
        isinstance(expected, tuple)
        and len(tokens) not in expected
        and not (native_extensions and prefix in {"V", "I"} and len(tokens) >= 4)
    ):
        raise _error(
            "SPIKES_NETLIST_ELEMENT_ARITY",
            (
                "S requires NAME NODE+ NODE- CTRL+ CTRL- RON ROFF VT VSLOPE."
                if prefix == "S"
                else f"{prefix} element requires NAME NODE+ NODE- VALUE; independent sources may use optional DC VALUE."
            ),
            line,
            source_name,
        )
    if prefix == "S" and not native_extensions:
        raise _error(
            "SPIKES_NETLIST_ELEMENT_UNSUPPORTED",
            "Voltage-controlled switches require the explicit native CLI route.",
            line,
            source_name,
        )
    try:
        if any(":" in token for token in tokens[:3]):
            raise ValueError("Colon is reserved for elaborated hierarchical names.")
        if prefix == "S":
            if any(":" in token for token in tokens[3:5]):
                raise ValueError("Colon is reserved for elaborated hierarchical names.")
            model = SwitchModel(
                on_resistance_ohm=_evaluate_expression(tokens[5], parameters, "resistor"),
                off_resistance_ohm=_evaluate_expression(tokens[6], parameters, "resistor"),
                threshold_voltage_v=_evaluate_expression(tokens[7], parameters, "voltage_source"),
                transition_voltage_v=_evaluate_expression(tokens[8], parameters, "voltage_source"),
            )
            return CircuitElement(
                name=name,
                kind=kind,
                positive_node=tokens[1],
                negative_node=tokens[2],
                value=0.0,
                control_positive_node=tokens[3],
                control_negative_node=tokens[4],
                switch_model=model,
            )
        if prefix in {"E", "G"}:
            value = _evaluate_expression(tokens[5], parameters, "scalar")
            return CircuitElement(
                name=name, kind=kind, positive_node=tokens[1], negative_node=tokens[2],
                control_positive_node=tokens[3], control_negative_node=tokens[4], value=value,
            )
        if prefix in {"F", "H"}:
            value = _evaluate_expression(tokens[4], parameters, "scalar")
            return CircuitElement(
                name=name, kind=kind, positive_node=tokens[1], negative_node=tokens[2],
                control_source_id=tokens[3], value=value,
            )
        if prefix in {"V", "I"} and native_extensions and len(tokens) >= 4:
            expression = " ".join(tokens[3:])
            if re.match(r"(?is)^\s*(pulse|pwl)\s*\(", expression):
                waveform = _source_waveform(expression, kind, parameters)
                initial = waveform.pulse[0] if waveform.kind == "pulse" else waveform.points[0][1]
                return CircuitElement(
                    name=name,
                    kind=kind,
                    positive_node=tokens[1],
                    negative_node=tokens[2],
                    value=initial,
                    waveform=waveform,
                )
        if prefix in {"V", "I"}:
            tail = tokens[3:]
            position = 0
            dc_value = 0.0
            ac_magnitude = 0.0
            ac_phase = 0.0
            saw_dc = False
            saw_ac = False
            if position < len(tail) and tail[position].lower() not in {"dc", "ac"}:
                dc_value = _evaluate_expression(tail[position], parameters, kind)
                saw_dc = True
                position += 1
            while position < len(tail):
                keyword = tail[position].lower()
                position += 1
                if keyword == "dc" and not saw_dc:
                    if position >= len(tail):
                        raise ValueError("DC source keyword requires a value.")
                    dc_value = _evaluate_expression(tail[position], parameters, kind)
                    saw_dc = True
                    position += 1
                elif keyword == "ac" and not saw_ac:
                    if position >= len(tail):
                        raise ValueError("AC source keyword requires a magnitude.")
                    ac_magnitude = _evaluate_expression(tail[position], parameters, "scalar")
                    position += 1
                    if position < len(tail) and tail[position].lower() not in {"dc", "ac"}:
                        ac_phase = _evaluate_expression(tail[position], parameters, "scalar")
                        position += 1
                    saw_ac = True
                else:
                    raise ValueError("Unsupported or duplicate independent-source token sequence.")
            return CircuitElement(
                name=name, kind=kind, positive_node=tokens[1],
                negative_node=tokens[2], value=dc_value,
                ac_magnitude=ac_magnitude, ac_phase_deg=ac_phase,
            )
        value = _evaluate_expression(tokens[3], parameters, kind)
        initial_condition = 0.0
        if prefix in {"C", "L"} and len(tokens) == 5:
            matched_ic = re.fullmatch(r"(?is)ic\s*=\s*(.+)", tokens[4])
            if matched_ic is None:
                raise ValueError("C/L optional fifth token must be IC=VALUE.")
            initial_condition = _evaluate_expression(
                matched_ic.group(1), parameters,
                "voltage_source" if prefix == "C" else "current_source",
            )
        return CircuitElement(
            name=name, kind=kind, positive_node=tokens[1],
            negative_node=tokens[2], value=value,
            initial_condition=initial_condition,
        )
    except ValueError as exc:
        raise _error("SPIKES_NETLIST_ELEMENT_INVALID", str(exc), line, source_name) from exc


def _instance(tokens: list[str], line: int, source_name: str) -> _Instance:
    if len(tokens) < 3:
        raise _error(
            "SPIKES_NETLIST_INSTANCE_ARITY",
            "X instance requires NAME, at least one node, and a subcircuit name.",
            line,
            source_name,
        )
    parameter_index = next(
        (index for index, token in enumerate(tokens[1:], 1) if "=" in token or token.lower() == "params:"),
        len(tokens),
    )
    positional = tokens[:parameter_index]
    if len(positional) < 3:
        raise _error("SPIKES_NETLIST_INSTANCE_ARITY", "X instance requires nodes and a subcircuit name before parameters.", line, source_name)
    name, definition = positional[0], positional[-1]
    raw_names = (name, definition, *positional[1:-1])
    if any(_LOCAL_NAME_RE.fullmatch(token) is None for token in raw_names):
        raise _error(
            "SPIKES_NETLIST_INSTANCE_INVALID",
            "Instance names, nodes, and subcircuit names may not contain hierarchy separators.",
            line,
            source_name,
        )
    if not name.upper().startswith("X"):
        raise _error("SPIKES_NETLIST_INSTANCE_INVALID", "Subcircuit instances must use an X designator.", line, source_name)
    assignment_text = " ".join(token for token in tokens[parameter_index:] if token.lower() != "params:")
    overrides = _parse_assignments(assignment_text, line, source_name) if assignment_text else ()
    return _Instance(
        name=name.upper(), nodes=tuple(node.lower() for node in positional[1:-1]),
        definition=definition.lower(), parameter_overrides=overrides,
    )


def _statement(
    tokens: list[str], line: int, source_name: str, *, native_extensions: bool = False
) -> _Statement:
    prefix = tokens[0][0].upper()
    if prefix in {"R", "C", "L", "V", "I", "E", "G", "F", "H", "B"} or (native_extensions and prefix == "S"):
        expected = (
            9 if prefix == "S" else 6 if prefix in {"E", "G"} else
            5 if prefix in {"F", "H"} else None if prefix == "B" else
            (4 if prefix == "R" else (4, 5) if prefix in {"C", "L"} else None)
        )
        valid = (
            len(tokens) >= 4 if expected is None else len(tokens) == expected if isinstance(expected, int)
            else len(tokens) in expected or (native_extensions and prefix in {"V", "I"} and len(tokens) >= 4)
        )
        if not valid:
            raise _error(
                "SPIKES_NETLIST_ELEMENT_ARITY",
                "Controlled source or primitive has an invalid argument count."
                if prefix == "S" else f"{prefix} element has an invalid argument count.",
                line,
                source_name,
            )
        return _Statement(_ElementSpec(tuple(tokens), native_extensions), line)
    if prefix == "D":
        return _Statement(_diode(tokens, line, source_name), line)
    if prefix == "X":
        return _Statement(_instance(tokens, line, source_name), line)
    raise _error(
        "SPIKES_NETLIST_ELEMENT_UNSUPPORTED",
        f"Unsupported element {tokens[0]}; only R, C, L, V, I, D, E, G, F, H, B, X{', and native S' if native_extensions else ''} are accepted.",
        line,
        source_name,
    )


def _subcircuit_header(
    tokens: list[str], line: int, source_name: str
) -> tuple[str, tuple[str, ...], tuple[tuple[str, str], ...]]:
    if len(tokens) < 3:
        raise _error(
            "SPIKES_NETLIST_SUBCKT_ARITY",
            ".subckt requires a name and at least one formal pin.",
            line,
            source_name,
        )
    name = tokens[1]
    parameter_index = next(
        (index for index, token in enumerate(tokens[2:], 2) if "=" in token or token.lower() == "params:"),
        len(tokens),
    )
    pins = tuple(pin.lower() for pin in tokens[2:parameter_index])
    assignment_text = " ".join(token for token in tokens[parameter_index:] if token.lower() != "params:")
    defaults = _parse_assignments(assignment_text, line, source_name) if assignment_text else ()
    if _LOCAL_NAME_RE.fullmatch(name) is None or any(_LOCAL_NAME_RE.fullmatch(pin) is None for pin in pins):
        raise _error(
            "SPIKES_NETLIST_SUBCKT_INVALID",
            "Subcircuit names and pins may not contain hierarchy separators.",
            line,
            source_name,
        )
    if "0" in pins:
        raise _error(
            "SPIKES_NETLIST_SUBCKT_GROUND_PIN",
            "Node 0 is global and cannot be declared as a formal subcircuit pin.",
            line,
            source_name,
        )
    if len(pins) != len(set(pins)):
        raise _error("SPIKES_NETLIST_SUBCKT_PIN_DUPLICATE", "Subcircuit formal pins must be unique.", line, source_name)
    return name.lower(), pins, defaults


def _validate_hierarchy(
    definitions: dict[str, _Subcircuit],
    top: tuple[_Statement, ...],
    source_name: str,
) -> None:
    """Resolve all references and reject cycles, including unreachable ones."""

    def validate_instance(instance: _Instance, line: int) -> None:
        definition = definitions.get(instance.definition)
        if definition is None:
            raise _error(
                "SPIKES_NETLIST_SUBCKT_UNKNOWN",
                f"Instance {instance.name} references unknown subcircuit {instance.definition}.",
                line,
                source_name,
            )
        if len(instance.nodes) != len(definition.pins):
            raise _error(
                "SPIKES_NETLIST_INSTANCE_PIN_MISMATCH",
                f"Instance {instance.name} binds {len(instance.nodes)} nodes but {definition.name} requires {len(definition.pins)}.",
                line,
                source_name,
            )

    for statement in top:
        if isinstance(statement.value, _Instance):
            validate_instance(statement.value, statement.line)
    for definition in definitions.values():
        local_names: set[str] = set()
        for statement in definition.body:
            value = statement.value
            if isinstance(value, _ParamStatement):
                continue
            local_name = value.name.upper()
            if local_name in local_names:
                raise _error(
                    "SPIKES_NETLIST_ELEMENT_DUPLICATE",
                    f"Name {value.name} is duplicated in subcircuit {definition.name}.",
                    statement.line,
                    source_name,
                )
            local_names.add(local_name)
            if isinstance(value, _Instance):
                validate_instance(value, statement.line)

    visiting: list[str] = []
    complete: set[str] = set()

    def visit(name: str) -> None:
        if name in complete:
            return
        if name in visiting:
            cycle = visiting[visiting.index(name):] + [name]
            definition = definitions[name]
            raise _error(
                "SPIKES_NETLIST_SUBCKT_RECURSION",
                f"Recursive subcircuit dependency detected: {' -> '.join(cycle)}.",
                definition.line,
                source_name,
            )
        visiting.append(name)
        for statement in definitions[name].body:
            if isinstance(statement.value, _Instance):
                visit(statement.value.definition)
        visiting.pop()
        complete.add(name)

    for name in definitions:
        visit(name)


def _flatten(
    top: tuple[_Statement, ...],
    definitions: dict[str, _Subcircuit],
    diode_models: dict[str, DiodeModel],
    global_nodes: set[str],
    source_name: str,
    top_parameter_overrides: dict[str, float] | None = None,
) -> tuple[tuple[CircuitElement, ...], tuple[HierarchyInstance, ...]]:
    elements: list[CircuitElement] = []
    hierarchy: list[HierarchyInstance] = []
    top_parameter_overrides = top_parameter_overrides or {}

    def scoped_node(node: str, bindings: dict[str, str], path: str) -> str:
        if node == "0":
            return "0"
        if node in global_nodes:
            return node
        if node in bindings:
            return bindings[node]
        return f"{path.lower()}:{node}" if path else node

    def scoped_behavioral(expression: str | None, bindings: dict[str, str], path: str) -> str | None:
        if expression is None or not path:
            return expression

        def replace_signal(matched: re.Match[str]) -> str:
            kind = matched.group("kind").upper()
            first = matched.group("first")
            second = matched.group("second")
            if kind == "V":
                scoped_first = scoped_node(first.lower(), bindings, path)
                if second is None:
                    return f"V({scoped_first})"
                return f"V({scoped_first},{scoped_node(second.lower(), bindings, path)})"
            return f"I({path}:{first.upper()})"

        return _BEHAVIOR_SIGNAL_RE.sub(replace_signal, expression)

    def expand(
        statements: tuple[_Statement, ...], bindings: dict[str, str], path: str,
        depth: int, parameters: dict[str, float],
    ) -> None:
        if depth > MAX_HIERARCHY_DEPTH:
            raise _error(
                "SPIKES_NETLIST_HIERARCHY_DEPTH_LIMIT",
                f"Hierarchy exceeds the maximum depth of {MAX_HIERARCHY_DEPTH}.",
                0,
                source_name,
            )
        for statement in statements:
            value = statement.value
            if isinstance(value, _ParamStatement):
                parameters = _apply_assignments(parameters, value.assignments, statement.line, source_name)
                if depth == 0:
                    declared_here = {name for name, _ in value.assignments}
                    for name in declared_here & set(top_parameter_overrides):
                        parameters[name] = top_parameter_overrides[name]
                continue
            if isinstance(value, (_ElementSpec, _Diode)):
                if len(elements) >= MAX_EXPANDED_ELEMENTS:
                    raise _error(
                        "SPIKES_NETLIST_EXPANSION_LIMIT",
                        f"Flattened circuit exceeds {MAX_EXPANDED_ELEMENTS} elements.",
                        statement.line,
                        source_name,
                    )
                name = f"{path}:{value.name}" if path else value.name
                try:
                    if isinstance(value, _Diode):
                        model = diode_models.get(value.model_name)
                        if model is None:
                            raise _error(
                                "SPIKES_NETLIST_MODEL_UNKNOWN",
                                f"Diode {value.name} references unknown model {value.model_name}.",
                                statement.line,
                                source_name,
                            )
                        elements.append(CircuitElement(
                            name=name,
                            kind="diode",
                            positive_node=scoped_node(value.anode, bindings, path),
                            negative_node=scoped_node(value.cathode, bindings, path),
                            value=0.0,
                            model_name=value.model_name,
                            diode_model=model,
                        ))
                    else:
                        resolved = _element(
                            list(value.tokens), statement.line, source_name,
                            native_extensions=value.native_extensions, parameters=parameters,
                        )
                        elements.append(CircuitElement(
                            name=name,
                            kind=resolved.kind,
                            positive_node=scoped_node(resolved.positive_node, bindings, path),
                            negative_node=scoped_node(resolved.negative_node, bindings, path),
                            value=resolved.value,
                            waveform=resolved.waveform,
                            control_positive_node=(
                                scoped_node(resolved.control_positive_node, bindings, path)
                                if resolved.control_positive_node is not None
                                else None
                            ),
                            control_negative_node=(
                                scoped_node(resolved.control_negative_node, bindings, path)
                                if resolved.control_negative_node is not None
                                else None
                            ),
                            control_source_id=(
                                f"{path}:{resolved.control_source_id}" if path and resolved.control_source_id is not None
                                else resolved.control_source_id
                            ),
                            behavioral_expression=scoped_behavioral(resolved.behavioral_expression, bindings, path),
                            switch_model=resolved.switch_model,
                            ac_magnitude=resolved.ac_magnitude,
                            ac_phase_deg=resolved.ac_phase_deg,
                            initial_condition=resolved.initial_condition,
                        ))
                except NetlistParseError:
                    raise
                except ValueError as exc:
                    raise _error("SPIKES_NETLIST_ELABORATION_INVALID", str(exc), statement.line, source_name) from exc
                continue

            if len(hierarchy) >= MAX_EXPANDED_INSTANCES:
                raise _error(
                    "SPIKES_NETLIST_INSTANCE_LIMIT",
                    f"Flattened circuit exceeds {MAX_EXPANDED_INSTANCES} subcircuit instances.",
                    statement.line,
                    source_name,
                )
            definition = definitions[value.definition]
            declared = {name for name, _ in definition.parameter_defaults}
            unknown = {name for name, _ in value.parameter_overrides} - declared
            if unknown:
                raise _error(
                    "SPIKES_NETLIST_INSTANCE_PARAM_UNKNOWN",
                    f"Instance {value.name} overrides undeclared parameters: {', '.join(sorted(unknown))}.",
                    statement.line,
                    source_name,
                )
            instance_path = f"{path}:{value.name}" if path else value.name
            bound_nodes = tuple(scoped_node(node, bindings, path) for node in value.nodes)
            hierarchy.append(HierarchyInstance(
                path=instance_path,
                definition=definition.name,
                parent_path=path,
                pins=definition.pins,
                nodes=bound_nodes,
            ))
            child_bindings = dict(zip(definition.pins, bound_nodes, strict=True))
            child_parameters = _apply_assignments(
                parameters, definition.parameter_defaults, definition.line, source_name
            )
            child_parameters = _apply_assignments(
                child_parameters, value.parameter_overrides, statement.line, source_name
            )
            expand(definition.body, child_bindings, instance_path, depth + 1, child_parameters)

    expand(top, {}, "", 0, {})
    return tuple(elements), tuple(hierarchy)


def parse_netlist(
    text: str,
    *,
    source_name: str = "<memory>",
    probes: Iterable[ProbeDescriptor] = (),
    native_extensions: bool = False,
    transient_capture: str = "full",
) -> CircuitProject:
    """Parse the bounded owned-engine subset with deterministic elaboration.

    Parameter expressions are arithmetic-only and scoped to the top level or a
    subcircuit instance. Includes are confined to the top-level file directory.
    ``rolling`` is for editor validation / bounded persistent-session capture;
    it does not authorize allocating a full transient history beyond the limit.
    """

    if not isinstance(text, str):
        raise TypeError("netlist text must be a string.")
    if transient_capture not in {"full", "rolling"}:
        raise ValueError("transient_capture must be full or rolling")
    original_encoded = text.encode("utf-8")
    if len(original_encoded) > MAX_NETLIST_BYTES or len(text.splitlines()) > MAX_NETLIST_LINES:
        raise _error("SPIKES_NETLIST_SIZE_LIMIT", "Top-level netlist exceeds the input resource limits.", 0, source_name)
    text = _expand_local_includes(text, source_name)
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_NETLIST_BYTES:
        raise _error("SPIKES_NETLIST_SIZE_LIMIT", "Netlist exceeds the 8 MiB input limit.", 0, source_name)
    physical_lines = text.splitlines()
    if len(physical_lines) > MAX_NETLIST_LINES:
        raise _error("SPIKES_NETLIST_LINE_LIMIT", "Netlist exceeds the line-count limit.", 0, source_name)
    lines: list[tuple[int, str]] = []
    for physical_line_number, raw_line in enumerate(physical_lines, start=1):
        content = _content(raw_line)
        if not content:
            continue
        if content.startswith("+"):
            continuation = content[1:].strip()
            if not lines:
                raise _error(
                    "SPIKES_NETLIST_CONTINUATION_ORPHAN",
                    "Continuation line has no preceding statement.",
                    physical_line_number, source_name,
                )
            if not continuation:
                raise _error(
                    "SPIKES_NETLIST_CONTINUATION_EMPTY",
                    "Continuation line contains no statement text.",
                    physical_line_number, source_name,
                )
            original_line_number, original = lines[-1]
            combined = f"{original} {continuation}"
            if len(combined.encode("utf-8")) > MAX_NETLIST_BYTES:
                raise _error(
                    "SPIKES_NETLIST_SIZE_LIMIT", "Logical line exceeds the input resource limit.",
                    physical_line_number, source_name,
                )
            lines[-1] = (original_line_number, combined)
        else:
            lines.append((physical_line_number, content))
    lines = _expand_user_functions(lines, source_name)

    title = ""
    top: list[_Statement] = []
    definitions: dict[str, _Subcircuit] = {}
    diode_models: dict[str, DiodeModel] = {}
    current_name = ""
    current_pins: tuple[str, ...] = ()
    current_parameter_defaults: tuple[tuple[str, str], ...] = ()
    current_body: list[_Statement] = []
    current_line = 0
    analysis: AnalysisDirective | None = None
    ac_request: tuple[str, int, float, float] | None = None
    ended = False
    saw_statement = False
    significant_index = 0
    global_nodes: set[str] = set()
    top_parameter_values: dict[str, float] = {}
    steps: list[StepDirective] = []
    measurements: list[MeasureDirective] = []
    temperature_c = 27.0
    temperature_declared = False

    for line_number, line in lines:
        significant_index += 1
        if ended:
            raise _error("SPIKES_NETLIST_AFTER_END", "Statements after .end are not allowed.", line_number, source_name)
        try:
            tokens = _tokens(line)
        except ValueError as exc:
            raise _error("SPIKES_NETLIST_TOKEN_INVALID", str(exc), line_number, source_name) from exc
        keyword = tokens[0].lower()

        if keyword == ".subckt":
            if current_name:
                raise _error(
                    "SPIKES_NETLIST_SUBCKT_DEFINITION_NESTED",
                    "Subcircuit definitions cannot be lexically nested; instantiate a separately defined subcircuit instead.",
                    line_number,
                    source_name,
                )
            current_name, current_pins, current_parameter_defaults = _subcircuit_header(tokens, line_number, source_name)
            if current_name in definitions:
                raise _error(
                    "SPIKES_NETLIST_SUBCKT_DUPLICATE",
                    f"Subcircuit {current_name} is defined more than once.",
                    line_number,
                    source_name,
                )
            if len(definitions) >= MAX_SUBCIRCUITS:
                raise _error(
                    "SPIKES_NETLIST_SUBCKT_LIMIT",
                    f"Netlist exceeds {MAX_SUBCIRCUITS} subcircuit definitions.",
                    line_number,
                    source_name,
                )
            current_body = []
            current_line = line_number
            saw_statement = True
            continue
        if keyword == ".ends":
            if not current_name:
                raise _error("SPIKES_NETLIST_ENDS_UNMATCHED", ".ends has no matching .subckt.", line_number, source_name)
            if len(tokens) > 2:
                raise _error("SPIKES_NETLIST_ENDS_ARITY", ".ends accepts only an optional subcircuit name.", line_number, source_name)
            if len(tokens) == 2 and tokens[1].lower() != current_name:
                raise _error(
                    "SPIKES_NETLIST_ENDS_MISMATCH",
                    f".ends {tokens[1]} does not match .subckt {current_name}.",
                    line_number,
                    source_name,
                )
            definitions[current_name] = _Subcircuit(
                current_name, current_pins, tuple(current_body), current_line,
                current_parameter_defaults,
            )
            current_name = ""
            current_pins = ()
            current_parameter_defaults = ()
            current_body = []
            current_line = 0
            continue

        if keyword == ".param":
            assignments = _parse_assignments(line[len(tokens[0]):], line_number, source_name)
            statement = _Statement(_ParamStatement(assignments), line_number)
            if current_name:
                current_body.append(statement)
            else:
                top.append(statement)
                top_parameter_values = _apply_assignments(
                    top_parameter_values, assignments, line_number, source_name
                )
                saw_statement = True
            continue

        if keyword == ".temp":
            if current_name:
                raise _error("SPIKES_NETLIST_SUBCKT_DIRECTIVE_UNSUPPORTED", ".temp is permitted only at top level.", line_number, source_name)
            if len(tokens) != 2 or temperature_declared:
                raise _error("SPIKES_NETLIST_TEMP_ARITY", ".temp requires exactly one temperature and may appear once.", line_number, source_name)
            try:
                temperature_c = _evaluate_expression(tokens[1], top_parameter_values, "scalar")
                if not -273.15 < temperature_c <= 2000.0:
                    raise ValueError("Circuit temperature must be above absolute zero and at most 2000 C.")
            except ValueError as exc:
                raise _error("SPIKES_NETLIST_TEMP_INVALID", str(exc), line_number, source_name) from exc
            temperature_declared = True
            saw_statement = True
            continue

        if keyword == ".global":
            if current_name:
                raise _error("SPIKES_NETLIST_SUBCKT_DIRECTIVE_UNSUPPORTED", ".global is permitted only at top level.", line_number, source_name)
            if len(tokens) < 2:
                raise _error("SPIKES_NETLIST_GLOBAL_ARITY", ".global requires at least one node name.", line_number, source_name)
            for node in tokens[1:]:
                normalized = node.lower()
                if normalized == "0" or _LOCAL_NAME_RE.fullmatch(node) is None or ":" in node:
                    raise _error("SPIKES_NETLIST_GLOBAL_INVALID", "Global node names must be local names other than node 0.", line_number, source_name)
                global_nodes.add(normalized)
            saw_statement = True
            continue

        if keyword == ".step":
            if current_name:
                raise _error("SPIKES_NETLIST_SUBCKT_DIRECTIVE_UNSUPPORTED", ".step is permitted only at top level.", line_number, source_name)
            list_sweep=len(tokens)>=5 and tokens[3].lower()=='list'
            if (not list_sweep and len(tokens) != 6) or len(tokens)<3 or tokens[1].lower() != "param":
                raise _error(
                    "SPIKES_NETLIST_STEP_UNSUPPORTED",
                    "Use .step param NAME START STOP STEP or .step param NAME list VALUE... .",
                    line_number,
                    source_name,
                )
            parameter = tokens[2].lower()
            if parameter not in top_parameter_values:
                raise _error("SPIKES_NETLIST_STEP_PARAM_UNKNOWN", f"STEP parameter {parameter} must be declared by an earlier top-level .param.", line_number, source_name)
            if any(step.parameter == parameter for step in steps):
                raise _error("SPIKES_NETLIST_STEP_DUPLICATE", f"STEP parameter {parameter} is duplicated.", line_number, source_name)
            if len(steps) >= MAX_STEP_DIRECTIVES:
                raise _error("SPIKES_NETLIST_STEP_LIMIT", f"More than {MAX_STEP_DIRECTIVES} nested STEP axes are not allowed.", line_number, source_name)
            try:
                if list_sweep and len(tokens)-4>MAX_STEP_VARIANTS:
                    raise ValueError(f'STEP list exceeds {MAX_STEP_VARIANTS} values')
                values = tuple(_evaluate_expression(token,top_parameter_values,'scalar') for token in tokens[4:]) if list_sweep else _linear_step_values(
                    _evaluate_expression(tokens[3], top_parameter_values, "scalar"),
                    _evaluate_expression(tokens[4], top_parameter_values, "scalar"),
                    _evaluate_expression(tokens[5], top_parameter_values, "scalar"),
                )
                step = StepDirective(parameter=parameter, values=values)
            except ValueError as exc:
                raise _error("SPIKES_NETLIST_STEP_INVALID", str(exc), line_number, source_name) from exc
            if math.prod(len(item.values) for item in (*steps, step)) > MAX_STEP_VARIANTS:
                raise _error("SPIKES_NETLIST_STEP_LIMIT", f"Nested STEP expansion exceeds {MAX_STEP_VARIANTS} variants.", line_number, source_name)
            steps.append(step)
            saw_statement = True
            continue

        if keyword in {".measure", ".meas"}:
            if current_name:
                raise _error("SPIKES_NETLIST_SUBCKT_DIRECTIVE_UNSUPPORTED", ".measure is permitted only at top level.", line_number, source_name)
            measure = _measure_directive(tokens, top_parameter_values, line_number, source_name)
            if any(item.name.lower() == measure.name.lower() for item in measurements):
                raise _error("SPIKES_NETLIST_MEASURE_DUPLICATE", f"Measurement {measure.name} is duplicated.", line_number, source_name)
            if len(measurements) >= MAX_MEASUREMENTS:
                raise _error(
                    "SPIKES_NETLIST_MEASURE_LIMIT",
                    f"More than {MAX_MEASUREMENTS} measurements are not allowed.",
                    line_number,
                    source_name,
                )
            measurements.append(measure)
            saw_statement = True
            continue

        if keyword == ".model":
            if current_name:
                raise _error(
                    "SPIKES_NETLIST_SUBCKT_DIRECTIVE_UNSUPPORTED",
                    ".model cards are supported only at top level in this bounded slice.",
                    line_number,
                    source_name,
                )
            model_name, model = _diode_model(line, line_number, source_name)
            if model_name in diode_models:
                raise _error(
                    "SPIKES_NETLIST_MODEL_DUPLICATE",
                    f"Model {model_name} is defined more than once.",
                    line_number,
                    source_name,
                )
            diode_models[model_name] = model
            saw_statement = True
            continue

        if current_name:
            if keyword.startswith("."):
                raise _error(
                    "SPIKES_NETLIST_SUBCKT_DIRECTIVE_UNSUPPORTED",
                    f"Directive {tokens[0]} is not supported inside a subcircuit definition.",
                    line_number,
                    source_name,
                )
            current_body.append(
                _statement(
                    tokens, line_number, source_name,
                    native_extensions=native_extensions,
                )
            )
            continue

        if keyword == ".title":
            if saw_statement or title or len(tokens) < 2:
                raise _error("SPIKES_NETLIST_TITLE_INVALID", ".title must appear once before circuit statements.", line_number, source_name)
            title = line[len(tokens[0]):].strip()
            continue
        if keyword == ".end":
            if len(tokens) != 1:
                raise _error("SPIKES_NETLIST_END_ARITY", ".end takes no arguments.", line_number, source_name)
            ended = True
            continue
        if keyword == ".op":
            if len(tokens) != 1:
                raise _error("SPIKES_NETLIST_OP_ARITY", ".op takes no arguments.", line_number, source_name)
            if analysis is not None or ac_request is not None:
                raise _error("SPIKES_NETLIST_ANALYSIS_DUPLICATE", "Exactly one .op, .dc, .ac, or .tran analysis is allowed.", line_number, source_name)
            analysis = AnalysisDirective(mode="operating_point")
            saw_statement = True
            continue
        if keyword == ".dc":
            if len(tokens) != 5:
                raise _error("SPIKES_NETLIST_DC_ARITY", ".dc requires SOURCE START STOP STEP.", line_number, source_name)
            if analysis is not None or ac_request is not None:
                raise _error("SPIKES_NETLIST_ANALYSIS_DUPLICATE", "Exactly one .op, .dc, .ac, or .tran analysis is allowed.", line_number, source_name)
            try:
                source_leaf = tokens[1].rsplit(":", 1)[-1]
                source_quantity = "voltage_source" if source_leaf[:1].lower() == "v" else "current_source"
                analysis = AnalysisDirective(
                    mode="dc_sweep",
                    source=tokens[1],
                    start=_evaluate_expression(tokens[2], top_parameter_values, source_quantity),
                    stop=_evaluate_expression(tokens[3], top_parameter_values, source_quantity),
                    step=_evaluate_expression(tokens[4], top_parameter_values, source_quantity),
                )
            except ValueError as exc:
                raise _error("SPIKES_NETLIST_DC_INVALID", str(exc), line_number, source_name) from exc
            point_count = int(math.floor(abs((analysis.stop - analysis.start) / analysis.step) + 1e-12)) + 1
            if point_count > MAX_SWEEP_POINTS:
                raise _error("SPIKES_NETLIST_SWEEP_LIMIT", f"DC sweep exceeds {MAX_SWEEP_POINTS} points.", line_number, source_name)
            saw_statement = True
            continue
        if keyword == ".ac":
            if len(tokens) != 5:
                raise _error(
                    "SPIKES_NETLIST_AC_ARITY",
                    ".ac requires LIN|DEC|OCT POINTS START STOP.",
                    line_number, source_name,
                )
            if analysis is not None or ac_request is not None:
                raise _error("SPIKES_NETLIST_ANALYSIS_DUPLICATE", "Exactly one .op, .dc, .ac, or .tran analysis is allowed.", line_number, source_name)
            scale = tokens[1].lower()
            if scale not in {"lin", "dec", "oct"}:
                raise _error("SPIKES_NETLIST_AC_SCALE", ".ac scale must be LIN, DEC, or OCT.", line_number, source_name)
            try:
                density = int(tokens[2])
                if str(density) != tokens[2].lstrip("+") or density <= 0:
                    raise ValueError("AC point count must be a positive integer.")
                start_hz = _evaluate_expression(tokens[3], top_parameter_values, "scalar")
                stop_hz = _evaluate_expression(tokens[4], top_parameter_values, "scalar")
                if start_hz <= 0.0 or stop_hz < start_hz:
                    raise ValueError("AC frequencies must be positive and ascending.")
                if scale == "lin":
                    point_count = density
                else:
                    span = math.log10(stop_hz / start_hz) if scale == "dec" else math.log2(stop_hz / start_hz)
                    point_count = int(math.floor(density * span + 1.0e-12)) + 1
                if not 1 <= point_count <= 65_536:
                    raise ValueError("AC sweep exceeds 65536 points.")
                ac_request = (scale, point_count, start_hz, stop_hz)
            except ValueError as exc:
                raise _error("SPIKES_NETLIST_AC_INVALID", str(exc), line_number, source_name) from exc
            saw_statement = True
            continue
        if keyword == ".tran":
            if len(tokens) not in {3, 4} or (len(tokens) == 4 and tokens[3].lower() != "uic"):
                raise _error(
                    "SPIKES_NETLIST_TRAN_ARITY",
                    ".tran requires TSTEP TSTOP with an optional UIC token; TSTART and TMAX remain unsupported.",
                    line_number,
                    source_name,
                )
            if analysis is not None or ac_request is not None:
                raise _error(
                    "SPIKES_NETLIST_ANALYSIS_DUPLICATE",
                    "Exactly one .op, .dc, .ac, or .tran analysis is allowed.",
                    line_number,
                    source_name,
                )
            try:
                analysis = AnalysisDirective(
                    mode="transient",
                    time_step_s=_evaluate_expression(tokens[1], top_parameter_values, "time"),
                    stop_time_s=_evaluate_expression(tokens[2], top_parameter_values, "time"),
                    use_initial_conditions=len(tokens) == 4,
                )
            except ValueError as exc:
                raise _error("SPIKES_NETLIST_TRAN_INVALID", str(exc), line_number, source_name) from exc
            assert analysis.time_step_s is not None and analysis.stop_time_s is not None
            point_ratio = analysis.stop_time_s / analysis.time_step_s
            if transient_capture == 'full' and (
                not math.isfinite(point_ratio)
                or int(math.floor(point_ratio + 1e-12)) + 1 > MAX_TRANSIENT_POINTS
            ):
                raise _error(
                    "SPIKES_NETLIST_TRAN_LIMIT",
                    f"Transient analysis exceeds {MAX_TRANSIENT_POINTS} output points.",
                    line_number,
                    source_name,
                )
            saw_statement = True
            continue
        if keyword.startswith("."):
            raise _error("SPIKES_NETLIST_DIRECTIVE_UNSUPPORTED", f"Unsupported directive {tokens[0]}.", line_number, source_name)

        prefix = tokens[0][0].upper()
        if prefix in {"R", "C", "L", "V", "I", "D", "E", "G", "F", "H", "B", "X"} or (
            native_extensions and prefix == "S"
        ):
            # A prose first line is accepted as a conventional title only when
            # its arity cannot be mistaken for a circuit statement.
            try:
                parsed = _statement(
                    tokens, line_number, source_name,
                    native_extensions=native_extensions,
                )
            except NetlistParseError:
                minimum_arity = 3 if prefix == "X" else (9 if prefix == "S" else 4)
                if significant_index == 1 and len(tokens) < minimum_arity and not _DESIGNATOR_RE.fullmatch(tokens[0]):
                    title = line
                    continue
                raise
            top.append(parsed)
            saw_statement = True
            continue
        if significant_index == 1 and len(tokens) < 4 and not _DESIGNATOR_RE.fullmatch(tokens[0]):
            title = line
            continue
        raise _error(
            "SPIKES_NETLIST_ELEMENT_UNSUPPORTED",
            f"Unsupported element {tokens[0]}; only R, C, L, V, I, D, X{', and native S' if native_extensions else ''} are accepted.",
            line_number,
            source_name,
        )

    if current_name:
        raise _error(
            "SPIKES_NETLIST_SUBCKT_UNTERMINATED",
            f"Subcircuit {current_name} is missing .ends.",
            current_line,
            source_name,
        )
    _validate_hierarchy(definitions, tuple(top), source_name)
    elements, hierarchy = _flatten(
        tuple(top), definitions, diode_models, global_nodes, source_name
    )
    temperature_k = temperature_c + 273.15
    elements = tuple(
        replace(element, diode_model=replace(element.diode_model, temperature_k=temperature_k))
        if element.kind == "diode" and element.diode_model is not None
        else element
        for element in elements
    )
    if not elements:
        raise _error("SPIKES_NETLIST_EMPTY", "Netlist contains no supported circuit elements.", 0, source_name)
    if ac_request is not None:
        ac_sources = [
            element for element in elements
            if element.kind in {"voltage_source", "current_source"}
            and element.ac_magnitude > 0.0
        ]
        if len(ac_sources) != 1:
            raise _error(
                "SPIKES_NETLIST_AC_EXCITATION",
                "The owned .ac route requires exactly one independent source with a positive AC magnitude.",
                0, source_name,
            )
        scale, point_count, start_hz, stop_hz = ac_request
        analysis = AnalysisDirective(
            mode="ac", source=ac_sources[0].name,
            frequency_scale=scale, frequency_points=point_count,
            start_frequency_hz=start_hz, stop_frequency_hz=stop_hz,
        )
    if analysis is None:
        raise _error(
            "SPIKES_NETLIST_ANALYSIS_REQUIRED",
            "Netlist requires exactly one .op, .dc, .ac, or .tran directive.",
            0,
            source_name,
        )
    analysis_points = 1
    if analysis.mode == "dc_sweep":
        assert analysis.start is not None and analysis.stop is not None and analysis.step is not None
        analysis_points = int(math.floor(abs((analysis.stop - analysis.start) / analysis.step) + 1e-12)) + 1
    elif analysis.mode == "transient":
        assert analysis.time_step_s is not None and analysis.stop_time_s is not None
        analysis_points = int(math.floor(analysis.stop_time_s / analysis.time_step_s + 1e-12)) + 1
    elif analysis.mode == "ac":
        assert analysis.frequency_points is not None
        analysis_points = analysis.frequency_points
    variant_count = math.prod(len(step.values) for step in steps) if steps else 0
    if variant_count and variant_count * analysis_points > MAX_STEPPED_WORK_POINTS:
        raise _error(
            "SPIKES_NETLIST_STEP_WORK_LIMIT",
            f"STEP expansion times analysis points exceeds {MAX_STEPPED_WORK_POINTS} work points.",
            0,
            source_name,
        )
    step_variants: list[StepVariant] = []
    if steps:
        names = tuple(step.parameter for step in steps)
        for values in itertools.product(*(step.values for step in steps)):
            parameters = dict(zip(names, values, strict=True))
            variant_elements, variant_hierarchy = _flatten(
                tuple(top), definitions, diode_models, global_nodes, source_name,
                parameters,
            )
            variant_elements = tuple(
                replace(element, diode_model=replace(element.diode_model, temperature_k=temperature_k))
                if element.kind == "diode" and element.diode_model is not None
                else element
                for element in variant_elements
            )
            if variant_hierarchy != hierarchy:
                raise _error("SPIKES_NETLIST_STEP_TOPOLOGY", "STEP parameters may not alter hierarchy topology.", 0, source_name)
            step_variants.append(StepVariant(tuple(zip(names, values, strict=True)), variant_elements))
    names = [element.name for element in elements]
    if len(names) != len(set(names)):
        raise _error("SPIKES_NETLIST_ELEMENT_DUPLICATE", "Element names must be unique ignoring case.", 0, source_name)

    try:
        return CircuitProject(
            title=title,
            elements=tuple(elements),
            analysis=analysis,
            probes=tuple(probes),
            hierarchy=hierarchy,
            global_nodes=tuple(sorted(global_nodes)),
            steps=tuple(steps),
            step_variants=tuple(step_variants),
            measurements=tuple(measurements),
            temperature_c=temperature_c,
            source_name=source_name,
            source_sha256=hashlib.sha256(encoded).hexdigest(),
        )
    except ValueError as exc:
        raise _error("SPIKES_NETLIST_PROJECT_INVALID", str(exc), 0, source_name) from exc


__all__ = [
    "MAX_NETLIST_BYTES",
    "MAX_NETLIST_LINES",
    "MAX_SWEEP_POINTS",
    "MAX_TRANSIENT_POINTS",
    "MAX_SUBCIRCUITS",
    "MAX_HIERARCHY_DEPTH",
    "MAX_EXPANDED_INSTANCES",
    "MAX_EXPANDED_ELEMENTS",
    "NetlistParseError",
    "parse_netlist",
    "parse_spice_number",
]
