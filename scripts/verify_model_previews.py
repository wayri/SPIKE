"""Self-closing rendering check for the native model preview families."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'standalone/spikes_project/studio/python'),str(ROOT/'.tmp/studio-deps')]
import wx
from spikes_studio.document import Document,write_json
from spikes_studio.model_preview import ModelPreview


def main():
    output=ROOT/'artifacts/model-preview-families';output.mkdir(parents=True,exist_ok=True)
    decks={
        'diode':'.title D\nV1 a 0 .1\nD1 a 0 dm\n.model dm D(IS=1p N=1.3)\n.op\n.end',
        'voltage_controlled_switch':'.title S\nV1 a 0 1\nV2 ctl 0 .5\nS1 a 0 ctl 0 2 1000 .5 .1\n.op\n.end',
        'voltage_source':'.title V\nV1 a 0 PULSE(0 5 1u 2u 2u 3u 10u)\nR1 a 0 1k\n.tran 1u 30u\n.end',
        'current_source':'.title I\nI1 0 a PWL(0 0 1m .01 2m 0)\nR1 a 0 1k\n.tran 10u 3m\n.end'}
    app=wx.App(False);frame=wx.Frame(None,size=(900,400));panel=ModelPreview(frame)
    checks=[]
    try:
        for kind,source in decks.items():
            doc=Document.from_netlist(source);part=next(p for p in doc.data['components'] if p['kind']==kind)
            panel.update_model(part,{},source);panel.figure.savefig(output/(kind+'.png'))
            if not panel.figure.axes[1].lines:raise AssertionError('Missing characteristic curve')
            checks.append(kind)
        write_json(output/'checks.json',{'passed':True,'rendered':checks})
    finally:frame.Destroy()


if __name__=='__main__':main()
