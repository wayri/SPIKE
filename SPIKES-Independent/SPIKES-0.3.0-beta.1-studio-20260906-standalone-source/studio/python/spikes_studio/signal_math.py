"""Vector expressions on recorded signals, with dimensional checks and no eval."""
from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass
import numpy as np


class ExpressionError(ValueError):
    pass


@dataclass(frozen=True)
class Unit:
    powers: tuple[float, ...] = (0, 0, 0, 0)  # V, A, s, K

    def mul(self, other):
        return Unit(tuple(a + b for a, b in zip(self.powers, other.powers)))

    def pow(self, exponent):
        return Unit(tuple(a * exponent for a in self.powers))

    def __str__(self):
        conventional={(1,1,0,0):'W',(1,-1,0,0):'Ω',(1,1,1,0):'J',(0,0,-1,0):'Hz',(0,1,1,0):'C'}
        if self.powers in conventional:return conventional[self.powers]
        return " ".join(n if p == 1 else f"{n}^{p:g}" for n, p in zip(("V", "A", "s", "K"), self.powers) if p) or "1"


ONE, VOLT, AMP, SECOND, KELVIN = (Unit(), Unit((1, 0, 0, 0)), Unit((0, 1, 0, 0)), Unit((0, 0, 1, 0)), Unit((0, 0, 0, 1)))


@dataclass(frozen=True)
class Quantity:
    values: object
    unit: Unit = ONE


FUNCTION_HELP = """v(out), v(out,ref), i(R1), p(R1), signal(\"name\"), t
Constants: pi, e, j; units: V, A, s, K, Hz, ohm, W
Arithmetic: + - * / **; comparisons; where(condition,a,b), minimum, maximum
sin cos tan asin acos atan atan2 sinh cosh tanh asinh acosh atanh
exp expm1 log log10 log2 log1p sqrt abs real imag conj angle unwrap
degrees radians floor ceil erf erfc hypot clip
mean rms min max pp integral derivative
Transcendental functions require dimensionless arguments (use v(out)/V).
mean/rms use time weighting. Integral and derivative use recorded timestamps.
All time signals must share the same sampling grid. No implicit resampling."""


class SignalMath:
    def __init__(self, time, signals: dict[str, Quantity]):
        self.time = np.asarray(time, dtype=float).copy()
        if self.time.ndim != 1 or len(self.time) < 2 or len(self.time) > 2_000_000 or not np.isfinite(self.time).all() or not (np.diff(self.time) > 0).all():
            raise ExpressionError("Need 2..2,000,000 finite, strictly increasing timestamps")
        self.signals = {}
        for name, value in signals.items():
            a = np.asarray(value.values).copy()
            if a.shape != self.time.shape or not np.isfinite(a).all():
                raise ExpressionError(f"{name}: samples must be finite and match the time grid")
            self.signals[name.lower()] = Quantity(a, value.unit)

    @classmethod
    def from_result(cls, result):
        data = result["data"]
        signals = {}
        for key, prefix, unit in (("node_voltage_v", "v", VOLT), ("element_current_a", "i", AMP), ("element_power_w", "p", VOLT.mul(AMP))):
            for name, values in data.get(key, {}).items():
                signals[f"{prefix}({name})"] = Quantity(values, unit)
        return cls(data["time_s"], signals)

    def evaluate(self, expression, *, variables=None):
        if not isinstance(expression, str) or len(expression) > 8192:
            raise ExpressionError("Expression exceeds 8192 characters")
        try:
            # SPICE node names such as `in`, `return`, `0` and `/sheet/out`
            # are identifiers in probe calls even when Python reserves them.
            expression = re.sub(r'\b(v|i|p)\(\s*([A-Za-z0-9_.$:/+-]+(?:\s*,\s*[A-Za-z0-9_.$:/+-]+)?)\s*\)',
                lambda m: m[1].lower() + '(' + ','.join(repr(s.strip()) for s in m[2].split(',')) + ')', expression,flags=re.IGNORECASE)
            tree = ast.parse(expression, mode="eval")
            if sum(1 for _ in ast.walk(tree)) > 256:
                raise ExpressionError("Expression exceeds 256 syntax nodes")
            with np.errstate(all="raise"):
                answer = self._visit(tree.body, variables or {})
            if not isinstance(answer, Quantity) or not np.isfinite(answer.values).all():
                raise ExpressionError("Expression produced nonfinite values")
            return answer
        except (SyntaxError, TypeError, FloatingPointError, OverflowError, ZeroDivisionError, RecursionError) as exc:
            raise ExpressionError(str(exc)) from exc

    def _visit(self, node, variables):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float, complex):
            return Quantity(node.value)
        if isinstance(node, ast.Name):
            constants = {"pi": Quantity(math.pi), "e": Quantity(math.e), "j": Quantity(1j), "t": Quantity(self.time, SECOND)}
            constants.update({n: Quantity(1.0, u) for n, u in {"V": VOLT, "A": AMP, "s": SECOND, "K": KELVIN, "Hz": SECOND.pow(-1), "ohm": VOLT.mul(AMP.pow(-1)), "W": VOLT.mul(AMP)}.items()})
            if node.id in variables:
                return variables[node.id]
            if node.id in constants:
                return constants[node.id]
            raise ExpressionError(f"Unknown variable: {node.id}")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            a = self._visit(node.operand, variables)
            return Quantity(-a.values if isinstance(node.op, ast.USub) else a.values, a.unit)
        if isinstance(node, ast.BinOp):
            a, b = self._visit(node.left, variables), self._visit(node.right, variables)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                self._same(a, b)
                return Quantity(a.values + b.values if isinstance(node.op, ast.Add) else a.values - b.values, a.unit)
            if isinstance(node.op, ast.Mult):
                return Quantity(a.values * b.values, a.unit.mul(b.unit))
            if isinstance(node.op, ast.Div):
                return Quantity(a.values / b.values, a.unit.mul(b.unit.pow(-1)))
            if isinstance(node.op, ast.Pow):
                self._dimensionless(b)
                if np.ndim(b.values) or abs(b.values) > 100:
                    raise ExpressionError("Power requires a scalar exponent within ±100")
                return Quantity(np.power(np.asarray(a.values, dtype=complex if np.iscomplexobj(a.values) else float), b.values), a.unit.pow(b.values))
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            a, b = self._visit(node.left, variables), self._visit(node.comparators[0], variables)
            self._same(a, b)
            fn = {ast.Lt: np.less, ast.Gt: np.greater, ast.LtE: np.less_equal, ast.GtE: np.greater_equal, ast.Eq: np.equal, ast.NotEq: np.not_equal}.get(type(node.ops[0]))
            if fn:
                return Quantity(fn(a.values, b.values))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name = node.func.id.lower()
            if name in ("v", "i", "p", "signal"):
                refs = []
                for arg in node.args:
                    if isinstance(arg, ast.Name): refs.append(arg.id)
                    elif isinstance(arg, ast.Constant) and isinstance(arg.value, (str, int)): refs.append(str(arg.value))
                    else: raise ExpressionError("Probe targets must be names or quoted strings")
                if name == "v" and len(refs) == 2:
                    a, b = self._signal("v", refs[0]), self._signal("v", refs[1])
                    return Quantity(a.values - b.values, VOLT)
                if len(refs) != 1: raise ExpressionError("Wrong number of probe targets")
                return self._signal(name, refs[0])
            return self._call(name, [self._visit(a, variables) for a in node.args])
        raise ExpressionError(f"Unsupported expression syntax: {type(node).__name__}")

    def _signal(self, kind, target):
        if kind == "v" and target == "0": return Quantity(np.zeros_like(self.time), VOLT)
        key = target.lower() if kind == "signal" else f"{kind}({target.lower()})"
        if key not in self.signals: raise ExpressionError(f"Signal not recorded: {key}")
        return self.signals[key]

    @staticmethod
    def _same(a, b):
        if a.unit != b.unit: raise ExpressionError(f"Incompatible units: {a.unit} and {b.unit}")

    @staticmethod
    def _dimensionless(a):
        if a.unit != ONE: raise ExpressionError(f"Expected a dimensionless argument, got {a.unit}")

    def _call(self, name, args):
        if name in ("where", "clip") and len(args) == 3:
            a, b, c = args
            self._same(b, c)
            if name == "where": self._dimensionless(a)
            else: self._same(a, b)
            return Quantity((np.where if name == "where" else np.clip)(a.values, b.values, c.values), b.unit)
        if name in ("atan2", "hypot", "minimum", "maximum") and len(args) == 2:
            a, b = args
            self._same(a, b)
            return Quantity(getattr(np, "arctan2" if name == "atan2" else name)(a.values, b.values), ONE if name == "atan2" else a.unit)
        if len(args) != 1: raise ExpressionError(f"{name}: wrong argument count")
        a = args[0]
        aliases = {"asin": "arcsin", "acos": "arccos", "atan": "arctan", "asinh": "arcsinh", "acosh": "arccosh", "atanh": "arctanh"}
        if name in ("sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh", "asinh", "acosh", "atanh", "exp", "expm1", "log", "log10", "log2", "log1p", "degrees", "radians", "floor", "ceil", "erf", "erfc"):
            self._dimensionless(a)
            fn = np.vectorize(getattr(math, name)) if name in ("erf", "erfc") else getattr(np, aliases.get(name, name))
            return Quantity(fn(a.values))
        if name in ("abs", "real", "imag", "conj", "sqrt", "angle", "unwrap"):
            if name == "unwrap": self._dimensionless(a)
            unit = ONE if name == "angle" else a.unit.pow(.5) if name == "sqrt" else a.unit
            return Quantity(getattr(np, name)(a.values), unit)
        values = np.broadcast_to(a.values, self.time.shape)
        if name in ("mean", "rms", "min", "max", "pp"):
            if name == "mean": value = np.sum((values[1:] + values[:-1]) * np.diff(self.time) / 2) / np.ptp(self.time)
            elif name == "rms": value = np.sqrt(np.sum((abs(values[1:])**2 + abs(values[:-1])**2) * np.diff(self.time) / 2) / np.ptp(self.time))
            else: value = {"min": np.min, "max": np.max, "pp": np.ptp}[name](values)
            return Quantity(value, a.unit)
        if name == "integral":
            return Quantity(np.r_[0, np.cumsum((values[1:] + values[:-1]) * np.diff(self.time) / 2)], a.unit.mul(SECOND))
        if name == "derivative": return Quantity(np.gradient(values, self.time), a.unit.mul(SECOND.pow(-1)))
        raise ExpressionError(f"Unknown function: {name}")

    def crossings(self, expression, level=0.0, edge="either"):
        if edge not in ("rising", "falling", "either"): raise ExpressionError("Unknown edge")
        y = np.asarray(self.evaluate(expression).values) - level
        if y.shape != self.time.shape or np.iscomplexobj(y): raise ExpressionError("Crossings require a real trace")
        rising, falling = (y[:-1] < 0) & (y[1:] >= 0), (y[:-1] > 0) & (y[1:] <= 0)
        indices = np.where(rising if edge == "rising" else falling if edge == "falling" else rising | falling)[0]
        return [float(self.time[k] - y[k] * (self.time[k+1] - self.time[k]) / (y[k+1] - y[k])) for k in indices]

    def solve(self, equation, left, right, tolerance=1e-10):
        """Bracketed scalar root of expression = 0, using dimensionless x."""
        if not all(math.isfinite(v) for v in (left, right, tolerance)) or left >= right or tolerance <= 0:
            raise ExpressionError("Invalid root bracket or tolerance")
        def f(x):
            q = self.evaluate(equation, variables={"x": Quantity(x)})
            if np.ndim(q.values) or np.iscomplexobj(q.values): raise ExpressionError("Root equation must return a real scalar")
            return float(q.values)
        a, b = f(left), f(right)
        if a == 0: return left
        if b == 0: return right
        if np.sign(a) == np.sign(b): raise ExpressionError("Root is not bracketed")
        for _ in range(200):
            mid = left + (right-left)/2
            value = f(mid)
            if value == 0 or right-left <= tolerance: return mid
            if np.sign(value) == np.sign(a): left, a = mid, value
            else: right = mid
        raise ExpressionError("Root did not converge")
