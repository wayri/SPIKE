# SPDX-License-Identifier: Apache-2.0
"""Run the real coupled worker from SPIKE's Python Workspace, not replay data."""
import json
import math
from pathlib import Path
import spike

REQUEST_FILE = Path('worker-params.json')
RESULT_FILE = None  # Optional NEW file; existing data is never overwritten.

data = REQUEST_FILE.read_bytes()
if len(data) > 4*1024*1024:
    raise ValueError('Request exceeds 4 MiB')
params = json.loads(data)
if not isinstance(params, dict) or set(params) != {'request'}:
    raise ValueError('Expected one reviewed request object')
if RESULT_FILE is not None and Path(RESULT_FILE).exists():
    raise ValueError('RESULT_FILE already exists; choose a new output file')

result = spike.call('run_propulsion_pod', params)
if result.get('contract') != 'spike/propulsion-pod-result/v1' or result.get('status') != 'completed':
    raise ValueError('No completed coupled result returned')
if RESULT_FILE is not None:
    with Path(RESULT_FILE).open('x', encoding='utf-8') as stream:
        json.dump(result, stream, allow_nan=False)

history = result['history']
times = [row['time_s'] for row in history]
provenance = ('Actual compiled SPIKES C + reciprocal linear P1 FEM + hover BEM; '
              'synthetic two-phase reference, not VESC firmware or resolved blade CFD; '
              'request '+result['request_sha256'])

def plot(title, series, unit):
    spike.publish_plot(title, times, [{'name': s['name'], 'values': s['y']} for s in series], x_label='Time', y_label=title,
                             x_unit='s', y_unit=unit, provenance=provenance)

plot('Coupled shaft speed', [{'name': 'computed speed', 'y': [r['speed_rad_s'] for r in history]},
    {'name': 'controller target', 'y': [params['request']['transient']['target_speed_rad_s']]*len(times)}], 'rad/s')
plot('Computed winding currents', [{'name': 'phase A', 'y': [r['currents_a'][0] for r in history]},
                                  {'name': 'phase B', 'y': [r['currents_a'][1] for r in history]}], 'A')
plot('Field and propeller torque', [{'name': 'FEM torque', 'y': [r['torque_n_m'] for r in history]},
                                  {'name': 'BEM reaction', 'y': [r['propeller_torque_n_m'] for r in history]}], 'N m')
plot('Computed propeller thrust', [{'name': 'thrust', 'y': [r['thrust_n'] for r in history]}], 'N')
plot('Linked winding flux', [{'name': 'phase A', 'y': [r['flux_linkage_wb_turn'][0] for r in history]},
                            {'name': 'phase B', 'y': [r['flux_linkage_wb_turn'][1] for r in history]}], 'Wb turn')

mesh, frame = result['field_mesh'], result['frames'][-1]
samples = []
for triangle, field in zip(mesh['triangles'], frame['element_b_t']):
    u = sum(mesh['nodes_m'][node][0] for node in triangle)/3
    v = sum(mesh['nodes_m'][node][1] for node in triangle)/3
    # Benchmark plane is y/z, shaft +x, motor origin z=0.2 m.
    samples.append({'x': 0., 'y': u, 'z': .2+v, 'vector': [0., field[0], field[1]]})
spike.publish_spatial('Actual final P1 motor B field', samples, quantity='magnetic flux density',
                            unit='T', provenance=provenance)
flow = []
for annulus in frame['radial_airflow']:
    radius = annulus['radius_m']
    for j in range(16):
        angle = 2*math.pi*j/16
        flow.append({'x': .085, 'y': radius*math.cos(angle), 'z': .2+radius*math.sin(angle),
                     'vector': [annulus['disk_axial_velocity_m_s'], 0., 0.]})
spike.publish_spatial('Computed BEM disk inflow - not CFD wake', flow,
                            quantity='disk axial induced velocity', unit='m/s', provenance=provenance)
spike.publish_table('Coupled energy ledger', ['Quantity', 'Value', 'Unit'],
    [[name, value, 'J'] for name, value in result['energy'].items()
     if name.endswith('_j') and isinstance(value, (int, float))], provenance=provenance)
print('SPIKE_COUPLED_POD_SUMMARY='+json.dumps({'status': result['status'], 'accepted_steps': result['accepted_steps'],
    'controller_ticks': result['controller_ticks'], 'field_frames': len(result['frames']),
    'final_speed_rad_s': history[-1]['speed_rad_s'], 'final_thrust_n': history[-1]['thrust_n'],
    'energy_defect_j': result['energy']['defect_j'], 'request_sha256': result['request_sha256']}))
