// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { scoreUniversalSearchItem } from "../src/universalSearchModel.ts";

const item = (label, category, description = "", keywords = "") => ({ label, category, description, keywords });

// Text can change while an action keeps its object identity (for example a live net name).
const changing = item("Inspect copper", "View", "Original description", "layers");
assert.equal(scoreUniversalSearchItem(changing, "inspect copper"), 1000);
changing.label = "Inspect temperature";
changing.keywords = "cooling";
changing.category = "Thermal";
changing.description = "New airflow details";
assert.equal(scoreUniversalSearchItem(changing, "inspect copper"), 0);
assert.equal(scoreUniversalSearchItem(changing, "inspect temperature"), 1000);
assert.ok(scoreUniversalSearchItem(changing, "airflow cooling") > 0);
changing.disabled = true;
assert.equal(scoreUniversalSearchItem(changing, ""), -1, "enabled state is never cached");
changing.disabled = false;
assert.equal(scoreUniversalSearchItem(changing, ""), 1);

assert.ok(
  scoreUniversalSearchItem(item("Layered board thermal", "Saved thermal result", "Inspect board temperatures", "heat map pcb"), "thermal pcb") > 0,
  "multiword queries should match across labels and aliases",
);
assert.ok(
  scoreUniversalSearchItem(item("Temperature plots", "Thermal results", "Open saved probe traces", "chart graph waveform"), "temp graph") > 0,
  "word prefixes and keyword synonyms should compose",
);
assert.ok(
  scoreUniversalSearchItem(item("Transient animation", "Thermal results", "Play time-history frames", "movie playback timestep"), "thermal movie") > 0,
  "category terms and aliases should compose",
);
assert.equal(
  scoreUniversalSearchItem(item("Solver settings", "Settings"), "saved thermal"),
  0,
  "every query token must be represented",
);
assert.ok(
  scoreUniversalSearchItem(item("Temperature plots", "Thermal results", "", "chart"), "temperature")
    > scoreUniversalSearchItem(item("Open plots", "Results", "Review temperature data", ""), "temperature"),
  "label matches should outrank incidental description matches",
);
assert.ok(
  scoreUniversalSearchItem(item("Application settings", "Settings", "", "preferences options configuration"), "preferences") > 0,
  "settings synonyms should be searchable through keywords",
);

console.log("universal search: all assertions passed");

assert.ok(scoreUniversalSearchItem(item("Application settings", "Settings"), "could you open the settings") > 0);
assert.ok(scoreUniversalSearchItem(item("Thermal workspace", "Workspace"), "please show thermal") > 0);

assert.equal(scoreUniversalSearchItem(item("Hide orientation grid", "View"), "show grid"), 0, "Showing a control must not suggest its opposite action");

assert.ok(scoreUniversalSearchItem(item("Thermal workspace","Workspace"),"theraml")>0);
assert.ok(scoreUniversalSearchItem(item("Thermal workspace","Workspace"),"thermal")>scoreUniversalSearchItem(item("Thermal workspace","Workspace"),"theraml"));
assert.equal(scoreUniversalSearchItem(item("Net TX21","Objects"),"TX22"),0,"Never fuzzy-correct numeric object identities");
assert.equal(scoreUniversalSearchItem(item("Show orientation grid","View"),"hide grid"),0);
