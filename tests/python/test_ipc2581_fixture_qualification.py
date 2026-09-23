import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_module():
    spec = importlib.util.spec_from_file_location(
        "qualify_ipc2581_fixture", ROOT / "scripts" / "qualify_ipc2581_fixture.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Ipc2581FixtureQualificationTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.report = {
            "parser_revision": "ipc2581-conductor-primitives-v13",
            "coverage": {
                "layers": 44, "nets": 514, "tracks": 27147, "arcs": 0, "zones": 1,
                "pads": 1611, "vias": 1690, "drills": 1859, "components": 56,
            },
            "source_geometry": {
                "declared": 39094, "normalized_source_records": 39094,
                "unsupported_or_unresolved": 0, "normalized_retained_negative_contours": 6,
                "normalized_retained_unnetted_pad_occurrences": 36,
                "normalized_retained_nonregular_padstack_occurrences": 345,
                "normalized_retained_standard_contour_land_occurrences": 98,
                "normalized_retained_standard_contour_land_declared_layer_matches": 32,
                "normalized_retained_standard_contour_land_declared_layer_mismatches": 66,
                "normalized_heterogeneous_land_profiles": 1152,
                # These are reviewed fixture observations, not an IPC-2581 conformance claim.
                "retained_standard_contour_land_empirical_distribution": {
                    "label": "empirical_source_observation_not_conformance",
                    "profile_xforms": [{"padstack_ref": "EMPIRICAL", "rotation_deg": 0.0, "mirror": False}],
                    "occurrences": [
                        {"declared_regular_layer_id": "TOP", "observed_layer_id": "BOTTOM", "rotation_deg": 360.0, "mirror": True, "count": 66},
                        {"declared_regular_layer_id": "TOP", "observed_layer_id": "TOP", "rotation_deg": 90.0, "mirror": False, "count": 32},
                    ],
                },
            },
            "solver_readiness": {name: {"ready": False} for name in ("pi_dc", "pi_ac", "si", "thermal", "emi")},
        }

    def test_official_v13_baseline_is_exact_and_solver_ineligible(self):
        self.module.validate_official_rev_c_baseline(
            self.module.OFFICIAL_REV_C_FULL_SHA256, self.report,
        )

    def test_official_v13_baseline_rejects_partition_or_readiness_promotion(self):
        for target in ("count", "partition", "empirical", "readiness"):
            with self.subTest(target=target):
                report = copy.deepcopy(self.report)
                if target == "count":
                    report["source_geometry"]["normalized_retained_standard_contour_land_occurrences"] = 97
                elif target == "partition":
                    report["source_geometry"]["normalized_retained_standard_contour_land_declared_layer_mismatches"] = 65
                elif target == "empirical":
                    report["source_geometry"]["retained_standard_contour_land_empirical_distribution"]["occurrences"][0]["count"] = 65
                else:
                    report["solver_readiness"]["pi_dc"]["ready"] = True
                with self.assertRaises(ValueError):
                    self.module.validate_official_rev_c_baseline(
                        self.module.OFFICIAL_REV_C_FULL_SHA256, report,
                    )


if __name__ == "__main__":
    unittest.main()
