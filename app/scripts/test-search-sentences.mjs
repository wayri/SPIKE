// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";
const { parseSearchSentence, suggestSearchCommands } = await importTestTypescript("searchSentences");
const targets = [
 { id: "1", kind: "net", name: "netK-A1" }, { id: "2", kind: "net", name: "netK-A10" },
 { id: "3", kind: "net", name: "/Power/VCC" }, { id: "4", kind: "net", name: "Net with spaces" },
 { id: "r", kind: "component", name: "R1" }, { id: "f", kind: "layer", name: "F.Cu" },
];
assert.deepEqual(parseSearchSentence("run PI on net netK-A1"), { action: "run-pi", kind: "net", target: "netK-A1" });
assert.equal(parseSearchSentence("Could you run a power integrity analysis on the net netK-A1").target, "netK-A1");
assert.equal(parseSearchSentence("please calculate voltage drop for net /Power/VCC").action, "run-pi");
assert.equal(parseSearchSentence("configure PI for net netK-A1").action, "configure-pi");
assert.equal(parseSearchSentence("show layer F.Cu").action, "show-layer");
assert.equal(parseSearchSentence("hide layer F.Cu").action, "hide-layer");
assert.equal(parseSearchSentence("focus part R1").kind, "component");
assert.equal(parseSearchSentence("isolate net /Power/VCC").target, "/Power/VCC");
let rows = suggestSearchCommands("run PI on net netK-A", targets);
assert.equal(rows.length, 2);
assert.equal(suggestSearchCommands("run PI on net netK-A1", targets)[0].target, "1", "Exact name outranks longer prefix; dispatch retains canonical ID");
assert.equal(suggestSearchCommands("select net /Power", targets)[0].target, "3", "Hierarchical net identity retains slash punctuation");
rows = suggestSearchCommands('run PI on net "Net with spaces"', targets);
assert.equal(rows[0].target, "4");
assert.equal(parseSearchSentence(rows[0].completion).target, "Net with spaces", "Tab completion round-trips quoted names");
assert.equal(suggestSearchCommands("run PI on net missing-net", targets).length, 0, "Unknown net must never dispatch to the current net");
assert.equal(parseSearchSentence("delete all projects"), null);
assert.equal(parseSearchSentence("run shell rm -rf"), null);
assert.equal(parseSearchSentence("hide component R1"), null);
assert.equal(parseSearchSentence("x".repeat(513)), null);
assert.equal(suggestSearchCommands("focus part R", targets).length, 1, "Kinds prevent matching nets as components");
assert.equal(suggestSearchCommands("run PI", Array.from({length:100},(_,i)=>({kind:"net",id:String(i),name:`N${i}`}))).length,20);
console.log("Sentence grammar, target resolution, completion and unsupported-command regression checks passed.");

assert.equal(suggestSearchCommands("run PI", targets, "2")[0].target, "2", "No-target suggestions prefer the active canonical net");
assert.equal(parseSearchSentence("isolate layer F.Cu").kind, "layer");
