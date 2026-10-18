# SPDX-License-Identifier: Apache-2.0
"""Compare equivalent Studio search paths; not solver or competitor evidence."""
import argparse
import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'standalone/spikes_project/studio/python')]
from spikes_studio.component_catalog import catalog
from spikes_studio.discovery_index import DiscoveryIndex,manufacturer_text
from spikes_studio.manufacturer_parts import load_catalog
from spikes_studio.quick_insert import suggestions


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repetitions',type=int,default=5)
    args=parser.parse_args()
    if not 2<=args.repetitions<=25:parser.error('Use 2..25 repetitions')
    records=catalog(include_passives=True,include_lumped_physics=True)['records'];manufacturers=load_catalog()['records']
    started=time.perf_counter_ns()
    index=DiscoveryIndex(records);vendor=DiscoveryIndex(manufacturers,manufacturer_text)
    build_ms=(time.perf_counter_ns()-started)/1e6
    queries=('r','n','resistor','capacitor','inductor','resistr','LM358','nmos','oscillator','nonexistentpart8472')
    indexed=dict(component_index=index,manufacturer_index=vendor)
    checks={};measurements={query:{'baseline_ms':[],'indexed_ms':[]} for query in queries}
    for repetition in range(args.repetitions):
        for query in queries:
            answers={}
            # Alternate order to reduce bias from shared fuzzy-match caches.
            for label,options in ([('baseline',{}),('indexed',indexed)] if repetition%2==0 else [('indexed',indexed),('baseline',{})]):
                started=time.perf_counter_ns();answers[label]=suggestions(query,records,manufacturers,**options)
                measurements[query][label+'_ms'].append((time.perf_counter_ns()-started)/1e6)
            if answers['baseline']!=answers['indexed']:raise AssertionError('Ranking changed: '+query)
            checks[query]=True
    report=dict(contract='spikes/discovery-benchmark/v1',platform=platform.platform(),python=platform.python_version(),
                component_records=len(records),manufacturer_records=len(manufacturers),repetitions=args.repetitions,
                index_build_ms=build_ms,query_equivalence=checks,
                measurements={q:{key:dict(median_ms=statistics.median(values),max_ms=max(values)) for key,values in data.items()} for q,data in measurements.items()},
                limitations=['Search/model timings only; GUI rendering and solver execution excluded.',
                             'Hot indexed queries use a bounded cache of 16 pages.',
                             'Not a cross-simulator or reference-hardware performance qualification.'])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
