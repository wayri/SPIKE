// Offline frontend parser smoke for explicitly supplied public/local boards.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { basename } from "node:path";
import { createHash } from "node:crypto";
import ts from "typescript";

const options = { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } };
const numeric = ts.transpileModule(readFileSync(new URL("../src/numericRange.ts", import.meta.url), "utf8"), options).outputText;
const numericUrl = `data:text/javascript;base64,${Buffer.from(numeric).toString("base64")}`;
const code = ts.transpileModule(readFileSync(new URL("../src/boardParser.ts", import.meta.url), "utf8"), options).outputText
  .replace('from "./numericRange";', `from "${numericUrl}";`);
const { parseKicadBoard } = await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
assert.ok(process.argv.length > 2, "Pass at least one local .kicad_pcb path");
const records = [];
for (const file of process.argv.slice(2)) {
  const bytes = readFileSync(file);
  const start = performance.now();
  const board = parseKicadBoard(bytes.toString("utf8"));
  assert.ok(board.layers.length > 0 && board.layers.length <= 32, "physical copper stack must be present and admitted");
  assert.equal(new Set(board.layers).size, board.layers.length);
  assert.ok(board.components.length > 0, "fixture must contain imported components");
  assert.ok(board.tracks.length > 0, "fixture must contain imported routing");
  assert.ok(Number.isFinite(board.width) && board.width > 0 && Number.isFinite(board.height) && board.height > 0);
  records.push({ file: basename(file), sha256: createHash("sha256").update(bytes).digest("hex"),
    copper_layers: board.layers, drawable_layers: board.layerDefinitions.length,
    components: board.components.length, tracks: board.tracks.length, pads: board.pads.length,
    nets: Object.keys(board.nets).length, width_mm: board.width, height_mm: board.height,
    parse_ms: Math.round((performance.now() - start) * 100) / 100 });
}
console.log(JSON.stringify({ scope: "frontend-parser-only", viewport_verified: false, records }, null, 2));
