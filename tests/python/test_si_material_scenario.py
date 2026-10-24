# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
import copy
import math
import unittest
from unittest.mock import patch

from python.spike_core.si_channel import analyze_uniform_design_channel
from python.spike_core.si_material_scenario import (
    METADATA_KEY,
    REQUEST_CONTRACT,
    SiMaterialScenarioError,
    prepare_si_material_scenario,
)
from python.spike_core.spider_v2 import (
    Layer,
    Material,
    Net,
    SourceIdentity,
    SpiDeRV2,
    Track,
    Zone,
)
from python.spike_core.spider_v2_schema import content_digest


def uniform_design() -> dict:
    copper = Material(
        id="material-copper", name="Unspecified imported copper",
        material_class="conductor", conductivity_s_per_m=None,
    )
    dielectric = Material(
        id="material-fr4", name="Fixture dielectric", material_class="dielectric",
        relative_permittivity=4.0, loss_tangent=0.015,
    )
    signal = Net(id="net-signal", name="SIG")
    ground = Net(id="net-ground", name="GND")
    return SpiDeRV2(
        design_id="generated-uniform-channel",
        name="generated uniform channel",
        source=SourceIdentity(source_format="fixture", source_digest="a" * 64),
        materials=[copper, dielectric],
        layers=[
            Layer(id="layer-signal", name="F.Cu", layer_type="copper", order=0,
                  z_mm=0.0, thickness_mm=0.035, material_id=copper.id),
            Layer(id="layer-dielectric", name="Core", layer_type="dielectric", order=1,
                  z_mm=0.035, thickness_mm=0.2, material_id=dielectric.id),
            Layer(id="layer-reference", name="In1.Cu", layer_type="copper", order=2,
                  z_mm=0.235, thickness_mm=0.035, material_id=copper.id),
        ],
        nets=[signal, ground],
        tracks=[Track(
            id="track-1", net_id=signal.id, layer_id="layer-signal",
            start_mm=(0.0, 0.0), end_mm=(50.0, 0.0), width_mm=0.35,
        )],
        zones=[Zone(
            id="zone-reference", net_id=ground.id, layer_ids=["layer-reference"],
            outlines_mm=[[(-5.0, -5.0), (55.0, -5.0), (55.0, 5.0), (-5.0, 5.0)]],
        )],
    ).to_dict()


def scenario_request(design: dict, conductivity: float = 5.8e7) -> dict:
    return {
        "contract": REQUEST_CONTRACT,
        "design_digest_sha256": content_digest(design),
        "source_digest": design["source"]["source_digest"],
        "material_overrides": [{
            "material_id": "material-copper",
            "material_type": "conductor",
            "conductivity_s_per_m": conductivity,
            "provenance": {
                "source": "explicit test input; not board-source metadata",
                "model": "constant isotropic conductivity",
                "temperature_k": 293.15,
                "assumption_status": "assumed",
            },
        }],
    }


def channel_request() -> dict:
    return {
        "contract": "spike/si-uniform-channel-request/v1",
        "channel_id": "scenario-channel",
        "signal_net": "SIG",
        "reference_net": "GND",
        "reference_layer": "In1.Cu",
        "reference_impedance_ohm": 50.0,
        "frequencies_hz": [0.0, 5.0e7, 1.0e8],
        "trace_limit": 8,
    }


class SiMaterialScenarioTests(unittest.TestCase):
    def test_preparation_is_immutable_source_bound_and_auditable(self) -> None:
        design = uniform_design()
        before = copy.deepcopy(design)
        result = prepare_si_material_scenario(design, scenario_request(design))

        self.assertEqual(design, before)
        self.assertIsNot(result["design"], design)
        self.assertEqual(result["design"]["source"], design["source"])
        self.assertIsNone(design["materials"][0]["conductivity_s_per_m"])
        self.assertEqual(result["design"]["materials"][0]["conductivity_s_per_m"], 5.8e7)
        record = result["design"]["metadata"][METADATA_KEY]
        self.assertEqual(record["base_design_sha256"], content_digest(design))
        self.assertEqual(record["source_digest"], design["source"]["source_digest"])
        self.assertEqual(record["material_overrides"][0]["base_value"], None)
        self.assertEqual(record["scenario_sha256"], result["provenance"]["scenario_sha256"])
        self.assertEqual(result["provenance"]["prepared_design_sha256"], content_digest(result["design"]))

    def test_uniform_channel_resistance_uses_only_the_explicit_scenario_value(self) -> None:
        design = uniform_design()
        width_m = 0.35e-3
        thickness_m = 0.035e-3
        resistances = []
        for conductivity in (5.8e7, 2.9e7):
            prepared = prepare_si_material_scenario(
                design, scenario_request(design, conductivity)
            )["design"]
            extraction = analyze_uniform_design_channel(
                SpiDeRV2.from_dict(prepared), channel_request()
            )["extraction"]
            expected = 1.0 / (conductivity * width_m * thickness_m)
            actual = extraction["rlgc_per_m"]["resistance_ohm_per_m"]
            self.assertAlmostEqual(actual, expected, places=12)
            resistances.append(actual)
        self.assertAlmostEqual(resistances[1], 2.0 * resistances[0], places=12)

    def test_retained_marble_copper_class_is_an_explicit_conductive_target(self) -> None:
        design = uniform_design()
        design["materials"][0]["material_class"] = "copper"
        request = scenario_request(design)
        request["material_overrides"][0]["material_type"] = "copper"
        prepared = prepare_si_material_scenario(design, request)["design"]
        self.assertEqual(prepared["materials"][0]["material_class"], "copper")
        self.assertEqual(prepared["materials"][0]["conductivity_s_per_m"], 5.8e7)

    def test_wrong_revision_source_and_prepared_input_fail_closed(self) -> None:
        design = uniform_design()
        for field in ("design_digest_sha256", "source_digest"):
            request = scenario_request(design)
            request[field] = "0" * 64
            with self.subTest(field=field), self.assertRaises(SiMaterialScenarioError):
                prepare_si_material_scenario(design, request)
        prepared = prepare_si_material_scenario(design, scenario_request(design))["design"]
        with self.assertRaisesRegex(SiMaterialScenarioError, "already carries"):
            prepare_si_material_scenario(prepared, scenario_request(prepared))

    def test_override_target_type_duplicates_and_exact_fields_are_guarded(self) -> None:
        design = uniform_design()
        mutations = []
        unknown = scenario_request(design)
        unknown["material_overrides"][0]["material_id"] = "missing"
        mutations.append(unknown)
        dielectric = scenario_request(design)
        dielectric["material_overrides"][0]["material_id"] = "material-fr4"
        mutations.append(dielectric)
        wrong_type = scenario_request(design)
        wrong_type["material_overrides"][0]["material_type"] = "dielectric"
        mutations.append(wrong_type)
        duplicate = scenario_request(design)
        duplicate["material_overrides"].append(copy.deepcopy(duplicate["material_overrides"][0]))
        mutations.append(duplicate)
        surprise = scenario_request(design)
        surprise["material_overrides"][0]["resistivity_ohm_m"] = 1.0
        mutations.append(surprise)
        missing = scenario_request(design)
        del missing["material_overrides"][0]["provenance"]["model"]
        mutations.append(missing)
        for index, request in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(SiMaterialScenarioError):
                prepare_si_material_scenario(design, request)

    def test_numbers_arrays_and_declared_provenance_are_bounded(self) -> None:
        design = uniform_design()
        bad_values = ["58000000", True, math.nan, math.inf, 0.0, 1.0e13, 10 ** 1000]
        for value in bad_values:
            request = scenario_request(design)
            request["material_overrides"][0]["conductivity_s_per_m"] = value
            with self.subTest(conductivity=value), self.assertRaises(SiMaterialScenarioError):
                prepare_si_material_scenario(design, request)
        for value in ("293.15", False, math.nan, 0.0, 1.0e6):
            request = scenario_request(design)
            request["material_overrides"][0]["provenance"]["temperature_k"] = value
            with self.subTest(temperature=value), self.assertRaises(SiMaterialScenarioError):
                prepare_si_material_scenario(design, request)
        empty = scenario_request(design)
        empty["material_overrides"] = []
        with self.assertRaises(SiMaterialScenarioError):
            prepare_si_material_scenario(design, empty)
        oversized = scenario_request(design)
        oversized["material_overrides"] *= 257
        with self.assertRaises(SiMaterialScenarioError):
            prepare_si_material_scenario(design, oversized)

        oversized_request = scenario_request(design)
        oversized_request["material_overrides"][0]["provenance"]["source"] = "x" * (8 * 1024 * 1024)
        with self.assertRaisesRegex(SiMaterialScenarioError, "request exceeds"):
            prepare_si_material_scenario(design, oversized_request)

        with patch("python.spike_core.si_material_scenario.MAX_DESIGN_ENTITIES", 1):
            with self.assertRaisesRegex(SiMaterialScenarioError, "entity"):
                prepare_si_material_scenario(design, scenario_request(design))


if __name__ == "__main__":
    unittest.main()
