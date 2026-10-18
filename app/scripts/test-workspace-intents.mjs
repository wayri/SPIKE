// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";
const { suggestWorkspaceIntents: suggest, parseWorkspaceIntentValue: parse, WORKSPACE_INTENT_SCHEMAS: schemas } = await importTestTypescript("workspaceIntentModel");
const context = {
 version: "board:7|assembly:3",
 nets: [{ id: "n1", name: "DATA" }, { id: "n2", name: "DATA CLK" }, { id: "n3", name: "DATA1" }],
 components: [{ id: "a/U21", name: "U21", occurrenceId: "a" }, { id: "b/U21", name: "U21", occurrenceId: "b" }, { id: "a/U22", name: "U22" }, { id: "a/U23", name: "U23" }],
 occurrences: [{ id: "a", name: "Main board" }, { id: "b", name: "Sensor board" }],
 selectedNetIds: ["n1"], selectedComponentIds: ["a/U22"], selectedOccurrenceIds: ["a"],
};
const draft = text => { const rows = suggest(text, context); assert.equal(rows.length, 1, text); return rows[0].draft; };
assert.equal(draft("analyse signal integrity on DATA").workflowKey, "si");
assert.equal(draft("analyse singal integrty on DATA").workflowKey, "si");
assert.equal(draft("run thermal on U22").scope, "component");
assert.ok(draft("run thermal on U22").missing.some(item => item.includes("heat")));
assert.deepEqual(draft("cool U22 with 2W").bindings.componentIds, ["a/U22"]);
assert.equal(draft("cool U22 with 2W").parameters.powerW, 2);
let result = draft("cool U21 with 2W");
assert.equal(result.bindings.componentIds.length, 0);
assert.equal(result.ambiguities[0].candidates.length, 2);
assert.equal(result.contextVersion, context.version);
result = draft('RF s parameters net "DATA CLK" 1GHz to3GHz');
assert.equal(result.workflowKey, "rf");
assert.deepEqual(result.bindings.netIds, ["n2"]);
assert.equal(result.parameters.frequencyStartHz, 1e9);
assert.equal(result.parameters.frequencyStopHz, 3e9);
assert.equal(result.suppliedText, 'RF s parameters net "DATA CLK" 1GHz to3GHz');
assert.deepEqual(draft("run SI on DATA1").bindings.netIds, ["n3"]);
assert.equal(draft("run SI on DATA1").issues.length, 0);
result = draft("run SI on DATA_MISSING selected");
assert.equal(result.bindings.netIds.length, 0, "Explicit unknown identifiers cannot fall back to selection");
assert.ok(result.issues.some(item => item.includes("DATA_MISSING")));
assert.deepEqual(draft("analyse SI on selected net").bindings.netIds, ["n1"]);
result = draft("cool U999 with 2W selected");
assert.equal(result.bindings.componentIds.length, 0);
assert.ok(result.issues.some(item => item.includes("U999")));
result = draft("cool U22 and U23 with 2W");
assert.deepEqual(result.bindings.componentIds, ["a/U22", "a/U23"]);
assert.ok(result.missing.some(item => item.includes("allocation")));
for (const quantity of ["power=2A", "power=NaNW", "power=InfinityW", "power=-2W", "power=1e999W", "power=2", "2watts", "2V"]) {
 assert.ok(draft(`cool U22 ${quantity}`).issues.length > 0, quantity);
 assert.equal(draft(`cool U22 ${quantity}`).parameters.powerW, undefined, quantity);
}
for (const text of ["cool U22 power=2W power=3W", "cool U22 2W 3W", "cool U22 power=2W power=3W power=4W"]) {
 result = draft(text); assert.equal(result.parameters.powerW, undefined); assert.ok(result.issues.some(item => item.includes("Repeated")));
}
assert.equal(draft("cool U22 ambient=-273.15C power=2W").parameters.ambientC, undefined);
assert.equal(draft("cool U22 ambient=-20C power=2W").parameters.ambientC, -20);
assert.equal(draft("run RF net DATA 3GHz to1GHz").issues.length, 1);
for (const text of ["run CHT on assembly", "CHT on U22", "CHT reference on assembly", "CHT cavity on U22"]) {
 result = draft(text); assert.equal(result.workflowKey, "assemblyCHT"); assert.equal(result.availability, "unsupported"); assert.ok(result.limitation.includes("fixed"));
}
assert.equal(draft("CHT cavity benchmark").workflowKey, "referenceCHT");
assert.equal(draft("CHT cavity benchmark").availability, "review");
assert.equal(draft("hybrid on assembly").workflowKey, "coupling");
assert.ok(draft("hybrid on assembly").missing.some(item => item.includes("coupling")));
assert.equal(draft("electrothermal on assembly").workflowKey, "electrothermal");
assert.equal(draft("CFD on assembly").availability, "unsupported");
result = draft("run SI on assembly");
assert.equal(result.scope, "assembly");
assert.equal(result.availability, "unsupported", "Acknowledging an issue must not enable an unsupported scope");
for (const text of ["open native CFD cavity", "run CFD workspace", "CFD cavity benchmark", "native CFD reference"]) {
 result = draft(text);
 assert.equal(result.workflowKey, "cfd");
 assert.equal(result.scope, "workspace");
 assert.equal(result.availability, "review");
}
for (const text of ["CFD workspace on board", "CFD cavity on assembly", "CFD reference component U999", "CFD workspace net DATA", "CFD cavity on U22", 'CFD cavity occurrence "Main board"', "CFD reference on selected"]) {
 assert.equal(draft(text).availability, "unsupported", text);
}
for (const text of ["import STEP", "import Touchstone", "load Touchstone", "import S2P", "import network.s4p"]) assert.equal(draft(text).workflowKey, "import");
for (const [text, operation] of [["open assembly", "open"], ["open board", "open"], ["move board", "move"], ["rotate board occurrence", "rotate"], ["place board in assembly", "place"], ["connect boards", "connect"]]) {
 result = draft(text);
 assert.equal(result.workflowKey, "assembly");
 assert.equal(result.assemblyOperation, operation);
 assert.equal(result.suppliedText, text);
}
assert.equal(draft("open assembly").missing.length, 0, "Opening an assembly does not require a fabricated connection pair");
assert.equal(draft('rotate board occurrence "Main board" by 90deg').issues.length, 0, "Placement quantities remain explicit text for assembly setup review");
assert.ok(draft("move board").missing.some(item => item.includes("occurrence")));
assert.ok(draft('rotate occurrence "Main board"').missing.some(item => item.includes("transform")));
for (const text of ["SI on DATA", "RF on DATA", "EM on board"]) {
 result = draft(text);
 assert.ok(result.missing.includes("Start frequency (Hz)"));
 assert.ok(result.missing.includes("Stop frequency (Hz)"));
}
result = draft("SI on DATA fstart=0Hz fstop=1GHz");
assert.equal(result.parameters.frequencyStartHz, 0);
assert.equal(result.parameters.frequencyStopHz, 1e9);
assert.equal(result.issues.length, 0);
assert.ok(!result.missing.some(item => item.includes("frequency")));
assert.ok(result.limitation.includes("0 Hz"));
assert.equal(draft("SI on DATA fstart=-1Hz fstop=1GHz").parameters.frequencyStartHz, undefined);
assert.equal(draft("SI on DATA fstart=0Hz fstop=0Hz").parameters.frequencyStopHz, undefined);
result = draft("SI on DATA 1MHz to 2MHz");
assert.ok(!result.missing.some(item => item.includes("frequency")));
assert.ok(draft("cool U22 with 2W").missing.includes("Ambient temperature (C)"));
assert.ok(!draft("cool U22 with 2W ambient=25C").missing.includes("Ambient temperature (C)"));
assert.ok(draft("electrothermal on board").missing.includes("Ambient temperature (C)"));
assert.equal(draft("connect boards").workflowKey, "assembly");
result = draft('connect occurrence "Main board" to occurrence "Sensor board"');
assert.deepEqual(result.bindings.occurrenceIds, ["a", "b"]);
for (const [text, key] of [["mesh board 0.5mm", "mesh"], ["show results", "results"], ["create study", "studies"], ["assign model to U22", "model-assignment"], ["export report", "export"], ["EM on board", "em"]]) assert.equal(draft(text).workflowKey, key);
result = draft('run SI on net DATA reference "DATA CLK" from U22 to U23');
assert.equal(result.roles.signalNetId, "n1");
assert.equal(result.roles.referenceNetId, "n2");
assert.equal(result.roles.sourceComponentId, "a/U22");
assert.deepEqual(result.roles.sinkComponentIds, ["a/U23"]);
assert.equal(draft("RF net DATA from 1GHz to 3GHz").issues.length, 0);
assert.equal(draft("cool U22 with 2kW").parameters.powerW, 2000);
assert.deepEqual(draft('thermal on U21 occurrence "Main board" power=2W').bindings.componentIds, ["a/U21"]);
assert.equal(draft("run SI on net MISSING reference UNKNOWN").roles.signalNetId, undefined);
assert.equal(draft("run SI on net MISSING reference UNKNOWN").roles.referenceNetId, undefined);
assert.equal(draft("mesh board 0.5mm").parameters.meshSizeM, 0.0005);
assert.equal(parse("25mW", "W"), 0.025);
assert.ok(Math.abs(draft("cool U22 power 25 uW").parameters.powerW - 0.000025) < 1e-15);
assert.deepEqual(draft("run SI on DATA from U22 to U23 and U22").roles.sinkComponentIds, ["a/U23", "a/U22"]);
assert.equal(parse("5MHz", "Hz"), 5e6);
assert.equal(parse("2A", "W"), undefined);
assert.equal(parse("NaNW", "W"), undefined);
assert.equal(suggest("thermal " + "a".repeat(513), context).length, 0);
assert.equal(suggest("", context).length, 0);
assert.equal(suggest("hello world", context).length, 0);
assert.equal(new Set(schemas.map(item => item.workflowKey)).size, schemas.length);
console.log("Workspace intent parsing, identity, units and scope tests passed.");
