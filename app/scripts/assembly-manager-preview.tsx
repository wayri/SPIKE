// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { createRoot } from "react-dom/client";
import AssemblyBoardManagers from "../src/AssemblyBoardManagers";
import type { AssemblyDesigns, AssemblyIr } from "../src/mcadAssembly";
import "../src/styles.css";
import "../src/buttonStandard.css";
import "../src/assemblyToolWindows.css";

const designs = { contract: "spike/assembly-designs/v1", active_design_id: "carrier", designs: [{
  contract: "spike/design-ir/v2", design_id: "carrier",
  nets: [{ id: "gnd", name: "GND" }, { id: "vbus", name: "+12V_INPUT" }, { id: "clk", name: "SPI_CLOCK_LONG_OCCURRENCE_NAME" }],
  materials: [{ id: "mat-cu", name: "Copper", properties: { conductivity_s_per_m: 5.8e7 } }, { id: "mat-fr4", name: "FR-4", properties: { relative_permittivity: 4.2 } }],
  layers: [
    { id: "F.Cu", layer_type: "copper", thickness_mm: 0.035, material_id: "mat-cu", z_mm: 0.8, extensions: { "spike.v1.stackup": { name: "F.Cu", thickness: 0.035, type: "Top Copper" } } },
    { id: "In1.Cu", layer_type: "copper", thickness_mm: 0.035, material_id: "mat-cu", z_mm: 0.2, extensions: { "spike.v1.stackup": { name: "In1.Cu", thickness: 0.035, type: "Inner Copper" } } },
    { id: "core", layer_type: "dielectric", thickness_mm: 1.13, material_id: "mat-fr4", z_mm: 0, extensions: { "spike.v1.stackup": { name: "Core", thickness: 1.13, type: "Core" } } },
    { id: "In2.Cu", layer_type: "copper", thickness_mm: 0.035, material_id: "mat-cu", z_mm: -0.2, extensions: { "spike.v1.stackup": { name: "In2.Cu", thickness: 0.035, type: "Inner Copper" } } },
    { id: "B.Cu", layer_type: "copper", thickness_mm: 0.035, material_id: "mat-cu", z_mm: -0.8, extensions: { "spike.v1.stackup": { name: "B.Cu", thickness: 0.035, type: "Bottom Copper" } } },
    { id: "F.Mask", layer_type: "user", thickness_mm: 0.02 }, { id: "B.Mask", layer_type: "user", thickness_mm: 0.02 },
    { id: "F.SilkS", layer_type: "user" }, { id: "B.SilkS", layer_type: "user" }, { id: "Edge.Cuts", layer_type: "user" },
  ],
  tracks: [{ net_id: "gnd", layer_id: "F.Cu" }, { net_id: "clk", layer_id: "In1.Cu" }],
  arcs: [{ net_id: "vbus", layer_id: "B.Cu" }], vias: [{ net_id: "gnd", start_layer_id: "F.Cu", end_layer_id: "B.Cu" }],
  pads: [{ net_id: "gnd", layer_ids: ["F.Cu", "B.Cu"], component_id: "J1" }], zones: [{ net_id: "gnd", layer_ids: ["In2.Cu"] }],
  extensions: { "spike.preview.source": { source: "app/scripts/test-assembly-board-managers.mjs", purpose: "native manager layout acceptance" } },
}] } as unknown as AssemblyDesigns;

const initialAssembly = { contract: "spike/assembly-ir/v1", assembly_id: "manager-preview", name: "Retained dual-board manager preview", parts: [],
  boards: [{ id: "controller", name: "Controller board with retained source metadata", design_id: "carrier" }, { id: "power", name: "Power daughterboard", design_id: "carrier" }],
  harnesses: [{ id: "board-link", endpoint_a: "controller::J1", endpoint_b: "power::J1", pin_map: { "1": "1", "2": "2" } }],
  connector_mappings: [
    { id: "controller-j1", kind: "connector", data: { board_id: "controller", connector_id: "J1", pins: { "1": "gnd", "2": "clk" } } },
    { id: "power-j1", kind: "connector", data: { board_id: "power", connector_id: "J1", pins: { "1": "gnd", "2": "vbus" } } },
  ], extensions: { "spike.preview.source": { source: "app/scripts/test-assembly-board-managers.mjs", generated: false } },
} as unknown as AssemblyIr;

const layerDefaults = { "F.Cu": true, "In1.Cu": true, "In2.Cu": true, "B.Cu": true, "F.Mask": true, "B.Mask": true, "F.SilkS": true, "B.SilkS": true, "Edge.Cuts": true };
function Preview() {
  const [assembly, setAssembly] = useState(initialAssembly);
  const [selectedBoardId, setSelectedBoardId] = useState("controller");
  const [visibility, setVisibility] = useState<Record<string, Record<string, boolean>>>({ controller: layerDefaults, power: layerDefaults });
  const [opacity, setOpacity] = useState<Record<string, Record<string, number>>>({ controller: {}, power: {} });
  const [status, setStatus] = useState("Synthetic assembly fixture · 600 × 720 manager preview");
  return <main className="assembly-tool-root assembly-tool-managers assembly-tool-native" style={{ width: 600, height: 720 }}>
    <fieldset className="assembly-tool-edit-scope">
      <AssemblyBoardManagers embedded nativeWindow assembly={assembly} designs={designs} selectedBoardId={selectedBoardId} initialTab="layers"
        assemblyLayerVisibility={visibility} assemblyLayerOpacity={opacity} onFocusBoard={setSelectedBoardId}
        onAssemblyLayerVisibility={(boardId, layer, value) => setVisibility(current => ({ ...current, [boardId]: { ...(current[boardId] ?? {}), [layer]: value } }))}
        onAssemblyLayerOpacity={(boardId, layer, value) => setOpacity(current => ({ ...current, [boardId]: { ...(current[boardId] ?? {}), [layer]: value } }))}
        onAssemblyLayersChange={(boardId, layers, values) => { setVisibility(current => ({ ...current, [boardId]: { ...(current[boardId] ?? {}), ...layers } })); if (values) setOpacity(current => ({ ...current, [boardId]: { ...(current[boardId] ?? {}), ...values } })); }}
        onSelectNet={(occurrence, netId) => setStatus(`Selected ${occurrence} / ${netId}`)} onUpdated={setAssembly} onStatus={setStatus} onClose={() => setStatus("Close requested")}/>
    </fieldset>
    <footer className="assembly-tool-status" role="status">{status}</footer>
  </main>;
}
createRoot(document.getElementById("root")!).render(<Preview />);