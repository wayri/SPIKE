// SPDX-License-Identifier: Apache-2.0
import { duplicateBoardInstance, removeBoardInstance, type BoardInstance } from "./assemblyBoardLifecycle";
import { connectorOccurrences, explicitNetLinkRows, validateExplicitNetLink, applyExplicitNetLink } from "./assemblyBoardManagerModel";
import { placeAssemblyBoard } from "./BoardPlacementTool";
import type { AssemblyIr, AssemblyDesigns } from "./mcadAssembly";
export function assistantAssemblyContext(assembly: AssemblyIr | null, designs: AssemblyDesigns | null, args: Record<string, unknown>): Record<string, unknown> {
  if (!assembly) return { loaded: false };
  const offset = Number(args.offset ?? 0), limit = Number(args.limit ?? 30);
  if (!Number.isSafeInteger(offset) || offset < 0 || !Number.isSafeInteger(limit) || limit < 1 || limit > 100) throw new Error("Invalid assembly page.");
  const page = (rows: unknown[]) => ({ count: rows.length, offset, items: rows.slice(offset, offset + limit), more: offset + limit < rows.length });
  return { loaded: true, assemblyId: assembly.assembly_id, units: "mm", boards: page(assembly.boards),
    parts: page(assembly.parts.map(({ id, name, part_type, model_id, material_id, frame }) => ({ id, name, part_type, model_id, material_id, frame }))),
    harnesses: page(assembly.harnesses ?? []), thermalContacts: page(assembly.thermal_contacts ?? []), electricalBonds: page(assembly.electrical_bonds ?? []),
    connectors: page(designs ? connectorOccurrences(assembly, designs) : []), links: page(explicitNetLinkRows(assembly)) };
}
export function mutateAssistantAssembly(command: string, args: Record<string, unknown>, assembly: AssemblyIr, designs: AssemblyDesigns | null): { assembly: AssemblyIr; evidence: Record<string, unknown> } {
  const boardId = String(args.boardId ?? "");
  const board = assembly.boards.find(item => item.id === boardId);
  if (command === "assembly_add_occurrence") {
    const designId = String(args.designId ?? "");
    const design = designs?.designs.find(item => item.design_id === designId);
    if (!design || !assembly.frame?.frame_id) throw new Error("Choose an existing retained design and a resolved assembly root frame.");
    const source = assembly.boards.find(item => item.design_id === designId) as BoardInstance | undefined;
    const seed = source ?? { id: "retained-seed", name: String(design.name ?? designId), design_id: designId,
      frame: { frame_id: "retained-seed-frame", parent_frame_id: assembly.frame.frame_id, units: "mm", handedness: "right", transform: [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1] } };
    const copy = duplicateBoardInstance(assembly, designs, seed, `board-${crypto.randomUUID()}`);
    return { assembly: { ...assembly, boards: [...assembly.boards, copy] }, evidence: { designId, occurrenceId: copy.id, saved: false } };
  }
  if (command === "assembly_duplicate_occurrence") {
    if (!board) throw new Error("Board occurrence no longer exists.");
    const copy = duplicateBoardInstance(assembly, designs, board as BoardInstance, `board-${crypto.randomUUID()}`);
    return { assembly: { ...assembly, boards: [...assembly.boards, copy] }, evidence: { duplicatedFrom: boardId, occurrenceId: copy.id, saved: false } };
  }
  if (command === "assembly_remove_occurrence") {
    if (!board || assembly.boards.length <= 1) throw new Error("Keep at least one retained board; choose an existing occurrence.");
    // Conservatively block dependencies until typed contact/bond cleanup is implemented.
    if ((assembly.thermal_contacts?.length ?? 0) || (assembly.electrical_bonds?.length ?? 0) || assembly.parts.some(part => part.frame?.parent_frame_id === (board.frame as {frame_id?:string})?.frame_id)) throw new Error("Resolve mechanical children, thermal contacts and electrical bonds in the assembly editor before removing a board.");
    const result = removeBoardInstance(assembly, boardId);
    return { assembly: result.assembly, evidence: { removed: boardId, removedLinks: result.removedLinks, saved: false } };
  }
  if (command === "assembly_set_transform") {
    const m = args.transform as number[];
    if (!Array.isArray(m) || m.length !== 16 || !m.every(Number.isFinite) || Math.max(Math.abs(m[12]), Math.abs(m[13]), Math.abs(m[14]), Math.abs(m[15] - 1)) > 1e-8) throw new Error("A row-major rigid transform is required.");
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) {
      const dot = [0,1,2].reduce((sum, k) => sum + m[i*4+k]*m[j*4+k], 0);
      if (Math.abs(dot - (i === j ? 1 : 0)) > 1e-6) throw new Error("Scale and shear are not board placement.");
    }
    const det = m[0]*(m[5]*m[10]-m[6]*m[9])-m[1]*(m[4]*m[10]-m[6]*m[8])+m[2]*(m[4]*m[9]-m[5]*m[8]);
    if (Math.abs(det - 1) > 1e-6) throw new Error("Reflections are not board placement.");
    return { assembly: placeAssemblyBoard(assembly, boardId, m), evidence: { placed: boardId, saved: false } };
  }
  if (command === "assembly_link_connectors") {
    if (!designs) throw new Error("Retained assembly designs are required.");
    const row = { id: `link-${crypto.randomUUID()}`, endpointA: String(args.endpointA), endpointB: String(args.endpointB), pinA: String(args.pinA), pinB: String(args.pinB), applied: false };
    validateExplicitNetLink(assembly, designs, row);
    if (explicitNetLinkRows(assembly).some(existing => existing.endpointA === row.endpointA && existing.pinA === row.pinA && existing.endpointB === row.endpointB && existing.pinB === row.pinB)) throw new Error("That explicit connector link already exists.");
    return { assembly: applyExplicitNetLink(assembly, row), evidence: { linked: row, saved: false } };
  }
  throw new Error("Unsupported assistant assembly action.");
}
