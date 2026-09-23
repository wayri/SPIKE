import tempfile
import unittest
from pathlib import Path

from python.spike_core.openfoam import prepare_case
from python.spike_core.thermal import ThermalScenario, estimate_compact_thermal, validate_scenario


class ThermalWorkflowTests(unittest.TestCase):
    def test_persisted_field_preview_is_not_solver_input(self):
        scenario = ThermalScenario(
            heat_sources=[{"id": "U1", "power_w": 0.0, "position": [50, 40, 3]}],
            field_result={"contract": "spike/thermal-field-result/v1", "fields": {"temperature_c": []}},
        )
        self.assertTrue(validate_scenario(scenario)["valid"])
        self.assertNotIn("field_result", scenario.to_dict())

    def test_thermal_assembly_elements_and_links_are_validated(self):
        material = {"id": "aluminum-6061", "conductivity_w_mk": 167.0}
        source = {
            "id": "element-u1", "reference": "U1", "material_id": "aluminum-6061",
            "power_w": 4.0, "emissivity": 0.85,
            "dimensions_mm": {"x": 5.0, "y": 5.0, "z": 1.0},
        }
        sink = {
            "id": "element-hs1", "reference": "HS1", "material_id": "aluminum-6061",
            "power_w": 0.0, "emissivity": 0.85,
            "dimensions_mm": {"x": 20.0, "y": 20.0, "z": 8.0},
        }
        link = {
            "id": "link-u1-hs1", "from_id": "element-u1", "to_id": "element-hs1",
            "resistance_c_per_w": 0.3, "contact_area_mm2": 25.0,
        }
        result = validate_scenario(ThermalScenario(
            material_library=[material], thermal_elements=[source, sink], thermal_links=[link],
        ))
        self.assertTrue(result["valid"])
        self.assertIn("solid_thermal_elements_and_contacts", result["capability"]["requested_but_unimplemented"])
        self.assertFalse(result["capability"]["case_generation_ready"])

    def test_invalid_thermal_link_is_blocking(self):
        result = validate_scenario(ThermalScenario(
            thermal_elements=[{
                "id": "element-u1", "reference": "U1", "power_w": 1.0, "emissivity": 0.8,
                "dimensions_mm": {"x": 2.0, "y": 2.0, "z": 1.0},
            }],
            thermal_links=[{"id": "broken", "from_id": "element-u1", "to_id": "missing"}],
        ))
        self.assertFalse(result["valid"])
        self.assertIn("THERMAL_LINK_ENDPOINT_INVALID", {issue["code"] for issue in result["issues"]})

    def test_simple_scenario_is_valid_without_openfoam(self):
        scenario = ThermalScenario(
            heat_sources=[{"id": "U1", "power_w": 8.0, "position": [50, 40, 3]}],
            flow_channels=[{"id": "main", "path": [[0, 0, 0], [220, 0, 0]], "width_mm": 20, "height_mm": 20}],
            fans=[{"id": "fan1", "position": [10, 10, 20], "direction": [0, 0, -1], "flow_rate_m3_s": 0.02}],
        )
        result = validate_scenario(scenario)
        self.assertTrue(result["valid"])
        self.assertFalse(result["solver_ready"])

    def test_invalid_fan_is_rejected(self):
        result = validate_scenario(ThermalScenario(fans=[{"id": "fan1"}]))
        self.assertFalse(result["valid"])
        self.assertTrue(any(issue["code"] == "FAN_GEOMETRY_INCOMPLETE" for issue in result["issues"]))

    def test_fan_and_heatsink_operating_geometry_is_validated(self):
        scenario = ThermalScenario(
            convection="forced",
            fans=[{
                "id": "fan1", "enabled": True, "position": [5, 50, 30],
                "direction": [1, 0, 0], "diameter_mm": 80, "depth_mm": 25,
                "flow_rate_m3_s": 0.012, "static_pressure_pa": 35, "rpm": 1800,
            }],
            virtual_heatsinks=[{
                "id": "sink1", "enabled": True, "target": "board-total",
                "dimensions_mm": {"x": 40, "y": 40, "z": 15},
                "interface_resistance_c_per_w": 0.15, "fin_count": 10,
                "fin_thickness_mm": 1, "fin_height_mm": 12,
            }],
        )
        result = validate_scenario(scenario)
        self.assertTrue(result["valid"])
        self.assertFalse(result["capability"]["case_generation_ready"])

        scenario.fans[0]["direction"] = [0, 0, 0]
        result = validate_scenario(scenario)
        self.assertFalse(result["valid"])
        self.assertIn("FAN_DIRECTION_INVALID", {issue["code"] for issue in result["issues"]})

    def test_vacuum_rejects_convection_and_airflow(self):
        result = validate_scenario(ThermalScenario(
            medium="vacuum",
            convection="forced",
            fans=[{"id": "fan1", "position": [0, 0, 0], "direction": [1, 0, 0]}],
        ))
        self.assertFalse(result["valid"])
        self.assertFalse(result["solver_ready"])
        self.assertTrue(any(issue["code"] == "VACUUM_CONVECTION_INVALID" for issue in result["issues"]))

    def test_advanced_thermal_case_is_capability_gated(self):
        result = validate_scenario(ThermalScenario(
            medium="potting",
            convection="none",
            potting={"conductivity_w_mk": 0.8},
            heat_sources=[{"id": "U1", "power_w": 2.0}],
        ))
        self.assertTrue(result["valid"])
        self.assertFalse(result["solver_ready"])
        self.assertEqual(result["capability"]["status"], "unsupported")

    def test_case_generation_is_local_and_inspectable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = prepare_case(ThermalScenario(), Path(temp_dir) / "case")
            self.assertIn(result["status"], {"prepared_experimental_case", "prepared_runtime_unavailable"})
            self.assertTrue((Path(temp_dir) / "case" / "spike_scenario.json").exists())
            self.assertTrue((Path(temp_dir) / "case" / "spike_case.json").exists())
            self.assertTrue((Path(temp_dir) / "case" / "constant" / "turbulenceProperties").exists())
            self.assertFalse((Path(temp_dir) / "case" / "Allrun").exists())

    def test_component_bond_thermal_properties_are_validated(self):
        valid = {
            "id": "bond:U1:1", "enabled": True, "component_ref": "U1",
            "pad_id": "pad-U1-1", "connected_layers": ["F.Cu"],
            "thermal": {"conductivity_w_mk": 50.0, "contact_area_mm2": 1.2},
        }
        result = validate_scenario(ThermalScenario(component_bonds=[valid]))
        self.assertTrue(result["valid"])

        invalid = dict(valid, thermal={"conductivity_w_mk": 0.0, "contact_area_mm2": 1.2})
        result = validate_scenario(ThermalScenario(component_bonds=[invalid]))
        self.assertFalse(result["valid"])
        self.assertIn("THERMAL_COMPONENT_BOND_PROPERTIES_INVALID", {item["code"] for item in result["issues"]})

    def test_compact_steady_state_estimate_uses_explicit_theta(self):
        result = estimate_compact_thermal(ThermalScenario(
            ambient_temperature_c=25.0,
            heat_sources=[{"id": "U1", "power_w": 8.0, "theta_ja_c_per_w": 12.5}],
        ))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["model_status"], "approximate")
        self.assertAlmostEqual(result["summary"]["max_steady_temperature_c"], 125.0)
        self.assertTrue(any(issue["code"] == "COMPACT_THERMAL_MODEL" for issue in result["issues"]))

    def test_compact_transient_requires_thermal_capacitance(self):
        result = estimate_compact_thermal(ThermalScenario(
            mode="transient",
            heat_sources=[{"id": "U1", "power_w": 2.0, "theta_ja_c_per_w": 10.0}],
        ))
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(issue["code"] == "THERMAL_CAPACITANCE_REQUIRED" for issue in result["issues"]))

    def test_compact_transient_emits_first_order_temperature_frames(self):
        result = estimate_compact_thermal(ThermalScenario(
            mode="transient",
            ambient_temperature_c=20.0,
            heat_sources=[{
                "id": "Q1",
                "power_w": 5.0,
                "theta_ja_c_per_w": 8.0,
                "thermal_capacitance_j_per_c": 2.0,
            }],
        ))
        self.assertEqual(result["status"], "completed")
        self.assertAlmostEqual(result["sources"][0]["time_constant_s"], 16.0)
        self.assertEqual(result["sources"][0]["transient"][0]["temperature_c"], 20.0)

    def test_lumped_network_solves_explicit_solid_and_contact_paths(self):
        result = estimate_compact_thermal(ThermalScenario(
            thermal_elements=[
                {"id": "u1", "reference": "U1", "power_w": 10.0, "emissivity": 0.8,
                 "dimensions_mm": {"x": 5, "y": 5, "z": 1}, "ambient_resistance_c_per_w": 10.0},
                {"id": "sink", "reference": "HS1", "power_w": 0.0, "emissivity": 0.8,
                 "dimensions_mm": {"x": 20, "y": 20, "z": 8}, "ambient_resistance_c_per_w": 5.0},
            ],
            thermal_links=[{"id": "tim", "from_id": "u1", "to_id": "sink", "resistance_c_per_w": 1.0}],
        ))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["model_status"], "approximate")
        by_id = {node["id"]: node for node in result["nodes"]}
        self.assertAlmostEqual(by_id["u1"]["temperature_rise_c"], 37.5)
        self.assertAlmostEqual(by_id["sink"]["temperature_rise_c"], 31.25)
        self.assertEqual(result["provenance"]["qualification"], "engineering_precheck_only")

    def test_lumped_network_accepts_explicit_ambient_link_and_heat_source_table(self):
        result = estimate_compact_thermal(ThermalScenario(
            thermal_elements=[{"id": "u1", "reference": "U1", "power_w": 1.0, "emissivity": 0.8,
                               "dimensions_mm": {"x": 5, "y": 5, "z": 1}}],
            thermal_links=[{"id": "u1-air", "from_id": "u1", "to_id": "ambient", "conductance_w_per_k": 0.5}],
            heat_sources=[{"id": "u1-table", "element_id": "u1", "power_w": 4.0}],
        ))
        self.assertEqual(result["status"], "completed")
        self.assertAlmostEqual(result["nodes"][0]["steady_temperature_c"], 35.0)

    def test_lumped_network_transient_uses_bounded_backward_euler_frames(self):
        result = estimate_compact_thermal(ThermalScenario(
            mode="transient", ambient_temperature_c=20.0,
            run={"end_time_s": 2.0, "write_interval_s": 0.5, "max_iterations": 100, "residual_target": 1e-6},
            thermal_elements=[{"id": "u1", "reference": "U1", "power_w": 10.0, "emissivity": 0.8,
                               "dimensions_mm": {"x": 5, "y": 5, "z": 1},
                               "ambient_resistance_c_per_w": 2.0, "thermal_capacitance_j_per_c": 4.0}],
        ))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["transient"]), 5)
        self.assertEqual(result["transient"][0]["temperatures_c"]["u1"], 20.0)
        self.assertGreater(result["transient"][-1]["temperatures_c"]["u1"], 20.0)
        self.assertLess(result["transient"][-1]["temperatures_c"]["u1"], result["nodes"][0]["steady_temperature_c"])

    def test_lumped_network_blocks_floating_thermal_islands(self):
        result = estimate_compact_thermal(ThermalScenario(
            thermal_elements=[{"id": "u1", "reference": "U1", "power_w": 1.0, "emissivity": 0.8,
                               "dimensions_mm": {"x": 5, "y": 5, "z": 1}}],
        ))
        self.assertEqual(result["status"], "blocked")
        self.assertIn("THERMAL_NETWORK_AMBIENT_PATH_REQUIRED", {issue["code"] for issue in result["issues"]})


if __name__ == "__main__":
    unittest.main()
