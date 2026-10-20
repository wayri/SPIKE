# SPDX-License-Identifier: Apache-2.0
"""Native wx checks for visible wire targeting and reversible controls."""
from copy import deepcopy
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','opt-in native wx')
class WiringInteractionUiTests(unittest.TestCase):
    def test_branch_snap_chooses_nearest_visible_route(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.document import Document

        app=wx.GetApp() or wx.App(False);frame=Studio()
        try:
            frame.Show();wx.Yield()
            frame.doc=Document.from_netlist('Parallel routes\nV1 a 0 1\nR1 a 0 1k\nV2 b 0 2\nR2 b 0 2k\n.op\n.end\n')
            for part,position in zip(frame.doc.data['components'],((100,100),(400,100),(100,108),(400,108))):
                part['x'],part['y']=position
            parts=frame.doc.data['components']
            frame.doc.connect((parts[0]['id'],0),(parts[1]['id'],0),[[200,100]])
            frame.doc.connect((parts[2]['id'],0),(parts[3]['id'],0),[[200,108]])
            first,second=frame.doc.data['wires'];canvas=frame.canvas
            canvas.zoom=1;canvas.offset=np.array([20.,15.]);canvas.wire_mode=True;canvas.wire_start=(parts[3]['id'],1)
            nearest_first=canvas.wire_snap_target(canvas.point(200,100))
            nearest_second=canvas.wire_snap_target(canvas.point(200,108))
            tie=canvas.wire_snap_target(canvas.point(200,104))
            self.assertEqual((nearest_first['wire_id'],nearest_first['label'].split(' · ')[0]),(first['id'],'a'))
            self.assertEqual((nearest_second['wire_id'],nearest_second['label'].split(' · ')[0]),(second['id'],'b'))
            self.assertEqual(tie['wire_id'],second['id'])
        finally:
            frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()

    def test_snap_bend_backtrack_and_two_stage_escape_do_not_mutate(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.editor_geometry import route

        app=wx.GetApp() or wx.App(False);frame=Studio()
        event=lambda point:SimpleNamespace(GetPosition=lambda:point,GetKeyCode=lambda:0)
        try:
            frame.SetSize((1000,720));frame.Show();wx.Yield();canvas=frame.canvas;before=deepcopy(frame.doc.data)
            canvas.board_tools.pending={'board':{'name':'pending','pins':[]}}
            canvas.board_tools.drag={'id':'stale drag'}
            frame.start_wire();canvas.Refresh();canvas.Update();wx.Yield()
            wire_control=next(control for control,command in frame.command_controls if command=='edit.wire')
            self.assertTrue(wire_control.GetValue())
            self.assertIsNone(canvas.board_tools.pending)
            self.assertIsNone(canvas.board_tools.drag)
            component_pins=[row for row in canvas.wire_pins if row[2] is not None]
            self.assertGreaterEqual(len(component_pins),2)
            source=component_pins[0]
            source_part=next(p for p in frame.doc.data['components'] if p['id']==source[1])
            from spikes_studio.editor_geometry import terminal
            source_world=terminal(source_part,source[2]);original_offset=canvas.offset.copy()
            canvas.offset=canvas.offset+(137,83)
            canvas.wire_pins=[(source[0],'deleted component',99)]
            moved=canvas.point(*source_world)
            self.assertEqual(canvas.wire_snap_target(moved)['endpoint'],(source[1],source[2]))
            old=canvas.wire_snap_target(source[0])
            self.assertFalse(old and old.get('endpoint')==(source[1],source[2]))
            parts=frame.doc.data['components'];frame.doc.data['components']=[p for p in parts if p['id']!=source[1]]
            deleted=canvas.wire_snap_target(moved)
            self.assertFalse(deleted and deleted.get('endpoint')==(source[1],source[2]))
            frame.doc.data['components']=parts
            canvas.sheet_scope='NO_SUCH_SCOPE'
            self.assertIsNone(canvas.wire_snap_target(moved))
            canvas.sheet_scope=None;canvas.offset=original_offset
            source_point=canvas.point(*source_world);canvas.motion(event(source_point))
            self.assertEqual(canvas.wire_target['kind'],'terminal')
            self.assertIn('·',canvas.wire_target['label'])
            canvas.click(event(source_point));self.assertIsNotNone(canvas.wire_start)

            bitmap=wx.Bitmap(max(1,canvas.GetClientSize().width),max(1,canvas.GetClientSize().height))
            dc=wx.MemoryDC(bitmap);long_label='SNAP '+('very-long-target-name-'*50)
            display,position=canvas._wire_label_position(dc,long_label,wx.Point(canvas.GetClientSize().width-1,canvas.GetClientSize().height-1))
            width,height=dc.GetTextExtent(display)
            self.assertTrue(display.endswith('…'))
            self.assertGreaterEqual(position.x,8);self.assertGreaterEqual(position.y,8)
            self.assertLessEqual(position.x+width,canvas.GetClientSize().width-8)
            self.assertLessEqual(position.y+height,canvas.GetClientSize().height-8)
            anchor=wx.Point(canvas.GetClientSize().width//2,canvas.GetClientSize().height//2)
            obstacle=wx.Rect(anchor.x+8,anchor.y-40,220,70)
            label,position=canvas._wire_label_position(dc,'BRANCH input · existing wire route',anchor,34,[obstacle])
            width,height=dc.GetTextExtent(label);dc.SelectObject(wx.NullBitmap)
            self.assertLessEqual(position.x+width,obstacle.x)

            corner=None
            size=canvas.GetClientSize()
            for x in range(60,max(61,size.width-60),40):
                for y in range(80,max(81,size.height-60),40):
                    candidate=canvas.wire_snap_target(wx.Point(x,y))
                    if candidate and candidate['kind']=='corner':corner=wx.Point(x,y);break
                if corner:break
            self.assertIsNotNone(corner)
            canvas.motion(event(corner));canvas.click(event(corner));self.assertEqual(len(canvas.wire_corners),1)
            canvas.context(event(corner));self.assertEqual(canvas.wire_corners,[])
            self.assertIsNotNone(canvas.wire_start)
            canvas.motion(event(corner));canvas.click(event(corner));self.assertEqual(len(canvas.wire_corners),1)
            frame.toggle_wire_bend();self.assertEqual(canvas.wire_bend,'vertical')
            canvas.placement_key(SimpleNamespace(GetKeyCode=lambda:wx.WXK_BACK))
            self.assertEqual(canvas.wire_corners,[])
            canvas.context(event(corner));self.assertIsNone(canvas.wire_start)
            canvas.click(event(source_point));self.assertIsNotNone(canvas.wire_start)

            parts={p['id']:p for p in frame.doc.data['components']};junctions={j['id']:j for j in frame.doc.data['junctions']}
            branch_point=None
            for wire in canvas.visible_wires():
                points=route(parts,wire,junctions)
                for a,b in zip(points,points[1:]):
                    candidate=canvas.point((a[0]+b[0])/2,(a[1]+b[1])/2)
                    target=canvas.wire_snap_target(candidate)
                    if target and target['kind']=='branch':branch_point=candidate;break
                if branch_point:break
            self.assertIsNotNone(branch_point)
            canvas.motion(event(branch_point));self.assertEqual(canvas.wire_target['kind'],'branch')
            self.assertTrue(canvas.wire_target['label'].endswith(' · existing wire route'))
            self.assertIn('Backspace',frame.GetStatusBar().GetStatusText())
            dragged=wx.Point(branch_point.x+40,branch_point.y+30);canvas.drag_start=branch_point
            canvas.motion(event(dragged));canvas.drag_start=None
            self.assertEqual(canvas.wire_target['kind'],'branch')
            self.assertLess(np.linalg.norm(np.asarray(canvas.wire_target['world'])-np.asarray(canvas.world(dragged))),1e-9)
            canvas.Refresh();canvas.Update();wx.Yield()

            canvas.placement_key(SimpleNamespace(GetKeyCode=lambda:wx.WXK_ESCAPE))
            self.assertTrue(canvas.wire_mode);self.assertIsNone(canvas.wire_start)
            canvas.placement_key(SimpleNamespace(GetKeyCode=lambda:wx.WXK_ESCAPE))
            self.assertFalse(canvas.wire_mode);self.assertEqual(frame.doc.data,before)
            self.assertFalse(wire_control.GetValue())
        finally:
            frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()


if __name__=='__main__':unittest.main()
