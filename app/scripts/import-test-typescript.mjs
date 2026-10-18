import { mkdtempSync, readFileSync, writeFileSync, unlinkSync, rmdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

// Real module URLs preserve ESM cycles and shared module identity, unlike nested
// data URLs. Emit only the runtime dependency closure of the requested fixture.
const directory = mkdtempSync(join(tmpdir(), "spike-schematic-test-"));
const emitted = new Set();
function emit(name) {
  if (!/^[A-Za-z0-9_-]+$/.test(name)) throw new Error(`Unsupported test module: ${name}`);
  if (emitted.has(name)) return;
  emitted.add(name);
  const source = readFileSync(new URL(`../src/${name}.ts`, import.meta.url), "utf8");
  let code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  code = code.replace(/from (["'])([^"']+)\1/g, (_, quote, dependency) => {
    if (dependency.startsWith("./")) {
      const name = dependency.slice(2); emit(name); return `from "./${name}.mjs"`;
    }
    // Emitted fixtures live outside node_modules' resolution tree. Resolve
    // installed dependencies from this test helper, retaining ESM identity.
    return `from ${JSON.stringify(import.meta.resolve(dependency))}`;
  });
  writeFileSync(join(directory, `${name}.mjs`), code);
}
export function importTestTypescript(name) {
  emit(name);
  return import(pathToFileURL(join(directory, `${name}.mjs`)).href);
}
process.on("exit", () => {
  // Delete only the known flat files created by this loader; no recursive delete.
  for (const name of emitted) { try { unlinkSync(join(directory, `${name}.mjs`)); } catch {} }
  try { rmdirSync(directory); } catch {}
});
