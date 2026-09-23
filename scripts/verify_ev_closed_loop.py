"""Exercise real native interactive plant and trusted example C controller."""
from pathlib import Path
import sys,time,json,argparse
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'standalone/spikes_project/studio/python')]
from spikes_studio.document import Document,write_json
from spikes_studio.controller_block import Controller
from spikes_studio.run_control import InteractiveRun


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--library',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();doc=Document.load(ROOT/'examples/spikes/advanced_systems/two_wheeler_dashboard.spksch')
    controller=Controller(doc.data['controller_setup'],trusted=True);session=None
    report={'contract':'spikes/ev-example-check/v1','passed':False,'checks':[]}
    try:
        session=InteractiveRun(doc.data['source'],args.library,controller=controller,speed_ratio=10,capacity=2000)
        session.set_source('VTHROTTLE',.3)
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            result=session.snapshot()
            if session.state=='failed':raise RuntimeError(session.error)
            if result and result['data']['time_s'][-1]>=.12:break
            time.sleep(.02)
        else:raise TimeoutError('Did not reach 120 ms virtual time')
        current=result['data']['node_voltage_v']['current'][-1]
        speed=result['data']['node_voltage_v']['omega'][-1]
        if current<=0 or speed<=0:raise AssertionError('Throttle must produce positive current and acceleration')
        report['checks'].append('Throttle drives positive native armature current and C mechanical acceleration')
        session.set_source('VBRAKE',1)
        start=result['data']['time_s'][-1];deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            result=session.snapshot()
            if session.state=='failed':raise RuntimeError(session.error)
            if result and result['data']['time_s'][-1]>=start+.12:break
            time.sleep(.02)
        else:raise TimeoutError('Brake test did not advance')
        if result['data']['node_voltage_v']['current'][-1]>=0:raise AssertionError('Brake must request negative current at nonzero speed')
        report['checks'].append('Brake priority drives negative armature current')
        report.update(passed=True,result=result)
    finally:
        if session:session.stop();session.thread.join(5)
        controller.close();write_json(args.output,report)


if __name__=='__main__':main()
