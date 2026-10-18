// SPDX-License-Identifier: Apache-2.0
export type SolverBlockSelection = { selected_blocks?: string[]; selected_groups?: string[] };
export type SolverBlock = {
  id: string; name: string; groups: string[]; requires: string[]; optional: string[];
  capability_ids: string[]; delivery: "bundled" | "external" | "planned";
  description: string; external_requirements?: string[];
};
export type SolverBlockCatalog = {
  contract: "spike/solver-blocks/v1"; catalog_version: string; packaging_mode: "bundled_all"; managed_downloads: false;
  groups: Array<{ id: string; name: string }>; blocks: SolverBlock[];
  plan: { requested_blocks: string[]; required_blocks: string[]; ordered_blocks: string[];
    blocked_blocks: string[]; warnings: string[]; action: "preview_only" };
};
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(item => typeof item === "string");
export function readSolverBlockCatalog(value: unknown): SolverBlockCatalog {
  const data = value as SolverBlockCatalog | undefined;
  if (!data || data.contract !== "spike/solver-blocks/v1" || typeof data.catalog_version !== "string" || data.packaging_mode !== "bundled_all" || data.managed_downloads !== false ||
      !Array.isArray(data.groups) || !data.groups.every(group => typeof group.id === "string" && typeof group.name === "string") ||
      !Array.isArray(data.blocks) || !data.blocks.every(block => typeof block.id === "string" && typeof block.name === "string" &&
        typeof block.description === "string" && ["bundled", "external", "planned"].includes(block.delivery) &&
        [block.groups, block.requires, block.optional, block.capability_ids].every(strings)) ||
      !data.plan || data.plan.action !== "preview_only" ||
      ![data.plan.requested_blocks, data.plan.required_blocks, data.plan.ordered_blocks, data.plan.blocked_blocks, data.plan.warnings].every(strings)) {
    throw new Error("Solver block catalog is unavailable or incompatible. Update the matching SPIKE worker and retry.");
  }
  const ids = new Set(data.blocks.map(block => block.id));
  if (ids.size !== data.blocks.length || data.blocks.some(block => [...block.requires, ...block.optional].some(id => !ids.has(id))) ||
      [...data.plan.requested_blocks, ...data.plan.required_blocks, ...data.plan.ordered_blocks, ...data.plan.blocked_blocks].some(id => !ids.has(id))) {
    throw new Error("Solver block catalog contains unresolved identities. Dependency preview was not applied.");
  }
  return data;
}
export function filterSolverBlocks(catalog: SolverBlockCatalog, query: string, group: string): SolverBlock[] {
  const terms = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  return catalog.blocks.filter(block => (group === "all" || block.groups.includes(group)) && terms.every(term =>
    `${block.id} ${block.name} ${block.description} ${block.groups.join(" ")} ${block.requires.join(" ")} ${block.optional.join(" ")}`.toLowerCase().includes(term)));
}
