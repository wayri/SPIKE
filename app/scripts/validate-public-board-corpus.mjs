// Exercise the actual desktop parsers. This is not a viewport pixel test.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";
const options = { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } };
const url = code => `data:text/javascript;base64,${Buffer.from(code).toString("base64")}`;
const compile = file => ts.transpileModule(readFileSync(new URL(file, import.meta.url), "utf8"), options).outputText;
const numeric = url(compile("../src/numericRange.ts"));
const { parseKicadBoard } = await import(url(compile("../src/boardParser.ts").replace('from "./numericRange";', `from "${numeric}";`)));
const { parseNormalizedBoard } = await import(url(compile("../src/normalizedBoard.ts")));
const root = fileURLToPath(new URL("../../", import.meta.url));
const base = resolve(root, "build/public-board-corpus");
const manifest = JSON.parse(readFileSync(resolve(base, "manifest.json"), "utf8"));
const results = [];
for (const c of manifest.cases) {
  const file = c.format === "kicad_pcb" ? resolve(root, c.local_path) : resolve(base, "final", c.id, "board.spike-design.json");
  if (!existsSync(file)) { results.push({ id: c.id, status: "unavailable", reason: "No normalized snapshot was produced" }); continue; }
  const start = performance.now();
  try {
    const text = readFileSync(file, "utf8");
    const board = c.format === "kicad_pcb" ? parseKicadBoard(text) : parseNormalizedBoard(text);
    if (![board.width, board.height].every(v => Number.isFinite(v) && v > 0)) throw Error("Nonpositive/nonfinite board extents");
    results.push({ id: c.id, status: "parsed", counts: { components: board.components.length, pads: board.pads.length, tracks: board.tracks.length, vias: board.vias.length, zones: board.zones.length, copper_layers: board.layers.length }, bounds: board.bounds, elapsed_ms: Math.round(performance.now() - start) });
  } catch (error) { results.push({ id: c.id, status: "failed", error: String(error) }); }
  console.log(c.id, results.at(-1).status);
  writeFileSync(resolve(base, "frontend-results.json"), JSON.stringify(results, null, 2));
}
writeFileSync(resolve(base, "frontend-results.json"), JSON.stringify(results, null, 2));
