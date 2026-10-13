// SPDX-License-Identifier: Apache-2.0

export type PiQuickTuneTerminal = {
  id: string;
  net: string;
  anchorId: string;
  anchorType?: string;
  x: string;
  y: string;
  value: string;
};

export type PiQuickTuneSetup<T extends PiQuickTuneTerminal = PiQuickTuneTerminal> = {
  net: string;
  loads: T[];
};

export type PiQuickTuneAdjustment<T> = {
  setup: T;
  terminalId: string;
  previousCurrentA: number;
  currentA: number;
  stepA: number;
};

/**
 * Adjust the one existing anchored current sink for a tested net and occurrence.
 * Wheel-up increases current and wheel-down decreases it. No terminal or limit is
 * inferred; ambiguous and stale occurrence bindings fail closed.
 */
export function adjustPiLoadFromWheel<
  TTerminal extends PiQuickTuneTerminal,
  TSetup extends PiQuickTuneSetup<TTerminal>,
>(setup: TSetup, input: {
  net: string;
  occurrenceId?: string;
  terminalId?: string;
  deltaY: number;
  altKey: boolean;
}, setupOccurrenceId?: string): PiQuickTuneAdjustment<TSetup> {
  const net = input.net.trim();
  const testedOccurrence = input.occurrenceId?.trim() ?? "";
  const setupOccurrence = setupOccurrenceId?.trim() ?? "";
  if (!net) throw new Error("Quick tune requires an explicit tested net.");
  if (testedOccurrence !== setupOccurrence) {
    throw new Error("Quick tune occurrence does not match the retained PI setup.");
  }
  if (setup.net.trim() !== net) throw new Error("Quick tune net does not match the retained PI setup.");
  if (!Number.isFinite(input.deltaY) || input.deltaY === 0) throw new Error("Quick tune requires a finite wheel direction.");

  const ids = setup.loads.map(load => load.id.trim());
  if (ids.some(id => !id) || new Set(ids).size !== ids.length) throw new Error("PI sink IDs must be nonblank and unique before viewport tuning.");
  const candidates = setup.loads.filter(load => {
    const loadNet = load.net.trim() || setup.net.trim();
    const positioned = load.x.trim().length > 0 && load.y.trim().length > 0
      && Number.isFinite(Number(load.x)) && Number.isFinite(Number(load.y));
    const anchored = load.anchorType === "coordinate" ? positioned : load.anchorId.trim().length > 0 && positioned;
    return loadNet === net && anchored;
  });
  const selectedCandidates = input.terminalId === undefined
    ? candidates
    : candidates.filter(load => load.id === input.terminalId);
  if (selectedCandidates.length !== 1) {
    throw new Error(selectedCandidates.length ? "Quick tune is ambiguous because multiple anchored loads match the tested net." : "Quick tune requires one existing anchored load on the tested net.");
  }
  if (input.terminalId === undefined && candidates.length !== 1) throw new Error("Quick tune is ambiguous because multiple anchored loads match the tested net.");
  const selected = selectedCandidates[0];
  const previous = Number(selected.value);
  if (!Number.isFinite(previous) || previous < 0) throw new Error("Quick tune requires an existing finite nonnegative load current.");
  const step = input.altKey ? 0.01 : 0.1;
  const direction = input.deltaY < 0 ? 1 : -1;
  const current = Math.max(0, Math.round((previous + direction * step) * 1e12) / 1e12);
  const loads = setup.loads.map(load => load.id === selected.id ? { ...load, value: String(current) } : load) as TTerminal[];
  return {
    setup: { ...setup, loads } as TSetup,
    terminalId: selected.id,
    previousCurrentA: previous,
    currentA: current,
    stepA: step,
  };
}

type TimerHandle = ReturnType<typeof setTimeout>;

export function createPiQuickTuneScheduler<T>(options: {
  run: (latest: T) => Promise<void>;
  onError?: (error: unknown) => void;
  delayMs?: number;
  setTimer?: (callback: () => void, delayMs: number) => TimerHandle;
  clearTimer?: (handle: TimerHandle) => void;
}) {
  const delay = options.delayMs ?? 500;
  if (!Number.isFinite(delay) || delay < 0) throw new Error("Quick tune debounce delay must be finite and nonnegative.");
  const setTimer = options.setTimer ?? ((callback, timeout) => setTimeout(callback, timeout));
  const clearTimer = options.clearTimer ?? (handle => clearTimeout(handle));
  let timer: TimerHandle | undefined;
  let latest: T | undefined;
  let queued = false;
  let busy = false;
  let disposed = false;
  let generation = 0;

  const launch = async (value: T, launchGeneration: number) => {
    if (disposed || launchGeneration !== generation) return;
    busy = true;
    try { await options.run(value); }
    catch (error) { if (!disposed && launchGeneration === generation) options.onError?.(error); }
    finally {
      busy = false;
      if (!disposed && queued && latest !== undefined) {
        queued = false;
        const next = latest;
        latest = undefined;
        void launch(next, generation);
      }
    }
  };

  const fire = () => {
    timer = undefined;
    if (disposed || latest === undefined) return;
    if (busy) { queued = true; return; }
    const value = latest;
    latest = undefined;
    void launch(value, generation);
  };

  const invalidate = () => {
    generation += 1;
    if (timer !== undefined) clearTimer(timer);
    timer = undefined;
    latest = undefined;
    queued = false;
  };

  return {
    schedule(value: T) {
      if (disposed) return false;
      latest = value;
      queued = false;
      if (timer !== undefined) clearTimer(timer);
      timer = setTimer(fire, delay);
      return true;
    },
    invalidate,
    dispose() { if (!disposed) { invalidate(); disposed = true; } },
    isBusy: () => busy,
  };
}
