# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','Native wx active forms')
class ActivePropertyForms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import wx
        cls.app=wx.GetApp() or wx.App(False)

    def test_real_model_forms_and_thermal_report(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.part_form_checks import verify
        frame=Studio(None)
        try:verify(frame,lambda condition,message:self.assertTrue(condition,message))
        finally:frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()


if __name__=='__main__':unittest.main()
