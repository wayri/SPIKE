"""Graphical topology and analytical curves, not fabricated measurements."""
import math
import wx
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg
from .passive_models import impedance


class ModelPreview(FigureCanvasWxAgg):
    def __init__(self,parent):
        self.figure=Figure(figsize=(7,2.7),tight_layout=True)
        super().__init__(parent,wx.ID_ANY,self.figure)
        self.SetMinSize((-1,250))

    def update_model(self,part,values,source):
        self.figure.clear();circuit=self.figure.add_subplot(121);curve=self.figure.add_subplot(122)
        circuit.set_xlim(-.3,4.3);circuit.set_ylim(-1.5,1.3);circuit.axis('off')
        circuit.set_title('Equivalent circuit · explicit model')
        if part is None:
            circuit.text(0,0,'Select a single component');curve.axis('off');self.draw();return
        from .part_properties import parse
        element=next(e for e in parse(source).elements if e.name.upper()==part['ref'].upper())
        if part['kind'] in ('diode','voltage_controlled_switch','voltage_source','current_source'):
            from .model_characteristics import characteristic
            data=characteristic(element)
            circuit.plot([0,1.5],[0,0],color='C0');circuit.plot([2.5,4],[0,0],color='C0')
            kind=part['kind']
            if kind=='diode':
                circuit.plot([1.5,1.5,2.5,1.5],[-.4,.4,0,-.4],color='C0')
                circuit.plot([2.5,2.5],[-.4,.4],color='C0')
            elif kind=='voltage_controlled_switch':
                circuit.plot([1.5,2.5],[0,.35],color='C0')
                circuit.plot([1.7,2.3],[-.8,-.8],'o',color='C1')
                circuit.text(2,-1.1,'control + / −',ha='center',fontsize=8)
            else:
                from matplotlib.patches import Circle
                circuit.add_patch(Circle((2,0),.5,fill=False,color='C0'))
                circuit.text(2,0,'+  −' if kind=='voltage_source' else '→',ha='center',va='center')
            circuit.plot([0,4],[0,0],'o',color='C0',markerfacecolor='white')
            for x,node in zip((0,4),part['nodes'][:2]):circuit.text(x,.55,node,ha='center')
            circuit.text(2,.8,part['ref'],ha='center')
            curve.plot(data['x'],data['y']);curve.set_yscale(data['scale'])
            curve.set_xlabel(data['xlabel']);curve.set_ylabel(data['ylabel']);curve.set_title(data['title'],fontsize=8)
            curve.grid(True,alpha=.3);self.draw();return
        if part['kind'] not in ('resistor','capacitor','inductor'):
            circuit.text(0,0,'No executable native binding.\nDetailed preview unavailable.')
            curve.axis('off');self.draw();return
        labels=([('ESR','R')] if 'esr_ohm' in values else [])+([('ESL','L')] if 'esl_h' in values else [])+[(part['ref'],part['kind'])]
        for i,(label,kind) in enumerate(labels):
            x=4*i/len(labels);end=4*(i+1)/len(labels);mid=(x+end)/2
            circuit.plot([x,mid-.2],[0,0],color='C0');circuit.plot([mid+.2,end],[0,0],color='C0')
            if kind=='capacitor':
                for a in (mid-.2,mid+.2):circuit.plot([a,a],[-.3,.3],color='C0')
            else:
                circuit.plot([mid-.2,mid-.2,mid+.2,mid+.2,mid-.2],[0,.25,.25,-.25,-.25],color='C0')
                circuit.plot([mid-.2,mid-.2],[-.25,0],color='C0')
            circuit.text(mid,.5,label,ha='center',fontsize=8)
        if 'leakage_ohm' in values:
            circuit.plot([0,0,1.7],[0,-.8,-.8],color='C1')
            circuit.plot([2.3,4,4],[-.8,-.8,0],color='C1')
            circuit.plot([1.7,1.7,2.3,2.3,1.7],[-.8,-.6,-.6,-1,-1],color='C1')
            circuit.plot([1.7,1.7],[-1,-.8],color='C1')
            circuit.text(2,-1.3,'R leakage',ha='center')
        circuit.plot([0,4],[0,0],'o',color='C0',markerfacecolor='white')
        for x,node in zip((0,4),part['nodes']):circuit.text(x,.9,node,ha='center',fontsize=8)
        if part['kind'] in ('capacitor','inductor','resistor'):
            f=[10**(i/30) for i in range(241)]
            z=[abs(impedance(element.value,hz,values)) if part['kind']=='capacitor' else
               (element.value if part['kind']=='resistor' else 2*math.pi*hz*element.value) for hz in f]
            curve.loglog(f,z);curve.set_xlabel('Frequency [Hz]');curve.set_ylabel('|Z| [ohm]')
            curve.set_title('Analytical linear-model response',fontsize=9);curve.grid(True,which='both',alpha=.3)
        else:
            curve.axis('off');curve.text(.05,.5,'No qualified curve preview\nfor this source model.',transform=curve.transAxes)
        self.draw()
