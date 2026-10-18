# SPDX-License-Identifier: Apache-2.0
"""Open isolated real Studio forms for interactive visual acceptance."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'standalone/spikes_project/studio/python'))
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dialog',choices=('properties','insert','catalog','manufacturer','semiconductor','model-library','controller-board','firmware'),default='properties')
    parser.add_argument('--width',type=int,default=800)
    args=parser.parse_args()
    import wx
    from spikes_studio.desktop import Studio,Properties
    app=wx.App(False)
    frame=Studio(None)
    frame.set_theme('Light',save=False)
    frame.SetSize((max(1000,args.width),800));frame.Show()
    frame.SetTitle(f'SPIKES form review — {args.dialog} — {args.width}')
    def begin():
        if args.dialog=='manufacturer':
            window=frame.tool_windows.open(frame.book.FindPage(frame.manufacturer_hub))
            window.SetSize((args.width,800));window.SetTitle('SPIKES manufacturer library review')
            return
        if args.dialog=='firmware':
            from spikes_studio.firmware_window import FirmwareWindow
            window=FirmwareWindow(frame);window.SetSize((args.width,800));window.SetTitle('SPIKES native firmware review')
            window.Raise();return
        if args.dialog=='catalog':
            frame.book.SetSelection(frame.book.FindPage(frame.catalog_host))
            return
        if args.dialog=='controller-board':
            from spikes_studio.controller_board_browser import ControllerBoardDialog
            dialog=ControllerBoardDialog(frame)
        elif args.dialog=='model-library':
            from spikes_studio.model_library_editor import ModelLibraryEditor
            dialog=ModelLibraryEditor(frame,'.SUBCKT Amplifier IN_P IN_N VP VN OUT PARAMS: GAIN=100000 GBW=1Meg ROUT=50 SLEW=500000\nE1 OUT 0 IN_P IN_N {GAIN}\n.ENDS Amplifier\n')
        elif args.dialog=='semiconductor':
            from spikes_studio.document import Document
            frame.doc=Document.from_netlist('Model form review\nZ1 drain gate 0 bulk tj model\n.model model SPK_GAN(THRESHOLD_VOLTAGE_V=2.5 GATE_DRAIN_CAPACITANCE_F=20p THERMAL_CAPACITANCE_J_PER_K=.01)\n.op\n.end\n')
            frame.refresh_document(force_source=True)
            frame.canvas.selected={frame.doc.data['components'][0]['id']}
            dialog=Properties(frame);dialog.model_choice.SetSelection(1);dialog.render_model()
        elif args.dialog=='properties':
            frame.canvas.selected={frame.doc.data['components'][2]['id']}
            dialog=Properties(frame)
        else:
            from spikes_studio.component_panel import InsertDialog
            record=next(row for row in frame.catalog_panel.catalog['records']
                        if row['family']=='resistor' and not row.get('model_type'))
            dialog=InsertDialog(frame.catalog_panel,record)
        dialog.SetTitle('SPIKES — component inputs review')
        dialog.SetSize((args.width,760));dialog.CentreOnParent()
        dialog.ShowModal();dialog.Destroy()
        frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
    wx.CallLater(500,begin)
    app.MainLoop()


if __name__=='__main__':main()
