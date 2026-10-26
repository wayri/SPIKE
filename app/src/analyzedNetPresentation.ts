// SPDX-License-Identifier: Apache-2.0
/** Presentation identities stay bound to the result's explicit board occurrence. */
export function analyzedNetPresentation(nets: readonly string[], occurrenceId: unknown,
  occurrenceNets: Readonly<Record<string, Readonly<Record<string, string>>>>, assembly = Object.keys(occurrenceNets).length > 0) {
  const unique = [...new Set(nets.filter(Boolean))];
  if (!assembly) return { normal: unique, byBoard: {} as Record<string, string[]>, count: unique.length };
  const names = typeof occurrenceId === "string" ? occurrenceNets[occurrenceId] : undefined;
  if (!names) return { normal: [] as string[], byBoard: {} as Record<string, string[]>, count: 0 };
  const canonical = unique.flatMap(net => {
    if (Object.prototype.hasOwnProperty.call(names, net)) return [net];
    const matches = Object.keys(names).filter(id => names[id] === net);
    return matches.length === 1 ? matches : [];
  });
  const ids = [...new Set(canonical)];
  return { normal: [] as string[], byBoard: ids.length ? { [occurrenceId as string]: ids } : {}, count: ids.length };
}
