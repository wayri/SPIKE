"""Create compact, reproducible IPC-2581 importer qualification evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.importers import FunctionImporter, ImporterDescriptor, ImporterRegistry  # noqa: E402
from python.spike_core.ipc2581_importer import import_ipc2581_design  # noqa: E402


OFFICIAL_REV_C_FULL_SHA256 = "6c10fea08943ca7261505bd531a8724bc1dffe8f9fec9e53a2f22d52bc83d347"


def validate_official_rev_c_baseline(digest: str, report: dict[str, object]) -> None:
    """Fail closed if the known official fixture drifts from reviewed v13 counts."""
    if digest != OFFICIAL_REV_C_FULL_SHA256:
        return
    expected_coverage = {
        "layers": 44, "nets": 514, "tracks": 27147, "arcs": 0, "zones": 1,
        "pads": 1611, "vias": 1690, "drills": 1859, "components": 56,
    }
    expected_source = {
        "declared": 39094, "normalized_source_records": 39094,
        "unsupported_or_unresolved": 0, "normalized_retained_negative_contours": 6,
        "normalized_retained_unnetted_pad_occurrences": 36,
        "normalized_retained_nonregular_padstack_occurrences": 345,
        "normalized_retained_standard_contour_land_occurrences": 98,
        "normalized_retained_standard_contour_land_declared_layer_matches": 32,
        "normalized_retained_standard_contour_land_declared_layer_mismatches": 66,
        "normalized_heterogeneous_land_profiles": 1152,
    }
    expected_contour_land_observations = [
        {"declared_regular_layer_id": "TOP", "observed_layer_id": "BOTTOM", "rotation_deg": 360.0, "mirror": True, "count": 66},
        {"declared_regular_layer_id": "TOP", "observed_layer_id": "TOP", "rotation_deg": 90.0, "mirror": False, "count": 32},
    ]
    coverage = report.get("coverage")
    source = report.get("source_geometry")
    readiness = report.get("solver_readiness")
    if not isinstance(coverage, dict) or any(coverage.get(key) != value for key, value in expected_coverage.items()):
        raise ValueError("Official IPC-2581 Rev C typed coverage differs from the reviewed v13 baseline")
    if not isinstance(source, dict) or any(source.get(key) != value for key, value in expected_source.items()):
        raise ValueError("Official IPC-2581 Rev C source accounting differs from the reviewed v13 baseline")
    empirical = source.get("retained_standard_contour_land_empirical_distribution")
    if not isinstance(empirical, dict) or empirical.get("label") != "empirical_source_observation_not_conformance":
        raise ValueError("Official IPC-2581 Rev C contour-land observations must be explicitly empirical")
    if empirical.get("occurrences") != expected_contour_land_observations:
        raise ValueError("Official IPC-2581 Rev C contour-land occurrence observations differ from the reviewed empirical baseline")
    profiles = empirical.get("profile_xforms")
    if not isinstance(profiles, list) or not profiles or any(
        not isinstance(item, dict) or item.get("rotation_deg") != 0.0 or item.get("mirror") is not False
        for item in profiles
    ):
        raise ValueError("Official IPC-2581 Rev C contour-land profile Xforms must retain the reviewed empirical identity facts")
    if report.get("parser_revision") != "ipc2581-conductor-primitives-v13":
        raise ValueError("Official IPC-2581 Rev C fixture was not parsed by the reviewed v13 adapter")
    if not isinstance(readiness, dict) or not readiness or any(
        not isinstance(value, dict) or value.get("ready") is not False
        for value in readiness.values()
    ):
        raise ValueError("Official IPC-2581 Rev C fixture must remain solver-ineligible")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--expected-sha256", default="")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--output", type=Path, default=ROOT / "build/ipc2581-fixture-qualification.json")
    args = parser.parse_args()

    fixture = args.fixture.resolve()
    digest = sha256_file(fixture)
    expected = args.expected_sha256.strip().lower()
    if expected and digest != expected:
        raise ValueError(f"Fixture SHA-256 mismatch: expected {expected}, got {digest}")

    registry = ImporterRegistry([FunctionImporter(
        descriptor=ImporterDescriptor(
            importer_id="ipc-2581",
            display_name="IPC-2581",
            source_formats=("ipc-2581", "ipc2581"),
            extensions=(fixture.suffix,),
        ),
        implementation=import_ipc2581_design,
    )])
    outcome = registry.import_outcome(str(fixture), "ipc-2581")
    metadata = outcome.design.metadata
    diagnostics = Counter(str(item.get("code", "UNKNOWN")) for item in outcome.report.diagnostics)
    report = {
        "contract": "spike/ipc2581-fixture-qualification/v1",
        "status": "passed_with_declared_gaps" if outcome.report.status != "completed" else "passed",
        "fixture": {
            "path": str(fixture),
            "bytes": fixture.stat().st_size,
            "sha256": digest,
            "source_url": args.source_url,
        },
        "parser_revision": metadata.get("parser_revision"),
        "ipc2581_revision": metadata.get("ipc2581_revision"),
        "coverage": outcome.report.coverage,
        "source_geometry": metadata.get("geometry_coverage", {}),
        "solver_readiness": outcome.report.solver_readiness,
        "diagnostics": dict(sorted(diagnostics.items())),
        "omitted_geometry_diagnostics": metadata.get("omitted_geometry_diagnostics", 0),
    }
    validate_official_rev_c_baseline(digest, report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"IPC-2581 fixture qualification: {report['status']}")
    print(f"Typed pads/vias: {outcome.report.coverage['pads']}/{outcome.report.coverage['vias']}")
    print(f"Unsupported/unresolved source geometry: {report['source_geometry'].get('unsupported_or_unresolved', 0)}")
    print(f"Report: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
