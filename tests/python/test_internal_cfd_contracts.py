# SPDX-License-Identifier: Apache-2.0
"""Schema/semantic alignment and actual public CFD process round trips."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from jsonschema import Draft202012Validator
from python.spike_core.native_cht import REQUEST, executable_path, run_native_cht
from python.spike_core.coupled_surface_exchange import transfer_coupled_surface_exchange
from tests.python.test_coupled_surface_exchange import request as exchange_fixture

ROOT = Path(__file__).resolve().parents[2]


def validator(name):
    return Draft202012Validator(json.loads((ROOT/"schemas"/(name+"-v1.schema.json")).read_text()))


class InternalCfdContractTests(unittest.TestCase):
    def test_new_schemas_and_catalog_are_complete(self):
        catalog = json.loads((ROOT/"schemas/manifest.json").read_text())["schemas"]
        for name in ("native-cht-request", "native-cht-result",
                     "coupled-surface-exchange-request", "coupled-surface-exchange-result"):
            schema = validator(name)
            schema.check_schema(schema.schema)
            self.assertEqual(catalog[f"spike/{name}/v1"], name+"-v1.schema.json")

    def test_all_checked_in_native_requests_validate(self):
        schema = validator("native-cht-request")
        for path in (ROOT/"examples/internal_cfd").glob("*.json"):
            schema.validate(json.loads(path.read_text()))
        for change in ({"n": True}, {"n": 9}, {"executable": "x"}, {"timeout_s": 2.5}):
            self.assertFalse(schema.is_valid({"contract": REQUEST, **change}))

    def test_actual_heat_and_traction_exchange_contracts_and_units(self):
        schema = validator("coupled-surface-exchange-request")
        result_schema = validator("coupled-surface-exchange-result")
        for quantity in ("heat_flux", "traction"):
            for paired in (False, True):
                r = exchange_fixture(quantity, paired=paired)
                schema.validate(r)
                result_schema.validate(transfer_coupled_surface_exchange(r))
                bad = deepcopy(r)
                bad["source_values"][0]["value"] = [1, 2, 3] if quantity == "heat_flux" else 1
                self.assertFalse(schema.is_valid(bad))
                bad = {**r, "destination_value_unit": "K"}
                if not paired:
                    self.assertFalse(schema.is_valid(bad))

    def test_actual_surface_exchange_cli_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            request, output = Path(directory)/"request.json", Path(directory)/"result.json"
            request.write_text(json.dumps(exchange_fixture("traction", paired=True)))
            r = subprocess.run([sys.executable, str(ROOT/"scripts/run_cfd.py"), "--engine", "surface-exchange",
                "--request", str(request), "--output", str(output)], capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            result = json.loads(output.read_text())["result"]
            validator("coupled-surface-exchange-result").validate(result)
            self.assertEqual(result["diagnostics"]["adjoint_pairing"]["unit"], "W")
            self.assertLess(result["diagnostics"]["maximum_absolute_balance"], 1e-12)

    def test_actual_source_worker_exposes_exchange_and_capability(self):
        from python.spike_core.headless import run_request
        response = run_request({"method": "run_coupled_surface_exchange",
            "params": {"request": exchange_fixture("traction", paired=True)}}, timeout_seconds=45)
        self.assertTrue(response["ok"], response)
        validator("coupled-surface-exchange-result").validate(response["result"])
        capability = run_request({"method": "cfd_capabilities", "params": {}}, timeout_seconds=45)
        self.assertTrue(capability["ok"], capability)
        self.assertIn("spike.native_cht", capability["result"]["engines"])
        self.assertFalse(capability["result"]["coupling"]["surface_exchange"]["two_way_fsi"])

    @unittest.skipUnless(executable_path().is_file(), "native CHT executable not built")
    def test_actual_converged_and_failed_native_result_schemas(self):
        for change in ({"lid_velocity_m_s": 0}, {"max_flow_steps": 1}):
            result = run_native_cht({"contract": REQUEST, "n": 8, **change})
            validator("native-cht-result").validate(result)
            bad = {**result, "production_qualified": True}
            self.assertFalse(validator("native-cht-result").is_valid(bad))

    @unittest.skipUnless(executable_path().is_file(), "native CHT executable not built")
    def test_actual_source_worker_exposes_native_cht(self):
        from python.spike_core.headless import run_request
        response = run_request({"method": "run_native_cht", "params": {"request": {
            "contract": REQUEST, "n": 8, "lid_velocity_m_s": 0}}}, timeout_seconds=45)
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["status"], "converged")
        validator("native-cht-result").validate(response["result"])


if __name__ == "__main__":
    unittest.main()
