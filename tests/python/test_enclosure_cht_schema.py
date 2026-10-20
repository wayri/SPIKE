# SPDX-License-Identifier: Apache-2.0
"""Strict schema checks against executed, independently tested CHT fixtures."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
import numpy as np

from python.spike_core.enclosure_cht import solve_enclosure_cht
from tests.python.test_enclosure_cht import fixture, layered_fixture, material

ROOT = Path(__file__).resolve().parents[2]


def golden_requests():
    steady = fixture()
    layered = layered_fixture(True)
    inertial = layered_fixture()
    inertial["flow"]["model"] = "laminar_inertial"
    inertial["flow"]["nonlinear_controls"] = {
        "max_iterations": 30, "relaxation": 1., "relative_tolerance": 1e-10}
    force = np.zeros((6, 2, 2, 3))
    force[1:-1, :, :, 0] = np.arange(2)[None, :, None] * .01
    inertial["flow"]["body_force_n_m3"] = force.tolist()
    transient = layered_fixture(True)
    transient["study"] = {"type": "transient", "time_step_s": .1, "steps": 3,
                          "initial_temperature_k": 300., "output_stride": 2}
    transient["boundaries"] = {name: {"type": "adiabatic"} for name in transient["boundaries"]}
    transient["boundaries"]["x_min"] = {"type": "heat_flux", "inward_heat_flux_w_m2": .2}
    transient["boundaries"]["x_max"] = {"type": "convection", "ambient_temperature_k": 300.,
                                       "heat_transfer_coefficient_w_m2k": .1}
    return steady, layered, inertial, transient


def object_paths(value, path=()):
    if isinstance(value, dict):
        yield path
        for key, child in value.items():
            yield from object_paths(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from object_paths(child, (*path, index))


def at(value, path):
    for key in path:
        value = value[key]
    return value


class EnclosureChtSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validators = {}
        for kind in ("request", "result"):
            schema = json.loads((ROOT / "schemas" / f"enclosure-cht-{kind}-v1.schema.json").read_text())
            Draft202012Validator.check_schema(schema)
            cls.validators[kind] = Draft202012Validator(schema)
        cls.requests = golden_requests()
        cls.results = [solve_enclosure_cht(q) for q in cls.requests]

    def test_executed_golden_requests_and_results(self):
        for request, result in zip(self.requests, self.results):
            self.assertEqual(result["status"], "completed", result)
            # The wire representation cannot contain Python-only objects, NaN or infinities.
            for kind, value in (("request", request), ("result", result)):
                self.validators[kind].validate(json.loads(json.dumps(value, allow_nan=False)))
        self.assertGreater(self.results[2]["flow_diagnostics"]["force_work_w"], 0)
        self.assertGreater(len(self.results[1]["interfaces"]), 0)
        self.assertEqual(len(self.results[3]["temperature_frames"]), 2)
        self.assertEqual(self.results[3]["temperature_frames"][-1]["time_s"], .1*3)

    def test_unknown_fields_rejected_at_every_emitted_object_boundary(self):
        for kind, examples in (("request", self.requests), ("result", self.results)):
            validator = self.validators[kind]
            for index, example in enumerate(examples):
                for path in object_paths(example):
                    changed = deepcopy(example)
                    at(changed, path)["unrecognized_schema_probe"] = 0
                    with self.subTest(kind=kind, example=index, path=path):
                        self.assertFalse(validator.is_valid(changed))

    def test_request_limits_variants_and_scalar_types(self):
        mutations = [
            (("grid", "shape", 0), 33),
            (("grid", "shape", 0), True),
            (("grid", "spacing_m", 0), 0),
            (("flow", "body_force_n_m3", 0, 0, 0, 0), True),
            (("flow", "body_force_n_m3", 0, 0, 0, 0), 1e12+1),
            (("heat_sources_w_m3", 0, 0, 0), -1e12-1),
            (("materials", 0, "density_kg_m3"), 1e-7),
            (("materials", 0, "dynamic_viscosity_pa_s"), 1e5),
            (("materials", 0, "id"), "not an ID"),
            (("boundaries", "x_min", "temperature_k"), 0),
            (("flow", "model"), "turbulent"),
        ]
        for path, value in mutations:
            changed = deepcopy(self.requests[0])
            at(changed, path[:-1])[path[-1]] = value
            with self.subTest(path=path):
                self.assertFalse(self.validators["request"].is_valid(changed))
        for key, value in (("max_iterations", 101), ("relaxation", .09), ("relative_tolerance", 1e-6)):
            changed = deepcopy(self.requests[2])
            changed["flow"]["nonlinear_controls"][key] = value
            self.assertFalse(self.validators["request"].is_valid(changed))
        for key, value in (("steps", 257), ("output_stride", 0), ("time_step_s", 1e-10),
                           ("initial_temperature_k", .5)):
            changed = deepcopy(self.requests[3])
            changed["study"][key] = value
            self.assertFalse(self.validators["request"].is_valid(changed))
        changed = deepcopy(self.requests[1])
        changed["grid"]["local_refinement"][0]["split_factor"] = 5
        self.assertFalse(self.validators["request"].is_valid(changed))
        changed = deepcopy(self.requests[0])
        changed["materials"].append(material("another_fluid"))
        self.assertFalse(self.validators["request"].is_valid(changed))
        changed["materials"] = [material("solid", "solid")]
        self.assertFalse(self.validators["request"].is_valid(changed))
        changed = deepcopy(self.requests[0])
        changed["boundaries"] = {name: {"type": "adiabatic"} for name in changed["boundaries"]}
        self.assertFalse(self.validators["request"].is_valid(changed))
        changed["study"] = deepcopy(self.requests[3]["study"])
        self.assertTrue(self.validators["request"].is_valid(changed))

    def test_actual_blocked_and_cancelled_shapes_forbid_partial_fields(self):
        malformed = fixture()
        malformed["extra"] = 1
        excessive = fixture()
        force = np.zeros((3, 3, 3, 3))
        force[..., 0] = np.arange(3)[None, :, None]*1e5
        excessive["flow"]["body_force_n_m3"] = force.tolist()
        calls = 0

        def during_flow():
            nonlocal calls
            calls += 1
            return calls >= 3

        results = [solve_enclosure_cht(malformed), solve_enclosure_cht(excessive),
                   solve_enclosure_cht(fixture(), cancel_check=lambda: True),
                   solve_enclosure_cht(fixture(), cancel_check=during_flow)]
        for result in results:
            self.assertIn(result["status"], ("blocked", "cancelled"))
            self.validators["result"].validate(result)
            for key in ("fields", "grid", "interfaces", "history", "temperature_frames"):
                changed = deepcopy(result)
                changed[key] = self.results[0][key]
                self.assertFalse(self.validators["result"].is_valid(changed))
        self.assertIn("flow_diagnostics", results[1])
        self.assertIn("flow_diagnostics", results[3])

    def test_success_required_diagnostics_and_state_consistency(self):
        validator = self.validators["result"]
        for result in self.results:
            for key in result:
                changed = deepcopy(result)
                del changed[key]
                with self.subTest(missing=key):
                    self.assertFalse(validator.is_valid(changed))
        for section in ("flow_diagnostics", "transfer_diagnostics", "energy_diagnostics"):
            for key in self.results[2][section]:
                changed = deepcopy(self.results[2])
                del changed[section][key]
                self.assertFalse(validator.is_valid(changed), (section, key))
        changed = deepcopy(self.results[0])
        changed["production_qualified"] = True
        self.assertFalse(validator.is_valid(changed))
        changed = deepcopy(self.results[0])
        changed["grid"]["momentum_locally_refined"] = True
        self.assertFalse(validator.is_valid(changed))
        changed = deepcopy(self.results[0])
        changed["temperature_frames"] = deepcopy(self.results[3]["temperature_frames"])
        self.assertFalse(validator.is_valid(changed))
        changed = deepcopy(self.results[3])
        del changed["energy_diagnostics"]["stored_energy_change_j"]
        self.assertFalse(validator.is_valid(changed))
        changed = deepcopy(self.results[3])
        changed["temperature_frames"] = []
        self.assertFalse(validator.is_valid(changed))


if __name__ == "__main__":
    unittest.main()
