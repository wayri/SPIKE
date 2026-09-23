import unittest

from python.spike_core.native_solver_contracts import (
    NATIVE_SOLVE_REQUEST_CONTRACT,
    NATIVE_SOLVE_RESULT_CONTRACT,
    NativeSolveRequest,
    NativeSolveResult,
    ResourceEstimate,
    SolveStatus,
    ValidationState,
)


class NativeSolverContractsTests(unittest.TestCase):
    def test_request_serializes_a_typed_resource_budget(self):
        request = NativeSolveRequest(
            request_id="job-001",
            solver_id="spike.native.peec_rlcg",
            workload_id="pi.ac_rlcg",
            design_digest_sha256="a" * 64,
            design_contract="spike/design-ir/v2",
            geometry_contract="spike/native-mesh/v1",
            analysis={"mode": "ac", "frequency_hz": [1000.0, 1000000.0]},
            resource_budget=ResourceEstimate(
                estimated_memory_bytes=2 * 1024 * 1024 * 1024,
                estimated_wall_time_s=12.5,
                recommended_threads=4,
                checkpoint_supported=True,
            ),
            required_entities=("layers", "materials", "nets", "ports"),
            result_fields=("impedance", "inductance", "capacitance"),
        )

        payload = request.to_dict()

        self.assertEqual(payload["contract"], NATIVE_SOLVE_REQUEST_CONTRACT)
        self.assertEqual(payload["resource_budget"]["estimated_memory_bytes"], 2 * 1024 * 1024 * 1024)
        self.assertEqual(payload["required_entities"], ["layers", "materials", "nets", "ports"])

    def test_result_accepts_catalogued_error_codes_and_rejects_noncanonical_codes(self):
        result = NativeSolveResult(
            request_id="job-001",
            solver_id="spike.native.copper_dc",
            status=SolveStatus.BLOCKED,
            validation_state=ValidationState.APPROXIMATE,
            fields={},
            networks={},
            provenance={"solver_version": "0.1"},
            resource_usage={"wall_time_s": 0.0},
            issue_codes=("SPIKE-BE-SOLVER-E-0001",),
        )

        payload = result.to_dict()

        self.assertEqual(payload["contract"], NATIVE_SOLVE_RESULT_CONTRACT)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["issue_codes"], ["SPIKE-BE-SOLVER-E-0001"])
        with self.assertRaisesRegex(ValueError, "Expected SPIKE"):
            NativeSolveResult(
                request_id="job-002",
                solver_id="spike.native.copper_dc",
                status=SolveStatus.FAILED,
                validation_state=ValidationState.UNVALIDATED,
                fields={},
                networks={},
                provenance={},
                resource_usage={},
                issue_codes=("SOLVER_FAILED",),
            )

    def test_contract_rejects_uppercase_digest_and_unsupported_completed_state(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            NativeSolveRequest(
                request_id="job-003",
                solver_id="spike.native.copper_dc",
                workload_id="pi.dc_conduction",
                design_digest_sha256="A" * 64,
                design_contract="spike/design-ir/v2",
                geometry_contract="spike/native-mesh/v1",
                analysis={},
                resource_budget=ResourceEstimate(0, 0.0),
                required_entities=("nets",),
                result_fields=("voltage",),
            )
        with self.assertRaisesRegex(ValueError, "cannot use the unsupported"):
            NativeSolveResult(
                request_id="job-003",
                solver_id="spike.native.copper_dc",
                status=SolveStatus.COMPLETED,
                validation_state=ValidationState.UNSUPPORTED,
                fields={},
                networks={},
                provenance={},
                resource_usage={},
            )


if __name__ == "__main__":
    unittest.main()
