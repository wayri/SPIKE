# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Transport/provenance tests only; actual physics checks live in native tests."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.verify_native_momentum_runtime import verify_native_momentum_runtime


class PackagedMomentumTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.worker = Path(self.temp.name) / "spike-worker.exe"
        self.worker.write_bytes(b"worker")
        self.native = self.worker.parent / "_internal/native/spike_native_cht.exe"
        self.native.parent.mkdir(parents=True)
        self.native.write_bytes(b"native")
        self.digest = hashlib.sha256(b"native").hexdigest()
        self.result = {"contract": "spike/native-cht-result/v1", "status": "converged",
            "model_status": "experimental", "production_qualified": False,
            "settings": {"n": 8, "lid_velocity_m_s": 1.},
            "scales": {"actual_reynolds": 100.}, "diagnostics": {
                "independent_momentum_verified": True,
                "independent_momentum_arithmetic": "exact_rational_binary_inputs",
                "independent_momentum_residual_linf": 1e-8,
                "independent_momentum_residual_limit": 2e-7},
            "fields": {"fluid": {"u_m_s": [.1]*64, "v_m_s": [0.]*64,
                                 "gauge_pressure_pa": [0.]*64}},
            "provenance": {"executable_sha256": self.digest}}

    def transport(self, worker, method, params):
        if method == "cfd_capabilities":
            return {"ok": True, "result": {"engines": {"spike.native_cht": {
                "available": True, "executable": str(self.native)}}}}
        self.assertEqual(method, "run_native_cht")
        self.assertEqual(params["request"]["lid_velocity_m_s"], 1.)
        return {"ok": True, "result": self.result}

    def test_valid_transport(self):
        result = verify_native_momentum_runtime(self.worker, self.transport)
        self.assertEqual(result["status"], "passed")
        self.assertFalse(result["production_qualified"])
        self.assertEqual(result["native_binary_sha256"], self.digest)

    def test_invalid_diagnostic_or_fields_reject(self):
        original = deepcopy(self.result)
        mutations = [
            lambda r: r["diagnostics"].pop("independent_momentum_verified"),
            lambda r: r["diagnostics"].update(independent_momentum_verified=False),
            lambda r: r["diagnostics"].update(independent_momentum_residual_linf=float("nan")),
            lambda r: r["diagnostics"].update(independent_momentum_residual_linf=1.),
            lambda r: r["diagnostics"].update(independent_momentum_residual_limit=0.),
            lambda r: r.update(production_qualified=True),
            lambda r: r.update(status="failed_to_converge"),
            lambda r: r["scales"].update(actual_reynolds=1.),
            lambda r: r["fields"]["fluid"].update(u_m_s=[0.]*64),
            lambda r: r["fields"]["fluid"].update(gauge_pressure_pa=[float("inf")]*64),
            lambda r: r["provenance"].update(executable_sha256="0"*64),
        ]
        for mutate in mutations:
            self.result = deepcopy(original)
            mutate(self.result)
            with self.subTest(mutate=mutate), self.assertRaises(RuntimeError):
                verify_native_momentum_runtime(self.worker, self.transport)

    def test_malformed_responses_reject(self):
        for malformed in (None, [], {}, {"ok": True, "result": None}):
            with self.subTest(malformed=malformed), self.assertRaises(RuntimeError):
                verify_native_momentum_runtime(self.worker, lambda *args: malformed)

    def test_native_change_during_execution_rejects(self):
        def transport(*args):
            result = self.transport(*args)
            if args[1] == "run_native_cht":
                self.native.write_bytes(b"changed")
            return result
        with self.assertRaises(RuntimeError):
            verify_native_momentum_runtime(self.worker, transport)
