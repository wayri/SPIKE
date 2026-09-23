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
