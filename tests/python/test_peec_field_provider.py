import unittest
from unittest.mock import patch

from python.spike_core.contracts import AnalysisResult, AnalysisSpec, DesignIR, ValidationIssue
from python.spike_core.field_circuit_cosim import FIELD_REQUEST_CONTRACT, FIELD_RESULT_CONTRACT
from python.spike_core.peec_field_provider import NativePeecFieldReductionProvider


def spec():
    return AnalysisSpec(analysis_id="peec-ac-1", mode="ac", net_names=["VDD"])


def field_request(**mapping_overrides):
    mapping = {
        "id": "path",
        "source_result_id": "peec-ac-1",
        "source_network_index": 0,
        "source_mesh_nodes": [10, 42],
        "net": "VDD",
    }
    mapping.update(mapping_overrides)
    return {
        "contract": FIELD_REQUEST_CONTRACT,
        "parasitics": [mapping],
    }


def extraction_result():
    return AnalysisResult(
        analysis_id="peec-ac-1",
        mode="ac",
        status="completed",
        model_status="approximate",
        networks={"parasitics": [{
            "contract": "spike/rlgc-network/v1",
            "net": "VDD",
            "source_node": 10,
            "sink_node": 42,
            "resistance_ohm": 0.012,
            "inductance_h": 3.4e-9,
            "capacitance_f": 18e-12,
            "conductance_s": 2e-8,
        }]},
        provenance={"solver": "spike-peec-native/v0.4", "formulation": "peec"},
    )


class NativePeecFieldProviderTests(unittest.TestCase):
    def test_requires_ac_mode_and_stable_analysis_id(self):
        with self.assertRaisesRegex(ValueError, "AC extraction mode"):
            NativePeecFieldReductionProvider(DesignIR(), AnalysisSpec(analysis_id="dc", mode="dc"))
        with self.assertRaisesRegex(ValueError, "stable analysis_id"):
            NativePeecFieldReductionProvider(DesignIR(), AnalysisSpec(mode="ac"))

    @patch("python.spike_core.peec_field_provider.solve_peec_2_5d")
    def test_maps_exact_reviewed_network_without_changing_topology(self, solve):
        solve.return_value = extraction_result()
        result = NativePeecFieldReductionProvider(DesignIR(), spec())(field_request())
        self.assertEqual(result["contract"], FIELD_RESULT_CONTRACT)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["parasitics"], [{
            "id": "path",
            "resistance_ohm": 0.012,
            "inductance_h": 3.4e-9,
            "capacitance_f": 18e-12,
            "conductance_s": 2e-8,
        }])
        self.assertFalse(result["diagnostics"]["circuit_state_feedback"])

    @patch("python.spike_core.peec_field_provider.solve_peec_2_5d")
    def test_rejects_completed_extraction_with_unsupported_capacitance(self, solve):
        solve.return_value = extraction_result()
        network = solve.return_value.networks["parasitics"][0]
        network["capacitance_f"] = None
        network["parameter_availability"] = {"capacitance": "unsupported"}

        provider = NativePeecFieldReductionProvider(DesignIR(), spec())
        with self.assertRaisesRegex(ValueError, "capacitance_f.*unsupported"):
            provider(field_request())

    @patch("python.spike_core.peec_field_provider.solve_peec_2_5d")
    def test_rejects_nonphysical_rlcg_values(self, solve):
        provider = NativePeecFieldReductionProvider(DesignIR(), spec())
        for value in (-1.0, float("nan"), float("inf"), True):
            with self.subTest(value=value):
                solve.return_value = extraction_result()
                solve.return_value.networks["parasitics"][0]["resistance_ohm"] = value
                with self.assertRaisesRegex(ValueError, "resistance_ohm.*finite"):
                    provider(field_request())

    @patch("python.spike_core.peec_field_provider.solve_peec_2_5d")
    def test_preserves_explicit_numeric_zero(self, solve):
        solve.return_value = extraction_result()
        network = solve.return_value.networks["parasitics"][0]
        network["capacitance_f"] = 0.0
        network["conductance_s"] = 0.0

        result = NativePeecFieldReductionProvider(DesignIR(), spec())(field_request())
        self.assertEqual(result["parasitics"][0]["capacitance_f"], 0.0)
        self.assertEqual(result["parasitics"][0]["conductance_s"], 0.0)

    @patch("python.spike_core.peec_field_provider.solve_peec_2_5d")
    def test_rejects_missing_or_unsupported_rlcg_values(self, solve):
        provider = NativePeecFieldReductionProvider(DesignIR(), spec())
        for parameter in (
            "resistance_ohm", "inductance_h", "capacitance_f", "conductance_s"
        ):
            with self.subTest(parameter=parameter):
                solve.return_value = extraction_result()
                solve.return_value.networks["parasitics"][0].pop(parameter)
                with self.assertRaisesRegex(ValueError, parameter):
                    provider(field_request())

        solve.return_value = extraction_result()
        network = solve.return_value.networks["parasitics"][0]
        network["capacitance_f"] = 0.0
        network["parameter_availability"] = {"capacitance": "unsupported"}
        with self.assertRaisesRegex(ValueError, "capacitance_f.*unsupported"):
            provider(field_request())

        solve.return_value = extraction_result()
        solve.return_value.issues.append(ValidationIssue(
            "PEEC_CAPACITANCE_UNSUPPORTED", "warning", "No valid reference conductor",
            status="unsupported",
        ))
        with self.assertRaisesRegex(RuntimeError, "PEEC_CAPACITANCE_UNSUPPORTED"):
            provider(field_request())

    @patch("python.spike_core.peec_field_provider.solve_peec_2_5d")
    def test_rejects_result_net_or_endpoint_identity_changes(self, solve):
        solve.return_value = extraction_result()
        provider = NativePeecFieldReductionProvider(DesignIR(), spec())
        with self.assertRaisesRegex(ValueError, "net identity changed"):
            provider(field_request(net="OTHER"))
        with self.assertRaisesRegex(ValueError, "endpoint identity changed"):
            provider(field_request(source_mesh_nodes=[10, 99]))

    @patch("python.spike_core.peec_field_provider.solve_peec_2_5d")
    def test_requires_exact_reviewed_mesh_endpoint_identity(self, solve):
        solve.return_value = extraction_result()
        provider = NativePeecFieldReductionProvider(DesignIR(), spec())
        for invalid in (None, [10], [10, 42.0], [True, 42], [-1, 42]):
            with self.subTest(source_mesh_nodes=invalid):
                with self.assertRaisesRegex(ValueError, "source_mesh_nodes"):
                    provider(field_request(source_mesh_nodes=invalid))
        for invalid_index in (0.5, True, "0"):
            with self.subTest(source_network_index=invalid_index):
                with self.assertRaisesRegex(ValueError, "integer source_network_index"):
                    provider(field_request(source_network_index=invalid_index))
        solve.return_value.networks["parasitics"][0]["sink_node"] = 99
        with self.assertRaisesRegex(ValueError, "endpoint identity changed"):
            provider(field_request())
        solve.return_value.networks["parasitics"][0]["sink_node"] = True
        with self.assertRaisesRegex(ValueError, "invalid mesh endpoint"):
            provider(field_request(source_mesh_nodes=[10, 1]))

    @patch("python.spike_core.peec_field_provider.solve_peec_2_5d")
    def test_rejects_failed_extraction_and_missing_provenance(self, solve):
        provider = NativePeecFieldReductionProvider(DesignIR(), spec())
        solve.return_value = AnalysisResult(
            analysis_id="peec-ac-1",
            mode="ac",
            status="failed",
            model_status="failed",
            issues=[ValidationIssue("PEEC_FAIL", "error", "fixture failure")],
        )
        with self.assertRaisesRegex(RuntimeError, "fixture failure"):
            provider(field_request())
        solve.return_value = extraction_result()
        with self.assertRaisesRegex(ValueError, "source_network_index"):
            provider(field_request(source_network_index=None))


if __name__ == "__main__":
    unittest.main()
