import { parseKicadBoard, ParsedBoard } from "./boardParser";
import { parseNormalizedBoard } from "./normalizedBoard";

export type DesignSourceDescriptor = {
  id: string;
  label: string;
  extensions: readonly string[];
  sourceFormats: readonly string[];
  status: "available" | "planned";
};

export interface DesignSourceAdapter {
  descriptor: DesignSourceDescriptor;
  parse(source: string): ParsedBoard;
}

const adapters: readonly DesignSourceAdapter[] = [{
  descriptor: {
    id: "kicad-pcb",
    label: "KiCad PCB",
    extensions: [".kicad_pcb"],
    sourceFormats: ["kicad", "kicad_pcb"],
    status: "available",
  },
  parse: parseKicadBoard,
}, {
  descriptor: { id: "spike-normalized", label: "Imported CAD design", extensions: [".spike-design.json"], sourceFormats: ["spike-normalized"], status: "available" },
  parse: parseNormalizedBoard,
}];

export function designSourceCatalog(): readonly DesignSourceDescriptor[] {
  return adapters.map(adapter => adapter.descriptor);
}

export function resolveDesignSourceAdapter(fileName: string, formatHint = ""): DesignSourceAdapter {
  const hint = formatHint.trim().toLowerCase();
  const lowerName = fileName.toLowerCase();
  const matches = adapters.filter(adapter => hint
    ? adapter.descriptor.id === hint || adapter.descriptor.sourceFormats.includes(hint)
    : adapter.descriptor.extensions.some(extension => lowerName.endsWith(extension)));
  if (matches.length === 1) return matches[0];
  if (matches.length > 1) throw new Error(`Ambiguous design source ${fileName}; specify its source format.`);
  throw new Error(`No installed design importer supports ${fileName}.`);
}

export function parseDesignSource(fileName: string, source: string, formatHint = ""): ParsedBoard {
  if (!source.trim()) throw new Error("The selected design source is empty.");
  return resolveDesignSourceAdapter(fileName, formatHint).parse(source);
}
