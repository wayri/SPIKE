import { readFileSync } from "node:fs";
import ts from "typescript";

const ARGS = process.argv.slice(2);
if (!ARGS.length) { console.error("usage: repro-parse.mjs <file...>"); process.exit(2); }

const compilerOptions = { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 };
const numericRangeSource = readFileSync(new URL("../src/numericRange.ts", import.meta.url), "utf8");
const numericRangeModule = ts.transpileModule(numericRangeSource, { compilerOptions }).outputText;
const numericRangeUrl = `data:text/javascript;base64,${Buffer.from(numericRangeModule).toString("base64")}`;
const parserSource = readFileSync(new URL("../src/boardParser.ts", import.meta.url), "utf8");
const parserModule = ts.transpileModule(parserSource, { compilerOptions }).outputText
  .replace('from "./numericRange";', `from "${numericRangeUrl}";`);
const parser = await import(`data:text/javascript;base64,${Buffer.from(parserModule).toString("base64")}`);

for (const file of ARGS) {
  try {
    const source = readFileSync(file, "utf8");
    const board = parser.parseKicadBoard(source);
    console.log(`OK   ${file}`);
    console.log(`     layers=${board.layers?.length} defs=${board.layerDefinitions?.length} tracks=${board.tracks?.length} pads=${board.pads?.length} vias=${board.vias?.length} zones=${board.zones?.length} comps=${board.components?.length} nets=${board.nets?.length} stackup=${board.stackup?.length}`);
  } catch (err) {
    console.log(`FAIL ${file}`);
    console.log(`     ${err && err.stack ? err.stack.split("\n").slice(0, 8).join("\n     ") : String(err)}`);
  }
}
