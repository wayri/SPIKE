# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Conservation, adjoint duality and fail-closed surface exchange tests."""

import copy
import json
import math
import unittest

from python.spike_core.coupled_surface_exchange import (
    MAX_CONTROL_BYTES,
    MIN_AREA_M2,
    coupled_surface_context_digest,
    parse_coupled_surface_exchange_json,
    transfer_coupled_surface_exchange,
)


def _patch(participant, patch, digest, faces):
    return {
        "participant_id": participant,
        "patch_id": patch,
        "geometry_digest": digest,
        "frame": {"id": "assembly-world", "rank": 3, "handedness": "right"},
        "faces": [{"id": face_id, "area_m2": area} for face_id, area in faces],
    }


def request(quantity="heat_flux", *, paired=False):
    value_units = ("W/m2", "W") if quantity == "heat_flux" else ("N/m2", "N")
    result = {
        "contract": "spike/coupled-surface-exchange-request/v1",
        "transfer_id": "original-nonuniform-partition",
        "quantity": quantity,
        "normal_relation": "opposite_outward_normals",
        "units": {"length": "m", "area": "m2",
                  "source_intensive": value_units[0],
                  "destination_integrated": value_units[1]},
        "source_patch": _patch("fluid", "wall", "a" * 64,
                               [("s-wide", 2.0), ("s-small", 1.0)]),
        "destination_patch": _patch("solid", "skin", "b" * 64,
                                    [("d-left", 1.5), ("d-right", 1.5)]),
        "overlaps": [
            {"source_face_id": "s-wide", "destination_face_id": "d-left", "area_m2": 1.5},
            {"source_face_id": "s-wide", "destination_face_id": "d-right", "area_m2": 0.5},
            {"source_face_id": "s-small", "destination_face_id": "d-right", "area_m2": 1.0},
        ],
    }
    if quantity == "heat_flux":
        result["source_values"] = [
            {"face_id": "s-wide", "value": 10.0},
            {"face_id": "s-small", "value": 20.0},
        ]
        if paired:
            result["destination_values"] = [
                {"face_id": "d-left", "value": 300.0},
                {"face_id": "d-right", "value": 330.0},
            ]
            result["destination_value_unit"] = "K"
    else:
        result["source_values"] = [
            {"face_id": "s-wide", "value": [2.0, -1.0, 4.0]},
            {"face_id": "s-small", "value": [-3.0, 5.0, 1.0]},
        ]
        if paired:
            result["destination_values"] = [
                {"face_id": "d-left", "value": [0.5, 2.0, -1.0]},
                {"face_id": "d-right", "value": [-2.0, 1.5, 3.0]},
            ]
            result["destination_value_unit"] = "m/s"
    result["context_digest"] = coupled_surface_context_digest(result)
    return result


def _records(records):
    return {item["face_id"]: item["value"] for item in records}


def one_face_request(area, source_value, destination_value=None):
    raw = {
        "contract": "spike/coupled-surface-exchange-request/v1",
        "transfer_id": "extreme-range-oracle",
        "quantity": "heat_flux",
        "normal_relation": "opposite_outward_normals",
        "units": {"length": "m", "area": "m2", "source_intensive": "W/m2",
                  "destination_integrated": "W"},
        "source_patch": _patch("fluid", "wall", "c" * 64, [("s", area)]),
        "destination_patch": _patch("solid", "skin", "d" * 64, [("d", area)]),
        "overlaps": [{"source_face_id": "s", "destination_face_id": "d",
                      "area_m2": area}],
        "source_values": [{"face_id": "s", "value": source_value}],
    }
    if destination_value is not None:
        raw["destination_values"] = [{"face_id": "d", "value": destination_value}]
        raw["destination_value_unit"] = "K"
    raw["context_digest"] = coupled_surface_context_digest(raw)
    return raw


class CoupledSurfaceExchangeTests(unittest.TestCase):
    def test_nonuniform_split_merge_conserves_heat_and_reverses_outward_sign(self):
        raw = request()
        before = copy.deepcopy(raw)
        result = transfer_coupled_surface_exchange(raw)
        self.assertEqual(raw, before)
        values = _records(result["destination_integrated_values"])
        self.assertEqual(values, {"d-left": -15.0, "d-right": -25.0})
        diagnostics = result["diagnostics"]
        self.assertEqual(diagnostics["source_outward_integrated_total"], 40.0)
        self.assertEqual(diagnostics["destination_outward_integrated_total"], -40.0)
        self.assertEqual(diagnostics["raw_global_balance"], 0.0)
        self.assertEqual(diagnostics["coverage"]["overlap_area_m2"], 3.0)
        self.assertFalse(result["production_qualified"])

    def test_reverse_temperature_map_is_adjoint_but_not_promoted_to_physical_work(self):
        result = transfer_coupled_surface_exchange(request(paired=True))
        mapped = _records(result["mapped_source_values"])
        self.assertEqual(mapped, {"s-small": 330.0, "s-wide": 307.5})
        pairing = result["diagnostics"]["adjoint_pairing"]
        self.assertEqual(pairing["kind"], "thermal_bilinear_duality_not_physical_work")
        self.assertEqual(pairing["unit"], "W*K")
        self.assertEqual(pairing["source_pairing"], 12750.0)
        self.assertEqual(pairing["destination_pairing"], -12750.0)
        self.assertEqual(pairing["raw_pairing_balance"], 0.0)

    def test_three_dimensional_traction_virtual_power_uses_transpose_pair(self):
        result = transfer_coupled_surface_exchange(request("traction", paired=True))
        force = _records(result["destination_integrated_values"])
        self.assertEqual(force["d-left"], [-3.0, 1.5, -6.0])
        self.assertEqual(force["d-right"], [2.0, -4.5, -3.0])
        mapped = _records(result["mapped_source_values"])
        self.assertEqual(mapped["s-wide"], [-0.125, 1.875, 0.0])
        self.assertEqual(mapped["s-small"], [-2.0, 1.5, 3.0])
        pairing = result["diagnostics"]["adjoint_pairing"]
        self.assertEqual(pairing["kind"], "virtual_power")
        self.assertEqual(pairing["unit"], "W")
        self.assertAlmostEqual(pairing["raw_pairing_balance"], 0.0, places=14)
        self.assertEqual(result["diagnostics"]["raw_global_balance"], [0.0, 0.0, 0.0])

    def test_displacement_pair_is_virtual_work_and_pressure_or_moment_is_not_promoted(self):
        raw = request("traction", paired=True)
        raw["destination_value_unit"] = "m"
        result = transfer_coupled_surface_exchange(raw)
        self.assertEqual(result["diagnostics"]["adjoint_pairing"]["kind"], "virtual_work")
        self.assertEqual(result["diagnostics"]["adjoint_pairing"]["unit"], "J")
        self.assertFalse(any("moment" in key.lower()
                             for key in result for _ in [None]))
        self.assertFalse(any("moment" in key.lower()
                             for key in result["diagnostics"] for _ in [None]))
        pressure = request()
        pressure["quantity"] = "pressure"
        with self.assertRaisesRegex(ValueError, "QUANTITY"):
            coupled_surface_context_digest(pressure)

    def test_json_parser_rejects_duplicate_keys_and_executes_pure_data(self):
        raw = request(paired=True)
        result = parse_coupled_surface_exchange_json(json.dumps(raw))
        self.assertEqual(result["context_digest"], raw["context_digest"])
        duplicate = json.dumps(raw).replace(
            '"transfer_id": "original-nonuniform-partition",',
            '"transfer_id": "first", "transfer_id": "second",', 1)
        with self.assertRaisesRegex(ValueError, "duplicate object key"):
            parse_coupled_surface_exchange_json(duplicate)

    def test_overlap_coverage_duplicates_and_numbers_fail_closed(self):
        mutations = [
            lambda value: value["overlaps"][0].update(area_m2=1.4),
            lambda value: value["overlaps"].append(copy.deepcopy(value["overlaps"][0])),
            lambda value: value["overlaps"][0].update(area_m2=-1.5),
            lambda value: value["overlaps"][0].update(area_m2=math.nan),
            lambda value: value["source_patch"]["faces"][0].update(area_m2=True),
        ]
        for mutation in mutations:
            raw = request()
            mutation(raw)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                transfer_coupled_surface_exchange(raw)

    def test_faces_values_unknown_fields_and_units_are_strict(self):
        mutations = [
            lambda value: value.update(extra=True),
            lambda value: value["source_patch"].update(extra=True),
            lambda value: value["source_patch"]["faces"].append(
                copy.deepcopy(value["source_patch"]["faces"][0])),
            lambda value: value["source_values"].append(copy.deepcopy(value["source_values"][0])),
            lambda value: value["source_values"][0].update(value=[1, 2, 3]),
            lambda value: value["units"].update(area="mm2"),
            lambda value: value.update(normal_relation="parallel_normals"),
        ]
        for mutation in mutations:
            raw = request()
            mutation(raw)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                transfer_coupled_surface_exchange(raw)

    def test_rank_frame_geometry_digest_and_stale_context_fail(self):
        mutations = [
            lambda value: value["source_patch"]["frame"].update(rank=2),
            lambda value: value["destination_patch"]["frame"].update(id="other-frame"),
            lambda value: value["source_patch"].update(geometry_digest="A" * 64),
            lambda value: value.update(context_digest="broken"),
            lambda value: value["source_patch"].update(geometry_digest="c" * 64),
        ]
        patterns = ["FRAME", "FRAME", "DIGEST", "DIGEST", "STALE"]
        for mutation, pattern in zip(mutations, patterns):
            raw = request()
            mutation(raw)
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, pattern):
                transfer_coupled_surface_exchange(raw)

    def test_destination_field_unit_and_presence_are_not_guessed(self):
        for mutation in [
            lambda value: value.pop("destination_value_unit"),
            lambda value: value.update(destination_value_unit="mm"),
        ]:
            raw = request("traction", paired=True)
            mutation(raw)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                transfer_coupled_surface_exchange(raw)
        heat = request(paired=True)
        heat["destination_value_unit"] = "m"
        with self.assertRaisesRegex(ValueError, "UNITS"):
            transfer_coupled_surface_exchange(heat)

    def test_face_overlap_and_byte_budgets_are_enforced(self):
        face_heavy = request()
        face_heavy["source_patch"]["faces"] = [
            {"id": f"s-{index}", "area_m2": 1.0} for index in range(511)]
        with self.assertRaisesRegex(ValueError, "512 total faces"):
            transfer_coupled_surface_exchange(face_heavy)

        overlap_heavy = request()
        overlap_heavy["overlaps"] = [
            {"source_face_id": "s-wide", "destination_face_id": "d-left", "area_m2": 1.0}
            for _ in range(8193)]
        with self.assertRaisesRegex(ValueError, "8192"):
            transfer_coupled_surface_exchange(overlap_heavy)

        with self.assertRaisesRegex(ValueError, "8 MiB"):
            parse_coupled_surface_exchange_json(" " * (MAX_CONTROL_BYTES + 1))

    def test_cancellation_discards_exchange(self):
        calls = 0

        def cancel_after_validation():
            nonlocal calls
            calls += 1
            return calls >= 3

        with self.assertRaisesRegex(ValueError, "CANCELLED"):
            transfer_coupled_surface_exchange(request(), cancel_check=cancel_after_validation)
        with self.assertRaisesRegex(ValueError, "must be callable"):
            transfer_coupled_surface_exchange(request(), cancel_check=False)

    def test_extreme_area_reverse_map_avoids_intermediate_underflow(self):
        # Directly evaluating area*temperature/area would first round to zero.
        raw = one_face_request(1.0e-300, 1.0e300, 1.0e-30)
        result = transfer_coupled_surface_exchange(raw)
        self.assertEqual(_records(result["destination_integrated_values"]), {"d": -1.0})
        self.assertEqual(_records(result["mapped_source_values"]), {"s": 1.0e-30})
        pairing = result["diagnostics"]["adjoint_pairing"]
        self.assertAlmostEqual(pairing["source_pairing"], 1.0e-30, places=44)
        self.assertAlmostEqual(pairing["destination_pairing"], -1.0e-30, places=44)
        self.assertEqual(pairing["raw_pairing_balance"], 0.0)

    def test_extreme_area_reverse_map_avoids_intermediate_overflow(self):
        # Directly evaluating area*temperature/area would first overflow.
        result = transfer_coupled_surface_exchange(
            one_face_request(1.0e300, 1.0e-300, 1.0e300))
        self.assertEqual(_records(result["destination_integrated_values"]), {"d": -1.0})
        self.assertEqual(_records(result["mapped_source_values"]), {"s": 1.0e300})
        self.assertEqual(result["diagnostics"]["adjoint_pairing"]["raw_pairing_balance"], 0.0)

    def test_nonzero_product_underflow_and_overflow_fail_instead_of_fabricating_zero(self):
        with self.assertRaisesRegex(ValueError, "UNDERFLOW"):
            transfer_coupled_surface_exchange(one_face_request(1.0e-300, 1.0e-30))
        with self.assertRaisesRegex(ValueError, "RANGE"):
            transfer_coupled_surface_exchange(one_face_request(1.0e300, 1.0e300))
        # The forward load and reverse field are representable, but their
        # nonzero bilinear pairing is below binary64 range and must not pass as 0.
        with self.assertRaisesRegex(ValueError, "UNDERFLOW"):
            transfer_coupled_surface_exchange(
                one_face_request(1.0, 0.5, math.ulp(0.0)))

    def test_subnormal_geometry_areas_are_not_admitted(self):
        self.assertGreater(MIN_AREA_M2, math.ulp(0.0))
        raw = request()
        raw["source_patch"]["faces"][0]["area_m2"] = math.ulp(0.0)
        with self.assertRaisesRegex(ValueError, "AREA_RANGE"):
            coupled_surface_context_digest(raw)

    def test_large_signed_totals_cancel_without_intermediate_overflow(self):
        raw = request()
        raw["source_patch"]["faces"] = [
            {"id": f"s{index}", "area_m2": 1.0} for index in range(4)]
        raw["destination_patch"]["faces"] = [
            {"id": f"d{index}", "area_m2": 1.0} for index in range(4)]
        raw["overlaps"] = [
            {"source_face_id": f"s{index}", "destination_face_id": f"d{index}",
             "area_m2": 1.0} for index in range(4)]
        raw["source_values"] = [
            {"face_id": f"s{index}", "value": value}
            for index, value in enumerate((1.0e308, 1.0e308, -1.0e308, -1.0e308))]
        raw["context_digest"] = coupled_surface_context_digest(raw)
        result = transfer_coupled_surface_exchange(raw)
        self.assertEqual(result["diagnostics"]["source_outward_integrated_total"], 0.0)
        self.assertEqual(result["diagnostics"]["destination_outward_integrated_total"], 0.0)
        self.assertEqual(result["diagnostics"]["raw_global_balance"], 0.0)


if __name__ == "__main__":
    unittest.main()
