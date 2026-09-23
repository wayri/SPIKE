# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Compare identical scalar-frequency and batch-128 loaded N-port algebra."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.si_workflow import _loaded_response
from python.spike_core.si_passives import KB
from python.spike_core.sparameters import NetworkData


def scalar_reference(network, y, drive, temperature, excess_current):
    """Original per-frequency formulation retained solely as benchmark oracle."""
    s, z = network.s_parameters(), network.reference_impedance_ohm
    identity, root = np.eye(network.port_count), np.diag(np.sqrt(z))
    transfer, noise, excess = [], [], []
    for i, matrix in enumerate(s):
        load = np.diag(z * y[i])
        boundary = identity + load + (load - identity) @ matrix
        current_to_voltage = root @ (identity + matrix) @ np.linalg.solve(boundary, root)
        transfer.append(current_to_voltage @ drive[i])
        current_noise = 4 * KB * (temperature + 273.15) * np.maximum(y[i].real, 0)
        noise.append(np.abs(current_to_voltage)**2 @ current_noise)
        excess.append(np.abs(current_to_voltage)**2 @ excess_current[i])
    return np.asarray(transfer), np.asarray(noise), np.asarray(excess)


def fixture(points):
    f = np.linspace(0, 8e9, points)
    matrix = np.array([[.03,.05,.65,.02],[.05,.02,.02,.6],[.65,.02,.04,.05],[.02,.6,.05,.03]])
    s = matrix[None,:,:] * np.exp(-2j*np.pi*f*300e-12)[:,None,None]
    network = NetworkData(f, s, np.array([40.,50.,60.,75.]))
    resistance = np.array([35.,70.,90.,125.])
    y = 1/resistance + 2j*np.pi*f[:,None]*np.array([.5,1.,2.,.25])*1e-12
    drive = np.zeros((points,4,3),complex)
    for source in range(3):
        drive[:,source,source] = 1/resistance[source]
    excess = np.broadcast_to(1e-24 * (1 + np.arange(4)), (points,4)).copy()
    return network, y, drive, 45., excess


def compare(a,b):
    metrics={}
    for label, left, right in zip(("voltage_transfer", "thermal_noise_psd", "excess_noise_psd"),a,b):
        np.testing.assert_allclose(left,right,rtol=1e-12,atol=0)
        metrics[label]={"relative_l2_error":float(np.linalg.norm(left-right)/np.linalg.norm(left)),
            "maximum_absolute_error":float(np.max(np.abs(left-right)))}
    return metrics


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        parser.error("Output must not already exist")
    paths=[Path(__file__),ROOT/"python/spike_core/si_workflow.py",ROOT/"python/spike_core/si_passives.py",ROOT/"python/spike_core/sparameters.py"]
    def hashes():
        return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in paths}
    before=hashes()
    report={"contract":"spike/si-loaded-response-performance/v1", "machine":platform.platform(),
        "processor":platform.processor(),"logical_cpu_count":os.cpu_count(),"python":sys.version,"numpy":np.__version__,
        "thread_environment":{key:os.environ.get(key)for key in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS")},
        "source_sha256":before,"port_count":4,"right_hand_sides":3,"warmups_per_path":1,"measured_runs_per_path":5,
        "equivalence_relative_tolerance":1e-12,"cases":{},"production_qualified":False,
        "scope":"Same-process identical network/load/RHS/noise inputs; includes output allocation. Local microbenchmark, not end-to-end solver or cross-machine qualification."}
    for points in (1025,4097):
        inputs=fixture(points)
        original=scalar_reference(*inputs)
        batched=_loaded_response(*inputs)
        metrics=compare(original,batched)
        samples={"scalar":[],"batch128":[]}
        functions={"scalar":scalar_reference,"batch128":_loaded_response}
        for iteration in range(5):
            # Alternate execution order to reduce systematic order bias.
            for label in (("scalar","batch128") if iteration%2==0 else ("batch128","scalar")):
                start=time.perf_counter()
                value=functions[label](*inputs)
                samples[label].append(time.perf_counter()-start)
                compare(original,value)
        medians={key:statistics.median(value)for key,value in samples.items()}
        report["cases"][str(points)]={"frequency_count":points,"equivalence":metrics,"seconds":samples,
            "median_seconds":medians,"observed_median_speedup":medians["scalar"]/medians["batch128"]}
    report["sources_unchanged"]=before==hashes()
    report["status"]="passed" if report["sources_unchanged"] else "source_changed"
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf-8")as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
    print(json.dumps(report,indent=2,allow_nan=False))
    return 0 if report["status"]=="passed" else 1


if __name__=="__main__":
    raise SystemExit(main())
