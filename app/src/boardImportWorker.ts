/// <reference lib="webworker" />

import { parseDesignSource } from "./designSourceRegistry";

self.onmessage = (event: MessageEvent<{ sourceFile: string; source: string; formatHint?: string }>) => {
  try {
    self.postMessage({ ok: true, board: parseDesignSource(event.data.sourceFile, event.data.source, event.data.formatHint) });
  } catch (error) {
    self.postMessage({ ok: false, error: error instanceof Error ? error.message : String(error) });
  }
};

export {};
