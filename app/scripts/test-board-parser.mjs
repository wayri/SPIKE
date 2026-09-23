import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const parserSource = readFileSync(new URL("../src/boardParser.ts", import.meta.url), "utf8");
const numericRangeSource = readFileSync(new URL("../src/numericRange.ts", import.meta.url), "utf8");
const compilerOptions = { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 };
const numericRangeModule = ts.transpileModule(numericRangeSource, {
  compilerOptions,
}).outputText;
const numericRangeUrl = `data:text/javascript;base64,${Buffer.from(numericRangeModule).toString("base64")}`;
const transpiled = ts.transpileModule(parserSource, {
  compilerOptions,
}).outputText.replace('from "./numericRange";', `from "${numericRangeUrl}";`);
const parser = await import(`data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`);
for (const filename of process.argv.slice(2)) {
  const started = performance.now();
  const parsed = parser.parseKicadBoard(readFileSync(filename, "utf8"));
  console.log(JSON.stringify({ file: filename, ms: Math.round(performance.now() - started), components: parsed.components.length, pads: parsed.pads.length, vias: parsed.vias.length, tracks: parsed.tracks.length, zones: parsed.zones.length, copper: parsed.layers.length, layers: parsed.layerDefinitions.length }));
}

const copperNames = ["F.Cu", ...Array.from({ length: 30 }, (_, index) => `In${index + 1}.Cu`), "B.Cu"];
const copperRows = copperNames.map((name, index) => {
  const id = name === "F.Cu" ? 0 : name === "B.Cu" ? 2 : (index + 1) * 2;
  const userName = name === "In10.Cu" ? ' "MEMORY_PWR"' : "";
  return `    (${id} "${name}" ${index % 3 === 0 ? "power" : "signal"}${userName})`;
}).join("\n");
const board = `(kicad_pcb
  (version 20241229)
  (generator pcbnew)
  (layers
${copperRows}
    (7 "B.SilkS" user "Bottom Silkscreen")
    (5 "F.SilkS" user "Top Silkscreen")
    (25 "Edge.Cuts" user)
  )
  (setup (stackup
    (layer "F.Cu" (type "copper") (thickness 0.035))
    (layer "dielectric 1" (type "core") (thickness 1.53) (epsilon_r 4.2))
    (layer "B.Cu" (type "copper") (thickness 0.035))
  ))
  (net 0 "")
  (net 1 "VCC")
  (segment (start 1 1) (end 9 1) (width 0.25) (layer "In30.Cu") (net 1))
)`;

const parsed = parser.parseKicadBoard(board);
assert.deepEqual(parsed.layers, copperNames, "all copper layers must retain KiCad physical order");
assert.equal(parsed.layerDefinitions.length, 35, "all enabled board layers must be retained");
assert.equal(parsed.layerDefinitions.find(layer => layer.name === "In10.Cu")?.userName, "MEMORY_PWR");
assert.equal(parsed.tracks[0].layer, "In30.Cu");
assert.equal(
  parser.isCopperLayerDefinition({ id: 96, name: "POWER_CORE_32", kind: "power" }),
  true,
  "semantic copper layers must not be capped by numeric ID",
);

const footprintMetadata = parser.parseKicadBoard(`(kicad_pcb
  (version 20241229)
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (36 "B.SilkS" user) (37 "F.SilkS" user)
    (44 "Edge.Cuts" user) (48 "B.Fab" user) (49 "F.Fab" user) (46 "B.CrtYd" user) (47 "F.CrtYd" user))
  (footprint "Package_SO:TSSOP-8" (layer "F.Cu") (at 20 30 90)
    (property "Reference" "U1")
    (property "Value" "TEST_IC")
    (fp_rect (start -2 -1.5) (end 2 1.5) (stroke (width 0.1) (type default)) (fill none) (layer "F.Fab"))
    (fp_rect (start -2.4 -1.9) (end 2.4 1.9) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd"))
    (pad "1" smd rect (at -2.7 -1) (size 1.4 0.6) (layers "F.Cu" "F.Paste" "F.Mask"))
    (pad "2" smd rect (at 2.7 1) (size 1.4 0.6) (layers "F.Cu" "F.Paste" "F.Mask"))))`);
assert.deepEqual(footprintMetadata.components[0].bodyBounds, { minX: -2, minY: -1.5, maxX: 2, maxY: 1.5 });
assert.deepEqual(footprintMetadata.components[0].courtyardBounds, { minX: -2.4, minY: -1.9, maxX: 2.4, maxY: 1.9 });
console.log(`boardParser high-layer regression passed: ${parsed.layers.length} copper / ${parsed.layerDefinitions.length} total layers`);
