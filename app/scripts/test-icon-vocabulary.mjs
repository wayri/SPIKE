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
  EMI: ["Net domain", "Preflight", "Risk screen", "Ports", "PI transient", "SPICE", "Domain mesh", "Prepare case", "Run solver", "Solver manager", "Dashboard", "Near field", "Far field", "EMI report"],
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

const toolbarContracts = [
  ["Part selection", "<Component size={14} /><span>Part</span>"],
  ["Net selection", "<Route size={14} /><span>Net</span>"],
  ["Absolute voltage", "<Zap size={14} /> Voltage"],
  ["Voltage drop", "<TrendingDown size={14} /> Drop"],
  ["Current", "<ArrowRightLeft size={14} /> Current"],
  ["Current density", "<ChartNoAxesColumnIncreasing size={14} /> Density"],
  ["Impedance", "<Omega size={14} /> Impedance"],
  ["RLC", "<Component size={14} /> RLC"],
  ["Translucency", "<Blend size={14} /> Translucent"],
  ["Net isolation", "<RouteOff size={14} /> Nets only"],
  ["Model visibility", "<Boxes size={14} /> Models"],
  ["Contour", "<Spline size={14} /> Contour"],
  ["Smooth field", "<Combine size={14} /> Smooth field"],
  ["Vectors", "<MoveUpRight size={14} /> Arrows"],
];
for (const [name, snippet] of toolbarContracts) {
  if (!source.includes(snippet)) throw new Error(`${name} toolbar icon contract is missing.`);
}

console.log(`Ribbon icon vocabulary passed for ${Object.keys(groups).length} workspaces.`);
