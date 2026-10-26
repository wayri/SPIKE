// SPDX-License-Identifier: Apache-2.0
import manifest from "../../examples/catalog/work-examples.json";
import { optionMatchesQuery } from "./optionSearch";
import { workExampleAssets } from "./workExampleAssets";

export type WorkExampleStatus = "runnable" | "setup-only" | "saved-evidence" | "guide";
export type WorkExample = {
  id: string; title: string; category: string; status: WorkExampleStatus; summary: string;
  engine: string; dependencies: string; primaryAction: "download" | "emerge-library" | "ibis" | "spatial" | "project";
  steps: string[]; limits: string; command?: string; assets: string[]; license: string;
  projectAsset?: string;
  preview?: { asset: string; alt: string; caption: string };
};
/** Opening stages reviewed text only. The parent owns all workspace mutation and run authority. */
export type WorkExampleAction = { kind: "emerge-library" }
  | { kind: "ibis"; requestText: string }
  | { kind: "spatial"; designText: string; solverText: string; samplesText: string }
  | { kind: "project"; snapshotText: string; fileName: string };
export const workExamples = manifest.examples as WorkExample[];
export const workExampleStatuses: WorkExampleStatus[] = ["runnable", "setup-only", "saved-evidence", "guide"];
export function findWorkExamples(query: string, category = "all", status = "all"): WorkExample[] {
  return workExamples.filter(row => (category === "all" || row.category === category)
    && (status === "all" || row.status === status)
    && optionMatchesQuery([row.title, row.category, row.summary, row.engine, row.dependencies, ...row.steps].join(" "), query));
}
export async function loadWorkExampleAsset(entryId: string, path: string): Promise<{ name: string; text: string }> {
  const row = workExamples.find(entry => entry.id === entryId);
  const loader = row?.assets.includes(path) && workExampleAssets[`../../${path}`];
  if (!loader) throw new Error("This file is not bundled for the selected example. Update SPIKE resources and try again.");
  const text = await loader();
  const limit = row?.primaryAction === "project" && row.projectAsset === path ? 8 * 1024 * 1024 : 512 * 1024;
  if (typeof text !== "string" || !text.length || new TextEncoder().encode(text).byteLength > limit) throw new Error(`The example text is empty or exceeds the ${limit / 1024} KiB resource limit.`);
  return { name: path.split("/").pop()!, text };
}
export async function prepareWorkExampleAction(entryId: string): Promise<WorkExampleAction> {
  const row = workExamples.find(entry => entry.id === entryId);
  if (!row) throw new Error("Unknown example. Clear filters and select an example again.");
  if (row.primaryAction === "project") {
    if (!row.projectAsset?.endsWith(".spike.json")) throw new Error("The example has no reviewed project snapshot.");
    const file = await loadWorkExampleAsset(entryId, row.projectAsset);
    return { kind: "project", snapshotText: file.text, fileName: file.name.replace(/\.json$/, "") };
  }
  if (row.primaryAction === "emerge-library") return { kind: "emerge-library" };
  if (row.primaryAction === "ibis") return { kind: "ibis", requestText: (await loadWorkExampleAsset(entryId, "examples/si/ibis_driver_receiver/request.json")).text };
  if (row.primaryAction === "spatial") {
    const [design, solver, samples] = await Promise.all(["board.spike-design", "solver", "samples"].map(name => loadWorkExampleAsset(entryId, `examples/si/spatial_crosstalk/${name}.json`)));
    return { kind: "spatial", designText: design.text, solverText: solver.text, samplesText: samples.text };
  }
  throw new Error("This example provides files for manual review and execution; it has no automatic workspace action.");
}
