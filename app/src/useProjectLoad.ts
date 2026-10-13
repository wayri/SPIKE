// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
import { useCallback, useRef, useState } from 'react';
import { advanceProjectLoad, beginProjectLoad, finishProjectLoad, measuredLoadFraction,
  readLoadTimings, validLoadCalibration, LOAD_TIMING_STORAGE_KEY,
  type LoadTimingRecord, type ProjectLoadStage, type ProjectLoadState } from './projectLoadProgress';

export type ProjectLoadSession = {
  id: string; signal: AbortSignal; workerId: string | null; committed: boolean;
  stage: (stage: ProjectLoadStage, detail?: string) => void;
  units: (done: number, total: number, detail?: string) => void;
  identity: (digest: string) => void;
  check: () => void;
};
export function useProjectLoad(cancelWorker: (id: string) => Promise<boolean>) {
  const [state, setState] = useState<ProjectLoadState | null>(null);
  const live = useRef<ProjectLoadState | null>(null);
  const session = useRef<ProjectLoadSession | null>(null);
  const abort = useRef<AbortController | null>(null);
  const identity = useRef<string | null>(null);
  const history = useRef<LoadTimingRecord[] | null>(null);
  if (history.current === null) {
    try { history.current = readLoadTimings(localStorage.getItem(LOAD_TIMING_STORAGE_KEY), Date.now()); }
    catch { history.current = []; }
  }
  const update = useCallback((fn: (current: ProjectLoadState) => ProjectLoadState) => {
    if (!live.current) return;
    live.current = fn(live.current); setState(live.current);
  }, []);
  const start = useCallback((fileName: string): ProjectLoadSession => {
    if (live.current?.status === 'running') throw new Error('Another project is still loading. Cancel or finish it first.');
    const id = crypto.randomUUID();
    const controller = new AbortController(); abort.current = controller; identity.current = null;
    const previous = [...history.current!].reverse().find(entry => entry.fileName === fileName);
    const initial = { ...beginProjectLoad(id, fileName, performance.now()),
      previousDurationMs: previous ? Object.values(previous.durations).reduce((sum, ms) => sum + ms!, 0) : undefined };
    live.current = initial; setState(initial);
    const current: ProjectLoadSession = {
      id, signal: controller.signal, workerId: null, committed: false,
      check: () => { if (controller.signal.aborted || session.current?.id !== id) throw new DOMException('Project loading cancelled.', 'AbortError'); },
      stage: (stage, detail = '') => { current.check(); update(value => advanceProjectLoad(value, stage, performance.now(), detail)); },
      units: (done, total, detail = '') => { current.check(); update(value => measuredLoadFraction(value, done, total, detail)); },
      identity: digest => {
        current.check(); identity.current = digest;
        const calibration = history.current!.find(entry => entry.digest === digest)?.durations;
        update(value => ({ ...value, calibration }));
      },
    };
    session.current = current;
    return current;
  }, [update]);
  const fail = useCallback((load: ProjectLoadSession, error: unknown) => {
    if (session.current?.id !== load.id) return;
    update(value => finishProjectLoad(value, load.signal.aborted ? 'cancelled' : 'failed', performance.now(),
      error instanceof Error ? error.message : String(error)));
  }, [update]);
  const ready = useCallback((token: string) => {
    if (session.current?.id !== token || session.current.signal.aborted || live.current?.stage !== 'scene') return;
    update(value => finishProjectLoad(value, 'ready', performance.now()));
    if (identity.current && live.current?.status === 'ready') {
      if (validLoadCalibration(live.current.durations)) {
        history.current = [...history.current!.filter(entry => entry.digest !== identity.current), {
          digest: identity.current, fileName: live.current.fileName, savedAt: Date.now(), durations: live.current.durations,
        }].slice(-8);
        try { localStorage.setItem(LOAD_TIMING_STORAGE_KEY, JSON.stringify(history.current)); }
        catch { /* Timing hints remain available in memory when storage is disabled. */ }
      }
    }
  }, [update]);
  const cancel = useCallback(async () => {
    const load = session.current;
    if (!load || live.current?.status !== 'running') return;
    abort.current?.abort();
    update(value => finishProjectLoad(value, 'cancelled', performance.now(), load.committed
      ? 'Project state retained; remaining visual preparation cancelled.' : 'Project loading cancelled before workspace replacement.'));
    if (load.workerId) await cancelWorker(load.workerId);
  }, [cancelWorker, update]);
  const dismiss = useCallback(() => { if (live.current?.status !== 'running') { live.current = null; setState(null); } }, []);
  return { state, session, start, fail, ready, cancel, dismiss };
}
