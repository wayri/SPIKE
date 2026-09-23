# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Trusted exploratory PEC Yagi model; not a replica of the NBS feed/range."""
import json
import math
from pathlib import Path
import sys
import numpy as np
from CSXCAD import ContinuousStructure
from openEMS import openEMS

root = Path(sys.argv[1])
h = float(sys.argv[2])
if h not in (10.0, 15.0, 20.0):
    raise ValueError('Unsupported bounded mesh level')
f = 400e6
lam = 299792458.0 / f * 1000
radius = .0085 * lam / 2
gap = 4.0
csx = ContinuousStructure()
fdtd = openEMS(NrTS=12000, EndCriteria=1e-5)
fdtd.SetCSX(csx)
fdtd.SetGaussExcite(f, 200e6)
fdtd.SetBoundaryCond(['PML_8'] * 6)
metal = csx.AddMetal('pec_elements')
# NBS Table 1 parasitics; assumed straight driven wire replaces folded feed.
for x, length in [(-.2*lam, .482*lam), (.2*lam, .424*lam)]:
    metal.AddCylinder(start=[x,-length/2,0], stop=[x,length/2,0], radius=radius, priority=10)
for a,b in [(-.5*lam/2,-gap/2),(gap/2,.5*lam/2)]:
    metal.AddCylinder(start=[0,a,0], stop=[0,b,0], radius=radius, priority=10)
grid = csx.GetGrid()
grid.SetDeltaUnit(.001)
grid.AddLine('x', [-.8*lam,.8*lam,-.2*lam-radius,-.2*lam,-.2*lam+radius,-radius,0,radius,.2*lam-radius,.2*lam,.2*lam+radius])
grid.AddLine('y', [-.8*lam,.8*lam,-.25*lam,-.241*lam,-.212*lam,-gap/2,gap/2,.212*lam,.241*lam,.25*lam])
grid.AddLine('z', [-.6*lam,-radius,0,radius,.6*lam])
grid.SmoothMeshLines('all', h, 1.4)
port = fdtd.AddLumpedPort(1, 50, [0,-gap/2,0], [0,gap/2,0], 'y', 1, priority=20, edges2grid='all')
counts = [len(grid.GetLines(axis))-1 for axis in 'xyz']
if math.prod(counts)>3000000:
    raise ValueError('Mesh exceeds three million cell budget')
nf = fdtd.CreateNF2FFBox()
csx.Write2XML(str(root/'geometry.xml'))
fdtd.Run(str(root/'simulation'), cleanup=False, numThreads=2, verbose=0)
port.CalcPort(str(root/'simulation'), [f])
ff = nf.CalcNF2FF(str(root/'simulation'), [f], [90], [0], radius=1, center=[0,0,0], read_cached=False, verbose=0)
prad = float(np.asarray(ff.Prad).flat[0])
flux = float(np.asarray(ff.P_rad).flat[0])
directivity = 4*math.pi*flux/prad
accepted = float((.5*np.real(port.uf_tot*np.conj(port.if_tot)))[0])
gain = 4*math.pi*flux/accepted
incident = float((.5*np.abs(port.uf_inc)**2/50)[0])
if not all(math.isfinite(v) and v>0 for v in (prad,flux,directivity,accepted,gain)):
    raise ValueError('Nonpositive/nonfinite power normalization')
result = dict(status='completed', frequency_hz=f, mesh_max_mm=h, mesh_cells=math.prod(counts), mesh_dimensions=counts,
              timestep_budget=12000, temporal_decay_check='host_log_admission_required',
              forward_directivity_dbi=10*math.log10(directivity), forward_accepted_power_gain_dbi=10*math.log10(gain),
              power_normalization='one_watt_incident', radiated_power_w=prad/incident,
              accepted_power_w=accepted/incident, radiated_to_accepted_ratio=prad/accepted,
              measured_gain_dbd=7.1, source_dbd_to_dbi_db=2.16, measured_gain_dbi=9.26,
              gain_discrepancy_db=10*math.log10(gain)-9.26, measured_reported_accuracy_db=.5,
              qualification='exploratory_model_mismatch', geometry_matched=False, production_qualified=False,
              model_assumptions=['PEC replaces aluminum', 'straight half-wave wire replaces folded dipole and tuner',
                                 'free space replaces ground range at three wavelengths', 'nonconducting boom omitted'])
(root/'solver-result.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
