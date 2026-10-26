// SPDX-License-Identifier: Apache-2.0
import advanced from "../../examples/emerge/gallery/advanced.json";
import catalog from "../../examples/emerge/gallery/catalog.json";
import { optionMatchesQuery } from "./optionSearch";
export type EMergeExample = { id: string; title: string; category: string; summary: string; capabilities: string[]; project_path: string; snapshot_path: string; model_status: string; status?: string };
export const emergeExamples = catalog.examples as EMergeExample[];
export function findEMergeExamples(query: string, category = "all") {
  return emergeExamples.filter(row => (category === "all" || row.category === category) && optionMatchesQuery([row.title, row.category, row.summary, ...row.capabilities].join(" "), query));
}
const snapshots = import.meta.glob("../../examples/emerge/gallery/snapshots/*.json", { query: "?raw", import: "default" });
export async function loadEMergeExampleSnapshot(id: string): Promise<string> {
  const row = emergeExamples.find(example => example.id === id);
  const load = row && snapshots[`../../${row.snapshot_path}`];
  if (!load) throw new Error("The selected EMerge example is not bundled. Update or rebuild SPIKE with the example resources.");
  const value = await load();
  if (typeof value !== "string" || value.length > 32 * 1024 * 1024) throw new Error("The bundled example has an invalid payload.");
  return value;
}

export type AdvancedEMergeStudy = { id: string; title: string; category: string; study_path: string; status: string; license: string };
export const advancedEMergeStudies = advanced.studies as AdvancedEMergeStudy[];
export function findAdvancedEMergeStudies(query: string, category = "all") {
  return advancedEMergeStudies.filter(row => (category === "all" || row.category === category) && optionMatchesQuery(`${row.title} ${row.category} ${row.status}`, query));
}
const studies = import.meta.glob("../../examples/upstream-emerge/studies/*.spike-em.json", { query: "?raw", import: "default" });
export async function loadAdvancedEMergeStudy(id: string): Promise<{ name: string; text: string }> {
  const row = advancedEMergeStudies.find(study => study.id === id);
  if (!row || row.status === "suspended") throw new Error("This study is suspended; no runnable wrapper is offered.");
  const load = studies[`../../${row.study_path}`];
  if (!load) throw new Error("This study wrapper is not bundled. Update SPIKE resources.");
  const text = await load();
  if (typeof text !== "string") throw new Error("Invalid study resource.");
  return { name: row.study_path.split("/").pop()!, text };
}
