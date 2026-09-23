"""Menus for explicit assembly feedback and solid clearance measurements."""
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui

from .commands import QtWidgets, _dialog_path, _parent, _error, _information
from .collaboration import import_session, session_root, build_feedback, measure_clearance, write_feedback
from .session_contract import loads, MAX_BYTES


class ImportSessionCommand:
    def GetResources(self):
        return {"MenuText": "Open SPIKE Collaboration Session...", "ToolTip": "Import board/part occurrences from SPIKE for interactive placement"}

    def IsActive(self): return True

    def Activated(self):
        path = _dialog_path(QtWidgets.QFileDialog.getOpenFileName(_parent(), "Open SPIKE Session", "", "SPIKE session (*.json)"))
        if not path: return
        try:
            if Path(path).stat().st_size > MAX_BYTES: raise ValueError("Session exceeds 32 MiB.")
            payload = loads(Path(path).read_text(encoding="utf-8"))
            doc = App.ActiveDocument or App.newDocument("SPIKE_Collaboration")
            import_session(doc, payload)
            if Gui.activeDocument(): Gui.activeDocument().activeView().fitAll()
            _information("SPIKE Session Opened", f"Imported {len(payload['objects'])} occurrences. Move occurrence containers to edit placements.\n\n" + "\n".join(payload["diagnostics"]))
        except (OSError, RuntimeError, ValueError) as exc: _error("SPIKE Session Import Failed", str(exc))


class ExportFeedbackCommand:
    def GetResources(self):
        return {"MenuText": "Send Placement Feedback to SPIKE...", "ToolTip": "Save occurrence placements and current clearance measurements for review in SPIKE"}

    def IsActive(self): return App.ActiveDocument is not None

    def Activated(self):
        try:
            doc = App.ActiveDocument
            root = session_root(doc, Gui.Selection.getSelection())
            feedback = build_feedback(doc, root)
            path = _dialog_path(QtWidgets.QFileDialog.getSaveFileName(_parent(), "Save SPIKE Feedback", "assembly-feedback.json", "SPIKE feedback (*.json)"))
            if not path: return
            write_feedback(path, feedback)
            _information("SPIKE Feedback Saved", "In SPIKE, open FreeCAD collaboration and choose Review FreeCAD feedback, then apply the reviewed changes.")
        except (OSError, RuntimeError, ValueError) as exc: _error("SPIKE Feedback Failed", str(exc))


class MeasureClearanceCommand:
    def GetResources(self):
        return {"MenuText": "Measure SPIKE Solid Clearance", "ToolTip": "Measure separation and overlap volume between two selected session solids"}

    def IsActive(self): return App.ActiveDocument is not None

    def Activated(self):
        try:
            doc = App.ActiveDocument
            selected = Gui.Selection.getSelection()
            row = measure_clearance(doc, session_root(doc, selected), selected)
            _information("SPIKE Clearance", f"Separation: {row['distance_mm']:.6g} mm\nOverlap volume: {row['overlap_volume_mm3']:.6g} mm³\n\nApplies only to the exported solids. Saved with placement feedback; moving an occurrence invalidates these measurements.")
        except (OSError, RuntimeError, ValueError) as exc: _error("SPIKE Clearance Failed", str(exc))
