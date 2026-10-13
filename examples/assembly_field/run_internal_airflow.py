# SPDX-License-Identifier: Apache-2.0
"""Original independent laminar channel screening example; no board CHT claim.

From repository root: python examples/assembly_field/run_internal_airflow.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from python.spike_core.automation import SpikeAutomation

request = {
    'contract': 'spike/internal-channel-airflow-request/v1',
    'geometry': {'length_m': .12, 'gap_m': .008, 'span_m': .04},
    'fluid': {'density_kg_m3': 1.184, 'specific_heat_j_kgk': 1007.,
              'thermal_conductivity_w_mk': .0262, 'dynamic_viscosity_pa_s': 1.85e-5},
    'operating': {'mean_velocity_m_s': .35, 'inlet_temperature_k': 298.15,
                  'lower_wall_heat_flux_w_m2': 50., 'upper_wall_heat_flux_w_m2': 0.},
    'mesh': {'axial_cells': 64, 'transverse_cells': 17},
}
if __name__ == '__main__':
    print(json.dumps(SpikeAutomation().call('run_internal_airflow', {'request': request}), indent=2))
