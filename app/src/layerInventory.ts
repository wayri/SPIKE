import type { ParsedLayerDefinition, ParsedStackupLayer } from "./boardParser";

export type LayerInventoryGroup =
  | "Copper"
  | "Dielectric"
  | "Board finish"
  | "Documentation"
  | "Mechanical"
  | "User"
  | "Other physical";

export type LayerInventoryEntry = {
  key: string;
  name: string;
  group: LayerInventoryGroup;
  description: string;
  physical: boolean;
  drawable: boolean;
  definition?: ParsedLayerDefinition;
  stackup?: ParsedStackupLayer;
};

export type LayerManagerInventory = {
  entries: LayerInventoryEntry[];
  copperCount: number;
  physicalCount: number;
  drawableCount: number;
  drawableNames: string[];
};

const physicalGroup = (layer: ParsedStackupLayer): LayerInventoryGroup => {
  const identity = `${layer.name} ${layer.type}`.toLowerCase();
  if (layer.name.endsWith(".Cu") || identity.includes("copper") || ["signal", "power", "power_ground", "mixed", "conductor"].includes(layer.type)) return "Copper";
  if (/core|prepreg|dielectric|insulator|substrate/.test(identity)) return "Dielectric";
  if (/mask|paste|silk|adhes|finish|coverlay/.test(identity)) return "Board finish";
  return "Other physical";
};

const definitionGroup = (layer: ParsedLayerDefinition): LayerInventoryGroup => {
  const name = layer.name;
  if (["drill", "rout", "route", "component", "document"].includes(layer.kind)) return "Mechanical";
  if (name.endsWith(".Cu") || ["signal", "power", "power_ground", "mixed", "copper", "conductor"].includes(layer.kind)) return "Copper";
  if (/\.(Mask|Paste|Adhes)$/.test(name)) return "Board finish";
  if (/\.(SilkS|Fab|CrtYd)$/.test(name)) return "Documentation";
  if (name === "Edge.Cuts" || name === "Margin") return "Mechanical";
  return "User";
};

const thicknessLabel = (thickness: number | undefined): string => {
  if (!(Number(thickness) > 0)) return "thickness not specified";
  const micrometres = Number(thickness) * 1000;
  return `${micrometres.toFixed(micrometres < 10 ? 1 : 0)} µm`;
};

const physicalDescription = (layer: ParsedStackupLayer): string => {
  const details = [layer.type || "physical layer", thicknessLabel(layer.thickness)];
  if (layer.material) details.push(layer.material);
  if (Number(layer.epsilonR) > 0) details.push(`εr ${Number(layer.epsilonR).toFixed(3).replace(/\.?0+$/, "")}`);
  if (Number.isFinite(layer.lossTangent)) details.push(`tanδ ${Number(layer.lossTangent)}`);
  return details.join(" · ");
};

const definitionDescription = (layer: ParsedLayerDefinition): string => {
  if (layer.userName) return layer.userName;
  if (layer.name.endsWith(".Cu")) return "Copper signal";
  if (layer.name.endsWith(".Mask")) return "Solder mask";
  if (layer.name.endsWith(".Paste")) return "Solder paste";
  if (layer.name.endsWith(".Adhes")) return "Adhesive";
  if (layer.name.endsWith(".SilkS")) return "Silkscreen";
  if (layer.name.endsWith(".CrtYd")) return "Courtyard";
  if (layer.name.endsWith(".Fab")) return "Fabrication";
  if (layer.name === "Edge.Cuts") return "Board outline";
  if (layer.name === "Margin") return "Board margin";
  return layer.kind === "signal" ? "Signal" : "User";
};

/**
 * Project the canonical physical stack and drawable KiCad layer table into one
 * manager inventory. Stackup rows remain in source order and are never inferred
 * from drawable layers; technical/documentation layers are appended separately.
 */
export function buildLayerManagerInventory(
  definitions: ParsedLayerDefinition[],
  stackup: ParsedStackupLayer[],
): LayerManagerInventory {
  const definitionsByName = new Map(definitions.map(layer => [layer.name, layer]));
  const representedDefinitions = new Set<string>();
  const entries: LayerInventoryEntry[] = stackup.map((layer, index) => {
    const definition = definitionsByName.get(layer.name);
    if (definition) representedDefinitions.add(definition.name);
    return {
      key: `physical:${index}:${layer.name}`,
      name: layer.name,
      group: physicalGroup(layer),
      description: physicalDescription(layer),
      physical: true,
      drawable: Boolean(definition),
      definition,
      stackup: layer,
    };
  });

  // The rendered dielectric body is a scene surface, separate from the
  // physical dielectric rows. It must have its own visibility control so
  // hiding mask or copper cannot accidentally hide the substrate.
  entries.push({
    key: "scene:Board body", name: "Board body", group: "Dielectric",
    description: "FR-4 substrate and board outline", physical: false, drawable: true,
  });

  definitions.forEach(definition => {
    if (representedDefinitions.has(definition.name)) return;
    entries.push({
      key: `drawable:${definition.id}:${definition.name}`,
      name: definition.name,
      group: definitionGroup(definition),
      description: definitionDescription(definition),
      physical: false,
      drawable: true,
      definition,
    });
  });

  const drawableNames = [...new Set(entries.filter(entry => entry.drawable).map(entry => entry.name))];
  const copperCount = new Set([
    ...definitions.filter(layer => definitionGroup(layer) === "Copper").map(layer => layer.name),
    ...stackup.filter(layer => physicalGroup(layer) === "Copper").map(layer => layer.name),
  ]).size;
  return {
    entries,
    copperCount,
    physicalCount: stackup.length,
    drawableCount: drawableNames.length,
    drawableNames,
  };
}

export const LAYER_INVENTORY_GROUP_ORDER: LayerInventoryGroup[] = [
  "Copper", "Dielectric", "Board finish", "Other physical", "Documentation", "Mechanical", "User",
];
