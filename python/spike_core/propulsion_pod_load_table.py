# SPDX-License-Identifier: Apache-2.0
"""Immutable interpolation of retained CFD load anchors; no extrapolation."""
import copy
import hashlib
import json
import math
import numpy as np
from scipy.interpolate import PchipInterpolator

CONTRACT='spike/propulsion-cfd-load-table/v1'


class CfdLoadTable:
    """Quasi-steady supplied CFD surrogate, with explicit source/evidence identity.

    Construction validates numerical representation, not the truth of imported
    case records. Grid/domain/traction and physical-regime evidence must be
    admitted separately before a demonstration can claim load convergence.
    """
    def __init__(self, table):
        if not isinstance(table,dict) or set(table)!={'contract','anchors','geometry_sha256','physics_sha256','evidence'} or table['contract']!=CONTRACT:
            raise ValueError('Explicit CFD load-table contract required')
        self.table=copy.deepcopy(table)
        for name in ('geometry_sha256','physics_sha256'):
            value=table[name]
            if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
                raise ValueError('Exact geometry/physical-source hashes required')
        rows=table['anchors']
        if not isinstance(rows,list) or not 3<=len(rows)<=101 or not isinstance(table['evidence'],dict):
            raise ValueError('Three to101 retained CFD anchors and explicit evidence required')
        for row in rows:
            if not isinstance(row,dict) or set(row)!={'omega_rad_s','torque_nm','thrust_n','case_sha256'}:
                raise ValueError('Malformed CFD anchor')
            for name in ('omega_rad_s','torque_nm','thrust_n'):
                if type(row[name]) not in (int,float) or not math.isfinite(row[name]):raise ValueError('Finite SI CFD load required')
            if row['omega_rad_s']<0 or row['torque_nm']<0:raise ValueError('Forward passive CFD load required')
            value=row['case_sha256']
            if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):raise ValueError('Exact CFD case hash required')
        speed=np.array([r['omega_rad_s'] for r in rows])
        if np.any(np.diff(speed)<=0):raise ValueError('Strictly increasing CFD anchor speeds required')
        if len({r['case_sha256'] for r in rows})!=len(rows):raise ValueError('Distinct retained CFD cases required')
        self.minimum_speed_rad_s=float(speed[0]);self.maximum_speed_rad_s=float(speed[-1])
        self.torque=PchipInterpolator(speed,[r['torque_nm'] for r in rows],extrapolate=False)
        self.thrust=PchipInterpolator(speed,[r['thrust_n'] for r in rows],extrapolate=False)
        self.source_sha256=hashlib.sha256(json.dumps(table,sort_keys=True,allow_nan=False).encode()).hexdigest()

    def __call__(self, omega):
        if type(omega) not in (int,float) or not math.isfinite(omega) or not self.minimum_speed_rad_s<=omega<=self.maximum_speed_rad_s:
            raise ValueError('Shaft speed outside retained CFD anchor range; extrapolation refused')
        Q=float(self.torque(omega));F=float(self.thrust(omega))
        if not math.isfinite(Q+F) or Q<0:raise ValueError('Interpolated CFD load is not passive/finite')
        return {'torque_nm':Q,'thrust_n':F,'power_w':Q*omega,
                'provider_kind':'retained_CFD_anchor_interpolation',
                'is_blade_resolved_cfd':False,'anchor_sources_are_blade_cfd':True,
                'load_table_sha256':self.source_sha256,
                'scope':'PCHIP quasi-steady interpolation; no new fluid solve, unsteady wake or heat-transfer field is implied.'}
