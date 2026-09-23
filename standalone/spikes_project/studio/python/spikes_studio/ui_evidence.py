"""Capture the running workbench after real solver and property operations."""
from __future__ import annotations

import hashlib
import json
import ctypes
from pathlib import Path
import wx
from PIL import Image
from .document import write_json


def capture_window(target,path):
    """Capture this application's HWND only; never sample the user's desktop."""
    target.Update();wx.YieldIfNeeded()
    rectangle=target.GetRect();bitmap=wx.Bitmap(rectangle.width,rectangle.height)
    dc=wx.MemoryDC(bitmap)
    api=ctypes.windll.user32.PrintWindow
    api.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint]
    api.restype=ctypes.c_bool
    ok=api(target.GetHandle(),dc.GetHandle(),2)
    dc.SelectObject(wx.NullBitmap)
    if not ok:raise RuntimeError('Could not capture the actual workbench window')
    bitmap.SaveFile(str(path),wx.BITMAP_TYPE_PNG)


def capture_session(frame, destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    captures=[]

    def screenshot(name, target=None):
        target=target or frame
        path=destination/name;capture_window(target,path);captures.append(path)

    def await_result():
        if frame.job_running:wx.CallLater(150,await_result);return
        try:
            if frame.math is None:raise RuntimeError("Native solver did not produce a result")
            import numpy as np
            error=float(np.max(np.abs(frame.math.signals['v(out)'].values-(1-np.exp(-frame.math.time/.001)))))
            if error>.012:raise RuntimeError(f"RC analytical comparison failed: {error}")
            frame.analytical_error=error
            frame.add_trace("v(in,out)");frame.add_trace("v(in,out)*i(R1)")
            frame.expression.SetValue("v(out)");frame.measure()
            frame.figure.savefig(destination/"recorded-rc-response.svg")
            from .result_file import save_result
            save_result(destination/"rc-run.spkdata",frame.math,frame.result["provenance"])
            write_json(destination/"rc-run.json",frame.result)
            frame.doc.save(destination/"rc-project.spksch")
            wx.CallLater(400,plot_capture)
        except Exception as exc:fail(exc)

    def plot_capture():
        screenshot("01-recorded-plots.png")
        frame.book.SetSelection(0);part=frame.doc.data["components"][1];frame.canvas.selected={part["id"]}
        frame.canvas.Refresh();frame.canvas.Update();wx.YieldIfNeeded()
        frame.probe('differential')
        for node in ('in','out'):
            position=next(point for point,name,pid in frame.canvas.pins if pid==part['id'] and name==node)
            event=wx.MouseEvent(wx.wxEVT_LEFT_DOWN);event.SetPosition(position);frame.canvas.GetEventHandler().ProcessEvent(event)
        if not any(probe['expression']=='V(in,out)' for probe in frame.doc.data['probes']):return fail(RuntimeError('Canvas differential probe placement failed'))
        wx.CallLater(250,schematic_capture)

    def schematic_capture():
        screenshot("02-differential-probe.png")
        from .desktop import Properties
        dlg=Properties(frame)
        def edit():
            dlg.book.SetSelection(2);dlg.fields["limits"].SetValue('{"power_w": 0.25, "voltage_v": 50}')
            dlg.Update();wx.YieldIfNeeded();screenshot("03-limits-editor.png",dlg)
            dlg.apply()
        wx.CallLater(350,edit);dlg.ShowModal();dlg.Destroy()
        part=frame.doc.data["components"][1]
        if part["limits"]!={"power_w":.25,"voltage_v":50}:return fail(RuntimeError("Property apply did not persist"))
        frame.doc.undo()
        if frame.doc.data["components"][1]["limits"]:return fail(RuntimeError("Undo failed"))
        frame.doc.redo()
        dlg=Properties(frame)
        def verify():
            dlg.book.SetSelection(3);dlg.fields["model_source"].SetValue("* Model source editor is distinct from Limits")
            screenshot("04-model-editor.png",dlg);dlg.EndModal(wx.ID_CANCEL)
        wx.CallLater(300,verify);dlg.ShowModal();dlg.Destroy()
        frame.book.SetSelection(3);frame.build_code("synthesize");wx.CallLater(200,await_build)

    def await_build():
        if frame.job_running:wx.CallLater(150,await_build);return
        report=getattr(frame,"last_build",None)
        if not report or report["exit_code"]!=0:return fail(RuntimeError("Real synthesis did not succeed"))
        write_json(destination/"synthesis-report.json",report)
        wx.CallLater(250,build_capture)

    def build_capture():
        screenshot("05-real-synthesis.png")
        frame.synthesis_exit=frame.last_build['exit_code']
        frame.code.SetText('`timescale 1ns/1ps\nmodule top;\nreg clk=0; reg [3:0] count=0;\nalways #5 clk=~clk;\nalways @(posedge clk) count<=count+1;\ninitial begin $dumpfile("wave.vcd"); $dumpvars(0,top); #100; $finish; end\nendmodule\n')
        frame.build_code('simulate');wx.CallLater(200,await_timing)

    def await_timing():
        if frame.job_running:wx.CallLater(150,await_timing);return
        if frame.last_build['exit_code']!=0 or 'timing' not in frame.last_build:return fail(RuntimeError('Real HDL simulation failed'))
        write_json(destination/'digital-simulation-report.json',frame.last_build)
        (destination/'counter.vcd').write_text(frame.last_build['vcd_source'])
        wx.CallLater(300,timing_capture)

    def timing_capture():
        screenshot('06-real-vcd-timing.png');frame.digital_exit=frame.last_build['exit_code']
        frame.language.SetStringSelection('C++');frame.code.SetLexer(wx.stc.STC_LEX_CPP)
        frame.code.SetText('#include <cmath>\ndouble observer_output(double state, double angle) {\n    return state * std::cos(angle);\n}\n')
        frame.build_code('check');wx.CallLater(200,await_cpp)

    def await_cpp():
        if frame.job_running:wx.CallLater(150,await_cpp);return
        if frame.last_build['exit_code']!=0:return fail(RuntimeError('Real C++ analysis failed'))
        write_json(destination/'cpp-analysis-report.json',frame.last_build)
        screenshot('08-cpp-analysis.png');frame.book.SetSelection(4);wx.CallLater(300,finish_capture)

    def finish_capture():
        screenshot('07-symbol-designer.png')
        images=[Image.open(p).convert("RGB") for p in captures]
        images[0].save(destination/"workbench-walkthrough.gif",save_all=True,append_images=images[1:],duration=1700,loop=0)
        for image in images:image.close()
        write_json(destination/"evidence.json",{"contract":"spikes/studio-ui-evidence/v1","solver_provenance":frame.result["provenance"],"sample_count":len(frame.math.time),"rc_max_error_v":frame.analytical_error,"property_apply_undo_redo":True,"canvas_differential_clicks":True,"real_synthesis_exit":frame.synthesis_exit,"real_digital_simulation_exit":frame.digital_exit,"real_cpp_analysis_exit":frame.last_build['exit_code'],"captures":[{"file":p.name,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in captures]})
        frame.timer.Stop();frame.Destroy()

    def fail(error):
        frame.validation_failure=True
        write_json(destination/"error.json",{"error":str(error)});frame.timer.Stop();frame.Destroy()

    try:frame.run();wx.CallLater(150,await_result)
    except Exception as exc:fail(exc)
