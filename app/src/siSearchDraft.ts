// SPDX-License-Identifier: Apache-2.0
/** Reviewed input only. App retains board and occurrence context admission. */
export type SiSearchDraft = {
  id: string;
  signalNetId?: string;
  referenceNetId?: string;
  frequencyStartHz?: number;
  frequencyStopHz?: number;
  bitRateHz?: number;
  impedanceOhm?: number;
  riseTimeS?: number;
  componentRefs?: string[];
};

export function siSearchDraftError(draft: SiSearchDraft, netIds: readonly string[]): string {
  if (!draft.id.trim()) return "Search setup has no review identity. Search again.";
  for (const id of [draft.signalNetId, draft.referenceNetId]) {
    if (id !== undefined && !netIds.includes(id)) return "A requested SI net no longer exists. Search the current board again.";
  }
  if (draft.signalNetId !== undefined && draft.signalNetId === draft.referenceNetId) return "Signal and reference nets must be distinct.";
  if (draft.frequencyStartHz !== undefined && (!Number.isFinite(draft.frequencyStartHz) || draft.frequencyStartHz < 0)) return "Frequency start must be finite and non-negative.";
  if (draft.frequencyStopHz !== undefined && (!Number.isFinite(draft.frequencyStopHz) || draft.frequencyStopHz <= (draft.frequencyStartHz ?? 0))) return "Frequency stop must be finite and greater than frequency start.";
  if (draft.bitRateHz !== undefined && (!Number.isFinite(draft.bitRateHz) || draft.bitRateHz <= 0)) return "Bit rate must be positive and finite.";
  if (draft.impedanceOhm !== undefined && (!Number.isFinite(draft.impedanceOhm) || draft.impedanceOhm <= 0)) return "Reference impedance must be positive and finite.";
  if (draft.riseTimeS !== undefined && (!Number.isFinite(draft.riseTimeS) || draft.riseTimeS <= 0)) return "Rise time must be positive and finite.";
  return "";
}
