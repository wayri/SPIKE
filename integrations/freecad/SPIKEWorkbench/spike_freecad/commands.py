"""GUI commands exposed by the SPIKE FreeCAD workbench."""

from __future__ import annotations

import os
from typing import Any, Optional

import FreeCAD as App
import FreeCADGui as Gui

try:
    from PySide import QtWidgets
except ImportError:  # FreeCAD 0.21 compatibility.
    from PySide import QtGui as QtWidgets  # type: ignore

from .constants import EXPORT_ROLES, ICON_ROOT
from .contracts import ContractError, load_geometry_exchange, write_mechanical_exchange
from .freecad_geometry import (
    build_mechanical_exchange,
    exportable_objects,
    import_geometry_exchange,
)


COMMAND_IDS = (
    "SPIKE_ImportGeometryExchange",
    "SPIKE_ExportMechanicalExchange",
    "SPIKE_ExportAssembly",
    "SPIKE_ImportCollaborationSession",
    "SPIKE_ExportPlacementFeedback",
    "SPIKE_MeasureClearance",
)

_REGISTERED = False


def _dialog_path(result: Any) -> str:
    if isinstance(result, (tuple, list)):
        result = result[0] if result else ""
    return str(result or "")


def _parent() -> Any:
    return Gui.getMainWindow()


def _error(title: str, message: str) -> None:
    App.Console.PrintError(f"SPIKE: {message}\n")
    QtWidgets.QMessageBox.critical(_parent(), title, message)


def _information(title: str, message: str) -> None:
    App.Console.PrintMessage(f"SPIKE: {message}\n")
    QtWidgets.QMessageBox.information(_parent(), title, message)


class ImportGeometryExchangeCommand:
    """Import a validated SPIKE primitive geometry exchange document."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICON_ROOT, "ImportGeometry.svg"),
            "MenuText": "Import SPIKE Geometry...",
            "ToolTip": "Import a versioned SPIKE ECAD/MCAD geometry JSON file",
            "Accel": "S, I",
        }

    def IsActive(self):
        return True

    def Activated(self):
        source_path = _dialog_path(
            QtWidgets.QFileDialog.getOpenFileName(
                _parent(),
                "Import SPIKE Geometry Exchange",
                "",
                "SPIKE exchange (*.json);;JSON files (*.json)",
            )
        )
        if not source_path:
            return
        try:
            payload = load_geometry_exchange(source_path)
            document = App.ActiveDocument
            if document is None:
                document = App.newDocument("SPIKE_ECAD_MCAD_Exchange")
            imported = import_geometry_exchange(document, payload, source_path)
            active_gui = Gui.activeDocument()
            if active_gui is not None:
                active_gui.activeView().fitAll()
        except (ContractError, OSError, RuntimeError, ValueError) as exc:
            _error("SPIKE Geometry Import Failed", str(exc))
            return
        _information(
            "SPIKE Geometry Imported",
            f"Imported {len(imported)} validated object(s) from {os.path.basename(source_path)}.",
        )


class ExportMechanicalExchangeCommand:
    """Export selected or tagged solids as SPIKE envelope/keepout AABBs."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICON_ROOT, "ExportMechanical.svg"),
            "MenuText": "Export SPIKE Envelopes/Keepouts...",
            "ToolTip": "Export selected or SPIKE-tagged solids as a versioned JSON exchange",
            "Accel": "S, E",
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        document = App.ActiveDocument
        if document is None:
            _error("SPIKE Mechanical Export Failed", "Open a FreeCAD document first.")
            return
        objects = exportable_objects(document, Gui.Selection.getSelection())
        if not objects:
            _error(
                "SPIKE Mechanical Export Failed",
                "Select one or more solid objects, or enable SPIKEExport on tagged objects.",
            )
            return

        needs_role = any(str(getattr(obj, "SPIKERole", "")) not in EXPORT_ROLES for obj in objects)
        fallback_role: Optional[str] = None
        if needs_role:
            fallback_role, accepted = QtWidgets.QInputDialog.getItem(
                _parent(),
                "SPIKE Mechanical Role",
                "Role for selected untagged objects:",
                list(EXPORT_ROLES),
                0,
                False,
            )
            if not accepted:
                return
            fallback_role = str(fallback_role)

        destination = _dialog_path(
            QtWidgets.QFileDialog.getSaveFileName(
                _parent(),
                "Export SPIKE Mechanical Exchange",
                f"{document.Name}-mechanical-exchange.json",
                "SPIKE exchange (*.json);;JSON files (*.json)",
            )
        )
        if not destination:
            return
        try:
            payload = build_mechanical_exchange(document, objects, fallback_role)
            written = write_mechanical_exchange(destination, payload)
        except (ContractError, OSError, RuntimeError, ValueError) as exc:
            _error("SPIKE Mechanical Export Failed", str(exc))
            return
        _information(
            "SPIKE Mechanical Exchange Exported",
            f"Exported {len(objects)} object(s) to {written}.",
        )


class ExportAssemblyCommand:
    def GetResources(self):
        return {"Pixmap": os.path.join(ICON_ROOT, "ExportMechanical.svg"), "MenuText": "Export SPIKE Assembly...",
                "ToolTip": "Export selected assembly roots with placed STEP parts and optional electrical board sources"}

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        from .assembly_export import export_assembly
        document = App.ActiveDocument
        if document is None: return
        destination = _dialog_path(QtWidgets.QFileDialog.getSaveFileName(_parent(), "Export SPIKE Assembly", document.Name + ".spikeassembly", "SPIKE assembly (*.spikeassembly)"))
        if not destination: return
        try:
            result = export_assembly(document, Gui.Selection.getSelection(), destination)
            _information("SPIKE Assembly Exported", f"Exported {result['occurrences']} occurrences to {result['path']}")
        except (OSError, RuntimeError, ValueError) as exc:
            _error("SPIKE Assembly Export Failed", str(exc))


def register_commands() -> None:
    """Register commands once per FreeCAD process."""

    global _REGISTERED
    if _REGISTERED:
        return
    Gui.addCommand(COMMAND_IDS[0], ImportGeometryExchangeCommand())
    Gui.addCommand(COMMAND_IDS[1], ExportMechanicalExchangeCommand())
    Gui.addCommand(COMMAND_IDS[2], ExportAssemblyCommand())
    from .collaboration_commands import ImportSessionCommand, ExportFeedbackCommand, MeasureClearanceCommand
    Gui.addCommand(COMMAND_IDS[3], ImportSessionCommand())
    Gui.addCommand(COMMAND_IDS[4], ExportFeedbackCommand())
    Gui.addCommand(COMMAND_IDS[5], MeasureClearanceCommand())
    _REGISTERED = True


__all__ = ["COMMAND_IDS", "register_commands"]
