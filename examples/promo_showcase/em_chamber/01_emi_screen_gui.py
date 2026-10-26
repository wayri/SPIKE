# SPDX-License-Identifier: Apache-2.0
import spike
import json
SETUP = {'contract': 'spike/emi-setup/v1', 'selected_nets': ['RF'], 'return_nets': ['GND'], 'requested_analyses': ['conducted_screening', 'near_field', 'far_field'], 'frequency': {'start_hz': 3000000000, 'stop_hz': 4200000000, 'points': 7}, 'environment': {'kind': 'free_space'}, 'mesh': {'resolution_mm': 2.0, 'padding_cells': 8}, 'max_solver_time_s': 3600, 'excitation': {'mode': 'explicit_ports', 'ports': [{'id': 'P1', 'name': 'RF-to-GND teaching port', 'start': [105.0, 115.0, 0.0], 'stop': [105.0, 115.0, -1.6], 'direction': 'z', 'impedance_ohm': 50.0, 'excite': True}]}, 'net_metrics': [{'net': 'RF', 'source': 'illustrative-manual-1Vpeak-50ohm-3.4GHz-sinusoid; not measured or extracted', 'dv_dt_v_per_s': 21362830044.4102, 'di_dt_a_per_s': 427256600.888204, 'peak_current_a': 0.02, 'loop_area_mm2': 1.0, 'return_discontinuities': 0}], 'chamber': {'distance_m': 3.0, 'table_height_m': 0.8, 'antenna_height_m': 1.5, 'azimuth_deg': 0.0, 'orientation': 'flat', 'polarization': 'horizontal', 'floor': 'absorber', 'cutaway': True}}
assert spike.design is not None, "Open the supplied antenna board first"
assert spike.design["design_id"] == 'kicad-f8fd038633c5b49a3867c8f0', "Selected design is not this pinned example"
preflight=spike.analysis.run("emi_preflight", {"design":spike.design,"setup":SETUP})
result=spike.analysis.run("emi_screen", {"design":spike.design,"setup":SETUP})
print("PREFLIGHT_JSON="+json.dumps(preflight))
print("SCREENING_JSON="+json.dumps(result))
spike.publish_table("Virtual EM review: model boundaries",["Item","Meaning"],[
 ["EMI risk screen", "Ranks supplied metrics; not a field calculation"],
 ["One selected candidate", "No comparative ranking; zero score is not low radiation"],
 ["Chamber", "Placement visualization; absorbers/antenna/room are not EM meshed"],
 ["Radiation", "Open saved EMerge result separately: relative pattern, unvalidated"],
 ["Radiated immunity", "Unsupported: no incident-field/loaded-board susceptibility run"]],
 provenance="Actual EMI worker execution; explicit scope, no compliance claim")
