# SPDX-License-Identifier: Apache-2.0
"""Native suite evidence from actual local Yosys and Icarus execution."""
from pathlib import Path
import wx
from matplotlib.backend_bases import MouseEvent
from .ide import analyze
from .document import write_json
from .ui_evidence import capture_window


def verify(frame,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True);checks={}
    def check(value,label):
        if not value:raise AssertionError(label)
        checks[label]=True
    try:
        frame.set_theme('Light',save=False);frame.show_code_split(3)
        source='module top(input a, input b, output y); assign y=a&b; endmodule'
        frame.code.SetText(source)
        report=analyze(source,'Verilog','synthesize','top')
        check(report['exit_code']==0 and 'netlist' in report,'actual Yosys synthesis returns a netlist')
        frame.hdl_suite.accept_report(report);frame.hdl_suite.book.SetSelection(1);frame.Layout();frame.fit();wx.Yield()
        check(frame.hdl_suite.cells.GetItemCount()>0,'actual cell counts populate synthesis table')
        capture_window(frame,directory/'synthesis-beside-canvas.png')
        source='''`timescale 1ns/1ps
module top;
reg clk=0; reg [3:0] count=0;
always #5 clk=~clk;
always @(posedge clk) count<=count+1;
initial begin $dumpfile("wave.vcd"); $dumpvars(0,top); #100; $finish; end
endmodule
'''
        frame.code.SetText(source);report=analyze(source,'Verilog','simulate','top')
        check(report['exit_code']==0 and 'timing' in report,'actual Icarus testbench returns VCD')
        frame.hdl_suite.accept_report(report);frame.hdl_suite.book.SetSelection(2)
        frame.close_code_split();frame.book.SetSelection(3);frame.Layout();wx.Yield()
        plotter=frame.hdl_suite.plotter;plotter.canvas.draw()
        line=plotter.cursor_lines[0];ax=line.axes
        middle_y=sum(ax.get_ylim())/2
        x,y=ax.transData.transform((0,middle_y));press=MouseEvent('button_press_event',plotter.canvas,x,y,button=1)
        plotter.canvas.callbacks.process('button_press_event',press)
        x,y=ax.transData.transform((25e-9,middle_y));move=MouseEvent('motion_notify_event',plotter.canvas,x,y,button=1)
        plotter.canvas.callbacks.process('motion_notify_event',move)
        plotter.canvas.callbacks.process('button_release_event',MouseEvent('button_release_event',plotter.canvas,x,y,button=1))
        check(abs(plotter.cursor_times[0]-25e-9)<1e-9,'native Matplotlib cursor drag changes time')
        check(frame.hdl_suite.readings.GetNumberRows()>0,'cursor table shows actual VCD readings')
        wx.Yield();capture_window(frame,directory/'timing-cursors.png')
        frame.SetSize((1000,720));frame.Layout();wx.Yield()
        frame.ide_split.SetSashPosition(120);wx.Yield();capture_window(frame,directory/'timing-narrow.png')
        source='''library ieee; use ieee.std_logic_1164.all;
entity top is end entity;
architecture test of top is signal clk: std_logic := '0'; begin
process begin wait for 5 ns; clk <= '1'; wait for 5 ns; clk <= '0'; wait; end process;
end architecture;
'''
        frame.language.SetStringSelection('VHDL');frame.configure_code_editors();frame.code.SetText(source)
        report=analyze(source,'VHDL','simulate','top')
        check(report['exit_code']==0 and 'timing' in report,'actual GHDL testbench returns VCD')
        frame.hdl_suite.accept_report(report);frame.hdl_suite.book.SetSelection(2);wx.Yield()
        capture_window(frame,directory/'vhdl-timing.png')
        write_json(directory/'verification.json',dict(ok=True,checks=checks,tool=report['tool']))
    except Exception as error:write_json(directory/'verification.json',dict(ok=False,checks=checks,error=str(error)))
    frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
