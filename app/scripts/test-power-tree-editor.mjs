import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../src/TopologyEditor.tsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

for (const marker of [
  "onContextMenu=", "topology-context-menu", "topology-marquee", "marqueeRef",
  "canvasPoint", "wirePointer", "topology-pending-wire",
  'style={{ left: marquee.x, top: marquee.y, width: marquee.width, height: marquee.height }}',
  'data-topology-port="input"', 'data-topology-port="output"',
  "Wire from selected", "Cancel wire", "startWire", "finishWire",
  "duplicateSelected", "deleteSelected", "runDestructive", "Confirm clear", "Confirm reset",
  'event.key === "Delete"', 'event.key === "Escape"', 'event.key.toLowerCase() === "a"',
  "layoutTopology(model.nodes, model.edges)", "onClick={useForAnalysis}", "onClick={autoExtract}",
  "onClick={buildSelectedPath}", "onClick={fitDiagram}", "zoomAtCenter(1.2)", "zoomAtCenter(0.83)",
  "topologyPorts(node, domain)", "fromPort: fromPort.id", "toPort: toPort.id", "portBinding: \"explicit\"",
  "BLOCK PORTS", "Differential template", "READ-ONLY TEXT EQUIVALENT", "Copy text", "Export text", "Copy JSON",
  "Save channel setup", "validateTopologyPorts(model)",
]) assert.ok(source.includes(marker), `Power Tree editor is missing ${marker}`);

for (const selector of [".topology-context-menu", ".topology-marquee", ".topology-pending-wire", ".topology-port.input", ".topology-port.output", ".topology-port-stack", ".topology-port-editor", ".topology-text-panel", ".topology-node.selected", ".topology-toolbar > button.danger-confirm"])
  assert.ok(styles.includes(selector), `Power Tree styles are missing ${selector}`);

console.log("SPIKE Power Tree editor command, selection, and destructive-action assertions passed");

// Render both domains to keep secondary commands available without expanding
// the permanent toolbar, and retain their selection/undo disabled states.
const [{ default: React }, { renderToStaticMarkup }, { default: ts }, { createRequire }, { importTestTypescript }] = await Promise.all([
  import("react"), import("react-dom/server"), import("typescript"), import("node:module"), import("./import-test-typescript.mjs"),
]);
const [powerTree, numericRange] = await Promise.all([importTestTypescript("powerTree"), importTestTypescript("numericRange")]);
const require = createRequire(import.meta.url);
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;
const loaded = { exports: {} };
new Function("require", "module", "exports", compiled)(name => {
  if (name.endsWith(".css")) return {};
  if (name === "./powerTree") return powerTree;
  if (name === "./numericRange") return numericRange;
  if (name === "./panelPresentation") return { usePanelPresentation: () => ({ ownerWindow: { innerWidth: 1200 }, ownerDocument: null }) };
  if (name === "./icons") return new Proxy({}, { get: () => () => React.createElement("svg") });
  if (name === "./CircuitSymbol") return { default: () => null, paletteSymbol: () => React.createElement("svg") };
  if (name.startsWith("./")) return { default: () => null };
  return require(name);
}, loaded, loaded.exports);
for (const domain of ["pi", "si"]) {
  const html = renderToStaticMarkup(React.createElement(loaded.exports.default, {
    domain, board: null, model: powerTree.emptyTopology(domain), setModel() {}, onClose() {}, onUseForAnalysis() {}, onStatus() {}, onOpenStudio() {},
  }));
  assert.ok(html.includes('</svg></div><div class="topology-empty">'), "empty hint is a canvas overlay outside the transformed graph surface");
  const menus = [...html.matchAll(/<details class="topology-tool-menu"[\s\S]*?<\/details>/g)].map(match => match[0]);
  assert.equal(menus.length, 2, `${domain}: source and edit commands remain contextual`);
  assert.ok(menus.every(menu => !menu.startsWith('<details class="topology-tool-menu" open')), "menus start collapsed");
  assert.match(menus[0], /Extract from board/);
  assert.match(menus[0], /Import schematic \/ netlist/);
  assert.match(menus[0], /tabindex="0"/, "file import remains keyboard reachable");
  assert.match(menus[1], /disabled=""[^>]*title="Connect the first selected element/, "connection requires exactly two selected elements");
  assert.match(menus[1], /Confirm|Reset/, "reset remains available in Edit");
  assert.match(html, /Open the circuit workspace in SPIKES Studio/, "optional adjacent circuit workspace remains explicit");
  assert.match(html, /disabled="" title="Undo/, "unavailable undo stays disabled");
  assert.ok(html.includes(domain === "pi" ? "Use for analysis" : "Save channel setup"));
}
console.log("SPIKE Power/Channel Tree compact toolbar rendering and disabled command states passed");
