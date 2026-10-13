# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original prescribed-air example; not package or conjugate-airflow qualification."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from python.spike_core.board_thermal import run_board_thermal
from python.spike_core.contracts import SpiDeR


def run_example():
    design = SpiDeR(design_id='original-local-air', units='mm',
        components=[{'reference': 'U1', 'at': [5, 5]}],
        stackup=[{'name': 'F.Cu', 'type': 'copper', 'thickness': .1},
                 {'name': 'core', 'type': 'dielectric', 'thickness': .8},
                 {'name': 'B.Cu', 'type': 'copper', 'thickness': .1}],
        metadata={'board_bounds_mm': [0, 0, 10, 10]})
    request = {'ambient_temperature_c': 25,
        'board': {'model': 'layered', 'thickness_mm': 1,
            'x_edges_mm': [0, 3, 10], 'y_edges_mm': [0, 10],
            'convection_top_w_m2k': 0, 'convection_bottom_w_m2k': 10,
            'convection_bottom_grid_w_m2k': [10, 20], 'ambient_bottom_grid_c': [25, 30],
            'dielectric_conductivity_w_mk': 1, 'copper_conductivity_w_mk': 100,
            'include_copper': False, 'include_vias': False, 'include_tracks': True,
            'include_pads': True, 'include_zones': True, 'fuzzy_sigma_mm': 0},
        'components': [{'component_ref': 'U1', 'power_w': .01,
            'r_junction_case_k_w': 2, 'r_case_board_k_w': 3,
            'contact_mode': 'square', 'contact_size_mm': 2}]}
    result = run_board_thermal(design, request)
    assert result['status'] == 'completed', result
    assert abs(result['summary']['energy_balance_error_w']) < 1e-10
    return {'scope': 'original_prescribed_surface_air_fixture_not_CFD',
            'request': request, 'result': result}


if __name__ == '__main__':
    print(json.dumps(run_example(), indent=2, allow_nan=False))
