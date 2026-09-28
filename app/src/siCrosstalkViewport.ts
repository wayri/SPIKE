// SPDX-License-Identifier: Apache-2.0

export type SiCrosstalkViewportResult = {
  binding: {
    sourceDesignId: string;
    activeDesignId: string;
    aggressorNetId: string;
    victimNetId: string;
    boardAggressorNetId: string;
    boardVictimNetId: string;
  };
  aggressorNet: string;
  victimNet: string;
  nextDb?: number;
  fextDb?: number;
  peakNextV?: number;
  peakFextV?: number;
  modelStatus: string;
  sourceLabel?: string;
};

export type AdmittedSiCrosstalkViewport = SiCrosstalkViewportResult & {
  metrics: { nextDb?: number; fextDb?: number; peakNextV?: number; peakFextV?: number };
};

const finiteOptional = (value: number | undefined) => value === undefined || Number.isFinite(value);

/** Admit only a result whose design and two net identities bind to the active canonical board. */
export function admitSiCrosstalkViewport(
  value: SiCrosstalkViewportResult | null | undefined,
  boardNetNames: ReadonlySet<string>,
): AdmittedSiCrosstalkViewport | null {
  if (!value) return null;
  const { binding } = value;
  if (!binding.sourceDesignId || binding.sourceDesignId !== binding.activeDesignId
      || !binding.aggressorNetId || binding.aggressorNetId !== binding.boardAggressorNetId
      || !binding.victimNetId || binding.victimNetId !== binding.boardVictimNetId
      || binding.aggressorNetId === binding.victimNetId
      || !value.aggressorNet || !value.victimNet || value.aggressorNet === value.victimNet
      || !boardNetNames.has(value.aggressorNet) || !boardNetNames.has(value.victimNet)
      || !finiteOptional(value.nextDb) || !finiteOptional(value.fextDb)
      || !finiteOptional(value.peakNextV) || !finiteOptional(value.peakFextV)
      || [value.nextDb, value.fextDb, value.peakNextV, value.peakFextV].every(metric => metric === undefined)) return null;
  return {
    ...value,
    metrics: { nextDb: value.nextDb, fextDb: value.fextDb, peakNextV: value.peakNextV, peakFextV: value.peakFextV },
  };
}
