// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { mapThermalRecords, parseThermalDelimited, suggestThermalMapping, thermalRowsFromOdb } from "../src/thermalBomParsing.ts";

const board = { components: [
  { ref: "U1", properties: [{ name: "POWER_W", values: ["1.2"] }, { name: "RTH_TOP_K_W", values: ["10"] }, { name: "RTH_BOTTOM_K_W", values: ["30"] }] },
  { ref: "R2", vendor_properties: { power_w: "250 mW", rth_top_k_w: "20", rth_bottom_k_w: "40" } },
] };
const bom = parseThermalDelimited('Reference,Power (W),Rth top (K/W),Rth bottom (K/W)\n"U1, R2",1.5,12,36\nX9,2,10,20');
const mapping = suggestThermalMapping(bom.headers);
assert.ok(Object.values(mapping).every(Boolean));
const matched = mapThermalRecords(bom.records, mapping, board);
assert.deepEqual(matched.rows.map(row => row.reference), ["U1", "R2"]);
assert.equal(matched.rows[0].power_w, 1.5);
assert.equal(matched.issues.length, 1);
assert.match(matched.issues[0], /X9 is not on the loaded board/);

const odb = thermalRowsFromOdb(board);
assert.equal(odb.rows.length, 2);
assert.equal(odb.rows[0].theta_top_c_per_w, 10);
assert.equal(odb.rows[1].power_w, 0.25);

const milli = parseThermalDelimited("Ref;Power (mW);Rth top K/W;Rth bottom K/W\nU1;250;10;30");
assert.equal(mapThermalRecords(milli.records, suggestThermalMapping(milli.headers), board).rows[0].power_w, 0.25);
for (const [cell, expected] of [["1 W", 1], ["250 mW", 0.25], ["2.5e2", 0.25]]) {
  const explicit = parseThermalDelimited(`Ref;Power (mW);Rth top K/W;Rth bottom K/W\nU1;${cell};10;30`);
  assert.equal(mapThermalRecords(explicit.records, suggestThermalMapping(explicit.headers), board).rows[0].power_w, expected);
  const odbUnits = { components: [{ ref: "U1", vendor_properties: { power_mw: cell, rth_top: "10", rth_bottom: "30" } }] };
  assert.equal(thermalRowsFromOdb(odbUnits).rows[0].power_w, expected);
}

const bad = parseThermalDelimited("Reference\tPower (W)\tRth top (K/W)\tRth bottom (K/W)\nU1\t2\t-1\t3");
assert.equal(mapThermalRecords(bad.records, suggestThermalMapping(bad.headers), board).rows.length, 0);
assert.throws(() => parseThermalDelimited("Reference,Power (W),Rth top (K/W),Rth bottom (K/W)\nU1,2,1"), /3 cells/);
assert.throws(() => parseThermalDelimited('Reference,Power (W),Rth top (K/W),Rth bottom (K/W)\nU1,2,1,"3'), /unterminated quoted cell/);
console.log("Thermal BOM and ODB++ mapping checks passed.");
