import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from python.spike_core.openfoam_polymesh import (
    OpenFoamPolyMeshError,
    REQUEST_CONTRACT,
    RESULT_CONTRACT,
    compile_polymesh,
    write_polymesh,
)


ROOT = Path(__file__).resolve().parents[2]


def request() -> dict:
    mesh = {
        "contract": "spike/solver-mesh/v1", "units": "mm", "coordinate_system": "right_handed_xyz",
        "vertices": [[0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10], [0, 0, -10]],
        "cells": [
            {"id": "upper", "kind": "tetrahedron", "vertices": [0, 1, 2, 3], "source_object_ids": ["solid:upper"], "material_id": "fr4"},
            {"id": "lower", "kind": "tetrahedron", "vertices": [0, 2, 1, 4], "source_object_ids": ["solid:lower"], "material_id": "fr4"},
        ],
        "object_map": {"solid:upper": {"kind": "solid"}, "solid:lower": {"kind": "solid"}},
        "counts": {"vertices": 5, "cells": 2},
    }
    digest = hashlib.sha256(json.dumps(mesh, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()
    return {
        "contract": REQUEST_CONTRACT, "region_id": "board",
        "mesh": mesh,
        "mesh_evidence": {"id": "mesh-board", "contract": "spike/solver-mesh/v1", "sha256": digest, "qualified": True},
        "boundary_patches": [
            {"name": "outer", "type": "wall", "groups": ["viewFactorWall"], "faces": [[0, 1, 3], [1, 2, 3], [2, 0, 3], [0, 2, 4], [2, 1, 4]]},
            {"name": "coupled", "type": "mappedWall", "faces": [[1, 0, 4]], "neighbour_region": "air", "neighbour_patch": "board_coupled", "interface_id": "board_air"},
        ],
        "cell_zones": [{"name": "upper_source", "cell_ids": ["upper"]}],
    }


class OpenFoamPolyMeshTests(unittest.TestCase):
    def test_materializes_manifold_volume_mesh_with_grouped_boundary(self):
        result = compile_polymesh(request())
        self.assertEqual(result["contract"], RESULT_CONTRACT)
        self.assertEqual(result["counts"], {"points": 5, "cells": 2, "faces": 7, "internal_faces": 1, "boundary_faces": 6})
        self.assertEqual(result["patches"][0]["start_face"], 1)
        self.assertEqual(result["cell_zones"], [{"name": "upper_source", "cell_count": 1}])
        self.assertIn("upper_source", result["files"]["cellZones"])
        self.assertIn("sampleRegion air", result["files"]["boundary"])
        self.assertIn("inGroups 1(viewFactorWall)", result["files"]["boundary"])
        self.assertIn("0.01", result["files"]["points"])

    def test_writes_digest_bound_poly_mesh_files(self):
        with tempfile.TemporaryDirectory() as directory:
            result = write_polymesh(request(), Path(directory) / "polyMesh")
            self.assertEqual(result["status"], "materialized")
            self.assertEqual(set(result["file_digests"]), {"points", "faces", "owner", "neighbour", "boundary", "cellZones"})
            self.assertEqual(result["poly_mesh_digest"], result["poly_mesh_evidence"]["sha256"])
            self.assertTrue((Path(result["poly_mesh_dir"]) / "boundary").is_file())

    def test_rejects_digest_mismatch_and_incomplete_boundary_ownership(self):
        bad_digest = request()
        bad_digest["mesh"]["vertices"][0][0] = 1
        with self.assertRaisesRegex(OpenFoamPolyMeshError, "digest"):
            compile_polymesh(bad_digest)
        missing = request()
        missing["boundary_patches"][0]["faces"].pop()
        with self.assertRaisesRegex(OpenFoamPolyMeshError, "every exterior"):
            compile_polymesh(missing)
        unknown_zone_cell = request()
        unknown_zone_cell["cell_zones"][0]["cell_ids"] = ["missing"]
        with self.assertRaisesRegex(OpenFoamPolyMeshError, "unknown cell ID"):
            compile_polymesh(unknown_zone_cell)
        duplicate_group = request()
        duplicate_group["boundary_patches"][0]["groups"] = ["viewFactorWall", "viewFactorWall"]
        with self.assertRaisesRegex(OpenFoamPolyMeshError, "groups must be unique"):
            compile_polymesh(duplicate_group)

    def test_schema_is_registered_and_rejects_unqualified_mesh(self):
        schema = json.loads((ROOT / "schemas" / "openfoam-polymesh-request-v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(request())
        catalog = json.loads((ROOT / "schemas" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["schemas"][REQUEST_CONTRACT], "openfoam-polymesh-request-v1.schema.json")
        value = copy.deepcopy(request())
        value["mesh_evidence"]["qualified"] = False
        with self.assertRaises(Exception):
            Draft202012Validator(schema).validate(value)


if __name__ == "__main__":
    unittest.main()
