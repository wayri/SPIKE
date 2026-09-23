import assert from "node:assert/strict";
import {
  builtinSiProtocolSuites, createCustomSiProtocolSuite, protocolSuiteExtensionBundle,
  validateSiProtocolSuite,
} from "../src/siProtocolSuites.ts";

const names = new Set(builtinSiProtocolSuites.map(item => item.name));
for (const required of ["DDR / LPDDR", "GDDR", "Generic SerDes", "LVDS", "PCI / PCI-X", "PCI Express", "PXI", "PXI Express", "DisplayPort", "HDMI"]) {
  assert.ok(names.has(required), `missing dedicated ${required} suite`);
}
assert.ok(builtinSiProtocolSuites.length >= 15, "the registry should cover other common high-speed families too");
for (const suite of builtinSiProtocolSuites) {
  assert.deepEqual(validateSiProtocolSuite(suite), [], `${suite.id} must satisfy the suite contract`);
  assert.equal(suite.qualification, "setup_only", `${suite.id} cannot claim solver validation`);
}

const custom = createCustomSiProtocolSuite();
assert.deepEqual(validateSiProtocolSuite(custom), []);
assert.ok(validateSiProtocolSuite({ ...custom, qualification: "validated" }).some(error => error.includes("self-assert")));
const bundle = protocolSuiteExtensionBundle(custom);
assert.equal(bundle.execution, "declarative_only");
assert.match(bundle.code_state, /dormant/);
assert.equal(bundle.files["spike-extension.json"].bundled, false);
assert.equal(bundle.files["spike-extension.json"].contributes.protocol_suites[0].definition.contract, "spike/si-protocol-suite/v1");

console.log("SI protocol suites: all assertions passed");
