"""Synthetic display-index microbenchmark, not simulation or competitor evidence."""
import argparse
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'standalone/spikes_project/studio/python'),str(ROOT/'.tmp/studio-deps')]
import numpy as np
from spikes_studio.waveform_index import WaveformIndex


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples',type=int,default=10_000_000)
    parser.add_argument('--traces',type=int,default=8)
    parser.add_argument('--queries',type=int,default=100)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not 1000<=args.samples<=10_000_000 or not 1<=args.traces<=8 or not 10<=args.queries<=1000:raise ValueError('Benchmark bounds exceeded')
    timestamps=np.arange(args.samples,dtype=float)*1e-9;indexes=[];cold=[]
    for i in range(args.traces):
        values=np.sin(timestamps*(i+1)*1e6)
        values[args.samples//2+i]=10+i
        started=time.perf_counter_ns();indexes.append(WaveformIndex(timestamps,values));cold.append((time.perf_counter_ns()-started)/1e6)
    timings=[];points=[]
    for query in range(args.queries):
        fraction=(query%10+1)/10;start=(1-fraction)*query/args.queries*timestamps[-1]
        limits=(start,start+fraction*timestamps[-1]);started=time.perf_counter_ns()
        chosen=[index.indices(limits) for index in indexes]
        timings.append((time.perf_counter_ns()-started)/1e6);points.append(max(map(len,chosen)))
    report=dict(scope=__doc__,platform=platform.platform(),python=platform.python_version(),logical_cpus=os.cpu_count(),
        samples_per_trace=args.samples,traces=args.traces,queries=args.queries,
        cold_index_build_ms=cold,warm_all_trace_query_median_ms=float(np.median(timings)),
        warm_all_trace_query_p95_ms=float(np.percentile(timings,95)),maximum_display_points=max(points),
        index_bytes=sum(index.cache_bytes for index in indexes),
        original_numpy_bytes=timestamps.nbytes+sum(index.values.nbytes for index in indexes),
        limitations=['Does not include GUI rendering or SignalMath ingestion','Does not measure process RSS or solver performance','Not an 8-core/16-GB reference-hardware qualification'])
    if args.output:
        from spikes_studio.document import write_json
        write_json(args.output,report)
    print(json.dumps(report,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
