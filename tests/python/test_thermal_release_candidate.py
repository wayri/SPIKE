from __future__ import annotations

import copy
import hashlib
import json
import unittest

from python.spike_core.thermal_release_candidate import (
    CANDIDATE_CONTRACT,
    PACKAGE_IDENTITY_CONTRACT,
    evaluate_thermal_release_candidate,
    validate_package_identity,
)


def digest(index: int) -> str:
    return f"{index:064x}"


def attest(record: dict) -> dict:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n"
    return {
        "contract": "spike/manifest-signature/v1", "algorithm": "ed25519", "key_id": "test-trust-root",
        "signed_payload_sha256": hashlib.sha256(payload).hexdigest(), "signature_base64url": "test-attested",
    }


def trusted_verifier(payload: bytes, signature: dict) -> bool:
    return signature.get("signature_base64url") == "test-attested" and signature.get("signed_payload_sha256") == hashlib.sha256(payload).hexdigest()


def identity(platform: str) -> dict:
    record = {
        "contract": PACKAGE_IDENTITY_CONTRACT,
        "platform": platform,
        "solver": {"id": "fixture.thermal", "version": "1.0.0"},
        "adapter_sha256": digest(1),
        "runtime": {"id": f"runtime-{platform}", "version": "1", "sha256": digest(2)},
        "package": {"id": f"package-{platform}", "version": "1", "sha256": digest(3)},
    }
    return {**record, "attestation": attest(record)}


def candidate() -> dict:
    return {
        "contract": CANDIDATE_CONTRACT,
        "solver": {"id": "fixture.thermal", "version": "1.0.0"},
        "records": {
            "layered_contact": {
                "layers": [
                    {"thickness_m": 0.001, "conductivity_w_mk": 200},
                    {"thickness_m": 0.002, "conductivity_w_mk": 2},
                ],
                "area_m2": 1e-4, "contact_resistances_k_per_w": [0.5],
                "heat_w": 3, "cold_temperature_k": 300, "relative_tolerance": 0.002,
                "result": {"hot_temperature_k": 331.65, "conducted_heat_w": 3, "energy_residual_w": 0},
            },
            "mesh_relative_tolerance": 0.001,
            "mesh_levels": [
                {"cells": 100, "hot_temperature_k": 330.0},
                {"cells": 400, "hot_temperature_k": 331.0},
                {"cells": 1600, "hot_temperature_k": 331.2},
            ],
            "time_relative_tolerance": 0.001,
            "time_levels": [
                {"time_step_s": 1e-3, "hot_temperature_k": 331.0},
                {"time_step_s": 5e-4, "hot_temperature_k": 331.15},
                {"time_step_s": 2.5e-4, "hot_temperature_k": 331.2},
            ],
        },
        "package_identities": [identity("windows-x64"), identity("linux-x64")],
        "references": [],
    }


def reference(identifier: str, kind: str, index: int) -> dict:
    record = {"id": identifier, "type": kind, "status": "passed", "reference_artifact_sha256": digest(index), "result_sha256": digest(index + 1)}
    return {**record, "attestation": attest(record)}


class ThermalReleaseCandidateTests(unittest.TestCase):
    def test_complete_candidate_is_digest_bound_and_valid(self) -> None:
        value = candidate(); value["references"] = [reference("trusted-fem", "independent_solver", 4), reference("lab-fixture", "measured", 6)]
        report = evaluate_thermal_release_candidate(value, evidence_verifier=trusted_verifier)
        self.assertTrue(report["valid"], report)
        self.assertEqual(len(report["candidate_digest"]), 64)
        self.assertTrue(all(item["passed"] for item in report["checks"]))

    def test_candidate_fails_without_measured_reference_and_linux_identity(self) -> None:
        value = candidate()
        value["references"] = [reference("trusted-fem", "independent_solver", 4)]
        value["package_identities"] = value["package_identities"][:1]
        report = evaluate_thermal_release_candidate(value, evidence_verifier=trusted_verifier)
        self.assertFalse(report["valid"])
        self.assertIn("Windows x64 and Linux x64", " ".join(report["issues"]))
        self.assertIn("measured", " ".join(report["issues"]))

    def test_energy_and_time_convergence_must_pass(self) -> None:
        value = candidate()
        value["references"] = [reference("trusted-fem", "independent_solver", 4), reference("lab-fixture", "measured", 6)]
        value["records"]["layered_contact"]["result"]["energy_residual_w"] = 2
        value["records"]["time_levels"][2]["hot_temperature_k"] = 340
        report = evaluate_thermal_release_candidate(value, evidence_verifier=trusted_verifier)
        self.assertFalse(report["valid"])
        self.assertFalse(report["checks"][0]["passed"])
        self.assertFalse(report["checks"][2]["passed"])

    def test_package_identity_requires_exact_shape_and_solver_identity(self) -> None:
        value = identity("windows-x64")
        self.assertTrue(validate_package_identity(value, solver_id="fixture.thermal", solver_version="1.0.0", verifier=trusted_verifier)["valid"])
        changed = copy.deepcopy(value)
        changed["extra"] = True
        self.assertFalse(validate_package_identity(changed, solver_id="fixture.thermal", solver_version="1.0.0", verifier=trusted_verifier)["valid"])
        changed = copy.deepcopy(value)
        changed["solver"]["version"] = "other"
        self.assertFalse(validate_package_identity(changed, solver_id="fixture.thermal", solver_version="1.0.0", verifier=trusted_verifier)["valid"])

    def test_arbitrary_hashes_cannot_become_valid_without_a_trusted_verifier(self) -> None:
        value = candidate(); value["references"] = [reference("trusted-fem", "independent_solver", 4), reference("lab-fixture", "measured", 6)]
        report = evaluate_thermal_release_candidate(value)
        self.assertFalse(report["valid"])
        self.assertIn("trusted attestation verifier", " ".join(issue for item in report["package_checks"] for issue in item["issues"]))

    def test_tampered_reference_digest_invalidates_its_attestation(self) -> None:
        value = candidate(); value["references"] = [reference("trusted-fem", "independent_solver", 4), reference("lab-fixture", "measured", 6)]
        value["references"][1]["result_sha256"] = digest(99)
        report = evaluate_thermal_release_candidate(value, evidence_verifier=trusted_verifier)
        self.assertFalse(report["valid"])
        self.assertIn("measured", " ".join(report["issues"]))


if __name__ == "__main__":
    unittest.main()
