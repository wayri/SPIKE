# SPDX-License-Identifier: Apache-2.0
"""Original SU2 fluid/solid cavity CHT compiler and bounded process adapter."""
from __future__ import annotations

import math
from pathlib import Path
import re
import tempfile
import time

from .sparselizard_process import run_adapter_process
from .su2_airflow import _Cancellation, _rows, _sha256, cavity_config, find_su2


def validate_su2_cht_request(request):
    defaults = {'cells': 16, 'lid_speed': 1.0, 'outer_iterations': 5000, 'timeout_s': 300}
    if not isinstance(request, dict) or set(request) - set(defaults):
        raise ValueError('SU2_CHT_REQUEST: unknown fields or non-object request.')
    data = {**defaults, **request}
    for key, low, high in [('cells', 8, 64), ('outer_iterations', 10, 20000), ('timeout_s', 1, 1800)]:
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f'SU2_CHT_REQUEST: {key} must be an integer in [{low}, {high}].')
    if data['cells'] % 4:
        raise ValueError('SU2_CHT_REQUEST: cells must be a multiple of four.')
    speed = data['lid_speed']
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed) or not 0 <= speed <= 1:
        raise ValueError('SU2_CHT_REQUEST: lid_speed must be finite in [0,1] m/s.')
    return data


def prepare_su2_cht(request):
    settings = validate_su2_cht_request(request)
    return {'settings': settings, 'model_status': 'experimental',
            'geometry': {'fluid_bounds_m': [[0, 0], [1, 1]], 'solid_bounds_m': [[0, -.25], [1, 0]],
                         'cold_solid_bounds_m': [[0, 1], [1, 1.25]],
                         'depth_m': 1, 'interface_y_m': 0, 'cold_interface_y_m': 1},
            'materials': {'fluid': {'density_kg_m3': 1, 'specific_heat_j_kg_k': 1,
                                    'viscosity_pa_s': .01, 'conductivity_w_m_k': .01},
                          'solid': {'density_kg_m3': 1, 'specific_heat_j_kg_k': 1, 'conductivity_w_m_k': .1},
                          'cold_solid': {'density_kg_m3': 1, 'specific_heat_j_kg_k': 1, 'conductivity_w_m_k': .1}},
            'boundaries': {'solid_bottom_temperature_k': 310, 'cold_solid_top_temperature_k': 300,
                           'lid_speed_m_s': settings['lid_speed'], 'sides': 'adiabatic no-slip',
                           'interface': 'matched temperature and normal conductive flux'},
            'limitations': ['Fixed 2D fluid cavity between hot and cold slabs; no arbitrary CAD or PCB geometry.',
                            'Lid velocity is a prescribed tangential fluid-wall condition; solids have no material advection.',
                            'Constant properties; no buoyancy, turbulence, radiation or contact resistance.']}


def su2_cht_capabilities():
    executable = find_su2()
    return {'engine': 'su2', 'available': executable is not None, 'model_status': 'experimental',
            'cases': ['cavity_between_thermal_slabs'], 'heat_transfer': True, 'dimensions': [2],
            'assembly_geometry': False, 'turbulence': False}


def _rectangle(nx, ny, lower_y, height, names):
    node = lambda i, j: j*(nx+1)+i
    lines = ['NDIME= 2', f'NELEM= {nx*ny}']
    for j in range(ny):
        for i in range(nx):
            lines.append(f'9 {node(i,j)} {node(i+1,j)} {node(i+1,j+1)} {node(i,j+1)}')
    lines += [f'NPOIN= {(nx+1)*(ny+1)}']
    lines.extend(f'{i/nx:.17g} {lower_y+height*j/ny:.17g}' for j in range(ny+1) for i in range(nx+1))
    edges = [[(node(i,0), node(i+1,0)) for i in range(nx)],
             [(node(nx,j), node(nx,j+1)) for j in range(ny)],
             [(node(i+1,ny), node(i,ny)) for i in range(nx)],
             [(node(0,j+1), node(0,j)) for j in range(ny)]]
    lines += ['NMARK= 4']
    for name, boundary in zip(names, edges):
        lines += [f'MARKER_TAG= {name}', f'MARKER_ELEMS= {len(boundary)}']
        lines.extend(f'3 {a} {b}' for a, b in boundary)
    return '\n'.join(lines)+'\n'


def compile_su2_cht(request):
    data = validate_su2_cht_request(request)
    n = data['cells']
    mesh = 'NZONE= 3\nIZONE= 1\n' + _rectangle(n,n,0,1,['fluid_join','fluid_east','cold_lid','fluid_west'])
    mesh += 'IZONE= 2\n' + _rectangle(n,n//4,-.25,.25,['hot_base','solid_east','solid_join','solid_west'])
    mesh += 'IZONE= 3\n' + _rectangle(n,n//4,1,.25,['cold_join','cold_east','cold_top','cold_west'])
    fluid = dict(line.split('= ', 1) for line in cavity_config({'reynolds':100,'iterations':100}).splitlines())
    for key in ('MESH_FILENAME','ITER','CONV_FIELD','SURFACE_MOVEMENT','MARKER_MOVING','SURFACE_TRANSLATION_RATE'):
        fluid.pop(key, None)
    fluid.update({'INC_ENERGY_EQUATION':'YES', 'INC_TEMPERATURE_INIT':'300', 'FLUID_MODEL':'CONSTANT_DENSITY',
        'INC_VELOCITY_INIT':f"({data['lid_speed']}, 0.0, 0.0)",
        'SPECIFIC_HEAT_CP':'1.0', 'CONDUCTIVITY_MODEL':'CONSTANT_CONDUCTIVITY', 'THERMAL_CONDUCTIVITY_CONSTANT':'0.01',
        'MARKER_HEATFLUX':'(fluid_east, 0.0, fluid_west, 0.0)',
        'MARKER_CHT_INTERFACE':'(fluid_join, cold_lid)', 'INNER_ITER':'20', 'CONV_FIELD':'(RMS_PRESSURE, RMS_VELOCITY-X, RMS_VELOCITY-Y, RMS_ENTHALPY)',
        'RESTART_FILENAME':'fluid', 'CONV_FILENAME':'fluid_history', 'OUTPUT_WRT_FREQ':str(data['outer_iterations']),
        'VOLUME_OUTPUT':'(COORDINATES, SOLUTION, TEMPERATURE)', 'OUTPUT_FILES':'(RESTART_ASCII, PARAVIEW_ASCII)',
        'VOLUME_FILENAME':'fluid_fields',
        'SCREEN_OUTPUT':'(INNER_ITER, RMS_PRESSURE, RMS_VELOCITY-X, RMS_VELOCITY-Y, RMS_ENTHALPY)'})
    if data['lid_speed']:
        fluid.update({'SURFACE_MOVEMENT':'MOVING_WALL', 'MARKER_MOVING':'(cold_lid)',
                      'SURFACE_TRANSLATION_RATE':f"({data['lid_speed']}, 0.0, 0.0)"})
    solid = {'SOLVER':'HEAT_EQUATION', 'MATERIAL_DENSITY':'1.0', 'SPECIFIC_HEAT_CP':'1.0',
        'THERMAL_CONDUCTIVITY_CONSTANT':'0.1', 'INC_TEMPERATURE_INIT':'300', 'FREESTREAM_TEMPERATURE':'1',
        'MARKER_ISOTHERMAL':'(hot_base, 310.0)',
        'MARKER_HEATFLUX':'(solid_east, 0.0, solid_west, 0.0)', 'MARKER_CHT_INTERFACE':'(solid_join)',
        'INNER_ITER':'20', 'CFL_NUMBER':'10', 'TIME_DISCRE_HEAT':'EULER_IMPLICIT',
        'LINEAR_SOLVER':'FGMRES', 'LINEAR_SOLVER_PREC':'ILU', 'LINEAR_SOLVER_ERROR':'1E-10',
        'LINEAR_SOLVER_ITER':'100', 'CONV_FIELD':'(RMS_TEMPERATURE)', 'CONV_RESIDUAL_MINVAL':'-10',
        'RESTART_FILENAME':'solid', 'CONV_FILENAME':'solid_history', 'HISTORY_OUTPUT':'(ITER, RMS_RES)',
        'SCREEN_OUTPUT':'(INNER_ITER, RMS_TEMPERATURE)', 'OUTPUT_FILES':'(RESTART_ASCII)',
        'VOLUME_OUTPUT':'(COORDINATES, SOLUTION)', 'TABULAR_FORMAT':'CSV',
        'OUTPUT_WRT_FREQ':str(data['outer_iterations'])}
    cold = {**solid,'MARKER_ISOTHERMAL':'(cold_top, 300.0)',
            'MARKER_HEATFLUX':'(cold_east, 0.0, cold_west, 0.0)', 'MARKER_CHT_INTERFACE':'(cold_join)',
            'RESTART_FILENAME':'cold_solid', 'CONV_FILENAME':'cold_solid_history'}
    main = {'SOLVER':'MULTIPHYSICS','CONFIG_LIST':'(fluid.cfg, solid.cfg, cold_solid.cfg)',
        'MARKER_ZONE_INTERFACE':'(fluid_join, solid_join, cold_lid, cold_join)',
        'MARKER_CHT_INTERFACE':'(fluid_join, solid_join, cold_lid, cold_join)',
        'CHT_COUPLING_METHOD':'DIRECT_TEMPERATURE_ROBIN_HEATFLUX', 'MESH_FILENAME':'cht.su2',
        'CONV_FIELD':'(BGS_PRESSURE[0], BGS_VELOCITY-X[0], BGS_VELOCITY-Y[0], BGS_ENTHALPY[0], BGS_TEMPERATURE[1], BGS_TEMPERATURE[2])',
        'MESH_FORMAT':'SU2','OUTER_ITER':str(data['outer_iterations']), 'CONV_RESIDUAL_MINVAL':'-9',
        'CONV_STARTITER':'10', 'SCREEN_WRT_FREQ_OUTER':'100', 'OUTPUT_FILES':'(RESTART_ASCII)',
        'OUTPUT_WRT_FREQ':str(data['outer_iterations']), 'CONV_FILENAME':'coupling_history', 'TABULAR_FORMAT':'CSV'}
    emit = lambda options: '\n'.join(f'{key}= {value}' for key,value in options.items())+'\n'
    return {'cht.su2':mesh, 'cht.cfg':emit(main), 'fluid.cfg':emit(fluid),
            'solid.cfg':emit(solid), 'cold_solid.cfg':emit(cold)}


def _zone_rows(path, nx, ny, lower_y):
    rows = _rows(path)
    count = (nx+1)*(ny+1)
    if len(rows) != count:
        raise ValueError('SU2_CHT_OUTPUT: incomplete zone node coverage.')
    ordered = [None]*count
    for row in rows:
        if not {'PointID','x','y'}.issubset(row):
            raise ValueError('SU2_CHT_OUTPUT: missing identity fields.')
        index = int(row['PointID'])
        if index != row['PointID'] or not 0 <= index < count or ordered[index] is not None:
            raise ValueError('SU2_CHT_OUTPUT: invalid or duplicate node identity.')
        if abs(row['x']-(index%(nx+1))/nx) > 1e-10 or abs(row['y']-lower_y-(index//(nx+1))/nx) > 1e-10:
            raise ValueError('SU2_CHT_OUTPUT: coordinate mismatch.')
        ordered[index] = row
    return ordered


def _vtk_temperature(path, rows):
    if not path.is_file() or path.stat().st_size > 32*1024*1024:
        raise ValueError('SU2_CHT_OUTPUT: missing or oversized temperature field.')
    text = path.read_text(encoding='ascii')
    match = re.search(r'POINTS\s+(\d+)\s+double\s+(.*?)\s+CELLS\b',text,re.S)
    # Bound the temperature block by the next VTK field keyword, not exponent letters.
    scalar = re.search(r'SCALARS Temperature double 1\s+LOOKUP_TABLE default\s+(.+?)(?=\n(?:SCALARS|VECTORS|FIELD)\b|\Z)',text,re.S)
    if not match or not scalar or int(match[1]) != len(rows):
        raise ValueError('SU2_CHT_OUTPUT: missing temperature or VTK identity.')
    coordinates = [float(value) for value in match[2].split()]
    values = [float(value) for value in scalar[1].split()]
    if len(coordinates) != 3*len(rows) or len(values) != len(rows) or not all(math.isfinite(v) for v in values+coordinates):
        raise ValueError('SU2_CHT_OUTPUT: incomplete or non-finite temperature field.')
    if any(abs(coordinates[3*i]-row['x']) > 1e-6 or abs(coordinates[3*i+1]-row['y']) > 1e-6
           or coordinates[3*i+2] != 0 for i,row in enumerate(rows)):
        raise ValueError('SU2_CHT_OUTPUT: temperature mesh differs from restart mesh.')
    return values


def thermal_diagnostics(fluid, solid, cold_solid, n):
    """Independent one-sided Fourier flux estimates; each 2D rate is per metre depth."""
    tf, ts, tc = fluid['temperature_k'], solid['temperature_k'], cold_solid['temperature_k']
    stride = n+1
    fi, si = tf[:stride], ts[-stride:]
    qf = [.01*n*(tf[i]-tf[stride+i]) for i in range(stride)]
    qs = [.1*n*(ts[-2*stride+i]-ts[-stride+i]) for i in range(stride)]
    hot = [.1*n*(ts[i]-ts[stride+i]) for i in range(stride)]
    cold = [.1*n*(tc[-2*stride+i]-tc[-stride+i]) for i in range(stride)]
    qcfluid = [.01*n*(tf[-2*stride+i]-tf[-stride+i]) for i in range(stride)]
    qcsolid = [.1*n*(tc[i]-tc[stride+i]) for i in range(stride)]
    integral = lambda values: (sum(values)-.5*(values[0]+values[-1]))/n
    qin,qout = integral(hot),integral(cold)
    scale = max(abs(qin),abs(qout),1e-12)
    interface = {'x_m':[i/n for i in range(stride)], 'fluid_temperature_k':fi,'solid_temperature_k':si,
                 'fluid_flux_w_m2':qf,'solid_flux_w_m2':qs}
    cold_interface = {'x_m':[i/n for i in range(stride)], 'fluid_temperature_k':tf[-stride:],
                      'solid_temperature_k':tc[:stride], 'fluid_flux_w_m2':qcfluid,'solid_flux_w_m2':qcsolid}
    diagnostics = {'interface_temperature_jump_k':max(abs(a-b) for a,b in zip(fi,si)),
        'interface_flux_relative_error':abs(integral(qf)-integral(qs))/scale,
        'global_energy_relative_error':abs(qin-qout)/scale, 'heat_input_w_per_m':qin,
        'heat_output_w_per_m':qout, 'fluid_interface_heat_w_per_m':integral(qf),
        'solid_interface_heat_w_per_m':integral(qs), 'flux_estimator':'first-order one-sided Fourier gradients, trapezoidal integration',
        'temperature_min_k':min(tf+ts+tc), 'temperature_max_k':max(tf+ts+tc)}
    diagnostics['cold_boundary_max_error_k'] = max(abs(t-300) for t in tc[-stride:])
    diagnostics['cold_interface_temperature_jump_k'] = max(abs(a-b) for a,b in zip(tf[-stride:],tc[:stride]))
    diagnostics['cold_interface_flux_relative_error'] = abs(integral(qcfluid)-integral(qcsolid))/scale
    return interface,cold_interface,diagnostics


def parse_su2_cht(directory, request):
    directory, data = Path(directory), validate_su2_cht_request(request)
    n = data['cells']
    fluid_rows = _zone_rows(directory/'fluid_0.csv',n,n,0)
    solid_rows = _zone_rows(directory/'solid_1.csv',n,n//4,-.25)
    cold_rows = _zone_rows(directory/'cold_solid_2.csv',n,n//4,1)
    try:
        fluid = {key:[row[column] for row in fluid_rows] for key,column in
                 [('x_m','x'),('y_m','y'),('u_m_s','Velocity_x'),('v_m_s','Velocity_y')]}
        fluid['temperature_k'] = _vtk_temperature(directory/'fluid_fields_0.vtk',fluid_rows)
        solid = {key:[row[column] for row in solid_rows] for key,column in
                 [('x_m','x'),('y_m','y'),('temperature_k','Temperature')]}
        cold_solid = {key:[row[column] for row in cold_rows] for key,column in
                      [('x_m','x'),('y_m','y'),('temperature_k','Temperature')]}
    except KeyError as exc:
        raise ValueError('SU2_CHT_OUTPUT: required zone field missing.') from exc
    if min(fluid['temperature_k']+solid['temperature_k']+cold_solid['temperature_k']) <= 0:
        raise ValueError('SU2_CHT_OUTPUT: nonphysical absolute temperature.')
    if any(abs(value-310) > 1e-4 for value in solid['temperature_k'][:n+1]):
        raise ValueError('SU2_CHT_OUTPUT: solid temperature units or hot boundary mismatch.')
    history = _rows(directory/'cht.csv')
    keys = ['bgs[P][0]','bgs[U][0]','bgs[V][0]','bgs[h][0]','bgs[T][1]','bgs[T][2]']
    if not history or not all(key in history[-1] for key in keys):
        raise ValueError('SU2_CHT_OUTPUT: missing coupled thermal residuals.')
    residuals = {key:history[-1][key] for key in keys}
    interface,cold_interface,diagnostics = thermal_diagnostics(fluid,solid,cold_solid,n)
    diagnostics['maximum_fluid_speed_m_s'] = max(math.hypot(u,v) for u,v in zip(fluid['u_m_s'],fluid['v_m_s']))
    if not all(math.isfinite(value) for value in diagnostics.values() if isinstance(value,(int,float))):
        raise ValueError('SU2_CHT_OUTPUT: non-finite thermal diagnostics.')
    violations = []
    if diagnostics['cold_boundary_max_error_k'] > 1e-4:
        violations.append('Cold solid boundary exceeds the 0.0001 K temperature tolerance.')
    if diagnostics['temperature_min_k'] < 299.999 or diagnostics['temperature_max_k'] > 310.001:
        violations.append('Passive temperature field exceeds the 300..310 K range by more than 0.001 K.')
    for prefix in ('','cold_'):
        if diagnostics[prefix+'interface_temperature_jump_k'] > .001:
            violations.append(prefix+'interface temperature continuity exceeds 0.001 K.')
        if diagnostics[prefix+'interface_flux_relative_error'] > .001:
            violations.append(prefix+'interface heat rate mismatch exceeds 0.1%.')
    if diagnostics['global_energy_relative_error'] > .02:
        violations.append('Global heat balance mismatch exceeds 2%.')
    return {'zones':{'fluid':fluid,'solid':solid,'cold_solid':cold_solid},'interface':interface,
            'cold_interface':cold_interface,'diagnostics':diagnostics,
            'validation':{'passed':not violations,'violations':violations},
            'convergence':{'converged':max(residuals.values()) <= -9,'final_log10_residuals':residuals,
                           'history_rows':len(history)}}


def run_su2_cht(request, *, executable=None, output_root=None, cancel_check=None):
    data = validate_su2_cht_request(request)
    program = find_su2(executable)
    if program is None:
        raise ValueError('SU2_UNAVAILABLE: configure a trusted SU2 installation.')
    if cancel_check and cancel_check():
        raise RuntimeError('SU2_CHT_CANCELLED: cancelled before launch.')
    root = Path(output_root) if output_root else Path(tempfile.gettempdir())/'spike-su2-cht'
    root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='cht-',dir=root)).resolve()
    compiled = compile_su2_cht(data)
    for name, content in compiled.items():
        (directory/name).write_text(content,encoding='ascii')
    hashes = {name:_sha256(directory/name) for name in compiled}
    executable_hash = _sha256(program)
    started = time.monotonic()
    process = run_adapter_process([str(program),'cht.cfg','-t','1'],cwd=directory,
        timeout_s=data['timeout_s'],memory_limit_mb=2048,output_limit_bytes=32*1024*1024,
        stream_limit_bytes=8*1024*1024,cancellation_event=_Cancellation(cancel_check))
    for name in ('stdout','stderr'):
        (directory/(name+'.log')).write_text(process[name],encoding='utf-8')
    if process['return_code']:
        raise RuntimeError(f"SU2_CHT_FAILED: exit {process['return_code']} in {directory}: " + process['stderr'][-2000:])
    if executable_hash != _sha256(program) or any(value != _sha256(directory/name) for name,value in hashes.items()):
        raise RuntimeError('SU2_CHT_INPUT_CHANGED: inputs or executable changed during solve.')
    parsed = parse_su2_cht(directory,data)
    version = re.search(r'\bRelease\s+(\d+\.\d+\.\d+)\b',process['stdout'])
    return {'contract':'spike/su2-cht-result/v1','engine':'su2','model_status':'experimental',
            'status':('completed' if parsed['validation']['passed'] else 'failed_validation')
                     if parsed['convergence']['converged'] else 'failed_to_converge',
            'request':data, **parsed, 'case':prepare_su2_cht(data),
            'limitations':prepare_su2_cht(data)['limitations'],
            'provenance':{'run_directory':str(directory),'elapsed_s':time.monotonic()-started,
                'input_sha256':hashes,'executable_sha256':executable_hash,'version':version[1] if version else 'unreported',
                'output_sha256':{name:_sha256(directory/name) for name in ['cht.csv','fluid_0.csv','solid_1.csv','cold_solid_2.csv','fluid_fields_0.vtk']},
                'clean_room':True,'threads':1}}
