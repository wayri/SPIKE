// SPDX-License-Identifier: Apache-2.0
// Execute generated Python through the real dispatcher with numerical owners replaced.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const source = readFileSync(new URL("../src/pythonWorkspaceTemplates.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
});
const { PYTHON_TEMPLATES } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`);
const routes = [
  ["run-em-resistor-cht", "run_em_network_resistor_cht", "em_network_resistor_cht.run_em_network_resistor_cht"],
  ["run-em-spice-coupling", "run_em_spice_coupling", "em_spice_coupling.run_em_spice_coupling"],
  ["run-em-body-heating", "run_em_body_heating", "em_body_heating.run_em_body_heating"],
  ["run-si-pam3", "simulate_si_pam3", "service_si_pam3.simulate_pam3_request"],
  ["run-cfd-tetra-cht", "run_cfd_tetra_cht", "cfd_tetra_cht.solve_cfd_tetra_cht"],
  ["run-pdn-electrostatic", "extract_pdn_electrostatic", "pdn_electrostatic.extract_pdn_electrostatic"],
  ["run-pdn-dielectric-ac", "extract_pdn_dielectric_ac", "pdn_dielectric_ac.extract_pdn_dielectric_ac"],
  ["run-pdn-admittance", "reduce_pdn_admittance", "pdn_admittance_reduction.reduce_pdn_admittance"],
  ["run-assembly-structural", "run_assembly_tetra_structural", "assembly_tetra_structural.run_assembly_tetra_structural"],
  ["run-assembly-thermomechanical", "run_assembly_thermomechanical", "assembly_thermomechanical.run_assembly_thermomechanical"],
].map(([id, method, owner]) => {
  const template = PYTHON_TEMPLATES.find(item => item.id === id);
  assert.ok(template, `Missing solver runner ${id}`);
  return { id, method, owner, code: template.code };
});

const probe = String.raw`
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from python.spike_core.service import handle

routes = json.load(sys.stdin)
class Spike:
    design = {"design_id": "loaded-design"}
    def __init__(self, expected):
        self.expected = expected
        self.calls = []
    def call(self, method, params):
        assert method == self.expected, (method, self.expected)
        self.calls.append((method, copy.deepcopy(params)))
        response = handle({"method": method, "params": params})
        if not response["ok"]:
            raise RuntimeError(json.dumps(response))
        return response["result"]
    def publish_result(self, value):
        raise AssertionError("Specialized results must never be automatically published")

def execute(code, spike):
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(code, "<solver-template>", "exec"), {"spike": spike})

with tempfile.TemporaryDirectory(prefix="spike-solver-template-") as temporary:
    request_path = Path(temporary) / "request.json"
    for route in routes:
        client = Spike(route["method"])
        execute(route["code"], client)
        assert not client.calls, route["id"]
        runnable = route["code"].replace("REQUEST_FILE = None", "REQUEST_FILE = " + repr(str(request_path)))
        for invalid in ({}, {"request": []}):
            request_path.write_text(json.dumps(invalid), encoding="utf-8")
            try:
                execute(runnable, client)
            except ValueError:
                pass
            else:
                raise AssertionError("Template admitted missing/non-object request: " + route["id"])
            assert not client.calls
        original = {"request": {"fixture": route["id"], "source_identity": "retained"}}
        request_path.write_text(json.dumps(original), encoding="utf-8")
        record = {"contract": "spike/template-test-result/v1", "model_status": "experimental",
                  "production_qualified": False, "diagnostics": [{"message": "retained child evidence"}]}
        # The electrostatic service enriches the result with the existing PDN element adapter.
        if route["method"] == "extract_pdn_electrostatic":
            record.update(reference_electrode={"node": "return"}, model={}, input_digest="input",
                          context_digest="context", nodes=[], matrix_f=[], mesh_digest="mesh")
        output = Path(temporary) / (route["id"] + ".json")
        exporting = runnable.replace("RESULT_FILE = None", "RESULT_FILE = " + repr(str(output)))
        with patch("python.spike_core." + route["owner"], return_value=record) as numerical_owner, \
             patch("python.spike_core.pdn_shunt_capacitance.pdn_capacitor_elements", return_value=[]):
            execute(exporting, client)
            numerical_owner.assert_called_once_with(original["request"])
            assert client.calls == [(route["method"], original)]
            saved = json.loads(output.read_text(encoding="utf-8"))
            assert saved["diagnostics"] == record["diagnostics"]
            assert saved["production_qualified"] is False
            before = output.read_bytes()
            try:
                execute(exporting, client)
            except FileExistsError:
                pass
            else:
                raise AssertionError("Existing export was overwritten")
            assert output.read_bytes() == before
            try:
                execute(runnable.replace("PUBLISH_RESULT = False", "PUBLISH_RESULT = True"), client)
            except ValueError as exc:
                assert "not a publishable" in str(exc)
            else:
                raise AssertionError("Specialized result passed board publication gate")
        with patch("python.spike_core." + route["owner"], side_effect=ValueError("retained admission failure")):
            try:
                execute(runnable, client)
            except RuntimeError as exc:
                assert "retained admission failure" in str(exc)
            else:
                raise AssertionError("Worker admission failure was lost")
print(str(len(routes)) + " solver templates: guarded execution, real dispatch, owner inputs, result evidence, no overwrite and publication gates passed")
`;
const localPython=fileURLToPath(new URL(process.platform==="win32"?"../../.venv/Scripts/python.exe":"../../.venv/bin/python",import.meta.url));
const python = process.env.PYTHON || (existsSync(localPython)?localPython:(process.platform === "win32" ? "python" : "python3"));
const result = spawnSync(python, ["-B", "-c", probe], {
  cwd: fileURLToPath(new URL("../../", import.meta.url)),
  input: JSON.stringify(routes), encoding: "utf8", timeout: 120000,
});
assert.equal(result.status, 0, result.stderr || result.error?.message);
console.log(result.stdout.trim());
