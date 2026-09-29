import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import { importTestTypescript } from "./import-test-typescript.mjs";

const APP = fileURLToPath(new URL("../", import.meta.url));
const compilerOptions = { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 };

async function loadModule(file, replacements = {}) {
  let src = readFileSync(`${APP}/src/${file}`, "utf8");
  let out = ts.transpileModule(src, { compilerOptions }).outputText;
  for (const [from, dataUrl] of Object.entries(replacements)) {
    out = out.split(`from "${from}";`).join(`from "${dataUrl}";`);
  }
  return import(`data:text/javascript;base64,${Buffer.from(out).toString("base64")}`);
}

async function compiledModule(file, baseUrl) {
  const src = readFileSync(`${APP}/src/${file}`, "utf8");
  const out = ts.transpileModule(src, { compilerOptions }).outputText;
  return `data:text/javascript;base64,${Buffer.from(out).toString("base64")}`;
}

const boardParser = await loadModule("boardParser.ts", {
  "./numericRange": await compiledModule("numericRange.ts"),
});
// The power-tree extraction path is cyclic after its extraction module split.
// Use file-backed fixtures so ESM can retain shared module identity.
const powerTree = await importTestTypescript("powerTree");
const spiceWorkspace = await loadModule("spiceWorkspace.ts");

const FILES = process.argv.slice(2);
for (const file of FILES) {
  const source = readFileSync(file, "utf8");
  const board = boardParser.parseKicadBoard(source);
  const name = file.split(/[\\/]/).pop();
  const results = [];
  try { const t = powerTree.extractTopologyFromBoard(board, "pi"); results.push(`topology:${t.nodes?.length ?? "?"}nodes`); }
  catch (e) { results.push(`topology:THROW ${e.message}`); }
  try { const w = spiceWorkspace.defaultSpiceWorkspace("pi", board); results.push(`workspace:${w.probes?.length ?? "?"}`); }
  catch (e) { results.push(`workspace:THROW ${e.message}`); }
  try { const nets = Object.values(board.nets ?? {}).filter(Boolean); results.push(`nets:${nets.length}`); }
  catch (e) { results.push(`nets:THROW ${e.message}`); }
  console.log(`${name}: ${results.join(" | ")}`);
}
