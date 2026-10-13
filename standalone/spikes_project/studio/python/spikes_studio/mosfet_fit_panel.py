# SPDX-License-Identifier: Apache-2.0
"""Explicitly reviewed offline CSV-to-Level-1 draft; no Qt or cloud dependency."""
from pathlib import Path
import json
import os
import subprocess
import sys

import wx
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg

from python.spikes.mosfet_curve_fit import model_card


def run_fit(path, options):
    """Run the bounded numerical service outside the GUI process (45 s limit)."""
    if getattr(sys, "frozen", False):
        raise ValueError("CSV fitting currently requires the source Python Studio runtime, not a frozen executable")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(str(Path(p).resolve()) for p in sys.path if p)
    completed = subprocess.run(
        [sys.executable, "-m", "python.spikes.mosfet_curve_fit", str(path), json.dumps(options)],
        capture_output=True, text=True, encoding="utf-8", timeout=45, env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if len(completed.stdout) > 4*1024*1024:
        raise ValueError("Fit report exceeds the 4 MiB transfer limit")
    try:
        report = json.loads(completed.stdout)
    except ValueError as exc:
        raise ValueError("Fit worker failed: " + completed.stderr[-1500:]) from exc
    if completed.returncode or "error" in report:
        raise ValueError(report.get("error", "Fit worker failed"))
    return report


class MosfetFitDialog(wx.Dialog):
    def __init__(self, owner):
        super().__init__(owner, title="Offline MOSFET DC curve fit - unqualified draft",
                         size=(900, 800), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.owner = owner; self.path = None; self.report = None; self.busy = False
        self.SetMinSize((720, 760))
        box = wx.BoxSizer(wx.VERTICAL)
        intro = wx.StaticText(self, label="Human-transcribed/measured CSV only: vgs_v,vds_v,id_a (V,V,A).\n"
                              "No image/PDF extraction. Forward NMOS, source-tied bulk, W/L=1; DC only, not BSIM/WBG.")
        box.Add(intro, 0, wx.ALL | wx.EXPAND, 10)
        self.path_label = wx.TextCtrl(self, value="Select an SI CSV (15-5,000 unique bias points; <=1 MiB)", style=wx.TE_READONLY)
        box.Add(self.path_label, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 10)
        form = wx.FlexGridSizer(cols=2, hgap=8, vgap=6); form.AddGrowableCol(1)
        self.kind = wx.Choice(self, choices=["measured", "datasheet_table"]); self.kind.SetSelection(0)
        self.temperature = wx.TextCtrl(self, value="298.15")
        self.note = wx.TextCtrl(self, value="")
        self.name = wx.TextCtrl(self, value="FITTED_NMOS")
        for label, control in (("Source type", self.kind), ("Single measurement temperature (K)", self.temperature),
                               ("Provenance (device, document/page/test setup)", self.note), ("Model name", self.name)):
            form.Add(wx.StaticText(self, label=label), 0, wx.ALIGN_CENTER_VERTICAL); form.Add(control, 1, wx.EXPAND)
        box.Add(form, 0, wx.ALL | wx.EXPAND, 10)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.load_button = wx.Button(self, label="Import CSV...")
        self.fit_button = wx.Button(self, label="Fit parameters"); self.fit_button.Disable()
        self.export_button = wx.Button(self, label="Export draft..."); self.export_button.Disable()
        self.place_button = wx.Button(self, label="Place draft..."); self.place_button.Disable()
        for control, handler in ((self.load_button, self.load), (self.fit_button, self.fit),
                                 (self.export_button, self.export), (self.place_button, self.place)):
            row.Add(control, 0, wx.RIGHT, 6)
            control.Bind(wx.EVT_BUTTON, lambda event, action=handler: owner.guarded(action))
        box.Add(row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.summary = wx.TextCtrl(self, value="Import CSV, declare its temperature/provenance, then fit.\n"
                                   "No charge or switching behavior is fitted. Export/placement requires review.",
                                   style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.summary.SetMinSize((-1, 100)); box.Add(self.summary, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        selector = wx.BoxSizer(wx.HORIZONTAL)
        selector.Add(wx.StaticText(self, label="Output curve Vgs (V):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.gate = wx.Choice(self); selector.Add(self.gate, 1, wx.EXPAND)
        box.Add(selector, 0, wx.ALL | wx.EXPAND, 10)
        self.figure = Figure(figsize=(7, 2.6), tight_layout=True)
        self.canvas = FigureCanvasWxAgg(self, wx.ID_ANY, self.figure); self.canvas.SetMinSize((-1, 180))
        box.Add(self.canvas, 2, wx.LEFT | wx.RIGHT | wx.EXPAND, 10)
        self.review = wx.CheckBox(self, label="Reviewed residuals, source and limits: export/place an unqualified DC draft.")
        self.review.Disable(); box.Add(self.review, 0, wx.ALL | wx.EXPAND, 10)
        box.Add(self.CreateButtonSizer(wx.CLOSE), 0, wx.ALL | wx.ALIGN_RIGHT, 8)
        self.SetSizer(box)
        self.gate.Bind(wx.EVT_CHOICE, lambda event: self.plot())
        self.review.Bind(wx.EVT_CHECKBOX, lambda event: self.actions())
        self.temperature.Bind(wx.EVT_TEXT, self.invalidate)
        self.note.Bind(wx.EVT_TEXT, self.invalidate)
        self.kind.Bind(wx.EVT_CHOICE, self.invalidate)
        self.Bind(wx.EVT_CLOSE, self.closing)
        self.Bind(wx.EVT_BUTTON, lambda event: self.Close(), id=wx.ID_CLOSE)

    def closing(self, event):
        if self.busy:
            wx.MessageBox("Fit worker is bounded to 45 seconds. Wait for completion before closing.", "Fit running", parent=self)
            event.Veto(); return
        event.Skip()

    def actions(self):
        enabled = self.report is not None and self.review.GetValue() and not self.busy
        self.export_button.Enable(enabled); self.place_button.Enable(enabled)

    def invalidate(self, event=None):
        self.report = None; self.review.SetValue(False); self.review.Disable(); self.actions()
        self.gate.Clear(); self.figure.clear(); self.canvas.draw()
        self.summary.SetValue("Input changed. Fit again before reviewing or exporting.")
        if event: event.Skip()

    def load(self):
        path = self.owner.choose_path("Import MOSFET SI table", "CSV table (*.csv)|*.csv")
        if path:
            self.path = Path(path); self.path_label.SetValue(str(path)); self.invalidate(); self.fit_button.Enable()

    def fit(self):
        if self.path is None: raise ValueError("Choose a CSV file first")
        if self.owner.job_running: raise ValueError("Finish the current job first")
        if not self.note.GetValue().strip(): raise ValueError("Record the device and source document/page or measurement setup")
        options = dict(temperature_k=float(self.temperature.GetValue()), source_kind=self.kind.GetStringSelection(),
                       source_note=self.note.GetValue().strip())
        path = self.path; self.invalidate(); self.busy = True
        for control in (self.load_button, self.fit_button, self.kind, self.temperature, self.note): control.Disable()
        self.summary.SetValue("Fitting in an offline child process; timeout 45 seconds...")

        def work():
            try: return dict(report=run_fit(path, options))
            except Exception as exc: return dict(error=str(exc))

        def done(result):
            self.busy = False
            for control in (self.load_button, self.fit_button, self.kind, self.temperature, self.note): control.Enable()
            if "error" in result:
                self.summary.SetValue("Fit rejected: " + result["error"]); return
            self.report = result["report"]
            summary = {key: value for key, value in self.report.items() if key != "points"}
            self.summary.SetValue(json.dumps(summary, indent=2))
            self.review.Enable()
            self.gate.Set([format(v, ".17g") for v in sorted({point["vgs_v"] for point in self.report["points"]})])
            self.gate.SetSelection(self.gate.GetCount()-1); self.plot()
        self.owner.background(work, done, "Fitting offline MOSFET DC draft...")

    def plot(self):
        self.figure.clear()
        if self.report is not None and self.gate.GetSelection() >= 0:
            gate = float(self.gate.GetStringSelection())
            points = [p for p in self.report["points"] if p["vgs_v"] == gate]
            axis = self.figure.add_subplot(111)
            for heldout, marker, label in ((False, "o", "Measured/table (fit)"), (True, "x", "Measured/table (held out)")):
                rows = [p for p in points if p["heldout"] == heldout]
                axis.scatter([p["vds_v"] for p in rows], [p["id_a"] for p in rows], marker=marker, label=label)
            axis.plot([p["vds_v"] for p in points], [p["fitted_id_a"] for p in points], label="Level-1 draft")
            axis.set(xlabel="Vds (V)", ylabel="Id (A)", title=f"Vgs={gate:g} V; fitted line joins sampled biases only")
            axis.legend(fontsize=8); axis.grid(True, alpha=.3)
        self.canvas.draw()

    def reviewed_card(self):
        if self.report is None: raise ValueError("Fit and review a CSV first")
        return model_card(self.report, self.name.GetValue().strip(), reviewed=self.review.GetValue())

    def export(self):
        card = self.reviewed_card()
        path = self.owner.choose_path("Export unqualified MOSFET model", "Model card (*.model)|*.model", True)
        if path:
            # One self-contained inert text file avoids a partial sidecar export.
            evidence = "* FIT_REPORT " + json.dumps(self.report, separators=(",", ":"), ensure_ascii=True)
            Path(path).write_text(card + evidence + "\n", encoding="utf-8")
            self.owner.SetStatusText("Exported unqualified DC draft with full source/fit/holdout evidence in comments.")

    def place(self):
        from .model_placement import prepare, insert
        card = self.reviewed_card(); self.owner.apply_source()
        plan = prepare(self.owner.doc, card)
        message = (plan["model"] + "\n\nCreate an unconnected D/G/S/B NMOS? Tie B to S and retain W/L=1.\n"
                   "This is an unqualified DC draft, with no fitted switching charge.\nExisting sheet contents are preserved.")
        if wx.MessageBox(message, "Review model placement", wx.YES_NO | wx.NO_DEFAULT, self) != wx.YES: return
        plan["part"]["evidence"] = json.dumps(self.report, allow_nan=False)
        plan["part"]["temperature_k"] = self.report["validity"]["temperature_k"]
        size = self.owner.canvas.GetClientSize()
        part_id = insert(self.owner.doc, plan, self.owner.canvas.world(wx.Point(size.width//2, size.height//2)))
        self.owner.canvas.selected = {part_id}; self.owner.refresh_document(force_source=True)
        self.owner.book.SetSelection(0); self.EndModal(wx.ID_OK)


def show(owner):
    """Command-registry integration entry point."""
    with MosfetFitDialog(owner) as dialog:
        dialog.ShowModal()
