import copy
import unittest

from python.spike_core.capability_ledger import (
    CAPABILITY_LEDGER_CONTRACT,
    CapabilityLedgerError,
    native_capability_ledger,
    release_ready_workflows,
    validate_capability_ledger,
    workflow_capability,
)


class CapabilityLedgerTests(unittest.TestCase):
    def test_ledger_covers_requested_domains_with_native_owners(self):
        ledger = native_capability_ledger()
        workflows = ledger["workflows"]

        self.assertEqual(ledger["contract"], CAPABILITY_LEDGER_CONTRACT)
        self.assertTrue(ledger["policy"]["released_ui_requires_native_owner"])
        self.assertTrue({"pi", "circuit", "thermal", "si", "emi", "magnetics", "multiphysics"}.issubset(
            {item["domain"] for item in workflows}
        ))
        for workflow in workflows:
            self.assertTrue(workflow["native_owner"].startswith("spike.native."))
            self.assertTrue(workflow["required_design_ir_entities"])
            self.assertTrue(workflow["blocking_error_codes"])
            self.assertTrue(all(engine.startswith("external.") for engine in workflow["external_comparison_engines"]))

    def test_ledger_exposes_exact_workflow_and_does_not_release_unsupported_paths(self):
        pdn = workflow_capability("pi.pdn_target_and_capacitor_optimization")

        self.assertEqual(pdn["native_owner"], "spike.native.pdn_optimizer")
        self.assertEqual(pdn["validation_state"], "experimental")
        self.assertIn("pdn_two_port_capacitor_loading_circuit_reference", pdn["validation_evidence"])
        self.assertEqual(release_ready_workflows(), [])
        with self.assertRaisesRegex(CapabilityLedgerError, "Unknown capability-ledger workflow"):
            workflow_capability("unknown.workflow")

    def test_ledger_rejects_external_only_owner_and_invalid_error_code(self):
        invalid_owner = copy.deepcopy(native_capability_ledger())
        invalid_owner["workflows"][0]["native_owner"] = "external.openems"
        with self.assertRaisesRegex(CapabilityLedgerError, "native_owner"):
            validate_capability_ledger(invalid_owner)

        invalid_error = copy.deepcopy(native_capability_ledger())
        invalid_error["workflows"][0]["blocking_error_codes"] = ["INVALID"]
        with self.assertRaisesRegex(CapabilityLedgerError, "unregistered blocking error code"):
            validate_capability_ledger(invalid_error)

    def test_validated_state_requires_digest_bound_qualification(self):
        invalid = copy.deepcopy(native_capability_ledger())
        workflow = invalid["workflows"][0]
        workflow["release_state"] = "reference_validated"
        workflow["validation_state"] = "reference_validated"
        workflow["validation_evidence"] = ["fixture"]
        with self.assertRaisesRegex(CapabilityLedgerError, "digest-bound release_qualification"):
            validate_capability_ledger(invalid)

        workflow["release_qualification"] = {
            "evidence_id": "fixture-evidence",
            "profile_id": "fixture-profile",
            "artifact_uri": "pi/fixture-evidence.json",
            "sha256": "a" * 64,
        }
        validated = validate_capability_ledger(invalid)
        self.assertEqual(validated["workflows"][0]["release_qualification"]["sha256"], "a" * 64)


if __name__ == "__main__":
    unittest.main()
