import { APP_VERSION } from "./appVersion";

export const SPIKE_PROJECT_FORMAT = "spike-project-package/v2";
export const SPIKE_PROJECT_CONTRACT = "spike/project/v2";
export const SPIKE_PROJECT_EXTENSION = ".spike";

export type SpikeProjectPackage = Record<string, any> & {
  format: string;
  contract: string;
  saved_at: string;
  project: { name: string; id?: string };
  manifest?: {
    application: string;
    application_version: string;
    source_checksum?: string;
    content: string[];
  };
};

function fnv1a(value: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

function projectId(name: string, source: string): string {
  return `spike-${fnv1a(`${name}\n${source.slice(0, 65536)}`)}`;
}

export function createProjectPackage(payload: Record<string, any>): SpikeProjectPackage {
  const source = String(payload.design?.source_board ?? "");
  const name = String(payload.project?.name ?? "untitled.spike");
  return {
    ...payload,
    format: SPIKE_PROJECT_FORMAT,
    contract: SPIKE_PROJECT_CONTRACT,
    saved_at: new Date().toISOString(),
    project: {
      ...payload.project,
      name,
      id: payload.project?.id ?? projectId(name, source),
    },
    manifest: {
      application: "SPIKE",
      application_version: APP_VERSION,
      source_checksum: source ? `fnv1a32:${fnv1a(source)}` : undefined,
      content: ["project", "design", "assembly_ir", "assembly_designs", "assembly_package_shapes", "models", "analysis", "spice", "emi", "thermal", "studies", "workspace", "probes", "selection"],
    },
  };
}

export function parseProjectPackage(text: string): { project: SpikeProjectPackage; migrated: boolean } {
  const raw = JSON.parse(text) as Record<string, any>;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("Project package must contain a JSON object.");
  const supported = [SPIKE_PROJECT_FORMAT, "spike-project-package/v1"];
  if (!supported.includes(String(raw.format ?? ""))) throw new Error(`Unsupported SPIKE project format: ${String(raw.format ?? "missing")}`);
  if (!raw.project || !raw.design || !raw.analysis) throw new Error("Project package is missing project, design, or analysis data.");
  const source = String(raw.design.source_board ?? "");
  const expected = String(raw.manifest?.source_checksum ?? "");
  if (expected && expected !== `fnv1a32:${fnv1a(source)}`) throw new Error("Embedded design checksum does not match the project manifest.");
  const migrated = raw.format !== SPIKE_PROJECT_FORMAT;
  return { project: createProjectPackage(raw), migrated };
}

export function projectFileName(name: string): string {
  const stem = name.replace(/\.spike(?:\.json)?$/i, "").replace(/[^a-z0-9._-]+/gi, "-") || "untitled";
  return `${stem}${SPIKE_PROJECT_EXTENSION}`;
}
