// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
import { importTestTypescript } from "../app/scripts/import-test-typescript.mjs";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const boardSha256 = createHash("sha256").update(readFileSync(resolve(root, "examples/esp32/source/iot-esp-eth-ind.kicad_pcb"))).digest("hex");
assert.equal(boardSha256, "3199ce0a25f8987020e716d82a4a35d9b6b04541d33b2f2e46406376713eab33");
const imported = JSON.parse(readFileSync(resolve(root, "examples/esp32/pi_request.json"), "utf8"));
const regulator = imported.design.components.find(part => part.reference === "U41");
assert.equal(regulator?.value, "AZ1117-3.3");
assert.deepEqual([...regulator.nets].sort(), ["+3.3V", "+5V", "GND"].sort());
const { calculatePowerTree, defaultTopologyScenarios } = await importTestTypescript("powerTree");
const base = {
  contract: "spike/topology/v1", domain: "pi", name: "ESP32 board U41 5 V to 3.3 V budget",
  scenarios: defaultTopologyScenarios(),
  extraction: { source: "manual", generatedAt: "2026-09-29T00:00:00Z", warnings: [] },
  nodes: [
    { id: "input", kind: "source", label: "+5V source", net: "+5V", voltageV: 5, x: 0, y: 0, origin: "user" },
    { id: "U41", kind: "regulator", ref: "U41", label: "U41 AZ1117-3.3", net: "+3.3V", converterKind: "ldo", voltageRatio: 3.3 / 5, x: 140, y: 0, origin: "user" },
    { id: "rail", kind: "rail", label: "+3.3V", net: "+3.3V", x: 280, y: 0, origin: "user" },
    { id: "assumed_load", kind: "load", label: "Illustrative 0.15 A rail load", net: "+3.3V", loadCurrentA: 0.15, x: 420, y: 0, origin: "user" },
  ],
  edges: [
    { id: "in-U41", from: "input", to: "U41", kind: "power", net: "+5V", origin: "user" },
    { id: "U41-rail", from: "U41", to: "rail", kind: "power", net: "+3.3V", origin: "user" },
    { id: "rail-load", from: "rail", to: "assumed_load", kind: "power", net: "+3.3V", origin: "user" },
  ],
};
const ldo = calculatePowerTree(base, "typical");
const buckStudy = { ...base, name: "Hypothetical 90% buck substitution, not populated on ESP32 board",
  nodes: base.nodes.map(node => node.id === "U41" ? { ...node, id: "buck_study", ref: undefined, label: "Hypothetical buck", converterKind: "buck", efficiencyPercent: 90 } : node),
  edges: base.edges.map(edge => ({ ...edge, from: edge.from === "U41" ? "buck_study" : edge.from, to: edge.to === "U41" ? "buck_study" : edge.to })) };
const buck = calculatePowerTree(buckStudy, "typical");
assert.equal(ldo.status, "complete");
assert.equal(buck.status, "complete");
assert.ok(Math.abs(ldo.nodes.U41.lossW - 0.255) < 1e-12);
assert.ok(Math.abs(buck.nodes.buck_study.lossW - 0.055) < 1e-12);
const evidence = { contract: "spike/esp32-pi-converter-example/v1", model_status: "approximate",
  source_board_sha256: boardSha256,
  board_design_id: imported.design.design_id,
  source_component: { reference: regulator.reference, value: regulator.value, nets: regulator.nets },
  assumption: "The 0.15 A load is illustrative and assigned to +3.3V for this converter budget; the separate board DC IR example uses +3.3VMCU. No regulator SPICE model, quiescent current, dropout, switching ripple, copper return, or thermal feedback is included.",
  ldo: { topology: base, budget: ldo },
  hypothetical_buck: { topology: buckStudy, budget: buck } };
const output = resolve(root, "examples/esp32/evidence/pi_converter_budget.json");
writeFileSync(output, `${JSON.stringify(evidence, null, 2)}\n`);
console.log(JSON.stringify({ ldo_loss_W: ldo.nodes.U41.lossW, buck_loss_W: buck.nodes.buck_study.lossW, output }, null, 2));
