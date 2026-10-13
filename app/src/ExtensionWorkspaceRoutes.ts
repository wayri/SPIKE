// SPDX-License-Identifier: Apache-2.0
/** Declared extension workflow routes, never inferred from names or installation. */
export type ExtensionWorkspace = "mesh" | "si" | "em" | "pi" | "thermal";
export type ExtensionWorkspaceRoute = {
  key: string; id: string; extensionId: string; extensionName: string; contributionId: string;
  setupContributionId: string; previewContributionId?: string; label: string; workspace: ExtensionWorkspace;
  operation: "mesh" | "solve"; modelStatus: string; meshKind?: string; compatibleSolverIds: string[];
  trusted: boolean; enabled: boolean; state: string; schema: Record<string, unknown> | null;
  requiresBoard: boolean;
};
const object = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const identifier = (value: unknown): value is string => typeof value === "string" && /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/.test(value);
const text = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0 && value.length <= 256;
export function extensionWorkspaceRoutes(catalog: unknown, workspace: ExtensionWorkspace, operation?: "mesh" | "solve"): ExtensionWorkspaceRoute[] {
  if (!Array.isArray(catalog)) return [];
  const result: ExtensionWorkspaceRoute[] = [], seen = new Set<string>();
  for (const item of catalog) {
    const extension = object(item);
    if (!identifier(extension.id) || !text(extension.name)) continue;
    const contributions = Object.values(object(extension.contributes)).flatMap(value => Array.isArray(value) ? value.map(object) : []);
    const byId = new Map(contributions.filter(row => identifier(row.id)).map(row => [String(row.id), row]));
    for (const contribution of contributions) {
      if (!identifier(contribution.id) || !Array.isArray(contribution.workspace_routes)) continue;
      for (const value of contribution.workspace_routes) {
        const route = object(value);
        if (!identifier(route.id) || !(["mesh", "si", "em", "pi", "thermal"] as unknown[]).includes(route.workspace) || route.workspace !== workspace || !["mesh", "solve"].includes(String(route.operation)) || operation && route.operation !== operation || !text(route.label) || !text(route.model_status)) continue;
        if (route.setup_contribution_id !== undefined && (!identifier(route.setup_contribution_id) || !byId.has(route.setup_contribution_id))) continue;
        if (route.preview_contribution_id !== undefined && (!identifier(route.preview_contribution_id) || !byId.has(route.preview_contribution_id))) continue;
        if (route.mesh_kind !== undefined && !text(route.mesh_kind)) continue;
        if (route.requires_board !== undefined && typeof route.requires_board !== "boolean") continue;
        if (route.compatible_solver_ids !== undefined && (!Array.isArray(route.compatible_solver_ids) || !route.compatible_solver_ids.every(identifier))) continue;
        const key = `${extension.id}:${route.id}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const setupId = String(route.setup_contribution_id ?? contribution.id);
        result.push({ key, id: route.id, extensionId: extension.id, extensionName: extension.name, contributionId: contribution.id,
          setupContributionId: setupId, previewContributionId: route.preview_contribution_id as string | undefined,
          label: route.label, workspace, operation: route.operation as "mesh" | "solve", modelStatus: route.model_status,
          meshKind: route.mesh_kind as string | undefined, compatibleSolverIds: route.compatible_solver_ids as string[] ?? [],
          requiresBoard: route.requires_board !== false,
          trusted: extension.trusted === true, enabled: !["disabled", "failed", "blocked", "removed"].includes(String(extension.state)),
          state: typeof extension.state === "string" ? extension.state : "unknown", schema: Object.keys(object(byId.get(setupId)?.input_schema)).length ? object(byId.get(setupId)?.input_schema) : null });
      }
    }
  }
  return result;
}
export type ExtensionInputField = { name: string; label: string; description: string; type: "string" | "number" | "integer" | "boolean"; required: boolean; choices?: unknown[]; minimum?: number; maximum?: number };
export function extensionScalarFields(schema: Record<string, unknown> | null): { fields: ExtensionInputField[]; requiresDedicatedGui: boolean } {
  if (!schema) return { fields: [], requiresDedicatedGui: true };
  const required = Array.isArray(schema.required) ? schema.required : [], fields: ExtensionInputField[] = [];
  let requiresDedicatedGui = ["oneOf", "anyOf", "allOf", "$ref", "if"].some(key => schema[key] !== undefined);
  for (const [name, value] of Object.entries(object(schema.properties))) {
    if (["__proto__", "constructor", "prototype"].includes(name)) { requiresDedicatedGui = true; continue; }
    const field = object(value), type = field.type;
    if (!["string", "number", "integer", "boolean"].includes(String(type)) || field.$ref !== undefined || field.oneOf !== undefined || field.anyOf !== undefined || field.allOf !== undefined || field.if !== undefined || field.const !== undefined) { requiresDedicatedGui = true; continue; }
    fields.push({ name, label: typeof field.title === "string" ? field.title : name.replace(/_/g, " "), description: typeof field.description === "string" ? field.description : "",
      type: type as ExtensionInputField["type"], required: required.includes(name), choices: Array.isArray(field.enum) ? field.enum : undefined,
      minimum: typeof field.minimum === "number" ? field.minimum : undefined, maximum: typeof field.maximum === "number" ? field.maximum : undefined });
  }
  if (required.some(name => !fields.some(field => field.name === name))) requiresDedicatedGui = true;
  return { fields, requiresDedicatedGui };
}
export function extensionScalarParameters(schema: Record<string, unknown> | null, values: Record<string, string>): Record<string, unknown> {
  const { fields, requiresDedicatedGui } = extensionScalarFields(schema);
  if (requiresDedicatedGui) throw new Error("Use this extension's dedicated GUI to configure its structured inputs.");
  const result: Record<string, unknown> = {};
  for (const field of fields) {
    const value = values[field.name] ?? "";
    if (!value.trim()) { if (field.required) throw new Error(`${field.label} is required.`); continue; }
    const parsed = field.type === "boolean" ? value === "true" ? true : value === "false" ? false : undefined : field.type === "string" ? value : Number(value);
    if (parsed === undefined || typeof parsed === "number" && (!Number.isFinite(parsed) || field.type === "integer" && !Number.isInteger(parsed) || field.minimum !== undefined && parsed < field.minimum || field.maximum !== undefined && parsed > field.maximum)) throw new Error(`${field.label} is invalid or outside its allowed range.`);
    if (field.choices && !field.choices.some(choice => choice === parsed)) throw new Error(`Choose an available ${field.label}.`);
    result[field.name] = parsed;
  }
  return result;
}
