// SPDX-License-Identifier: Apache-2.0
import {
  DEFAULT_MAX_WEBM_BYTES,
  assertCaptureBounds,
  throwIfCancelled,
  type AnimationExportPlan,
} from "./transientPlayback";

export type AnimationExportFormat = "gif" | "webm";
export type AnimationExportRequest = { format: AnimationExportFormat; playbackSpeed: number };

export type WebMCapability = { supported: boolean; mimeType: string | null; reason: string | null };

const WEBM_TYPES = [
  "video/webm;codecs=vp9",
  "video/webm;codecs=vp8",
  "video/webm",
] as const;

export function detectWebMCapability(): WebMCapability {
  if (typeof document === "undefined" || typeof HTMLCanvasElement === "undefined") {
    return { supported: false, mimeType: null, reason: "WebM export requires a browser canvas." };
  }
  if (typeof MediaRecorder === "undefined" || typeof HTMLCanvasElement.prototype.captureStream !== "function") {
    return { supported: false, mimeType: null, reason: "This WebView does not provide MediaRecorder canvas capture." };
  }
  const mimeType = WEBM_TYPES.find(type => typeof MediaRecorder.isTypeSupported !== "function" || MediaRecorder.isTypeSupported(type)) ?? null;
  return mimeType
    ? { supported: true, mimeType, reason: null }
    : { supported: false, mimeType: null, reason: "This WebView has no supported WebM codec." };
}

const wait = (durationMs: number, signal?: AbortSignal) => new Promise<void>((resolve, reject) => {
  throwIfCancelled(signal);
  const aborted = () => {
    window.clearTimeout(timer);
    reject(new DOMException("Animation export cancelled.", "AbortError"));
  };
  const timer = window.setTimeout(() => {
    signal?.removeEventListener("abort", aborted);
    resolve();
  }, durationMs);
  signal?.addEventListener("abort", aborted, { once: true });
});

/** Capture GIF inputs one at a time. Raw-frame memory is checked before capture. */
export async function captureGifFrames(options: {
  plan: AnimationExportPlan;
  width: number;
  height: number;
  presentFrame: (frameIndex: number) => Promise<void> | void;
  captureFrame: () => Promise<ImageData>;
  signal?: AbortSignal;
  onProgress?: (captured: number, total: number) => void;
}): Promise<ImageData[]> {
  assertCaptureBounds(options.width, options.height, options.plan.frames.length);
  const captured: ImageData[] = [];
  for (const item of options.plan.frames) {
    throwIfCancelled(options.signal);
    await options.presentFrame(item.frameIndex);
    throwIfCancelled(options.signal);
    const image = await options.captureFrame();
    if (image.width !== options.width || image.height !== options.height) throw new Error("Captured animation frame dimensions changed during export.");
    captured.push(image);
    options.onProgress?.(captured.length, options.plan.frames.length);
  }
  return captured;
}

/**
 * Stream exact scheduled frame holds through MediaRecorder. Encoded chunks are
 * retained only up to maximumBytes; capture stops on cancellation or overflow.
 */
export async function captureWebM(options: {
  plan: AnimationExportPlan;
  width: number;
  height: number;
  presentFrame: (frameIndex: number) => Promise<void> | void;
  captureFrame: () => Promise<ImageData>;
  signal?: AbortSignal;
  maximumBytes?: number;
  onProgress?: (captured: number, total: number) => void;
}): Promise<Blob> {
  const capability = detectWebMCapability();
  if (!capability.supported || !capability.mimeType) throw new Error(capability.reason ?? "WebM export is unavailable.");
  assertCaptureBounds(options.width, options.height, 1);
  throwIfCancelled(options.signal);
  const canvas = document.createElement("canvas");
  canvas.width = options.width;
  canvas.height = options.height;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("2D export canvas is unavailable.");
  const stream = canvas.captureStream(30);
  const recorder = new MediaRecorder(stream, { mimeType: capability.mimeType, videoBitsPerSecond: 8_000_000 });
  const chunks: Blob[] = [];
  const maximumBytes = options.maximumBytes ?? DEFAULT_MAX_WEBM_BYTES;
  let bytes = 0;
  let captureError: unknown = null;
  let recorderStarted = false;
  const stopped = new Promise<Error | null>(resolve => {
    recorder.addEventListener("dataavailable", event => {
      if (!event.data.size) return;
      bytes += event.data.size;
      if (bytes > maximumBytes) {
        captureError = new Error(`WebM export exceeded the ${(maximumBytes / 1024 / 1024).toFixed(0)} MiB memory limit.`);
        if (recorder.state !== "inactive") recorder.stop();
        return;
      }
      chunks.push(event.data);
    });
    recorder.addEventListener("stop", () => resolve(null), { once: true });
    recorder.addEventListener("error", event => {
      captureError = (event as ErrorEvent).error ?? new Error("WebM encoder failed.");
      resolve(captureError instanceof Error ? captureError : new Error(String(captureError)));
    }, { once: true });
  });
  let rejectCancelled: (error: unknown) => void = () => {};
  const cancelled = new Promise<never>((_, reject) => { rejectCancelled = reject; });
  const cancel = () => {
    captureError = new DOMException("Animation export cancelled.", "AbortError");
    if (recorder.state !== "inactive") recorder.stop();
    rejectCancelled(captureError);
  };
  options.signal?.addEventListener("abort", cancel, { once: true });
  const captureGraceMs = 15_000;
  let rejectWatchdog: (error: unknown) => void = () => {};
  const watchdog = new Promise<never>((_, reject) => { rejectWatchdog = reject; });
  const watchdogTimer = window.setTimeout(() => {
    captureError = new Error(`WebM export exceeded its ${((options.plan.durationMs + captureGraceMs) / 1000).toFixed(1)} second capture limit.`);
    if (recorder.state !== "inactive") recorder.stop();
    rejectWatchdog(captureError);
  }, options.plan.durationMs + captureGraceMs);
  try {
    const capture = async () => {
      for (let position = 0; position < options.plan.frames.length; position += 1) {
        throwIfCancelled(options.signal);
        if (captureError) throw captureError;
        const item = options.plan.frames[position];
        await options.presentFrame(item.frameIndex);
        const image = await options.captureFrame();
        if (image.width !== canvas.width || image.height !== canvas.height) throw new Error("Captured animation frame dimensions changed during export.");
        context.putImageData(image, 0, 0);
        if (!recorderStarted) {
          recorder.start(250);
          recorderStarted = true;
        }
        (stream.getVideoTracks()[0] as MediaStreamTrack & { requestFrame?: () => void } | undefined)?.requestFrame?.();
        options.onProgress?.(position + 1, options.plan.frames.length);
        await wait(item.durationMs, options.signal);
      }
    };
    await Promise.race([capture(), cancelled, watchdog]);
  } catch (error) {
    captureError = error;
  } finally {
    window.clearTimeout(watchdogTimer);
    try {
      if (recorderStarted) {
        if (recorder.state !== "inactive") recorder.stop();
        const stopError = await new Promise<Error | null>(resolve => {
          const timer = window.setTimeout(() => resolve(new Error("WebM encoder did not stop within 5 seconds.")), 5000);
          stopped.then(error => { window.clearTimeout(timer); resolve(error); });
        });
        if (stopError) throw stopError;
      }
    } catch (error) {
      captureError ??= error;
    } finally {
      options.signal?.removeEventListener("abort", cancel);
      stream.getTracks().forEach(track => track.stop());
    }
  }
  if (captureError) throw captureError;
  return new Blob(chunks, { type: capability.mimeType });
}
