// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {importTestTypescript} from "./import-test-typescript.mjs";
const {searchCategory}=await importTestTypescript("searchCategory");
for(const [text,want] of [["PI analysis","pi"],["HF / SI","si"],["EM","em"],["Thermal results","thermal"],["Solver manager","solver"],["CFD","flow"],["Project","project"],["Net","design"],["Settings","settings"],["Help","help"],["Studies","results"],["View","view"],["Sentence command","action"]])assert.equal(searchCategory(text),want,text);
assert.equal(searchCategory("Solver category PI analysis"),"pi","specific physics context wins over the generic solver field");
assert.equal(searchCategory("unknown category"),"action","unrecognized labels have a stable fallback");
console.log("Search category presentation: physics, solver, action and general categories passed.");
