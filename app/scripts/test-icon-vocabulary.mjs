import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = fs.readFileSync(path.join(root, "src", "App.tsx"), "utf8");
const vocabularyBlock = source.match(/const toolIconByLabel:[\s\S]*?= \{([\s\S]*?)\n\};/);
if (!vocabularyBlock) throw new Error("Ribbon icon vocabulary is missing from App.tsx.");

const iconByLabel = new Map();
for (const match of vocabularyBlock[1].matchAll(/^\s*(?:"([^"]+)"|([A-Za-z][\w ]*)):\s*([A-Za-z][A-Za-z0-9]*),$/gm)) {
  iconByLabel.set(match[1] ?? match[2], match[3]);
}

const groups = {
  PI: ["DC drop", "Bulk nets", "AC sweep", "Transient", "Batch nets", "Terminals", "Power tree", "Probes", "Validate", "Run PI", "PI results", "PI report", "Export data"],
  SI: ["Channel tree", "Impedance", "Parasitics", "Coupling risk", "S-parameters", "NEXT / FEXT", "Eye diagram", "PAM4", "Stackup", "Layer view", "Ports", "Touchstone", "SPICE model", "External engines"],
  EM: ["Net domain", "Preflight", "Risk screen", "Ports", "PI transient", "SPICE", "Domain mesh", "Prepare case", "Run solver", "Solver manager", "Dashboard", "Near field", "Far field", "EMI report"],
  Thermal: ["Bounding volume", "Board stack", "Heat sources", "Flow channels", "Fan placement", "Ambient", "Scenario", "Prepare case", "Solver console", "Temperature", "Report"],
  Probes: ["Hover probe", "Place probe", "Probe table", "Duplicate", "Voltage", "Current", "Impedance", "Compare", "Cross-layer", "Export CSV"],
  Results: ["Issues", "Probe table", "Power tree", "Console", "Fields", "Voltage / current", "Mesh", "Probe overlay", "Compare", "Limits", "Report"],
  Reports: ["Preview", "Print / PDF", "Analytics", "Probe CSV", "Touchstone", "SPICE", "STEP", "Result bundle", "Save instance"],
  Settings: ["Settings", "Extensions", "External engines", "Dependencies", "Verification", "Stackup", "3D library", "Models", "Shortcuts", "Resources", "User guide"],
};

for (const [group, labels] of Object.entries(groups)) {
  const missing = labels.filter(label => !iconByLabel.has(label));
  if (missing.length) throw new Error(`${group} ribbon lacks semantic icons for: ${missing.join(", ")}`);
  const labelsByIcon = new Map();
  for (const label of labels) {
    const icon = iconByLabel.get(label);
    const existing = labelsByIcon.get(icon) ?? [];
    existing.push(label);
    labelsByIcon.set(icon, existing);
  }
  const duplicates = [...labelsByIcon.entries()].filter(([, labelsForIcon]) => labelsForIcon.length > 1);
  if (duplicates.length) {
    throw new Error(`${group} ribbon reuses icons: ${duplicates.map(([icon, labelsForIcon]) => `${icon} (${labelsForIcon.join(" / ")})`).join(", ")}`);
  }
}

// Result controls now live in the result panel, and selection is a named combobox.
if(!source.includes('aria-label="Selection filter"'))throw new Error('Viewport selection combobox is missing');
for(const value of ['all','part','net'])if(!source.includes(`<option value="${value}">`))throw new Error(`Selection mode ${value} is missing`);
const results=fs.readFileSync(path.join(root,'src','ResultVisualizationPanel.tsx'),'utf8');
for(const id of ['voltage','voltage_drop','current','current_density','impedance','power_loss','mesh']){
 const entry=results.match(new RegExp(`\\{ id: "${id}", label: "[^"\\n]+", icon: ([A-Za-z0-9_]+)`));
 if(!entry)throw new Error(`Result mode ${id} has no named semantic icon`);
}
const quick=fs.readFileSync(path.join(root,'src','ViewportQuickTools.tsx'),'utf8');
for(const label of ['Fit','Layers','Inspect','PI setup','Channel','Probe','Thermal setup','EM domain','Results'])if(!quick.includes(`["${label}",`))throw new Error(`Quick tool ${label} has no icon mapping`);
if(!source.includes('<ResultVisualizationPanel'))throw new Error('Result visualization panel is not connected to the workspace');

console.log(`Ribbon icon vocabulary passed for ${Object.keys(groups).length} workspaces.`);
