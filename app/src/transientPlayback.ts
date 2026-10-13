// SPDX-License-Identifier: Apache-2.0

export type TimedFrame = {
  frameIndex: number;
  timeS: number;
  durationMs: number;
};

export type AnimationExportPlan = {
  frames: TimedFrame[];
  playbackSpeed: number;
  durationMs: number;
  sourceFrameCount: number;
};

export type PlaybackTimeline = {
  readonly timesS: readonly number[];
  frameAtElapsed: (startFrame: number, elapsedMs: number, playbackSpeed: number) => { frameIndex: number; ended: boolean };
};

export const DEFAULT_MAX_EXPORT_FRAMES = 180;
export const DEFAULT_MAX_EXPORT_DURATION_MS = 60_000;
export const DEFAULT_MAX_RAW_CAPTURE_BYTES = 256 * 1024 * 1024;
export const DEFAULT_MAX_WEBM_BYTES = 256 * 1024 * 1024;
export const DEFAULT_MAX_EXPORT_PIXELS = 1920 * 1080;

const finitePositive = (value: number, name: string) => {
  if (!Number.isFinite(value) || value <= 0) throw new Error(`${name} must be a positive finite number.`);
  return value;
};

export function validatedFrameTimes(timesS: readonly number[]): number[] {
  if (timesS.length < 2) throw new Error("Animation requires at least two saved solver frames.");
  const times = timesS.map(Number);
  for (let index = 0; index < times.length; index += 1) {
    if (!Number.isFinite(times[index])) throw new Error(`Saved frame ${index + 1} has no finite simulated time.`);
    if (index > 0 && times[index] < times[index - 1]) {
      throw new Error(`Saved frame times must be nondecreasing (frame ${index + 1}).`);
    }
  }
  if (times[times.length - 1] <= times[0]) throw new Error("Saved frames do not span a positive simulated duration.");
  return times;
}

/** Return the last saved sample at or before simulatedTimeS. No field interpolation is performed. */
export function savedFrameIndexAtTime(timesS: readonly number[], simulatedTimeS: number): number {
  if (!timesS.length) return 0;
  if (!Number.isFinite(simulatedTimeS) || simulatedTimeS <= timesS[0]) return 0;
  let low = 0;
  let high = timesS.length;
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (timesS[middle] <= simulatedTimeS) low = middle + 1;
    else high = middle;
  }
  return Math.min(timesS.length - 1, Math.max(0, low - 1));
}

export function playbackFrameAtElapsed(
  timesS: readonly number[],
  startFrame: number,
  elapsedMs: number,
  playbackSpeed: number,
): { frameIndex: number; ended: boolean } {
  const times = validatedFrameTimes(timesS);
  return frameAtElapsed(times, startFrame, elapsedMs, playbackSpeed);
}

function frameAtElapsed(
  times: readonly number[],
  startFrame: number,
  elapsedMs: number,
  playbackSpeed: number,
): { frameIndex: number; ended: boolean } {
  const speed = finitePositive(playbackSpeed, "Playback speed");
  const boundedStart = Math.min(times.length - 1, Math.max(0, Math.trunc(startFrame)));
  const simulatedTime = times[boundedStart] + Math.max(0, elapsedMs) * speed / 1000;
  const ended = simulatedTime >= times[times.length - 1];
  return { frameIndex: ended ? times.length - 1 : savedFrameIndexAtTime(times, simulatedTime), ended };
}

/** Validate and copy timestamps once for a requestAnimationFrame playback loop. */
export function createPlaybackTimeline(timesS: readonly number[]): PlaybackTimeline {
  const times = Object.freeze(validatedFrameTimes(timesS));
  return Object.freeze({
    timesS: times,
    frameAtElapsed: (startFrame: number, elapsedMs: number, playbackSpeed: number) =>
      frameAtElapsed(times, startFrame, elapsedMs, playbackSpeed),
  });
}

function boundedFrameIndices(frameCount: number, maximumFrames: number): number[] {
  const count = Math.max(2, Math.trunc(finitePositive(maximumFrames, "Maximum export frames")));
  if (frameCount <= count) return Array.from({ length: frameCount }, (_, index) => index);
  const indices = new Set<number>([0, frameCount - 1]);
  for (let slot = 1; slot < count - 1; slot += 1) {
    indices.add(Math.round(slot * (frameCount - 1) / (count - 1)));
  }
  return [...indices].sort((left, right) => left - right);
}

/**
 * Build a bounded export schedule from exact saved-sample timestamps. When
 * frames are thinned, each retained frame remains visible until the next
 * retained solved sample. The final frame uses the preceding retained interval.
 */
export function buildAnimationExportPlan(
  timesS: readonly number[],
  playbackSpeed: number,
  options: { maximumFrames?: number; maximumDurationMs?: number; minimumFrameDurationMs?: number } = {},
): AnimationExportPlan {
  const times = validatedFrameTimes(timesS);
  const speed = finitePositive(playbackSpeed, "Playback speed");
  const maximumFrames = options.maximumFrames ?? DEFAULT_MAX_EXPORT_FRAMES;
  const maximumDurationMs = finitePositive(options.maximumDurationMs ?? DEFAULT_MAX_EXPORT_DURATION_MS, "Maximum export duration");
  const minimumFrameDurationMs = finitePositive(options.minimumFrameDurationMs ?? 10, "Minimum frame duration");
  const indices = boundedFrameIndices(times.length, maximumFrames);
  const frames = indices.map((frameIndex, position) => {
    const nextIndex = indices[position + 1];
    const intervalS = nextIndex === undefined
      ? 0
      : times[nextIndex] - times[frameIndex];
    return {
      frameIndex,
      timeS: times[frameIndex],
      durationMs: Math.max(minimumFrameDurationMs, intervalS * 1000 / speed),
    };
  });
  const durationMs = frames.reduce((total, frame) => total + frame.durationMs, 0);
  if (durationMs > maximumDurationMs) {
    throw new Error(`Export would run for ${(durationMs / 1000).toFixed(1)} s; increase playback speed or keep it within ${(maximumDurationMs / 1000).toFixed(0)} s.`);
  }
  return { frames, playbackSpeed: speed, durationMs, sourceFrameCount: times.length };
}

export function estimatedRawCaptureBytes(width: number, height: number, frameCount: number): number {
  if (![width, height, frameCount].every(value => Number.isFinite(value) && value > 0)) return Infinity;
  return Math.ceil(width) * Math.ceil(height) * 4 * Math.ceil(frameCount);
}

export function assertCaptureBounds(
  width: number,
  height: number,
  frameCount: number,
  options: { maximumPixels?: number; maximumRawBytes?: number } = {},
): void {
  const pixels = Math.ceil(width) * Math.ceil(height);
  const maximumPixels = options.maximumPixels ?? DEFAULT_MAX_EXPORT_PIXELS;
  const maximumRawBytes = options.maximumRawBytes ?? DEFAULT_MAX_RAW_CAPTURE_BYTES;
  if (!Number.isFinite(pixels) || pixels <= 0 || pixels > maximumPixels) {
    throw new Error(`Export dimensions exceed the ${maximumPixels.toLocaleString()} pixel limit.`);
  }
  const bytes = estimatedRawCaptureBytes(width, height, frameCount);
  if (bytes > maximumRawBytes) {
    throw new Error(`GIF capture requires ${(bytes / 1024 / 1024).toFixed(1)} MiB before encoding; limit is ${(maximumRawBytes / 1024 / 1024).toFixed(0)} MiB.`);
  }
}

export function gifDelayCentiseconds(plan: AnimationExportPlan): number[] {
  return plan.frames.map(frame => Math.max(1, Math.min(65535, Math.round(frame.durationMs / 10))));
}

export function throwIfCancelled(signal?: AbortSignal): void {
  if (signal?.aborted) throw new DOMException("Animation export cancelled.", "AbortError");
}
