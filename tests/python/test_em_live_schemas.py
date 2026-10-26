# SPDX-License-Identifier: Apache-2.0
"""Offline structural schema checks; numerical admission remains mandatory."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from python.spike_core.solvers.execution.coupling.em_body_heating import run_em_body_heating
from python.spike_core.solvers.execution.coupling.em_spice_coupling import run_em_spice_coupling
from tests.python.test_em_body_heating import request as body_request
from tests.python.test_em_spice_coupling import request as spice_request

ROOT = Path(__file__).resolve().parents[2]


def validator(name):
    schema = json.loads((ROOT / "schemas" / (name+"-request-v1.schema.json")).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


class EmLiveSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spice_validator = validator("em-spice-coupling")
        cls.body_validator = validator("em-body-heating")
        cls.spice = spice_request()
        cls.body = body_request()[0]

    def assertRejected(self, validator, value):
        self.assertTrue(list(validator.iter_errors(value)))

    def test_golden_fixture_schemas_are_valid_and_self_contained(self):
        self.spice_validator.validate(self.spice)
        self.body_validator.validate(self.body)
        # Validation uses no registry/network resolver; all references are local.
        for selected in (self.spice_validator, self.body_validator):
            def references(value):
                if isinstance(value, dict):
                    for key, child in value.items():
                        if key == "$ref":
                            self.assertTrue(child.startswith("#/"), child)
                        references(child)
                elif isinstance(value, list):
                    for child in value:
                        references(child)
            references(selected.schema)

    def test_spice_rejects_unknown_fixed_fields_at_every_boundary(self):
        paths = ((), ("source",), ("source", "s_parameters", 0, 0, 0),
                 ("circuit",), ("circuit", "elements", 0), ("circuit", "elements", 1),
                 ("port_bindings", "P1"))
        for path in paths:
            candidate = deepcopy(self.spice)
            target = candidate
            for key in path:
                target = target[key]
            target["unexpected"] = "not admitted"
            with self.subTest(path=path):
                self.assertRejected(self.spice_validator, candidate)

    def test_spice_rejects_bad_types_values_and_resource_shapes(self):
        changes = (
            lambda r: r["circuit"]["elements"][0].update(value=2),
            lambda r: r["circuit"]["elements"][1].update(phasor=[1, 0]),
            lambda r: r["circuit"]["elements"][1].update(type="diode"),
            lambda r: r["circuit"]["elements"][1].update(value=-1),
            lambda r: r["circuit"]["elements"][1].update(value=True),
            lambda r: r["circuit"].update(ground_node="gnd\n"),
            lambda r: r["circuit"].update(elements=r["circuit"]["elements"]*65),
            lambda r: r["source"].update(frequencies_hz=[1]*65),
            lambda r: r["source"].update(frequencies_hz=[0]),
            lambda r: r["source"].update(reference_impedance_ohm=float("inf")),
            lambda r: r["port_bindings"]["P1"].update(reference_plane="plane\n"),
            lambda r: r["circuit"]["elements"][0].update(phasor=[1, 0, 0]),
        )
        for change in changes:
            candidate = deepcopy(self.spice)
            change(candidate)
            with self.subTest(change=change):
                self.assertRejected(self.spice_validator, candidate)

    def test_body_rejects_unknown_fields_in_all_fixed_records(self):
        face = next(iter(self.body["field_samples"]["boundary_faces"]))
        material = next(iter(self.body["loss_materials"]))
        obj = next(iter(self.body["thermal_request"]["mesh"]["object_map"]))
        port = next(iter(self.body["ac_request"]["boundaries"][0]))
        paths = ((), ("source_binding",), ("field_samples",), ("field_samples", "context"),
            ("field_samples", "boundary_faces", face), ("loss_materials", material),
            ("ac_request",), ("ac_request", "source"), ("ac_request", "source", "s_parameters", 0, 0, 0),
            ("ac_request", "boundaries", 0, port), ("thermal_request",),
            ("thermal_request", "mesh"), ("thermal_request", "mesh", "counts"),
            ("thermal_request", "mesh", "cells", 0), ("thermal_request", "mesh", "object_map", obj),
            ("thermal_request", "materials", 0), ("thermal_request", "boundaries", 0))
        for path in paths:
            candidate = deepcopy(self.body)
            target = candidate
            for key in path:
                target = target[key]
            target["unexpected"] = True
            with self.subTest(path=path):
                self.assertRejected(self.body_validator, candidate)

    def test_body_rejects_wrong_field_shapes_unsafe_physics_and_preexisting_heat(self):
        cell = next(iter(self.body["field_samples"]["cells"]))
        face = next(iter(self.body["field_samples"]["boundary_faces"]))
        material = next(iter(self.body["loss_materials"]))
        changes = (
            lambda r: r["field_samples"]["cells"][cell].pop(),
            lambda r: r["field_samples"]["boundary_faces"][face]["e"].pop(),
            lambda r: r["field_samples"]["cells"][cell][0].pop(),
            lambda r: r["field_samples"]["cells"][cell][0][0].append(1),
            lambda r: r["field_samples"]["cells"][cell][0][0].__setitem__(0, float("inf")),
            lambda r: r["thermal_request"].update(heat_sources_w_m3={cell: 1}),
            lambda r: r["thermal_request"].update(mode="transient"),
            lambda r: r["thermal_request"]["mesh"]["cells"][0].update(kind="hexahedron"),
            lambda r: r["thermal_request"]["mesh"].update(cells=r["thermal_request"]["mesh"]["cells"]*86),
            lambda r: r["source_binding"].update(solver_run_digest="not-a-digest"),
            lambda r: r["loss_materials"][material].update(conductivity_s_m=-1),
            lambda r: r["loss_materials"][material].update(permittivity_f_m=0),
            lambda r: r["ac_request"]["source"].update(port_names=["p0", "p1"]),
            lambda r: r["ac_request"]["source"].update(frequencies_hz=[1, 2]),
        )
        for change in changes:
            candidate = deepcopy(self.body)
            change(candidate)
            with self.subTest(change=change):
                self.assertRejected(self.body_validator, candidate)

    def test_thermal_boundary_variants_are_exact_and_contacts_typed(self):
        variations = (
            {"type": "temperature", "temperature_k": 300},
            {"type": "heat_flux", "heat_flux_w_m2": -1},
            {"type": "adiabatic"},
            {"type": "convection", "heat_transfer_coefficient_w_m2k": 2, "ambient_temperature_k": 300},
            {"type": "radiation", "emissivity": 0.8, "radiation_temperature_k": 300},
            {"type": "convection_radiation", "heat_transfer_coefficient_w_m2k": 2,
             "ambient_temperature_k": 300, "emissivity": 0.8, "radiation_temperature_k": 300},
        )
        for variant in variations:
            candidate = deepcopy(self.body)
            old = candidate["thermal_request"]["boundaries"][0]
            candidate["thermal_request"]["boundaries"][0] = {"id": old["id"], "vertices": old["vertices"], **variant}
            self.body_validator.validate(candidate)
            candidate["thermal_request"]["boundaries"][0]["unrelated"] = 1
            self.assertRejected(self.body_validator, candidate)
        candidate = deepcopy(self.body)
        candidate["thermal_request"]["contacts"] = [{"id": "explicit", "left_vertices": [0, 1, 2],
            "right_vertices": [3, 4, 5], "thermal_contact_conductance_w_m2k": 10}]
        self.body_validator.validate(candidate)
        candidate["thermal_request"]["contacts"][0]["extra"] = 1
        self.assertRejected(self.body_validator, candidate)

    def test_structural_acceptance_does_not_replace_semantic_decoder_gates(self):
        spice = deepcopy(self.spice)
        spice["source"]["s_parameters"][0][0][0]["real"] = 1.1
        self.spice_validator.validate(spice)
        with self.assertRaisesRegex(ValueError, "Nonpassive"):
            run_em_spice_coupling(spice)
        body = deepcopy(self.body)
        body["source_binding"]["mesh_digest"] = "f"*64
        self.body_validator.validate(body)
        with self.assertRaisesRegex(ValueError, "Stale"):
            run_em_body_heating(body)

    def test_nan_is_rejected_by_required_finite_json_boundary(self):
        # JSON Schema assumes JSON input. Python NaN is not a JSON value;
        # schema numeric bounds alone must not be presented as a NaN guard.
        for candidate in (deepcopy(self.spice), deepcopy(self.body)):
            candidate["invalid_non_json"] = float("nan")
            with self.assertRaises(ValueError):
                json.dumps(candidate, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
