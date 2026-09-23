import unittest

import pyarrow as pa

from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.geometry_arrow import (
    GEOMETRY_ARROW_CONTRACT_V1, GEOMETRY_ARROW_CONTRACT_V2, GEOMETRY_ARROW_CONTRACT_V3,
    GEOMETRY_ARROW_CONTRACT_V4, GeometryArrowError,
    build_geometry_arrow, canonical_geometry_rows, geometry_arrow_contract, validate_geometry_arrow,
)


def fixture(*, reverse: bool = False, path: bool = False) -> DesignIRV2:
    tracks = [
        {"id": "T2", "net_id": "N1", "layer": "TOP", "start": [1, 0], "end": [2, 0], "width": 0.2},
        {"id": "T1", "net_id": "N1", "layer": "TOP", "start": [0, 0], "end": [1, 0], "width": 0.2},
    ]
    if path:
        for track in tracks:
            step_index = 0 if track["id"] == "T1" else 1
            track.update({
                "path_id": "route-main", "path_step_index": step_index,
                "path_step_count": 2, "path_end_cap": "round", "path_join_style": "round",
            })
    if reverse:
        tracks.reverse()
    legacy = DesignIR(
        design_id="arrow-fixture",
        name="Arrow fixture",
        source_format="fixture",
        layers=[{"id": "L1", "name": "TOP", "type": "copper"}],
        nets=[{"id": "N1", "name": "VCC"}],
        tracks=tracks,
        pads=[{
            "id": "P1", "net_id": "N1", "layer": "TOP", "at": [0, 0], "size": [1, 2],
            "shape": "oval", "drill_size": [0.3, 0.6], "drill_shape": "oval", "plated": True,
        }],
        vias=[{
            "id": "V1", "net_id": "N1", "at": [2, 0], "diameter": 0.8, "drill": 0.4,
            "start_layer": "TOP", "end_layer": "TOP",
        }],
        zones=[{
            "id": "Z1", "net_id": "N1", "layer": "TOP",
            "points": [[0, 0], [2, 0], [2, 2], [0, 2]],
        }],
        metadata={
            "source_sha256": "a" * 64,
            "arcs": [{
                "id": "A1", "net_id": "N1", "layer": "TOP", "start": [2, 0],
                "mid": [2.5, 0.5], "end": [2, 1], "width": 0.2,
            }],
        },
    )
    return DesignIRV2.from_v1(legacy, source_digest="a" * 64)


class GeometryArrowTests(unittest.TestCase):
    def test_generation_is_deterministic_and_round_trips_all_copper_kinds(self):
        design = fixture()
        first = build_geometry_arrow(design)
        second = build_geometry_arrow(fixture(reverse=True))
        self.assertEqual(first, second)
        rows = validate_geometry_arrow(first, design)
        self.assertEqual({row["kind"] for row in rows}, {"track", "arc", "zone", "pad", "via"})
        self.assertEqual(rows, canonical_geometry_rows(design))
        pad = next(row for row in rows if row["kind"] == "pad")
        self.assertEqual((pad["drill_x_mm"], pad["drill_y_mm"], pad["drill_shape"]), (0.3, 0.6, "oval"))

    def test_invalid_bytes_and_wrong_design_binding_fail_closed(self):
        design = fixture()
        data = build_geometry_arrow(design)
        with self.assertRaisesRegex(GeometryArrowError, "valid Arrow IPC"):
            validate_geometry_arrow(data[:64], design)
        other = fixture()
        other.design_id = "different-design"
        with self.assertRaisesRegex(GeometryArrowError, "canonical uncompressed DesignIR projection"):
            validate_geometry_arrow(data, other)

        reader = pa.ipc.open_file(pa.BufferReader(data))
        sink = pa.BufferOutputStream()
        with pa.ipc.new_file(sink, reader.schema, options=pa.ipc.IpcWriteOptions(compression="zstd")) as writer:
            for batch_index in range(reader.num_record_batches):
                writer.write_batch(reader.get_batch(batch_index))
        compressed = sink.getvalue().to_pybytes()
        self.assertNotEqual(compressed, data)
        with self.assertRaisesRegex(GeometryArrowError, "canonical uncompressed DesignIR projection"):
            validate_geometry_arrow(compressed, design)

    def test_validation_enforces_caller_controlled_ipc_and_row_budgets(self):
        design = fixture()
        data = build_geometry_arrow(design)
        with self.assertRaisesRegex(GeometryArrowError, "IPC payload exceeds"):
            validate_geometry_arrow(data, design, max_ipc_bytes=len(data) - 1)
        with self.assertRaisesRegex(GeometryArrowError, "exceeds the 4-row limit"):
            validate_geometry_arrow(data, design, max_rows=4)

    def test_path_projection_uses_deterministic_versioned_arrow_v2(self):
        design = fixture(path=True)
        data = build_geometry_arrow(design)

        self.assertEqual(geometry_arrow_contract(fixture()), GEOMETRY_ARROW_CONTRACT_V1)
        self.assertEqual(geometry_arrow_contract(design), GEOMETRY_ARROW_CONTRACT_V2)
        self.assertEqual(data, build_geometry_arrow(fixture(path=True, reverse=True)))
        rows = validate_geometry_arrow(data, design)
        tracks = sorted(
            (row for row in rows if row["kind"] == "track"),
            key=lambda row: row["path_step_index"],
        )
        self.assertEqual(
            [(row["path_id"], row["path_step_index"], row["path_step_count"], row["path_end_cap"], row["path_join_style"]) for row in tracks],
            [("route-main", 0, 2, "round", "round"), ("route-main", 1, 2, "round", "round")],
        )
        with self.assertRaisesRegex(GeometryArrowError, "contract"):
            validate_geometry_arrow(data, fixture())

    def test_exact_curved_boundaries_use_deterministic_arrow_v3(self):
        legacy = fixture(path=True).to_v1()
        legacy.zones = [{
            "id": "Z-CURVE", "net_name": "VCC", "layer": "TOP",
            "boundary_rings": [
                {"role": "outer", "start_mm": [0, 0], "segments": [
                    {"kind": "line", "end_mm": [3, 0]},
                    {"kind": "line", "end_mm": [3, 3]},
                    {"kind": "line", "end_mm": [0, 3]},
                    {"kind": "line", "end_mm": [0, 0]},
                ]},
                {"role": "cutout", "start_mm": [2, 1.5], "segments": [
                    {"kind": "arc", "end_mm": [1, 1.5], "center_mm": [1.5, 1.5], "clockwise": True},
                    {"kind": "arc", "end_mm": [2, 1.5], "center_mm": [1.5, 1.5], "clockwise": True},
                ]},
            ],
            "fill_style_id": "SOLID", "fill_property": "FILL",
        }]
        design = DesignIRV2.from_v1(legacy)
        data = build_geometry_arrow(design)

        self.assertEqual(geometry_arrow_contract(design), GEOMETRY_ARROW_CONTRACT_V3)
        rows = validate_geometry_arrow(data, design)
        zone = next(row for row in rows if row["kind"] == "zone")
        self.assertEqual((zone["fill_style_id"], zone["fill_property"]), ("SOLID", "FILL"))
        self.assertEqual(zone["boundary_rings"][1]["segments"][0]["center_mm"], {"x_mm": 1.5, "y_mm": 1.5})
        self.assertEqual(data, build_geometry_arrow(DesignIRV2.from_dict(design.to_dict())))

    def test_per_layer_land_profiles_use_deterministic_arrow_v4(self):
        legacy = DesignIR(
            design_id="profile-fixture", name="Profile fixture", source_format="ipc-2581",
            layers=[{"id": "L1", "name": "TOP", "type": "copper"}, {"id": "L2", "name": "BOTTOM", "type": "copper"}],
            nets=[{"id": "N1", "name": "VCC"}],
            vias=[{
                "id": "V1", "net_id": "N1", "at": [1, 2], "diameter": 1.0, "drill": 0.3,
                "layers": ["TOP", "BOTTOM"],
                "land_profiles": [
                    {"layer_id": "TOP", "use": "regular", "shape": "circle", "size_mm": [1.0, 1.0], "offset_mm": [0, 0], "source_primitive_id": "C1"},
                    {"layer_id": "BOTTOM", "use": "regular", "shape": "circle", "size_mm": [0.8, 0.8], "offset_mm": [0, 0], "source_primitive_id": "C2"},
                ],
            }],
            metadata={"source_sha256": "b" * 64, "geometry_solver_ready": False},
        )
        design = DesignIRV2.from_v1(legacy)
        data = build_geometry_arrow(design)

        self.assertEqual(geometry_arrow_contract(design), GEOMETRY_ARROW_CONTRACT_V4)
        self.assertEqual(data, build_geometry_arrow(DesignIRV2.from_dict(design.to_dict())))
        row = validate_geometry_arrow(data, design)[0]
        self.assertEqual(row["land_profiles"][1], {
            "layer_id": design.vias[0].end_layer_id, "use": "regular", "shape": "circle",
            "size_mm": {"x_mm": 0.8, "y_mm": 0.8}, "offset_mm": {"x_mm": 0.0, "y_mm": 0.0},
            "source_primitive_id": "C2",
        })


if __name__ == "__main__":
    unittest.main()
