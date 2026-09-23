export type SceneRetryOptions = {
  attempts?: number;
  delayMs?: number;
  wait?: (delayMs: number) => Promise<void>;
};

/** Bound decode/preparation concurrency and stop dispatching stale scene work.
 * Preserve source order and isolate failures, just like Promise.allSettled.
 */
export async function loadScenesBounded<T, R>(items: readonly T[], operation: (item: T, index: number) => Promise<R>,
  options: { concurrency?: number; cancelled?: () => boolean } = {}): Promise<PromiseSettledResult<R>[]> {
  const concurrency = Math.max(1, Math.min(8, Math.floor(options.concurrency ?? 3) || 1));
  const results: PromiseSettledResult<R>[] = new Array(items.length);
  let cursor = 0;
  let cancellationError: Error | undefined;
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, async () => {
    let sliceStarted = performance.now();
    while (cursor < items.length) {
      const index = cursor++;
      if (options.cancelled?.()) {
        results[index] = { status: "rejected", reason: cancellationError ??= new Error("Scene load cancelled.") };
        continue;
      }
      try { results[index] = { status: "fulfilled", value: await operation(items[index], index) }; }
      catch (reason) { results[index] = { status: "rejected", reason }; }
      // Yield by elapsed work, not per part: timer clamping must not add many
      // seconds to thousands of inexpensive cache hits.
      if (cursor < items.length && performance.now() - sliceStarted >= 8) {
        await new Promise<void>(resolve => setTimeout(resolve, 0));
        sliceStarted = performance.now();
      }
    }
  }));
  return results;
}

/** Worker scene blobs are verified self-contained GLBs and have no extension.
 * Only explicitly named legacy VRML assets should enter the VRML parser.
 */
export function boardSceneFormat(url: string): "gltf" | "vrml" {
  const path = url.split(/[?#]/, 1)[0].toLowerCase();
  return /\.(?:wrl|vrml)$/.test(path) || /^data:model\/vrml[;,]/i.test(url) ? "vrml" : "gltf";
}

export const sceneLoadErrorMessage = (error: unknown) => {
  if (error instanceof Error && error.message) return error.message;
  if (error && typeof error === "object") {
    const target = (error as { target?: { status?: number; responseURL?: string } }).target;
    if (target?.status || target?.responseURL) {
      return `HTTP ${target.status ?? 0}${target.responseURL ? ` for ${target.responseURL}` : ""}`;
    }
  }
  return String(error);
};

export const retryableSceneLoadError = (error: unknown) => {
  const status = Number((error as { status?: number; target?: { status?: number } } | null)?.status
    ?? (error as { target?: { status?: number } } | null)?.target?.status);
  if (Number.isFinite(status)) return status === 0 || status >= 500;
  const message = sceneLoadErrorMessage(error);
  if (/\bHTTP\s+4\d\d\b/i.test(message)) return false;
  return true;
};

export async function loadSceneWithRetry<T>(
  operation: (attempt: number) => Promise<T>,
  options: SceneRetryOptions = {},
) {
  const attempts = Math.max(1, Math.min(Math.trunc(options.attempts ?? 3), 5));
  const delayMs = Math.max(0, Math.min(options.delayMs ?? 350, 5000));
  const wait = options.wait ?? ((duration: number) => new Promise<void>(resolve => window.setTimeout(resolve, duration)));
  let lastError: unknown;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await operation(attempt);
    } catch (error) {
      lastError = error;
      if (attempt >= attempts || !retryableSceneLoadError(error)) throw error;
      await wait(delayMs * attempt);
    }
  }
  throw lastError;
}
