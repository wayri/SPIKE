# SPDX-License-Identifier: Apache-2.0
"""Original bounded SU2 process adapter for a two-dimensional cavity reference.

No SU2 source, examples, meshes or reference data are included. See
docs/SU2_AIRFLOW.md for public interface sources and qualification limits.
"""
from __future__ import annotations

import csv
import hashlib
import io
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import time

from .sparselizard_process import run_adapter_process

ROOT = Path(__file__).resolve().parents[2]
MAX_OUTPUT = 32 * 1024 * 1024


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def find_su2(executable=None):
    """Resolve a trusted host selection; request JSON cannot select programs."""
    if executable is not None:
        candidates = [Path(executable)]
    elif os.environ.get('SPIKE_SU2_CFD'):
        candidates = [Path(os.environ['SPIKE_SU2_CFD'])]
    else:
        name = 'SU2_CFD.exe' if os.name == 'nt' else 'SU2_CFD'
        candidates = []
        if os.environ.get('SU2_RUN'):
            candidates.append(Path(os.environ['SU2_RUN']) / name)
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
        candidates.extend(sorted((ROOT / 'artifacts/su2-runtime').glob('v*/bin/**/' + name), reverse=True))
    return next((path.resolve() for path in candidates if path.is_file()), None)


def su2_airflow_capabilities():
    executable = find_su2()
    return {'engine': 'su2', 'available': executable is not None,
            'executable': str(executable) if executable else None,
            'validation_state': 'experimental', 'cases': ['lid_driven_cavity'],
            'dimensions': [2], 'turbulence': False, 'heat_transfer': False,
            'limitations': ['Cavity reference only; no assembly geometry or conjugate heat transfer.',
                            'A separate SU2 runtime is required; it is not bundled.']}


def validate_su2_request(request):
    if not isinstance(request, dict):
        raise ValueError('SU2_REQUEST: request must be an object.')
    allowed = {'case', 'cells', 'reynolds', 'iterations', 'timeout_s'}
    if set(request) - allowed:
        raise ValueError('SU2_REQUEST: unknown fields: ' + ', '.join(sorted(set(request) - allowed)))
    if request.get('case', 'lid_driven_cavity') != 'lid_driven_cavity':
        raise ValueError('SU2_UNSUPPORTED: only lid_driven_cavity is admitted.')
    data = {'case': 'lid_driven_cavity'}
    for key, default, low, high in [('cells', 32, 8, 128), ('iterations', 10000, 10, 100000),
                                   ('timeout_s', 300, 1, 1800)]:
        value = request.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f'SU2_REQUEST: {key} must be an integer in [{low}, {high}].')
        data[key] = value
    if data['cells'] % 2:
        raise ValueError('SU2_REQUEST: cells must be even for exact centerline sampling.')
    value = request.get('reynolds', 100.0)
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 1 <= value <= 400:
        raise ValueError('SU2_REQUEST: reynolds must be finite in [1, 400].')
    data['reynolds'] = float(value)
    return data


def cavity_mesh(cells):
    """Enumerate CCW quads from original Cartesian indexing, in SI metres."""
    n = cells
    node = lambda i, j: j * (n + 1) + i
    lines = ['NDIME= 2', f'NELEM= {n*n}']
    for j in range(n):
        for i in range(n):
            lines.append(f'9 {node(i,j)} {node(i+1,j)} {node(i+1,j+1)} {node(i,j+1)}')
    lines.append(f'NPOIN= {(n+1)**2}')
    lines.extend(f'{i/n:.17g} {j/n:.17g}' for j in range(n+1) for i in range(n+1))
    boundaries = {
        'floor': [(node(i, 0), node(i+1, 0)) for i in range(n)],
        'east': [(node(n, j), node(n, j+1)) for j in range(n)],
        'lid': [(node(i+1, n), node(i, n)) for i in range(n)],
        'west': [(node(0, j+1), node(0, j)) for j in range(n)],
    }
    lines.append('NMARK= 4')
    for name, edges in boundaries.items():
        lines.extend([f'MARKER_TAG= {name}', f'MARKER_ELEMS= {n}'])
        lines.extend(f'3 {a} {b}' for a, b in edges)
    return '\n'.join(lines) + '\n'


def cavity_config(data):
    """Translate the admitted physical case to documented SU2 option names."""
    options = {
        'SOLVER': 'INC_NAVIER_STOKES', 'KIND_TURB_MODEL': 'NONE',
        'INC_DENSITY_MODEL': 'CONSTANT', 'INC_ENERGY_EQUATION': 'NO',
        'INC_DENSITY_INIT': '1.0', 'INC_VELOCITY_INIT': '(1.0, 0.0, 0.0)',
        'INC_NONDIM': 'DIMENSIONAL', 'VISCOSITY_MODEL': 'CONSTANT_VISCOSITY',
        'MU_CONSTANT': format(1 / data['reynolds'], '.17g'),
        'MARKER_HEATFLUX': '(floor, 0.0, east, 0.0, lid, 0.0, west, 0.0)',
        'SURFACE_MOVEMENT': 'MOVING_WALL', 'MARKER_MOVING': '(lid)',
        'SURFACE_TRANSLATION_RATE': '(1.0, 0.0, 0.0)',
        'MESH_FILENAME': 'cavity.su2', 'MESH_FORMAT': 'SU2',
        'CONV_NUM_METHOD_FLOW': 'FDS', 'MUSCL_FLOW': 'YES', 'SLOPE_LIMITER_FLOW': 'NONE',
        'NUM_METHOD_GRAD': 'GREEN_GAUSS', 'TIME_DISCRE_FLOW': 'EULER_IMPLICIT',
        'CFL_NUMBER': '10.0', 'LINEAR_SOLVER': 'FGMRES', 'LINEAR_SOLVER_PREC': 'ILU',
        'LINEAR_SOLVER_ERROR': '1E-8', 'LINEAR_SOLVER_ITER': '40',
        'ITER': str(data['iterations']), 'CONV_FIELD': '(RMS_PRESSURE, RMS_VELOCITY-X, RMS_VELOCITY-Y)',
        'CONV_RESIDUAL_MINVAL': '-9', 'CONV_STARTITER': '20',
        'SCREEN_OUTPUT': '(INNER_ITER, RMS_PRESSURE, RMS_VELOCITY-X, RMS_VELOCITY-Y)',
        'SCREEN_WRT_FREQ_INNER': '100', 'HISTORY_OUTPUT': '(ITER, RMS_RES)',
        'CONV_FILENAME': 'history', 'TABULAR_FORMAT': 'CSV',
        'OUTPUT_FILES': '(RESTART_ASCII)', 'RESTART_FILENAME': 'solution',
        'OUTPUT_WRT_FREQ': str(data['iterations']), 'VOLUME_OUTPUT': '(COORDINATES, SOLUTION)',
    }
    return '\n'.join(f'{key}= {value}' for key, value in options.items()) + '\n'


def _rows(path):
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_OUTPUT:
        raise ValueError('SU2_OUTPUT: missing, empty or oversized ' + path.name)
    text = path.read_text(encoding='utf-8-sig')
    reader = csv.reader(io.StringIO(text), skipinitialspace=True)
    header = [item.strip().strip('"') for item in next(reader)]
    if len(set(header)) != len(header):
        raise ValueError('SU2_OUTPUT: duplicate CSV headers.')
    result = []
    for row in reader:
        if not row:
            continue
        # SU2 appends named restart metadata after the nodal CSV table.
        if len(row) == 1 and '=' in row[0]:
            break
        if len(row) != len(header):
            raise ValueError('SU2_OUTPUT: ragged CSV row.')
        values = [float(value) for value in row]
        if not all(math.isfinite(value) for value in values):
            raise ValueError('SU2_OUTPUT: non-finite CSV value.')
        result.append(dict(zip(header, values)))
    return result


def parse_su2_cavity(directory, cells):
    rows = _rows(Path(directory) / 'solution.csv')
    required = {'PointID', 'x', 'y', 'Pressure', 'Velocity_x', 'Velocity_y'}
    if len(rows) != (cells+1)**2 or not rows or not required.issubset(rows[0]):
        raise ValueError('SU2_OUTPUT: incomplete nodal field.')
    ordered = [None] * len(rows)
    for row in rows:
        index = int(row['PointID'])
        if row['PointID'] != index or not 0 <= index < len(rows) or ordered[index] is not None:
            raise ValueError('SU2_OUTPUT: duplicate or invalid node ID.')
        x, y = (index % (cells+1)) / cells, (index // (cells+1)) / cells
        if not math.isclose(row['x'], x, abs_tol=1e-10) or not math.isclose(row['y'], y, abs_tol=1e-10):
            raise ValueError('SU2_OUTPUT: nodal coordinates do not match the input mesh.')
        ordered[index] = row
    history = _rows(Path(directory) / 'history.csv')
    residual_keys = ['rms[P]', 'rms[U]', 'rms[V]']
    if not history or not all(key in history[-1] for key in residual_keys):
        raise ValueError('SU2_OUTPUT: missing convergence residuals.')
    residuals = {key: history[-1][key] for key in residual_keys}
    middle = cells // 2
    return {'fields': {key: [row[column] for row in ordered] for key, column in
                      [('x', 'x'), ('y', 'y'), ('u', 'Velocity_x'), ('v', 'Velocity_y'), ('p', 'Pressure')]},
            'centerlines': {'coordinate': [i/cells for i in range(cells+1)],
                           'u': [ordered[j*(cells+1)+middle]['Velocity_x'] for j in range(cells+1)],
                           'v': [ordered[middle*(cells+1)+i]['Velocity_y'] for i in range(cells+1)]},
            'convergence': {'converged': max(residuals.values()) <= -9,
                            'final_log10_residuals': residuals, 'history_rows': len(history)}}


class _Cancellation:
    def __init__(self, callback):
        self.callback = callback

    def is_set(self):
        return bool(self.callback and self.callback())


def run_su2_airflow(request, *, executable=None, output_root=None, cancel_check=None):
    """Run a trusted SU2 installation in a fresh retained directory, without a shell."""
    data = validate_su2_request(request)
    program = find_su2(executable)
    if program is None:
        raise ValueError('SU2_UNAVAILABLE: install SU2 and configure SPIKE_SU2_CFD or SU2_RUN.')
    if cancel_check and cancel_check():
        raise RuntimeError('SU2_CANCELLED: cancelled before launch.')
    root = Path(output_root) if output_root else Path(tempfile.gettempdir()) / 'spike-su2'
    root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='cavity-', dir=root)).resolve()
    mesh, config = directory / 'cavity.su2', directory / 'cavity.cfg'
    mesh.write_text(cavity_mesh(data['cells']), encoding='ascii')
    config.write_text(cavity_config(data), encoding='ascii')
    input_hashes = {'executable_sha256': _sha256(program), 'mesh_sha256': _sha256(mesh),
                    'config_sha256': _sha256(config)}
    started = time.monotonic()
    process = run_adapter_process([str(program), 'cavity.cfg', '-t', '1'], cwd=directory,
        timeout_s=data['timeout_s'], memory_limit_mb=2048, output_limit_bytes=MAX_OUTPUT,
        stream_limit_bytes=8*1024*1024, cancellation_event=_Cancellation(cancel_check))
    (directory / 'stdout.log').write_text(process['stdout'], encoding='utf-8')
    (directory / 'stderr.log').write_text(process['stderr'], encoding='utf-8')
    if process['return_code'] != 0:
        raise RuntimeError(f"SU2_FAILED: exit {process['return_code']}; see {directory}; " + process['stderr'][-1500:])
    if any(_sha256(path) != input_hashes[key] for key, path in
           [('executable_sha256', program), ('mesh_sha256', mesh), ('config_sha256', config)]):
        raise RuntimeError('SU2_INPUT_CHANGED: executable or input changed during execution.')
    parsed = parse_su2_cavity(directory, data['cells'])
    version = re.search(r'\bRelease\s+(\d+\.\d+\.\d+)\b', process['stdout'])
    return {'contract': 'spike/su2-cavity-result/v1', 'engine': 'su2',
            'status': 'completed' if parsed['convergence']['converged'] else 'failed_to_converge',
            'validation_state': 'experimental', 'request': data, **parsed,
            'units': {'x': 'm', 'y': 'm', 'u': 'm/s', 'v': 'm/s', 'p': 'Pa'},
            'provenance': {'executable': str(program), **input_hashes,
                           'version': version.group(1) if version else 'unreported',
                           'solution_sha256': _sha256(directory / 'solution.csv'),
                           'history_sha256': _sha256(directory / 'history.csv'),
                           'run_directory': str(directory), 'elapsed_s': time.monotonic()-started,
                           'threads': 1, 'clean_room': True}}
