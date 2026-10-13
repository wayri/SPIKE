# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original engine references, explicitly not SAS vendor-circuit qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from python.spikes.sourced_qualification import qualify_sourced_deck
from python.spikes.qualification_artifacts import export_qualification_evidence


def run(output):
    output = Path(output)
    output.mkdir(parents=True,exist_ok=False)
    cases = [('divider','Original divider\nV1 in 0 3.3\nR1 in out 1k\nR2 out 0 1k\n.op\n.end\n','last',0.,1.649999,1.650001),
             ('rc-fault-bus-reference','* Original independent RC reference\nV1 in 0 1\nR1 in out 1k\nC1 out 0 1u\n.tran 10u 5m uic\n.end\n',
              'first_rising_crossing',.5,.00068,.00071)]
    summaries = []
    for name,deck,kind,threshold,low,high in cases:
        source = output/(name+'.cir')
        source.write_text(deck,encoding='utf-8')
        request = {'contract':'spikes/sourced-qualification-request/v1','id':name,'deck_path':source.name,
                   'purpose':'solver_regression','pin_mapping':{},'sources':[{'path':source.name,
                       'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'role':'deck','revision':'1',
                       'origin':'Original independent mathematical fixture','conditions':'Ideal R/RC, no SAS parts/cooling assumptions',
                       'value_basis':'synthetic'}],
                   'checks':[{'probe':'V(out)','measurement':kind,'threshold':threshold,'minimum':low,'maximum':high,
                              'numerical_absolute_tolerance':1e-5 if kind!='last' else 1e-3,
                              'numerical_relative_tolerance':.01 if kind!='last' else .001}]}
        (output/(name+'-request.json')).write_text(json.dumps(request,indent=2)+'\n',encoding='utf-8')
        report = qualify_sourced_deck(request,output)
        export_qualification_evidence(report,output/(name+'-evidence'))
        summaries.append({'id':name,'status':report['status'],'hardware_qualified':False,'gates':report.get('gates',[])})
    return summaries


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True,help='New evidence directory; existing directories are rejected')
    options = parser.parse_args()
    summaries = run(options.output)
    print(json.dumps(summaries,indent=2,allow_nan=False))
    sys.exit(0 if all(case['status']=='PASS' for case in summaries) else 1)
