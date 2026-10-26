# SPDX-License-Identifier: Apache-2.0
"""Curate complete existing snapshots, provenance and original preview captures.

No solver runs, trimming, CAD authoring or numerical transformation occur here.
Run from the repository root: python -m examples.promo_release.build
"""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

from python.spike_core.project_package import read_project
from python.spike_core.project_state_artifacts import hydrate_result_state
from python.spike_core.service_project import frontend_project_payload

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PACK = ROOT / "output/promo-showcase-20261023/READY_TO_OPEN"
PROJECTS = [
    ("ebrake-transient", "01-pcb-temperature/01-ebrake-transient/01-ebrake-transient.spike"),
    ("case-contact", "02-case-heatsink/case-contact.spike"),
    ("poor-contact", "02-case-heatsink/poor-contact.spike"),
    ("planar-pm", "05-em-machines/planar_pm_fem.spike"),
    ("motor", "05-em-machines/motor.spike"),
    ("electromagnet", "05-em-machines/electromagnet.spike"),
    ("electromagnet-air", "05-em-machines/electromagnet-air.spike"),
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value, compact=False):
    path.write_text(json.dumps(value, ensure_ascii=True, allow_nan=False, indent=None if compact else 2,
                               separators=(",", ":") if compact else None) + "\n", encoding="utf-8")


def main():
    (HERE / "projects").mkdir(exist_ok=True)
    (HERE / "pictures").mkdir(exist_ok=True)
    receipt = {"contract": "spike/promo-release-curation/v1", "date": "2026-10-26",
               "license": "Apache-2.0; original SPIKE-owned inputs, generated results and UI captures",
               "owner": "wayri and SPIKE contributors", "solver_runs_performed": False,
               "installed_desktop_capture": False, "projects": [], "copies": []}
    for name, relative in PROJECTS:
        source = PACK / relative
        opened = read_project(source, include_members=False)
        projected = frontend_project_payload(hydrate_result_state(
            opened.payload, source, opened.manifest["manifest_payload_sha256"]))
        target = HERE / "projects" / (name + ".spike.json")
        write_json(target, projected, compact=True)
        assert target.stat().st_size <= (8 if name == "ebrake-transient" else 4) * 1024 * 1024
        # JSON normalizes Python tuples to arrays; compare the complete encoding.
        assert json.dumps(json.loads(target.read_text(encoding="utf-8")), sort_keys=True) == json.dumps(projected, sort_keys=True)
        receipt["projects"].append({"id": name, "source": source.relative_to(ROOT).as_posix(),
            "source_sha256": sha(source.read_bytes()), "source_bytes": source.stat().st_size,
            "manifest_payload_sha256": opened.manifest["manifest_payload_sha256"],
            "snapshot": target.relative_to(ROOT).as_posix(), "snapshot_sha256": sha(target.read_bytes()),
            "snapshot_bytes": target.stat().st_size,
            "projection": "Complete existing frontend_project_payload after hydrate_result_state; no arrays removed",
            "cad_member_limit": "Case STEP companion requires relinking for CAD display; thermal mesh/results retained" if "contact" in name else "External component model binaries are not included"})
    copies = [
        (ROOT / "LICENSE", HERE / "LICENSE"),
        (ROOT / "NOTICE", HERE / "NOTICE"),
        (ROOT / "docs/DEMO_BOARD_PROVENANCE.md", HERE / "DEMO_BOARD_PROVENANCE.md"),
        (ROOT / "examples/promo_showcase/START_HERE.md", HERE / "ORIGINAL_START_HERE.md"),
        (ROOT / "examples/promo_showcase/electrical/source-provenance.json", HERE / "original-electrical-provenance.json"),
        (PACK / "EVIDENCE/integration-verification.json", HERE / "original-integration-verification.json"),
        (ROOT / "examples/promo_showcase/electrical/magnetics/planar_solenoid_fem.json", HERE / "solenoid-request.json"),
        (ROOT / "artifacts/real-board-multiphysics-20261025/preview/verification.json", HERE / "capture-verification.json"),
        (ROOT / "artifacts/real-board-multiphysics-20261025/em/FIELD_LINE_METHOD_REVIEW.md", HERE / "FIELD_LINE_METHOD_REVIEW.md"),
        (ROOT / "artifacts/real-board-multiphysics-20261025/em/field-line-execution.json", HERE / "field-line-execution.json"),
    ]
    capture = json.loads((ROOT / "artifacts/real-board-multiphysics-20261025/preview/verification.json").read_text())
    for name in ("electric-field-lines.png", "magnetic-field-lines.png"):
        source = ROOT / "artifacts/real-board-multiphysics-20261025/preview" / name
        assert sha(source.read_bytes()) == capture["screenshots"][name]["sha256"]
        copies.append((source, HERE / "pictures" / name))
    for source, target in copies:
        shutil.copyfile(source, target)
        receipt["copies"].append({"source": source.relative_to(ROOT).as_posix(),
            "target": target.relative_to(ROOT).as_posix(), "sha256": sha(target.read_bytes()),
            "bytes": target.stat().st_size, "modified": False})
    with zipfile.ZipFile(PACK / "02-case-heatsink/case-contact.spike") as archive:
        data = archive.read("models/artifacts/original-case.step")
        (HERE / "original-case.step").write_bytes(data)
        receipt["copies"].append({"source": "output/promo-showcase-20261023/READY_TO_OPEN/02-case-heatsink/case-contact.spike#models/artifacts/original-case.step",
            "target": "examples/promo_release/original-case.step", "sha256": sha(data), "bytes": len(data), "modified": False})
    write_json(HERE / "provenance.json", receipt)
    total = sum(path.stat().st_size for path in HERE.rglob("*") if path.is_file())
    assert total < 20 * 1024 * 1024
    print(json.dumps({"projects": len(PROJECTS), "curated_bytes": total, "source_identity_and_complete_projection": "passed"}))


if __name__ == "__main__":
    main()
