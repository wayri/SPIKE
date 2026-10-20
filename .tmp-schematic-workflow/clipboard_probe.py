from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wx
from standalone.spikes_project.tests.python.test_quick_insert import QuickInsertTests
from standalone.spikes_project.tests.python.test_schematic_clipboard_ui import SchematicClipboardUiTests

app = wx.GetApp() or wx.App(False)
app.SetExitOnFrameDelete(False)
anchor = wx.Frame(None, size=(1, 1), pos=(-10000, -10000))
anchor.Show()
print('warm open', wx.TheClipboard.Open())
warm = wx.TextDataObject('warm')
print('warm set', wx.TheClipboard.SetData(warm), 'flush', wx.TheClipboard.Flush())
wx.TheClipboard.Close()
suite = unittest.TestSuite([
    QuickInsertTests('test_actual_component_editor_and_monitor_binding'),
    *unittest.defaultTestLoader.loadTestsFromTestCase(SchematicClipboardUiTests),
])
holder = {}
def run():
    holder['result'] = unittest.TextTestRunner(verbosity=2).run(suite)
    wx.CallAfter(app.ExitMainLoop)
wx.CallAfter(run)
app.MainLoop()
raise SystemExit(0 if holder['result'].wasSuccessful() else 1)
