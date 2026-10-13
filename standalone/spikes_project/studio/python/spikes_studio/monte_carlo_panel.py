# SPDX-License-Identifier: Apache-2.0
"""Bounded UI for the existing deterministic linear Monte Carlo reference API."""
from __future__ import annotations

import json
import math

import wx
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg
from matplotlib.figure import Figure

from .flat_controls import ActionButton
from .themes import figure_theme


SUPPORTED_ELEMENT_KINDS = frozenset(
    {"resistor", "capacitor", "inductor", "voltage_source", "current_source"}
)


def parse_variations(text: str):
    """Parse one ``element=tolerance`` item per line using percent or fraction."""
    from python.spikes.sweeps import RelativeVariation

    variations = []
    for line_number, raw_line in enumerate(str(text).splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        if "=" not in line:
            raise ValueError(f"Variation line {line_number} must be ELEMENT=TOLERANCE.")
        element, raw_tolerance = (part.strip() for part in line.split("=", 1))
        percent = raw_tolerance.endswith("%")
        number = raw_tolerance[:-1].strip() if percent else raw_tolerance
        try:
            tolerance = float(number) / (100.0 if percent else 1.0)
        except ValueError as exc:
            raise ValueError(f"Variation line {line_number} has an invalid tolerance.") from exc
        variations.append(RelativeVariation(element, tolerance))
    if not variations:
        raise ValueError("Enter at least one component variation.")
    return tuple(variations)


def prepare_request(source: str, variations_text: str, probe_text: str, samples, seed, distribution: str):
    """Validate all user input and return immutable backend arguments."""
    from python.spikes.contracts import ProbeDescriptor
    from python.spikes.netlist import parse_netlist

    probe = ProbeDescriptor.parse(str(probe_text).strip())
    project = parse_netlist(str(source), source_name="SPIKES Studio Monte Carlo", probes=(probe,))
    unsupported = [element.name for element in project.elements if element.kind not in SUPPORTED_ELEMENT_KINDS]
    if unsupported:
        raise ValueError(
            "Monte Carlo supports only linear R/L/C/V/I elements; unsupported: "
            + ", ".join(unsupported) + "."
        )
    if isinstance(samples, bool) or int(samples) != samples:
        raise ValueError("Sample count must be an integer.")
    if isinstance(seed, bool) or int(seed) != seed:
        raise ValueError("Seed must be an integer.")
    return project, parse_variations(variations_text), int(samples), int(seed), str(distribution), probe.name


def run_request(request):
    """Execute through the real Python reference orchestrator (never a faux native route)."""
    from python.spikes.sweeps import run_monte_carlo

    project, variations, samples, seed, distribution, _probe_name = request
    return run_monte_carlo(
        project, variations, samples=samples, seed=seed, distribution=distribution
    )


def probe_case_value(case: dict, probe_name: str) -> float:
    """Return a truthful scalar for the run-list plot (last recorded point for series)."""
    payload = case["result"]["probes"][probe_name]
    if "value" in payload:
        value = payload["value"]
    else:
        values = payload.get("values")
        if not values:
            raise ValueError(f"Probe {probe_name} returned no samples.")
        value = values[-1]
    if isinstance(value, complex):
        value = abs(value)
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"Probe {probe_name} returned a nonfinite value.")
    return value


class MonteCarloPanel(wx.Panel):
    """Automatic seeded Monte Carlo workflow for the current applied circuit text."""

    def __init__(self, parent, owner):
        super().__init__(parent)
        self.owner = owner
        self.result = None
        self.probe_name = ""
        self.source_sha256 = ""
        outer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(outer)

        title = wx.StaticText(self, label="Linear Monte Carlo reference")
        title.SetFont(wx.Font(13, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        outer.Add(title, 0, wx.ALL, 10)
        scope = wx.StaticText(
            self,
            label=(
                "Python linear-reference backend only - R/L/C/V/I decks, 1-256 runs, and the backend's "
                "250,000 solve-point budget. This is independent value sampling, not nonlinear or "
                "electrothermal Monte Carlo. Native execution is intentionally not inferred."
            ),
        )
        scope.Wrap(1000)
        outer.Add(scope, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        controls = wx.WrapSizer(wx.HORIZONTAL)
        self.samples = self._field(controls, "Runs", "100", 72)
        self.seed = self._field(controls, "Seed", "1", 120)
        controls.Add(wx.StaticText(self, label="Distribution"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        self.distribution = wx.Choice(self, choices=["uniform", "normal_3sigma_clipped"])
        self.distribution.SetSelection(0)
        controls.Add(self.distribution, 0, wx.ALL, 4)
        self.probe = self._field(controls, "Displayed probe", "V(out)", 150)
        run = ActionButton(self, label="Run Monte Carlo")
        run.Bind(wx.EVT_BUTTON, lambda event: owner.guarded(self.run))
        controls.Add(run, 0, wx.ALL, 3)
        outer.Add(controls, 0, wx.EXPAND)

        outer.Add(
            wx.StaticText(self, label="Component value targets (one ELEMENT=TOLERANCE per line; 10% or 0.1)"),
            0, wx.LEFT | wx.RIGHT | wx.TOP, 8,
        )
        self.variations = wx.TextCtrl(self, value="R1=5%", style=wx.TE_MULTILINE, size=(-1, 82))
        self.variations.SetName("Monte Carlo component value variations")
        outer.Add(self.variations, 0, wx.EXPAND | wx.ALL, 8)

        self.figure = Figure(figsize=(8, 4), layout="constrained")
        self.canvas = FigureCanvasWxAgg(self, -1, self.figure)
        self.canvas.SetMinSize((100, 170))
        outer.Add(self.canvas, 1, wx.EXPAND)
        self.status = wx.StaticText(self, label="No Monte Carlo study has run.")
        outer.Add(self.status, 0, wx.EXPAND | wx.ALL, 8)
        self.run_list = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 150))
        self.run_list.SetName("Read-only Monte Carlo run data and provenance")
        outer.Add(self.run_list, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.draw()

    def _field(self, sizer, label, value, width):
        sizer.Add(wx.StaticText(self, label=label), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        field = wx.TextCtrl(self, value=value, size=(width, -1))
        field.SetName(label)
        sizer.Add(field, 0, wx.ALL, 4)
        return field

    def request(self):
        if self.owner.source.GetText() != self.owner.doc.data["source"]:
            raise ValueError("Circuit text has unapplied edits. Validate and apply it before Monte Carlo.")
        return prepare_request(
            self.owner.doc.data["source"], self.variations.GetValue(), self.probe.GetValue(),
            int(self.samples.GetValue()), int(self.seed.GetValue()), self.distribution.GetStringSelection(),
        )

    def run(self):
        if self.owner.job_running:
            raise ValueError("A simulation or study is already running.")
        request = self.request()  # Validate synchronously before starting or committing anything.
        self.probe_name = request[-1]
        self.source_sha256 = request[0].source_sha256
        self.owner.background(
            lambda: run_request(request), self.accept,
            "Running bounded seeded linear Monte Carlo reference cases...",
        )

    def accept(self, result):
        if result.get("contract") != "spikes/monte-carlo-result/v1":
            raise ValueError("Unexpected Monte Carlo result contract.")
        self.result = result
        self.draw()
        analysis = result["analysis"]
        self.status.SetLabel(
            f"{len(result['cases'])} actual independent runs - seed {analysis['seed']} - "
            f"{analysis['distribution']} - {result['model_status']}"
        )
        rows = []
        for case in result["cases"]:
            rows.append({
                "run": case["index"], "relative_deviations": case["relative_deviations"],
                "probe": self.probe_name, "display_value": probe_case_value(case, self.probe_name),
                "result_status": case["result"]["status"],
            })
        self.run_list.SetValue(json.dumps({
            "analysis": analysis, "provenance": result["provenance"], "runs": rows,
        }, indent=2))

    def draw(self):
        self.figure.clear()
        axis = self.figure.add_subplot()
        if not self.result:
            axis.set_axis_off()
            axis.text(.5, .5, "Configure explicit value tolerances and run", ha="center", va="center", transform=axis.transAxes)
        else:
            cases = self.result["cases"]
            values = [probe_case_value(case, self.probe_name) for case in cases]
            axis.plot([case["index"] for case in cases], values, marker=".", linestyle="none", label=self.probe_name)
            axis.set_xlabel("Run index")
            axis.set_ylabel(self.probe_name + (" magnitude / final recorded point" if any("values" in case["result"]["probes"][self.probe_name] for case in cases) else ""))
            axis.set_title("Actual backend results by deterministic run")
            axis.grid(True, alpha=.25)
            axis.legend()
        figure_theme(self.figure, self.owner.palette, self.owner.theme_name)
        self.canvas.draw_idle()


def page_constructor(parent, owner):
    """Desktop page factory with the shared ``(parent, owner)`` convention."""
    return MonteCarloPanel(parent, owner)


__all__ = [
    "MonteCarloPanel", "page_constructor", "parse_variations", "prepare_request",
    "probe_case_value", "run_request",
]
