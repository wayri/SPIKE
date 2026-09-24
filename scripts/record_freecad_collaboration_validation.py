"""Record the completed 2026-09-07 checks and their current source digests.

This records observed results; it is not a test runner or a solver qualification.
"""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sources = ["python/spike_core/mcad_session_contract.py", "python/spike_core/service_mcad_collaboration.py",
           "python/spike_core/service_project_assembly.py", "python/spike_core/service_project_mcad_placement.py",
           "app/src/FreecadCollaboration.tsx", "app/src/AssemblyStructureEditor.tsx", "app/src/workerBridge.ts",
           "app/src-tauri/src/lib.rs", "app/src-tauri/src/project_trust_binding.rs",
           "integrations/freecad/SPIKEWorkbench/spike_freecad/collaboration.py",
           "integrations/freecad/SPIKEWorkbench/spike_freecad/collaboration_commands.py",
           "integrations/freecad/SPIKEWorkbench/spike_freecad/session_contract.py",
           "tests/python/test_mcad_collaboration.py", "schemas/mcad-session-v1.schema.json", "schemas/mcad-feedback-v1.schema.json"]
artifact = "artifacts/freecad/SPIKEWorkbench-0.2.0.zip"
record = {
    "date": "2026-09-07", "status": "source_integration_tested", "companion_version": "0.2.0",
    "runtime": "Installed FreeCAD 1.1.3, Windows, headless Part kernel",
    "checks": {"python_tests_passed": 61, "native_host_tests_passed": 35, "native_host_tests_ignored": 1,
               "typescript": "passed", "vite_production_build": "passed_with_large_chunk_warnings",
               "generated_help": "passed", "architecture": "passed", "workbench_zip_integrity": "passed"},
    "real_kernel_evidence": ["board-outline and embedded STEP import", "15 mm gap in retained demo",
        "10 mm separation and 80 mm3 overlap test fixtures", "nested rigid placements", "FCStd save/reopen",
        "SPIKE feedback apply", "unsupported geometry and hierarchy edit rejection"],
    "limitations": ["Native GUI interaction not manually qualified", "No new frozen worker or native installer built",
        "Thermal and other numerical simulation not implemented by this companion increment",
        "Harness route exchange and structural synchronization remain planned"],
    "source_sha256": {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in sources},
    "workbench_zip": {"path": artifact, "sha256": hashlib.sha256((root/artifact).read_bytes()).hexdigest()},
}
(root / "docs/validation/freecad-collaboration-20260907.json").write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
