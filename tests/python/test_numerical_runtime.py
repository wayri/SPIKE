# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Executable pre-import budgets without import-time host mutation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from python.spike_core.numerical_runtime import BLAS_ENVIRONMENT_KEYS, numerical_child_environment

ROOT = Path(__file__).resolve().parents[2]


class NumericalRuntimeTests(unittest.TestCase):
    def test_environment_copy_separates_outer_and_inner_budgets(self):
        base = {"SENTINEL": "preserved", "OMP_NUM_THREADS": "99", "SPIKE_BLAS_THREADS": "99",
                "MKL_DOMAIN_NUM_THREADS": "MKL_DOMAIN_BLAS=32"}
        result = numerical_child_environment(cpu_threads=8, base=base)
        self.assertEqual(base["OMP_NUM_THREADS"], "99")
        self.assertEqual(result["SENTINEL"], "preserved")
        self.assertEqual(result["SPIKE_CPU_THREADS"], "8")
        self.assertEqual(result["NUMBA_NUM_THREADS"], "8")
        self.assertTrue(all(result[key] == "1" for key in BLAS_ENVIRONMENT_KEYS))
        self.assertEqual(result["OMP_MAX_ACTIVE_LEVELS"], "1")
        self.assertNotIn("MKL_DOMAIN_NUM_THREADS", result)
        self.assertIn("MKL_DOMAIN_NUM_THREADS", base)

    def test_explicit_multicore_and_oversubscription_rejection(self):
        env = numerical_child_environment(cpu_threads=8, blas_threads=4, base={})
        self.assertTrue(all(env[key] == "4" for key in BLAS_ENVIRONMENT_KEYS))
        for cpu, blas in ((True, 1), (1, False), (1, 2), (0, 1), (257, 1), (1., 1)):
            with self.subTest(cpu=cpu, blas=blas), self.assertRaises(ValueError):
                numerical_child_environment(cpu_threads=cpu, blas_threads=blas, base={})

    def run_child(self, code, overrides=None):
        env = dict(os.environ)
        for key in (*BLAS_ENVIRONMENT_KEYS, "SPIKE_BLAS_THREADS", "SPIKE_CPU_THREADS", "MKL_DOMAIN_NUM_THREADS"):
            env.pop(key, None)
        env.update(overrides or {})
        return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                              text=True, capture_output=True, timeout=30, check=False)

    def test_plain_import_does_not_change_callers_environment(self):
        result = self.run_child("import os,json; import python.spike_core.numerical_runtime; "
                                "print(json.dumps(os.environ.get('OPENBLAS_NUM_THREADS')))",
                                {"OPENBLAS_NUM_THREADS": "7"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), "7")

    def test_late_bootstrap_refuses_false_reconfiguration(self):
        result = self.run_child(
            "import sys,types; from python.spike_core.numerical_runtime import bootstrap_worker_numerics; "
            "sys.modules['numpy']=types.ModuleType('numpy'); bootstrap_worker_numerics()")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("before NumPy/SciPy", result.stderr)

    def test_executable_entries_apply_budget_before_first_numpy_import(self):
        prefix = """
import builtins, json, os, runpy, sys
original = builtins.__import__
def inspect_import(name, *args, **kwargs):
    if name == 'numpy' or name.startswith('numpy.'):
        print(json.dumps({key: os.environ.get(key) for key in ('SPIKE_CPU_THREADS','SPIKE_BLAS_THREADS','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')}))
        raise SystemExit(0)
    return original(name, *args, **kwargs)
builtins.__import__ = inspect_import
"""
        for target in ("runpy.run_module('python.spike_core.service', run_name='__main__')",
                       "runpy.run_path('scripts/spike_worker_entry.py', run_name='__main__')",
                       "runpy.run_module('python.spike_core', run_name='__main__')"):
            with self.subTest(target=target):
                result = self.run_child(prefix+"\n"+target)
                self.assertEqual(result.returncode, 0, result.stderr)
                record = json.loads(result.stdout)
                self.assertEqual(record["SPIKE_BLAS_THREADS"], "1")
                self.assertEqual(record["OPENBLAS_NUM_THREADS"], "1")
                self.assertEqual(record["OMP_NUM_THREADS"], "1")

    def test_explicit_budget_before_import_and_malformed_rejected(self):
        # Isolate admission semantics from the test runner's CPU affinity.
        code = ("import json; from python.spike_core import numerical_runtime as runtime; "
                "runtime.cpu_thread_budget=lambda:4; print(json.dumps(runtime.bootstrap_worker_numerics()))")
        result = self.run_child(code + "; import os; assert 'MKL_DOMAIN_NUM_THREADS' not in os.environ",
                                {"SPIKE_CPU_THREADS": "4", "SPIKE_BLAS_THREADS": "2",
                                 "MKL_DOMAIN_NUM_THREADS": "MKL_DOMAIN_BLAS=32"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["blas_threads"], 2)
        for value in ("0", "01", " 1", "1;bad", "257"):
            result = self.run_child(code, {"SPIKE_BLAS_THREADS": value})
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
