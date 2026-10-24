// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { exportEMergeCosimulationDraft } = await importTestTypescript("emergeCosimulationDraft");
const fixture = JSON.parse(readFileSync(new URL("../../examples/emerge/gui_workflow/patch_admitted_result.json", import.meta.url), "utf8"));
const before = JSON.stringify(fixture);
const result = exportEMergeCosimulationDraft({ data: { analysis_result: fixture } });
assert.equal(result.name, "emerge-cosimulation.draft.json");
const params = JSON.parse(result.text);
// Standard JS JSON transport canonicalizes -0 to 0. Compare its full wire
// representation, not Object.is signed-zero identity; retain the source file.
assert.equal(JSON.stringify(params.request.result), before);
assert.deepEqual(params.request.result.issues, fixture.issues);
assert.equal(JSON.stringify(fixture), before, "Export never rewrites original source diagnostics");
assert.equal(params.request.binding.digest_sha256, fixture.provenance.design_digest_sha256);
assert.equal(params.request.expected_case_sha256, fixture.provenance.board_case_sha256);
assert.match(params.request.wave_convention, /REQUIRES_EXPLICIT/);
assert.deepEqual(Object.keys(params.request.port_bindings), fixture.networks.s_parameters.ports);
for (const port of Object.values(params.request.port_bindings)) assert.deepEqual(port,
  { positive_node: "", negative_node: "", reference_plane: "" });
for (const key of ["design_digest_sha256", "board_case_sha256", "generated_script_sha256"]) {
  const invalid = structuredClone(fixture); delete invalid.provenance[key];
  assert.throws(() => exportEMergeCosimulationDraft(invalid), /source identity/);
}
const invalid = structuredClone(fixture);
invalid.issues.push({ code: "NOT_CONVERGED", severity: "error", message: "Convergence failed" });
assert.throws(() => exportEMergeCosimulationDraft(invalid), /Blocking source issues/);
const nonfinite = structuredClone(fixture);
nonfinite.summary.unrelated_nonfinite_value = NaN;
assert.throws(() => exportEMergeCosimulationDraft(nonfinite), /nonfinite/,
  "Export must not turn an invalid source number silently into null");
const view = readFileSync(new URL("../src/EMergeExtension.tsx", import.meta.url), "utf8");
assert.match(view, /Export co-simulation draft/);
assert.match(view, /does not run SPICE or convert radiation into heat/);
console.log("EMerge editable co-simulation handoff checks passed.");
