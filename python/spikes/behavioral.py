"""Safe differentiable expressions for bounded nonlinear behavioral sources."""

from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass
from typing import Mapping, Sequence


BEHAVIORAL_EXPRESSION_CONTRACT = "spikes/behavioral-expression/v1"
MAX_BEHAVIORAL_NODES = 192
MAX_BEHAVIORAL_SIGNALS = 32


def structurally_affine(tree):
    """Conservative proof; point samples cannot establish global linearity."""
    def degree(node):
        if isinstance(node,ast.Expression):return degree(node.body)
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):return 0
        if isinstance(node,ast.Name):return 1
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):return degree(node.operand)
        if isinstance(node,ast.BinOp):
            a,b=degree(node.left),degree(node.right)
            if a is None or b is None:return None
            if isinstance(node.op,(ast.Add,ast.Sub)):return max(a,b)
            if isinstance(node.op,ast.Mult) and a+b<=1:return a+b
            if isinstance(node.op,ast.Div) and b==0:return a
        return None
    return degree(tree) is not None

_SIGNAL_RE = re.compile(
    r"(?i)\b(?P<kind>[vi])\(\s*(?P<first>[A-Za-z0-9_.$:+-]+)"
    r"(?:\s*,\s*(?P<second>[A-Za-z0-9_.$:+-]+))?\s*\)"
)
_UNARY_FUNCTIONS = {
    "abs", "acos", "acosh", "asin", "asinh", "atan", "cos", "cosh",
    "ceil", "exp", "floor", "int", "log", "log10", "sgn", "sin",
    "sinh", "sqrt", "tanh", "u", "uramp",
}
_BINARY_FUNCTIONS = {"atan2", "hypot", "max", "min", "pow"}
_TERNARY_FUNCTIONS = {"limit", "spice_if"}
_VARIADIC_FUNCTIONS = {"table"}
_FUNCTIONS = _UNARY_FUNCTIONS | _BINARY_FUNCTIONS | _TERNARY_FUNCTIONS | _VARIADIC_FUNCTIONS


@dataclass(frozen=True, slots=True)
class BehavioralSignal:
    kind: str
    first: str
    second: str = "0"

    def __post_init__(self) -> None:
        kind = self.kind.lower()
        if kind not in {"v", "i"}:
            raise ValueError("Behavioral signal kind must be V or I.")
        if kind == "i" and self.second != "0":
            raise ValueError("I(...) accepts exactly one voltage-defined branch name.")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "first", self.first.lower() if kind == "v" else self.first.upper())
        object.__setattr__(self, "second", self.second.lower() if kind == "v" else "0")


@dataclass(frozen=True, slots=True)
class BehavioralEvaluation:
    value: float
    gradient: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class CompiledBehavioralExpression:
    source: str
    normalized: str
    signals: tuple[BehavioralSignal, ...]
    tree: ast.Expression
    contract: str = BEHAVIORAL_EXPRESSION_CONTRACT

    def evaluate(self, signal_values: Sequence[float], *, time_s: float = 0.0) -> BehavioralEvaluation:
        if not math.isfinite(time_s):raise ValueError('Behavioral time must be finite')
        if len(signal_values) != len(self.signals):
            raise ValueError("Behavioral signal count does not match the compiled expression.")
        values = tuple(float(value) for value in signal_values)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("Behavioral signals must be finite.")
        count = len(values)

        def constant(value: float) -> tuple[float, list[float]]:
            return value, [0.0] * count

        def evaluate(node: ast.AST) -> tuple[float, list[float]]:
            if isinstance(node, ast.Expression):
                return evaluate(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return constant(float(node.value))
            if isinstance(node, ast.Name):
                if node.id == 'time':return constant(time_s)
                if node.id == "pi":
                    return constant(math.pi)
                if node.id == "e":
                    return constant(math.e)
                if node.id.startswith("__s") and node.id[3:].isdigit():
                    index = int(node.id[3:])
                    gradient = [0.0] * count
                    gradient[index] = 1.0
                    return values[index], gradient
                raise ValueError(f"Unknown behavioral name {node.id}.")
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                value, gradient = evaluate(node.operand)
                return (value, gradient) if isinstance(node.op, ast.UAdd) else (-value, [-item for item in gradient])
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow)):
                left, dl = evaluate(node.left)
                right, dr = evaluate(node.right)
                if isinstance(node.op, ast.Add):
                    result, gradient = left + right, [a + b for a, b in zip(dl, dr)]
                elif isinstance(node.op, ast.Sub):
                    result, gradient = left - right, [a - b for a, b in zip(dl, dr)]
                elif isinstance(node.op, ast.Mult):
                    result, gradient = left * right, [a * right + left * b for a, b in zip(dl, dr)]
                elif isinstance(node.op, ast.Div):
                    if right == 0.0:
                        raise ValueError("Behavioral expression divided by zero.")
                    result, gradient = left / right, [(a * right - left * b) / (right * right) for a, b in zip(dl, dr)]
                elif isinstance(node.op, ast.Mod):
                    if right == 0.0:
                        raise ValueError("Behavioral modulo divided by zero.")
                    quotient = left / right
                    if quotient == round(quotient):
                        raise ValueError("Behavioral modulo is on a discontinuity boundary.")
                    multiple = math.floor(quotient)
                    result = left - multiple * right
                    gradient = [a - multiple * b for a, b in zip(dl, dr)]
                else:
                    if any(dr):
                        if left <= 0.0:
                            raise ValueError("A variable exponent requires a positive base.")
                        result = left ** right
                        gradient = [result * (b * math.log(left) + right * a / left) for a, b in zip(dl, dr)]
                    else:
                        if abs(right) > 32.0:
                            raise ValueError("Behavioral exponent exceeds the bounded range.")
                        if left < 0.0 and abs(right - round(right)) > 1.0e-12:
                            raise ValueError("A negative base requires an integer constant exponent.")
                        if left == 0.0 and right < 1.0:
                            raise ValueError("Behavioral power is singular at zero.")
                        result = left ** right
                        factor = 0.0 if right == 0.0 else right * (left ** (right - 1.0))
                        gradient = [factor * item for item in dl]
                if not math.isfinite(result) or any(not math.isfinite(item) for item in gradient):
                    raise ValueError("Behavioral expression produced a non-finite value or derivative.")
                return result, gradient
            if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
                left, _dl = evaluate(node.left)
                right, _dr = evaluate(node.comparators[0])
                if left == right:
                    raise ValueError("Behavioral comparison is on its discontinuity boundary.")
                operator = node.ops[0]
                if isinstance(operator, (ast.Gt, ast.GtE)):
                    result = left > right
                elif isinstance(operator, (ast.Lt, ast.LtE)):
                    result = left < right
                else:  # pragma: no cover - validation rejects this before evaluation
                    raise ValueError("Unsupported behavioral comparison.")
                return constant(1.0 if result else 0.0)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _UNARY_FUNCTIONS and len(node.args) == 1 and not node.keywords:
                argument, derivative = evaluate(node.args[0])
                name = node.func.id
                if name == "exp":
                    if argument > 700.0:
                        raise ValueError("Behavioral exponential overflow.")
                    value, slope = math.exp(argument), math.exp(argument)
                elif name == "log":
                    if argument <= 0.0:
                        raise ValueError("Behavioral logarithm requires a positive argument.")
                    value, slope = math.log(argument), 1.0 / argument
                elif name == "sqrt":
                    if argument <= 0.0:
                        raise ValueError("Differentiable behavioral sqrt requires a positive argument.")
                    value, slope = math.sqrt(argument), 0.5 / math.sqrt(argument)
                elif name == "sin":
                    value, slope = math.sin(argument), math.cos(argument)
                elif name == "cos":
                    value, slope = math.cos(argument), -math.sin(argument)
                elif name == "tanh":
                    value, slope = math.tanh(argument), 1.0 - math.tanh(argument) ** 2
                elif name == "abs":
                    if argument == 0.0:
                        raise ValueError("Behavioral abs is nondifferentiable at zero.")
                    value, slope = abs(argument), math.copysign(1.0, argument)
                elif name == "atan":
                    value, slope = math.atan(argument), 1.0 / (1.0 + argument * argument)
                elif name in {"asin", "acos"}:
                    if abs(argument) >= 1.0:
                        raise ValueError(f"Differentiable behavioral {name} requires abs(argument) < 1.")
                    value = math.asin(argument) if name == "asin" else math.acos(argument)
                    slope = (1.0 if name == "asin" else -1.0) / math.sqrt(1.0 - argument * argument)
                elif name == "sinh":
                    value, slope = math.sinh(argument), math.cosh(argument)
                elif name == "cosh":
                    value, slope = math.cosh(argument), math.sinh(argument)
                elif name == "asinh":
                    value, slope = math.asinh(argument), 1.0 / math.sqrt(1.0 + argument * argument)
                elif name == "acosh":
                    if argument <= 1.0:
                        raise ValueError("Differentiable behavioral acosh requires an argument above 1.")
                    value, slope = math.acosh(argument), 1.0 / math.sqrt(argument * argument - 1.0)
                elif name == "log10":
                    if argument <= 0.0:
                        raise ValueError("Behavioral log10 requires a positive argument.")
                    value, slope = math.log10(argument), 1.0 / (argument * math.log(10.0))
                elif name in {"ceil", "floor", "int"}:
                    if argument == round(argument):
                        raise ValueError(f"Behavioral {name} is on a discontinuity boundary.")
                    if name == "ceil":
                        value = float(math.ceil(argument))
                    elif name == "floor":
                        value = float(math.floor(argument))
                    else:
                        value = float(math.trunc(argument))
                    slope = 0.0
                elif name in {"sgn", "u"}:
                    if argument == 0.0:
                        raise ValueError(f"Behavioral {name} is on a discontinuity boundary.")
                    value = math.copysign(1.0, argument) if name == "sgn" else (1.0 if argument > 0.0 else 0.0)
                    slope = 0.0
                elif name == "uramp":
                    if argument == 0.0:
                        raise ValueError("Behavioral uramp is nondifferentiable at zero.")
                    value, slope = (argument, 1.0) if argument > 0.0 else (0.0, 0.0)
                else:  # pragma: no cover - exhaustive over _UNARY_FUNCTIONS
                    raise ValueError(f"Unsupported behavioral function {name}.")
                if not math.isfinite(value) or not math.isfinite(slope):
                    raise ValueError("Behavioral function produced a non-finite value or derivative.")
                return value, [slope * item for item in derivative]
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _BINARY_FUNCTIONS and len(node.args) == 2 and not node.keywords:
                left, dl = evaluate(node.args[0])
                right, dr = evaluate(node.args[1])
                name = node.func.id
                if name == "atan2":
                    denominator = left * left + right * right
                    if denominator == 0.0:
                        raise ValueError("Behavioral atan2 is undefined at the origin.")
                    value = math.atan2(left, right)
                    gradient = [(right * a - left * b) / denominator for a, b in zip(dl, dr)]
                elif name == "hypot":
                    value = math.hypot(left, right)
                    if value == 0.0:
                        raise ValueError("Behavioral hypot is nondifferentiable at the origin.")
                    gradient = [(left * a + right * b) / value for a, b in zip(dl, dr)]
                elif name in {"min", "max"}:
                    if left == right:
                        raise ValueError(f"Behavioral {name} is nondifferentiable at equal arguments.")
                    select_left = left < right if name == "min" else left > right
                    value, gradient = (left, dl) if select_left else (right, dr)
                else:
                    if left <= 0.0 and any(dr):
                        raise ValueError("Behavioral pow with a variable exponent requires a positive base.")
                    if not any(dr) and abs(right) > 32.0:
                        raise ValueError("Behavioral exponent exceeds the bounded range.")
                    if left < 0.0 and abs(right - round(right)) > 1.0e-12:
                        raise ValueError("A negative pow base requires an integer constant exponent.")
                    if left == 0.0 and right < 1.0:
                        raise ValueError("Behavioral pow is singular at zero.")
                    value = left ** right
                    if any(dr):
                        gradient = [value * (b * math.log(left) + right * a / left) for a, b in zip(dl, dr)]
                    else:
                        factor = 0.0 if right == 0.0 else right * left ** (right - 1.0)
                        gradient = [factor * a for a in dl]
                if not math.isfinite(value) or any(not math.isfinite(item) for item in gradient):
                    raise ValueError("Behavioral function produced a non-finite value or derivative.")
                return value, list(gradient)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _TERNARY_FUNCTIONS and len(node.args) == 3 and not node.keywords:
                name = node.func.id
                first, dfirst = evaluate(node.args[0])
                if name == "spice_if":
                    if first == 0.0 and not isinstance(node.args[0], ast.Compare):
                        raise ValueError("Behavioral if condition is on its discontinuity boundary.")
                    # Evaluate only the selected branch.  This matches SPICE's
                    # guarded-expression behavior and permits e.g. IF(x>0,
                    # log(x), 0) without evaluating log(x) for x < 0.
                    return evaluate(node.args[1] if first > 0.0 else node.args[2])
                second, dsecond = evaluate(node.args[1])
                third, dthird = evaluate(node.args[2])
                if second >= third:
                    raise ValueError("Behavioral limit requires lower < upper.")
                if first == second or first == third:
                    raise ValueError("Behavioral limit is nondifferentiable at a bound.")
                if first < second:
                    return second, dsecond
                if first > third:
                    return third, dthird
                return first, dfirst
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "table" and len(node.args) >= 5 and len(node.args) % 2 == 1 and not node.keywords:
                argument, dargument = evaluate(node.args[0])
                points: list[tuple[float, list[float], float, list[float]]] = []
                previous_x: float | None = None
                for index in range(1, len(node.args), 2):
                    x_value, dx = evaluate(node.args[index])
                    y_value, dy = evaluate(node.args[index + 1])
                    if any(dx):
                        raise ValueError("Behavioral table breakpoints must be constant after parameter expansion.")
                    if previous_x is not None and x_value <= previous_x:
                        raise ValueError("Behavioral table breakpoints must increase strictly.")
                    previous_x = x_value
                    points.append((x_value, dx, y_value, dy))
                if argument <= points[0][0]:
                    if argument == points[0][0]:
                        raise ValueError("Behavioral table is nondifferentiable at a breakpoint.")
                    return points[0][2], list(points[0][3])
                if argument >= points[-1][0]:
                    if argument == points[-1][0]:
                        raise ValueError("Behavioral table is nondifferentiable at a breakpoint.")
                    return points[-1][2], list(points[-1][3])
                for left, right in zip(points, points[1:]):
                    if argument == left[0] or argument == right[0]:
                        raise ValueError("Behavioral table is nondifferentiable at a breakpoint.")
                    if left[0] < argument < right[0]:
                        fraction = (argument - left[0]) / (right[0] - left[0])
                        slope = (right[2] - left[2]) / (right[0] - left[0])
                        value = left[2] + fraction * (right[2] - left[2])
                        gradient = [
                            (1.0 - fraction) * dl + fraction * dr + slope * da
                            for dl, dr, da in zip(left[3], right[3], dargument)
                        ]
                        return value, gradient
                raise ValueError("Behavioral table interval selection failed.")
            raise ValueError("Unsupported behavioral expression node.")

        value, gradient = evaluate(self.tree)
        return BehavioralEvaluation(value=value, gradient=tuple(gradient))


def compile_behavioral_expression(
    expression: str,
    *,
    parameters: Mapping[str, float] | None = None,
) -> CompiledBehavioralExpression:
    """Compile one expression without executing arbitrary Python syntax."""

    source = str(expression).strip()
    if source.startswith("{") and source.endswith("}"):
        source = source[1:-1].strip()
    if not source:
        raise ValueError("Behavioral expression cannot be empty.")
    parameters = {str(name).lower(): float(value) for name, value in (parameters or {}).items()}
    if any(not math.isfinite(value) for value in parameters.values()):
        raise ValueError("Behavioral parameters must be finite.")
    signals: list[BehavioralSignal] = []
    signal_indices: dict[BehavioralSignal, int] = {}

    def replace_signal(matched: re.Match[str]) -> str:
        signal = BehavioralSignal(
            matched.group("kind"), matched.group("first"), matched.group("second") or "0"
        )
        index = signal_indices.get(signal)
        if index is None:
            if len(signals) >= MAX_BEHAVIORAL_SIGNALS:
                raise ValueError(f"Behavioral expression exceeds {MAX_BEHAVIORAL_SIGNALS} distinct signals.")
            index = len(signals)
            signal_indices[signal] = index
            signals.append(signal)
        return f"__s{index}"

    normalized = _SIGNAL_RE.sub(replace_signal, source)
    # SPICE uses ^ for exponentiation and IF(...) as a function.  Convert only
    # these two lexical forms; all resulting syntax is still checked below.
    normalized = normalized.replace("^", "**")
    normalized = re.sub(r"(?i)\bif\s*\(", "spice_if(", normalized)
    normalized = re.sub(r"(?i)\bln\s*(?=\()", "log", normalized)
    normalized = re.sub(r"(?i)\barctan\s*(?=\()", "atan", normalized)
    for function_name in sorted(_FUNCTIONS - {"spice_if"}, key=len, reverse=True):
        normalized = re.sub(
            rf"(?i)\b{re.escape(function_name)}\s*(?=\()", function_name, normalized
        )
    normalized = re.sub(r"(?i)\bpi\b", "pi", normalized)
    normalized = re.sub(r"(?i)\btime\b", "time", normalized)
    normalized = re.sub(r"(?i)\be\b", "e", normalized)
    for name, value in sorted(parameters.items(), key=lambda item: -len(item[0])):
        normalized = re.sub(rf"(?i)(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", repr(value), normalized)
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Invalid behavioral expression syntax.") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_BEHAVIORAL_NODES:
        raise ValueError(f"Behavioral expression exceeds {MAX_BEHAVIORAL_NODES} syntax nodes.")
    allowed_names = {f"__s{index}" for index in range(len(signals))} | {"pi", "e", "time"} | _FUNCTIONS
    allowed_nodes = (
        ast.Expression, ast.Constant, ast.Name, ast.Load, ast.UnaryOp, ast.UAdd, ast.USub,
        ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.Call,
        ast.Compare, ast.Gt, ast.GtE, ast.Lt, ast.LtE,
    )
    called_function_ids = {
        id(node.func) for node in nodes if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    for node in nodes:
        if not isinstance(node, allowed_nodes):
            raise ValueError(f"Unsupported behavioral syntax {type(node).__name__}.")
        if isinstance(node, ast.Constant) and (
            not isinstance(node.value, (int, float)) or isinstance(node.value, bool)
        ):
            raise ValueError("Behavioral constants must be numeric.")
        if isinstance(node, ast.Name) and node.id not in allowed_names:
            raise ValueError(f"Unknown or unsupported behavioral name {node.id}.")
        if isinstance(node, ast.Name) and node.id in _FUNCTIONS and id(node) not in called_function_ids:
            raise ValueError(f"Behavioral function {node.id} must be called with one argument.")
        if isinstance(node, ast.Compare) and (
            len(node.ops) != 1 or len(node.comparators) != 1
            or not isinstance(node.ops[0], (ast.Gt, ast.GtE, ast.Lt, ast.LtE))
        ):
            raise ValueError("Only one relational >, >=, <, or <= comparison is allowed at a time.")
        if isinstance(node, ast.Call):
            valid_arity = (
                node.func.id in _UNARY_FUNCTIONS and len(node.args) == 1
                or node.func.id in _BINARY_FUNCTIONS and len(node.args) == 2
                or node.func.id in _TERNARY_FUNCTIONS and len(node.args) == 3
                or node.func.id == "table" and len(node.args) >= 5 and len(node.args) % 2 == 1 and len(node.args) <= 33
            ) if isinstance(node.func, ast.Name) else False
            if not valid_arity or node.keywords:
                raise ValueError("Unsupported behavioral function or argument count.")
    return CompiledBehavioralExpression(source, normalized, tuple(signals), tree)


__all__ = [
    "BEHAVIORAL_EXPRESSION_CONTRACT", "BehavioralEvaluation", "BehavioralSignal",
    "CompiledBehavioralExpression", "compile_behavioral_expression",
]
