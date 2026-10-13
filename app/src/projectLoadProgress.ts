// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
/** Completed work only; time never advances the progress bar. */
export const PROJECT_LOAD_STAGES = [
  ['package', 'Start worker, read and verify package'],
  ['trust', 'Validate project identity and signatures'],
  ['results', 'Restore saved simulation results'],
  ['design', 'Parse board definitions'],
  ['visuals', 'Restore saved board visuals'],
  ['workspace', 'Apply workspace and study state'],
  ['scene', 'Build scenes and load component models'],
] as const;
export type ProjectLoadStage = typeof PROJECT_LOAD_STAGES[number][0];
export type ProjectLoadStatus = 'running' | 'ready' | 'failed' | 'cancelled';
export type LoadCalibration = Partial<Record<ProjectLoadStage, number>>;
export type ProjectLoadState = {
  id: string; fileName: string; startedAt: number; stageStartedAt: number;
  stage: ProjectLoadStage; status: ProjectLoadStatus; fraction: number;
  detail: string; error?: string; finishedAt?: number; durations: LoadCalibration;
  calibration?: LoadCalibration; previousDurationMs?: number;
};
export function beginProjectLoad(id: string, fileName: string, now: number): ProjectLoadState {
  return { id, fileName, startedAt: now, stageStartedAt: now, stage: 'package',
    status: 'running', fraction: 0, detail: '', durations: {} };
}
export function advanceProjectLoad(state: ProjectLoadState, stage: ProjectLoadStage, now: number, detail = ''): ProjectLoadState {
  if (state.status !== 'running') return state;
  const current = PROJECT_LOAD_STAGES.findIndex(([key]) => key === state.stage);
  const next = PROJECT_LOAD_STAGES.findIndex(([key]) => key === stage);
  if (next < current) throw new Error('Project loading stage cannot move backwards.');
  if (stage === state.stage) return { ...state, detail };
  return { ...state, stage, stageStartedAt: now, fraction: 0, detail,
    durations: { ...state.durations, [state.stage]: Math.max(0, now - state.stageStartedAt) } };
}
export function measuredLoadFraction(state: ProjectLoadState, done: number, total: number, detail = ''): ProjectLoadState {
  if (state.status !== 'running' || !Number.isFinite(done) || !Number.isFinite(total) || total <= 0 || done < 0 || done > total) return state;
  return { ...state, fraction: Math.max(state.fraction, done / total), detail };
}
export function finishProjectLoad(state: ProjectLoadState, status: Exclude<ProjectLoadStatus, 'running'>, now: number, error?: string): ProjectLoadState {
  if (state.status !== 'running') return state;
  if (status === 'ready' && state.stage !== 'scene') throw new Error('Project cannot finish before the scene is usable.');
  return { ...state, status, finishedAt: now, error,
    durations: { ...state.durations, [state.stage]: Math.max(0, now - state.stageStartedAt) } };
}
export function validLoadCalibration(value: unknown): value is LoadCalibration {
  if (!value || typeof value !== 'object') return false;
  const durations = value as LoadCalibration;
  return PROJECT_LOAD_STAGES.every(([key]) => Number.isFinite(durations[key]) && durations[key]! >= 0 && durations[key]! <= 86400_000)
    && PROJECT_LOAD_STAGES.some(([key]) => durations[key]! > 0);
}
export type LoadTimingRecord = { digest: string; fileName: string; savedAt: number; durations: LoadCalibration };
export const LOAD_TIMING_STORAGE_KEY = 'spike.project-load-timings.v1';
/** Optional local timing hints; malformed, old and incomplete entries are ignored. */
export function readLoadTimings(raw: string | null, now: number): LoadTimingRecord[] {
  if (!raw || raw.length > 32_768) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((entry): entry is LoadTimingRecord => Boolean(entry)
      && typeof entry.digest === 'string' && /^[0-9a-f]{64}$/.test(entry.digest)
      && typeof entry.fileName === 'string' && entry.fileName.length <= 1024
      && Number.isFinite(entry.savedAt) && entry.savedAt <= now && now - entry.savedAt <= 30 * 86400_000
      && validLoadCalibration(entry.durations)).slice(-8).map(entry => ({
        digest: entry.digest, fileName: entry.fileName, savedAt: entry.savedAt,
        durations: Object.fromEntries(PROJECT_LOAD_STAGES.map(([key]) => [key, entry.durations[key]])),
      }));
  } catch { return []; }
}
export function projectLoadView(state: ProjectLoadState, now: number) {
  const index = PROJECT_LOAD_STAGES.findIndex(([key]) => key === state.stage);
  const calibrated = validLoadCalibration(state.calibration);
  const weights = PROJECT_LOAD_STAGES.map(([key]) => calibrated ? state.calibration![key]! : 1);
  const completed = weights.slice(0, index).reduce((a, b) => a + b, 0) + weights[index] * state.fraction;
  const percent = state.status === 'ready' ? 100 : Math.min(99, Math.floor(100 * completed / weights.reduce((a, b) => a + b, 0)));
  const elapsedMs = Math.max(0, (state.finishedAt ?? now) - state.startedAt);
  const currentElapsed = Math.max(0, (state.finishedAt ?? now) - state.stageStartedAt);
  const laterMs = weights.slice(index + 1).reduce((a, b) => a + b, 0);
  // Work counters estimate only this stage. Different later stages cannot be
  // extrapolated from artifact bytes; exact-manifest history supplies those.
  const measuredEta = state.fraction > 0 && state.fraction < 1 && currentElapsed >= 1000
    ? currentElapsed * (1 - state.fraction) / state.fraction : null;
  let etaMs: number | null = null;
  let etaScope: 'project' | 'stage' = 'project';
  let etaNote = state.stage === 'package'
    ? 'Worker startup and package verification do not report work counters. Timing begins with this open.'
    : 'An estimate appears after measured work or a completed open of this exact project.';
  if (state.status === 'ready') etaMs = 0;
  else if (state.status === 'running') {
    if (measuredEta !== null) {
      etaMs = measuredEta + (calibrated ? laterMs : 0);
      etaScope = calibrated ? 'project' : 'stage';
      etaNote = calibrated ? 'Based on measured work and the previous open of this exact project.'
        : 'Based on work completed in this stage; later stages are still being measured.';
    } else if (calibrated && currentElapsed < weights[index]) {
      etaMs = weights[index] - currentElapsed + laterMs;
      etaNote = 'Based on the previous completed open of this exact project; timings can vary.';
    } else if (calibrated) {
      etaNote = 'This stage is taking longer than the previous open. The estimate will resume when work advances.';
    } else if (state.fraction === 1) {
      etaNote = 'Reported work is complete; waiting for this stage to finish.';
    }
  } else etaNote = state.status === 'cancelled' ? 'Loading was cancelled.' : 'Loading stopped after an error.';
  return { percent, elapsedMs, etaMs, etaScope, etaNote, stageLabel: PROJECT_LOAD_STAGES[index][1],
    basis: calibrated ? 'Previous measured stage weights' : 'Completed loading stages' };
}
/** Coarse estimates avoid suggesting that a throughput forecast is a countdown. */
export function loadEstimate(ms: number): string {
  if (ms < 5000) return 'less than 5 s';
  if (ms < 60_000) return `about ${Math.ceil(ms / 5000) * 5} s`;
  return `about ${Math.round(ms / 60_000)} min`;
}
export function loadDuration(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}
