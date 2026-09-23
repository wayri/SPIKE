import unittest

from python.spike_core.benchmarks import run_solver_benchmarks


class SolverBenchmarkTests(unittest.TestCase):
    def test_solver_benchmark_corpus_passes(self):
        report = run_solver_benchmarks()
        failed = [
            item for item in report["benchmarks"]
            if item["status"] == "failed"
        ]
        self.assertEqual(failed, [], failed)
        self.assertEqual(report["status"], "passed")
        pdn = next(
            item for item in report["benchmarks"]
            if item["name"] == "pdn_two_port_capacitor_loading_circuit_reference"
        )
        self.assertEqual(pdn["status"], "passed")
        self.assertLessEqual(pdn["measured"], pdn["tolerance"])


if __name__ == "__main__":
    unittest.main()
