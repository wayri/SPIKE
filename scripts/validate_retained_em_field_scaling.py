# SPDX-License-Identifier: Apache-2.0
"""Empirical public-API DFT convention and independent air-gap field check."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.interpolate import RegularGridInterpolator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from extensions.openems_suite.runtime import openems_install_root, openems_python
from scripts.validate_retained_assembly_em import static_reference

EXTRACT = r'''
import json,sys
from pathlib import Path
import h5py,numpy as np
from openEMS.utilities import DFT_time2freq
root=Path(sys.argv[1]); frequency=5e8
u=np.loadtxt(root/'simulation/port_ut_1',comments='%')
i=np.loadtxt(root/'simulation/port_it_1',comments='%')
uf=DFT_time2freq(u[:,0],u[:,1],[frequency])[0]
if_=DFT_time2freq(i[:,0],i[:,1],[frequency])[0]
inc=(uf+50*if_)/2
def pair(z):return [float(z.real),float(z.imag)]
with h5py.File(root/'simulation/electric-field.h5') as data:
    axes=[data['Mesh/'+a][...] for a in 'xyz']
    e=data['FieldData/FD/f0_real'][...]+1j*data['FieldData/FD/f0_imag'][...]
    samples=[]
    for iz,z in enumerate(axes[2]):
      for iy,y in enumerate(axes[1]):
        for ix,x in enumerate(axes[0]):
          if .002<=x<=.008 and .002<=y<=.008 and .0015<=z<=.0035:
            samples.append({'xyz_m':[float(x),float(y),float(z)],
                            'raw':[pair(v) for v in e[:,iz,iy,ix]],
                            'per_total_volt':[pair(v/uf) for v in e[:,iz,iy,ix]],
                            'per_incident_volt':[pair(v/inc) for v in e[:,iz,iy,ix]]})
t=np.arange(5)*.25
preview_checks={}
bound=root/'bound-result.json'
if bound.exists():
 result=json.loads(bound.read_text())
 for name,preview in result['field_capture'].get('preview',{}).get('datasets',{}).items():
  with h5py.File(root/'simulation'/(name+'.h5')) as data:
   raw=data['FieldData/FD/f0_real'][...]+1j*data['FieldData/FD/f0_imag'][...]
   axes=[data['Mesh/'+a][...] for a in 'xyz']
   errors=[]
   for position,vector in zip(preview['positions_m'],preview['vectors']):
    indexes=[int(np.argmin(abs(axis-coordinate))) for axis,coordinate in zip(axes,position)]
    assert all(float(axis[index])==coordinate for axis,index,coordinate in zip(axes,indexes,position))
    expected=raw[:,indexes[2],indexes[1],indexes[0]]/inc
    vector=np.asarray(vector); actual=vector[:,0]+1j*vector[:,1]
    errors.append(float(np.linalg.norm(actual-expected)/max(np.linalg.norm(expected),1e-30)))
   preview_checks[name]={'sample_count':len(errors),'maximum_relative_scaling_error':max(errors)}
   assert max(errors)<2e-6
print(json.dumps({'pulse_constant_dt_quarter':pair(DFT_time2freq(t,np.ones(5),[0.])[0]),
 'pulse_constant_dt_half':pair(DFT_time2freq(t*2,np.ones(5),[0.])[0]),
 'periodic_constant':pair(DFT_time2freq(t,np.ones(5),[0.],signal_type='periodic')[0]),
 'voltage_dft':pair(uf),'incident_voltage_dft':pair(inc),
 's11_from_public_dft':pair((uf-50*if_)/(uf+50*if_)),
 'legacy_hdf5_axis_order':'component,z,y,x','preview_checks':preview_checks,'samples':samples}))
'''


def correlate(directory):
    environment = dict(os.environ, OPENEMS_INSTALL_PATH=openems_install_root())
    extracted = subprocess.run([openems_python(), '-c', EXTRACT, str(directory)],
        env=environment, capture_output=True, text=True, check=True, timeout=30)
    report = json.loads(extracted.stdout)
    reference, potential = static_reference(6, return_potential=True)
    spacing = reference['spacing_m']
    coordinates = np.linspace(-.002, .012, potential.shape[0])
    electric = [-v for v in np.gradient(potential, spacing)]
    positions = np.array([s['xyz_m'] for s in report['samples']])
    expected = np.array([RegularGridInterpolator((coordinates,)*3, v)(positions) for v in electric]).T
    observed = np.array([s['per_total_volt'] for s in report['samples']])
    observed = observed[:,:,0]+1j*observed[:,:,1]
    errors = np.linalg.norm(observed-expected, axis=1)/np.linalg.norm(expected, axis=1)
    report.update(reference_capacitance_f=reference['capacitance_f'],
        reference_electric_v_m_at_one_total_volt=expected.tolist(),
        per_point_relative_complex_vector_error=errors.tolist(),
        maximum_relative_complex_vector_error=float(np.max(errors)),
        rms_relative_complex_vector_error=float(np.sqrt(np.mean(errors**2))),
        maximum_relative_complex_vector_error_limit=.05,
        field_reference_check_passed=bool(np.max(errors)<=.05),
        frequency_hz=5e8,
        model='Quasistatic finite cage; compare air-gap samples at least 0.5 mm from plates.')
    target = directory/'field-reference.json'
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    if not report['field_reference_check_passed']:
        raise AssertionError('Air-gap field exceeds declared 5 percent quasistatic reference tolerance')
    print(json.dumps({k:v for k,v in report.items() if k not in (
        'samples', 'reference_electric_v_m_at_one_total_volt','per_point_relative_complex_vector_error')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    correlate(parser.parse_args().directory)
