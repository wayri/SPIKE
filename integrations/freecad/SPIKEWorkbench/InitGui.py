"""FreeCAD GUI entry point for the SPIKE ECAD/MCAD exchange workbench."""

import os

import FreeCADGui as Gui


_ROOT = os.path.dirname(os.path.abspath(__file__))


class SPIKEWorkbench(Workbench):  # type: ignore[name-defined]  # FreeCAD injects Workbench.
    """Small, explicit ECAD/MCAD exchange workbench."""

    MenuText = "SPIKE ECAD/MCAD"
    ToolTip = "Exchange validated geometry, envelopes, and keepouts with SPIKE"
    Icon = os.path.join(_ROOT, "Resources", "icons", "SPIKEWorkbench.svg")

    def Initialize(self):
        from spike_freecad.commands import COMMAND_IDS, register_commands

        register_commands()
        self._commands = list(COMMAND_IDS)
        self.appendToolbar("SPIKE Exchange", self._commands)
        self.appendMenu("SPIKE", self._commands)

    def Activated(self):
        return None

    def Deactivated(self):
        return None

    def ContextMenu(self, recipient):
        del recipient
        self.appendContextMenu("SPIKE Exchange", self._commands)

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(SPIKEWorkbench())

