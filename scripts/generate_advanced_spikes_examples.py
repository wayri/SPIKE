"""Build source-backed Studio examples; no invented recorded waveforms."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'standalone/spikes_project/studio/python')]
from spikes_studio.document import Document,write_json
from spikes_studio.dashboard import widget
from spikes_studio.controller_block import default_config,validate


def main():
    folder=ROOT/'examples/spikes/advanced_systems'
    doc=Document.from_netlist((folder/'ev_motor_plant.cir').read_text())
    config=default_config();config.update(step_s=.001,state_count=3,source=(folder/'ev_current_controller.c').read_text())
    config['pins']=[]
    for name,node in (('current','sense'),('speed','omega'),('throttle','throttle'),('brake','brake')):
        config['pins'].append(dict(name=name,mode='AI',node=node,reference='0',source='',vdd=3.3))
    for name,source in (('drive','Vdrive'),('temperature','Vtemperature'),('bus','Vbus'),('backemf','Vback'),('omega','Vspeed'),('measured','Vcurrent')):
        config['pins'].append(dict(name=name,mode='AO',node='',reference='0',source=source.upper(),vdd=1000))
    validate(config);doc.data['controller_setup']=config
    rows=[]
    instruments=[('Source control','Throttle','', 'Vthrottle',0,1),
                 ('Source control','Regen brake','', 'Vbrake',0,1),
                 ('Meter','Motor current [A]','V(current)','',-150,150),
                 ('Meter','Motor speed [rad/s]','V(omega)','',0,650),
                 ('Meter','Controller temperature estimate [degC]','V(controller_temp)','',0,110),
                 ('Meter','Bus voltage estimate [V]','V(bus)','',60,80),
                 ('Scope','Armature current [A]','V(current)','',-150,150),
                 ('Scope','Closed-loop speed [rad/s]','V(omega)','',0,650)]
    for i,(kind,title,expression,source,lo,hi) in enumerate(instruments):
        row=widget(kind,expression);row.update(title=title,source=source.upper(),minimum=lo,maximum=hi,x=(i%3)*320,y=(i//3)*210,width=300,height=190);rows.append(row)
    doc.data['dashboard']['widgets']=rows
    doc.data['metadata']['example_limitations']='Averaged DC equivalent, hypothetical parameters; no three-phase PWM, vendor switches, battery chemistry, HIL or safety certification. Temperature and bus are controller estimates.'
    doc.validate();write_json(folder/'two_wheeler_dashboard.spksch',doc.data)
    print(folder/'two_wheeler_dashboard.spksch')


if __name__=='__main__':main()
