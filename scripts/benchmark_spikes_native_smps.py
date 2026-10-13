# SPDX-License-Identifier: Apache-2.0
"""Warm end-to-end SMPS timings with same model and verified numerical results."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    import numpy as np
    from python.spikes.smps_stability import analyze as reference
    from python.spikes.native_smps import analyze as native
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise ValueError('Refusing to replace earlier benchmark evidence')
    rows=[]
    for count in (401,10000):
        config=dict(controller_gain=5,points=count)
        a=reference(config);b=native(config,args.library)
        np.testing.assert_allclose(a['loop'],b['loop'],rtol=1e-10,atol=1e-9)
        functions={'python_reference':lambda:reference(config),'cpp_bulk_transport':lambda:native(config,args.library)}
        timing={}
        for name,fn in functions.items():
            fn();samples=[]
            for _ in range(30):
                start=time.perf_counter();fn();samples.append(time.perf_counter()-start)
            timing[name]=dict(median_s=statistics.median(samples),p95_s=sorted(samples)[28],repetitions=30,warmup=1)
        rows.append(dict(points=count,timings=timing,speed_ratio=timing['python_reference']['median_s']/timing['cpp_bulk_transport']['median_s']))
    report=dict(contract='spikes/native-smps-performance/v1',rows=rows,native_library_sha256=hashlib.sha256(args.library.read_bytes()).hexdigest(),
      scope='Warm end-to-end analysis including Python input validation and bulk-array transport; not cold startup, switching solve, or general superiority evidence')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='ascii')
    print(json.dumps(rows))


if __name__=='__main__':main()
