# SPDX-License-Identifier: Apache-2.0
"""Raw retained fields, source incidence and scope cannot be replaced by flags."""
from copy import deepcopy
import math
import unittest
import numpy as np
from python.spike_core.dc_annular_land import solve_annular_land
from python.spike_core.dc_annular_land_input import prepare
from python.spike_core.dc_port_circuit import solve_port_circuit
from python.spike_core.dc_annular_stack import solve_annular_stack
from python.spike_core.dc_annular_evidence import validate_annular_result, validate_annular_stack
from tests.python.test_dc_annular_land import request, spreading_request
from tests.python.test_dc_annular_stack import explicit_annular_stack


class AnnularEvidenceTests(unittest.TestCase):
    def test_nonzero_current_underflow_cannot_be_certified_by_retained_fields(self):
        result = solve_annular_land(request())
        factor = 1e-200
        for patch in result["source_request"]["contacts"]:
            patch["current_a"] *= factor
        data = prepare(result["source_request"])
        result["input_digest"] = data["digest"]
        result["face_potential_v"] = [v*factor for v in result["face_potential_v"]]
        assembled = np.zeros(data["face_count"])
        for cell in result["cells"]:
            for key in ("outward_face_current_a", "center_density_rz_a_m2", "radial_current_numerator_endpoint_a",
                        "axial_component_endpoint_density_a_m2"):
                cell[key] = [v*factor for v in cell[key]]
            cell["mean_potential_v"] *= factor
            cell["joule_heat_w"] = cell["mean_joule_density_w_m3"] = 0.
            np.add.at(assembled, cell["face_ids"], cell["outward_face_current_a"])
        for patch in result["contacts"]:
            for key in ("inward_current_a", "global_face_residual_tolerance_a", "mean_potential_v"):
                patch[key] *= factor
            patch["recovered_inward_current_a"] = -math.fsum(assembled[patch["face_ids"]])
            patch["absolute_current_recovery_error_a"] = abs(patch["recovered_inward_current_a"]-patch["inward_current_a"])
            patch["signed_terminal_work_w"] = 0.
        result["joule_heat_w"] = result["signed_terminal_work_w"] = 0.
        with self.assertRaises(ValueError):
            validate_annular_result(result)

    def test_nonzero_current_circuit_cannot_return_underflowed_zero_heat(self):
        with self.assertRaises(ValueError):
            solve_port_circuit([[[1.]], [[1.]]],
                [{"p": [0, 1], "n": [1, 0], "resistance_ohm": 1.}],
                [[1e-200, 0.], [0., -1e-200]])

    def test_response_and_actual_barrel_fields_remain_bound(self):
        result = solve_annular_stack(explicit_annular_stack(spreading=True))
        for mutate in (
            lambda r: r["reduced_responses_ohm"][0][0].__setitem__(0, 1.),
            lambda r: r["response_field_results"][0][0]["face_potential_v"].__setitem__(1, 1e308),
            lambda r: r["edges"][0]["current_density_a_m2"].__setitem__(2, 1.),
            lambda r: r["edges"][0].__setitem__("volume_m3", 1.),
            lambda r: r["edges"][0].__setitem__("mean_joule_density_w_m3", 1.),
            lambda r: r["circuit"]["body_gauge_v"].__setitem__(0, 1.)):
            changed = deepcopy(result); mutate(changed)
            with self.assertRaises(ValueError):
                validate_annular_stack(changed)

    def test_gate_rejects_authenticated_source_fixture_with_zero_drive(self):
        from scripts.parity_annular_contact_gate import validate_report
        from tests.python.test_dc_annular_source import source_stack
        from python.spike_core.dc_annular_source import solve_source_annular_stack
        source = source_stack()
        for currents in source["external_currents"].values():
            for name in currents:
                currents[name] = 0.
        wrapper = solve_source_annular_stack(source)
        self.assertTrue(wrapper["source_files_revalidated"])
        report = {"annular_refinement": [solve_annular_land(spreading_request(n)) for n in (4, 8, 16)],
                  "series_stack": solve_annular_stack(explicit_annular_stack()),
                  "spreading_stack": solve_annular_stack(explicit_annular_stack(spreading=True)),
                  "source_stack": wrapper}
        with self.assertRaisesRegex(ValueError, "[Ss]ource.*(input|request|fixture)|[Nn]ative.*(input|request|fixture)"):
            validate_report(report)

    def test_retained_local_fields_and_constitutive_witnesses(self):
        for raw in (request(), request("z"), spreading_request(8)):
            result = solve_annular_land(raw); validate_annular_result(result)
        for mutate in (lambda r: r["cells"][0]["outward_face_current_a"].__setitem__(0, 1.),
                       lambda r: r["cells"][0].__setitem__("mean_potential_v", 1.),
                       lambda r: r["cells"][0].__setitem__("joule_heat_w", 1.),
                       lambda r: r["cells"][0]["center_density_rz_a_m2"].__setitem__(0, 1e10),
                       lambda r: r["contacts"][0].__setitem__("attachment_id", "detached"),
                       lambda r: r["face_potential_v"].__setitem__(0, 1.),
                       lambda r: r.__setitem__("production_qualified", True)):
            changed = deepcopy(result); mutate(changed)
            with self.assertRaises(ValueError): validate_annular_result(changed)

    def test_coupled_field_incidence_heat_and_source_identity(self):
        for current in (0., 1., -2.):
            result = solve_annular_stack(explicit_annular_stack(spreading=True, current=current))
            validate_annular_stack(result)
        for mutate in (lambda r: r["edges"][0].__setitem__("current_a", 10.),
                       lambda r: r["edges"][0].__setitem__("heat_w", 1.),
                       lambda r: r["lands"][0].__setitem__("land_id", "detached"),
                       lambda r: r["lands"][0]["global_port_potentials_v"].__setitem__(0, 1.),
                       lambda r: r["lands"][0]["field_result"]["source_request"]["contacts"][0].__setitem__("id", "detached"),
                       lambda r: r["circuit"]["body_currents_a"][0].__setitem__(0, 1.),
                       lambda r: r.__setitem__("total_heat_w", 1.),
                       lambda r: r.__setitem__("ownership_currents_reused", True),
                       lambda r: r.__setitem__("complete_board_physical_volume", True)):
            changed = deepcopy(result); mutate(changed)
            with self.assertRaises(ValueError): validate_annular_stack(changed)


if __name__ == "__main__":
    unittest.main()
