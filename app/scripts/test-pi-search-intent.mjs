// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";
const { suggestPiSetupIntents: suggest } = await importTestTypescript("piSearchIntent");
// Minimal canonical ParsedBoard fixture, independently authored: ICs have several
// power and ground pads plus another rail, and the capacitor exposes both rails.
const pad = (ref, name, net) => ({ id: `${ref}:${name}`, ref, name, net, at: [0, 0], width: 1, height: 1, rotation: 0, shape: "rect", drill: 0, layers: ["F.Cu"], layer: "F.Cu" });
const component = ref => ({ id: ref, ref, value: "", library: "", at: [0, 0], width: 1, height: 1, rotation: 0, layer: "F.Cu", modelOffset: [0, 0, 0], modelScale: [1, 1, 1], modelRotation: [0, 0, 0] });
const board = {
 width: 10, height: 10, bounds: { minX: 0, minY: 0, maxX: 10, maxY: 10 }, outlineLoops: [],
 tracks: [], vias: [], zones: [], drawings: [], layers: ["F.Cu"], layerDefinitions: [], stackup: [],
 components: ["C10", "U21", "U22", "J1"].map(component),
 nets: { "0": "", "1": "netx", "2": "GND", "3": "/Power/3V3", "4": "nety" },
 pads: [pad("C10", "1", "1"), pad("C10", "2", "2"), pad("U21", "1", "1"), pad("U21", "2", "1"), pad("U21", "3", "2"), pad("U21", "4", "2"), pad("U21", "5", "3"), pad("U22", "1", "1"), pad("U22", "2", "2"), pad("J1", "1", "3")],
};
let rows = suggest("on board run PI on netx from C10 to U21", board);
assert.equal(rows.length, 1);
let draft = rows[0].draft;
assert.equal(draft.netId, "1");
assert.equal(draft.netName, "netx");
assert.deepEqual(draft.source, { ref: "C10", padIds: ["C10:1"] });
assert.deepEqual(draft.sinks, [{ ref: "U21", padIds: ["U21:1", "U21:2"] }]);
assert.equal(draft.voltageV, undefined);
assert.equal(draft.sourceCurrentA, undefined);
assert.equal(draft.sinkCurrentA, undefined);
assert.ok(draft.missing.some(text => text.includes("Vsup")));
rows = suggest("run power integrity on netx from C10 to U21 and U22 with Vsup=3300mV Isup 1 A Isink=500mA", board);
draft = rows[0].draft;
assert.ok(Math.abs(draft.voltageV - 3.3) < 1e-12);
assert.equal(draft.sourceCurrentA, 1);
assert.equal(draft.sinkCurrentA, 0.5);
assert.deepEqual(draft.sinks.map(item => item.ref), ["U21", "U22"]);
assert.ok(draft.assumptions.some(text => text.includes("total")));
assert.equal(draft.missing.length, 0);
assert.equal(suggest("rn power integrty on netx from C10 to U21", board)[0].draft.netId, "1");
assert.equal(suggest("set up DC IR drop on netx from C10 to U21", board)[0].draft.netId, "1");
assert.equal(suggest("run PI on netx from NO_SUCH_PART to U21", board)[0].draft.source, undefined);
assert.ok(suggest("run PI on netx from NO_SUCH_PART to U21", board)[0].draft.missing.some(text => text.includes("Unknown source")));
assert.equal(suggest("run PI from NO_SUCH_PART to U21", board)[0].draft.netId, undefined);
rows = suggest("run PI from C10 to U21", board);
assert.deepEqual(rows.map(row => row.draft.netId), ["1", "2"], "Power and ground shared nets require explicit choice");
assert.ok(rows[0].draft.ambiguities.some(item => item.field === "net" && item.candidates.length === 2));
const unique = { ...board, pads: board.pads.filter(item => item.id !== "C10:2") };
assert.equal(suggest("run PI from C10 to U21", unique)[0].draft.netId, "1");
assert.ok(suggest("run PI from C10 to U21", unique)[0].draft.assumptions.some(text => text.includes("inferred")));
rows = suggest("run PI on missing-name from C10 to U21", board);
assert.equal(rows[0].draft.netId, undefined, "Unknown explicit net must never fall back to endpoint connectivity");
rows = suggest("run PI on netz from C10 to U21", board);
assert.ok(rows.length > 1);
assert.ok(rows.every(row => row.draft.assumptions.some(text => text.includes("Suggested net spelling"))));
assert.equal(suggest("run PI on netx from C10 to U2", board)[0].draft.sinks.length, 0);
assert.equal(suggest("run PI on netx from C10 to U2", board)[0].draft.ambiguities[0].candidates.length, 2);
rows = suggest("run PI on /Power/3V3 from J1 to U21", board);
assert.deepEqual(rows[0].draft.sinks[0].padIds, ["U21:5"]);
assert.ok(suggest("run PI on netx from J1 to U21", board)[0].draft.missing.some(text => text.includes("J1 has no pad")));
for (const token of ["Vsup=-1V", "Vsup=0V", "Vsup=NaNV", "Vsup=3.3A", "Vsup=1e999V", "Isup=-1A", "Isup=0A", "Isink=2watts"]) {
 assert.ok(suggest(`run PI on netx from C10 to U21 ${token}`, board)[0].draft.missing.some(text => text.includes("Invalid")), token);
}
draft = suggest("run PI on netx from C10 to U21 Vsup=3.3 Vsup=5 Vsup=12 Isup=2uA Isink=2e-3A", board)[0].draft;
assert.equal(draft.voltageV, undefined);
assert.equal(draft.sourceCurrentA, 0.000002);
assert.equal(draft.sinkCurrentA, 0.002);
assert.ok(draft.missing.some(text => text.includes("Repeated")));
const duplicateNames = { ...board, nets: { ...board.nets, "5": "netx" } };
assert.deepEqual(suggest("run PI on netx from C10 to U21", duplicateNames).map(item => item.draft.netId), ["1", "5"]);
assert.equal(suggest("delete all projects", board).length, 0);
assert.equal(suggest("run shell rm everything", board).length, 0);
assert.equal(suggest("x".repeat(513), board).length, 0);
assert.ok(suggest("run PI on netx from C10 to U21", board)[0].draft.assumptions.some(text => text.includes("Review")));
console.log("PI intent canonical endpoints, net ambiguity, spelling suggestions and electrical units passed.");

const namedPads = { ...board, pads: board.pads.map(item => ({ ...item, net: board.nets[item.net] })) };
assert.deepEqual(suggest("run PI on netx from C10 to U21", namedPads)[0].draft.sinks[0].padIds, ["U21:1", "U21:2"]);
const mixedEligible = { ...namedPads, pads: [...namedPads.pads, { ...pad("U21", "99", "netx"), type: "np_thru_hole" }, { ...pad("U21", "100", "netx"), pad_kind: "npth" }, { ...pad("U21", "101", "netx"), layers: ["F.Mask"], layer: "F.Mask" }] };
assert.deepEqual(suggest("run PI on netx from C10 to U21", mixedEligible)[0].draft.sinks[0].padIds, ["U21:1", "U21:2"]);
const uniqueNamed = { ...namedPads, pads: namedPads.pads.filter(item => item.id !== "C10:2") };
assert.equal(suggest("run PI from C10 to U21", uniqueNamed)[0].draft.netId, "1");
const multiSourceBoard = { ...namedPads, pads: [...namedPads.pads, pad("J1", "2", "netx")] };
draft = suggest("run PI from C10 and J1 to U21 and U22 Vsup=3.3V Isup=1A Isink=200mA", multiSourceBoard)[0].draft;
assert.equal(draft.netId, "1", "All sources and sinks participate in unique shared-net inference");
assert.deepEqual(draft.sources, [{ ref: "C10", padIds: ["C10:1"] }, { ref: "J1", padIds: ["J1:2"] }]);
assert.deepEqual(draft.source, draft.sources[0], "Single-source compatibility retains first resolved source");
assert.deepEqual(draft.sourceInputs, ["C10", "J1"]);
assert.deepEqual(draft.sinkInputs, ["U21", "U22"]);
assert.ok(draft.assumptions.some(text => text.includes("separately for every source")));
rows = suggest("run PI from C10 and U21 to U22", namedPads);
assert.deepEqual(rows.map(row => row.draft.netId), ["1", "2"], "Multiple shared rails remain explicit candidate choices");
draft = suggest("run PI from C10 and UNKNOWN to U21", multiSourceBoard)[0].draft;
assert.equal(draft.netId, undefined, "Unknown second source prevents net inference");
assert.deepEqual(draft.sourceInputs, ["C10", "UNKNOWN"]);
assert.deepEqual(draft.sources.map(source => source.ref), ["C10"]);
assert.ok(draft.missing.some(text => text.includes("Unknown source component UNKNOWN")));
draft = suggest("run PI on netx from C10 and J1 to U21 Vsup=3.3V Vsup=5V Isup=1A Isup=2A", multiSourceBoard)[0].draft;
assert.equal(draft.voltageV, undefined);
assert.equal(draft.sourceCurrentA, undefined);
assert.equal(draft.missing.filter(text => text.includes("Repeated")).length, 2);
assert.equal(suggest("run PI from C10 and J1 to U21", namedPads)[0].draft.netId, undefined, "A source on another rail blocks inference");
