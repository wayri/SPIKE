# SPDX-License-Identifier: Apache-2.0
"""Real native parameter sweeps, annotation manipulation and reference MC."""
from pathlib import Path
import time
import numpy as np
import wx
from matplotlib.backend_bases import MouseEvent
from .document import Document,write_json
from .plot_annotations import create,commit,sweep_cursor_rows
from .ui_evidence import capture_window


def verify(frame,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True);checks={};deadline=time.monotonic()+45
    def check(condition,label):
        if not condition:raise AssertionError(label)
        checks[label]=True
    def finish(error=None):
        frame.plot_interactions.cancel_drag()
        write_json(directory/'verification.json',dict(ok=error is None,checks=checks,error=str(error) if error else None))
        frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
    def await_mc():
        if frame.job_running and time.monotonic()<deadline:wx.CallLater(100,await_mc);return
        try:
            panel=frame.monte_carlo_panel
            check(panel.result is not None and len(panel.result['cases'])==8,'automatic Monte Carlo produced eight real linear-reference cases')
            check(panel.result['analysis']['seed']==42,'Monte Carlo records chosen seed')
            frame.Layout();wx.Yield();panel.canvas.draw();capture_window(frame,directory/'monte-carlo.png')
            finish()
        except Exception as error:finish(error)
    def await_run():
        if frame.job_running and time.monotonic()<deadline:wx.CallLater(100,await_run);return
        try:
            check(len(frame.run_engines)==3,'native .step produced three actual runs')
            frame.book.SetSelection(1);frame.add_trace('i(R1)');frame.overlay_runs.SetValue(True);frame.put_cursor(.001,0,'v(out)');frame.draw_plot();frame.Layout();wx.Yield()
            rows=sweep_cursor_rows(frame)
            check(len(rows)==6,'cursor comparison includes both expressions across all three runs')
            check(len({row[2] for row in rows})==3,'cursor comparison retains parameter coordinates')
            axis=frame.axes[0]
            notes=[create(0,(.003,.7),'Text box'),create(0,(.002,.6),'Response',kind='arrow',head=(.001,.63))]
            commit(frame,notes);frame.draw_plot();frame.plot.draw()
            artist,note=frame.plot_interactions.annotation_artists[0];box=artist.get_bbox_patch().get_window_extent();x,y=(box.x0+box.x1)/2,(box.y0+box.y1)/2
            frame.plot.callbacks.process('button_press_event',MouseEvent('button_press_event',frame.plot,x,y,button=1))
            check(frame.plot_interactions.annotation_drag is not None and frame.plot.HasCapture(),'text annotation can be dragged with native mouse capture')
            frame.plot.callbacks.process('motion_notify_event',MouseEvent('motion_notify_event',frame.plot,x+35,y+20,button=1))
            frame.plot.callbacks.process('button_release_event',MouseEvent('button_release_event',frame.plot,x+35,y+20,button=1))
            check(frame.doc.data['metadata']['plot_annotations'][0]['point']!=notes[0]['point'],'annotation drag commits data-coordinate movement')
            arrow=frame.doc.data['metadata']['plot_annotations'][1];tail=list(arrow['point']);head=list(arrow['head'])
            axis=frame.axes[0];x,y=axis.transData.transform(head)
            frame.plot.callbacks.process('button_press_event',MouseEvent('button_press_event',frame.plot,x,y,button=1))
            frame.plot.callbacks.process('motion_notify_event',MouseEvent('motion_notify_event',frame.plot,x+30,y+15,button=1))
            frame.plot.callbacks.process('button_release_event',MouseEvent('button_release_event',frame.plot,x+30,y+15,button=1))
            arrow=frame.doc.data['metadata']['plot_annotations'][1]
            check(arrow['head']!=head and arrow['point']==tail,'arrow tip moves independently of its text box')
            frame.plot_interactions.set_grid(False);check(not any(line.get_visible() for line in frame.axes[0].get_xgridlines()),'graph grid can be hidden')
            frame.plot_interactions.set_grid(True);frame.plot_interactions.set_legends(False)
            check(not frame.axes[0].get_legend().get_visible(),'legends can be hidden');frame.plot_interactions.set_legends(True);frame.plot.draw()
            capture_window(frame,directory/'stepped-annotations.png')
            frame.plot_interactions.show_sweep_values();wx.Yield();capture_window(frame.plot_interactions.sweep_window,directory/'all-step-cursor-values.png')
            check(frame.plot_interactions.sweep_table.GetItemCount()==6,'live all-run cursor table shows actual readings');frame.plot_interactions.sweep_window.Hide()
            frame.doc.save(directory/'annotated.spksch');check(len(Document.load(directory/'annotated.spksch').data['metadata']['plot_annotations'])==2,'text and arrows persist on reopen')
            frame.source.SetText('Monte Carlo divider\nV1 in 0 1\nR1 in out 1k\nR2 out 0 1k\n.op\n.end\n');frame.apply_source()
            panel=frame.monte_carlo_panel;frame.book.SetSelection(frame.book.FindPage(panel));panel.samples.SetValue('8');panel.seed.SetValue('42');panel.variations.SetValue('R1=5%\nR2=5%');panel.run();wx.CallLater(100,await_mc)
        except Exception as error:finish(error)
    try:
        frame.set_theme('Light',save=False);frame.SetSize((1320,880))
        frame.source.SetText('Native RC step\n.param rval=1k\nV1 in 0 1\nR1 in out {rval}\nC1 out 0 1u\n.step param rval list 1k 2k 4k\n.temp 25\n.ic V(out)=0\n.tran 10u 5m uic\n.end\n')
        frame.apply_source();frame.run();wx.CallLater(100,await_run)
    except Exception as error:finish(error)
