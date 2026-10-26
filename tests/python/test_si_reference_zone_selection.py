# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Explicit plane identity cannot bypass retained-zone geometry/coverage gates."""
import copy
import json
from pathlib import Path
import unittest
import numpy as np
from jsonschema import Draft202012Validator

from python.spike_core.solvers.signal_integrity.channels.si_channel import extract_uniform_path_rlgc, SiChannelError
from python.spike_core.solvers.signal_integrity.channels.si_coupled_channel import extract_coupled_path_rlgc
from tests.python import test_si_channel as fixtures


class ReferenceZoneSelectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SiUniformChannelTests()

    def two_zones(self, *, coupled=False):
        design = self.fixture.coupled_design() if coupled else self.fixture.design()
        other = copy.deepcopy(design.zones[0])
        other.id = "other-plane"
        other.outlines_mm = [[(100, 100), (110, 100), (110, 110), (100, 110)]]
        design.zones.append(other)
        return design

    def test_no_implicit_choice_and_explicit_identity_preserves_rlgc(self):
        design = self.two_zones()
        request = self.fixture.request()
        with self.assertRaisesRegex(SiChannelError, "unambiguous"):
            extract_uniform_path_rlgc(design, request)
        baseline = extract_uniform_path_rlgc(self.fixture.design(), request)
        selected = extract_uniform_path_rlgc(design, {**request, "reference_zone_id": "zone-reference"})
        self.assertEqual(selected["rlgc_per_m"], baseline["rlgc_per_m"])
        self.assertEqual(selected["geometry"]["reference_zone_ids"], ["zone-reference"])
        self.assertEqual(selected["geometry"]["omitted_reference_zone_ids"], ["other-plane"])
        self.assertEqual(selected["geometry"]["reference_zone_selection"], "explicit")
        self.assertFalse(selected["qualification"]["production_qualified"])
        self.assertTrue(any("Other retained reference zones" in item for item in selected["limitations"]))

    def test_wrong_missing_foreign_or_malformed_selection_fails(self):
        design = self.two_zones()
        for value in ("nonexistent", " zone-reference", "", True, 1, "x" * 257):
            with self.subTest(value=value), self.assertRaises(SiChannelError):
                extract_uniform_path_rlgc(design, {**self.fixture.request(), "reference_zone_id": value})
        design.zones[1].net_id = "foreign"
        with self.assertRaisesRegex(SiChannelError, "matching"):
            extract_uniform_path_rlgc(design, {**self.fixture.request(), "reference_zone_id": "other-plane"})

    def test_explicit_selection_does_not_bypass_coverage_or_holes(self):
        design = self.two_zones()
        with self.assertRaisesRegex(SiChannelError, "not fully covered"):
            extract_uniform_path_rlgc(design, {**self.fixture.request(), "reference_zone_id": "other-plane"})
        design.zones[0].holes_mm = [[(1, 1), (2, 1), (2, 2), (1, 2)]]
        with self.assertRaisesRegex(SiChannelError, "without holes"):
            extract_uniform_path_rlgc(design, {**self.fixture.request(), "reference_zone_id": "zone-reference"})

    def test_coupled_selection_preserves_same_single_plane_operator(self):
        request = self.fixture.coupled_request()
        baseline = extract_coupled_path_rlgc(self.fixture.coupled_design(), request)
        selected = extract_coupled_path_rlgc(self.two_zones(coupled=True), {**request, "reference_zone_id": "zone-reference"})
        for name in ("capacitance_f_per_m", "inductance_h_per_m"):
            np.testing.assert_array_equal(selected["rlgc_per_m"][name], baseline["rlgc_per_m"][name])
        self.assertEqual(selected["geometry"]["omitted_reference_zone_ids"], ["other-plane"])

    def test_schema_admits_selector_without_changing_required_fields(self):
        root = Path(__file__).resolve().parents[2]
        schema = json.loads((root / "schemas/si-uniform-channel-request-v1.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        validator.validate(self.fixture.request())
        validator.validate({**self.fixture.request(), "reference_zone_id": "zone-reference"})
        self.assertFalse(validator.is_valid({**self.fixture.request(), "reference_zone_id": True}))

    def test_physical_material_change_changes_extraction_identity(self):
        design = self.fixture.design()
        before = extract_uniform_path_rlgc(design, self.fixture.request())
        design.materials[0].conductivity_s_per_m *= 0.5
        after = extract_uniform_path_rlgc(design, self.fixture.request())
        self.assertNotEqual(before["geometry_digest"], after["geometry_digest"])
        self.assertNotEqual(before["geometry"]["material_parameters_digest"], after["geometry"]["material_parameters_digest"])
        self.assertEqual(after["rlgc_per_m"]["resistance_ohm_per_m"], 2 * before["rlgc_per_m"]["resistance_ohm_per_m"])

    def test_nonfinite_supplied_conductivity_never_reaches_network_construction(self):
        for value in (float("nan"), float("inf")):
            with self.subTest(value=value):
                design = self.fixture.design()
                design.materials[0].conductivity_s_per_m = value
                with self.assertRaises(SiChannelError):
                    extract_uniform_path_rlgc(design, self.fixture.request())
                design = self.fixture.coupled_design()
                design.materials[0].conductivity_s_per_m = value
                with self.assertRaises(SiChannelError):
                    extract_coupled_path_rlgc(design, self.fixture.coupled_request())

    def test_declared_material_context_is_bound_separately_from_operator_values(self):
        design = self.fixture.design()
        before = extract_uniform_path_rlgc(design, self.fixture.request())
        design.metadata["spike.si_material_scenario"] = {"source": "explicit caller-declared context; not authenticated"}
        after = extract_uniform_path_rlgc(design, self.fixture.request())
        self.assertEqual(before["geometry"]["material_parameters_digest"], after["geometry"]["material_parameters_digest"])
        self.assertNotEqual(before["geometry_digest"], after["geometry_digest"])
        self.assertNotEqual(before["geometry"]["declared_material_scenario_context_digest"],
                            after["geometry"]["declared_material_scenario_context_digest"])
