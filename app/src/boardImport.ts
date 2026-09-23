import type { ParsedBoard } from "./boardParser";
import { parseDesignSource } from "./designSourceRegistry";

export async function parseDesignSourceOffThread(sourceFile: string, source: string, formatHint = ""): Promise<ParsedBoard> {
  if (typeof Worker === "undefined") return parseDesignSource(sourceFile, source, formatHint);
  const worker = new Worker(new URL("./boardImportWorker.ts", import.meta.url), { type: "module" });
  try {
    return await new Promise<ParsedBoard>((resolve, reject) => {
      const timeout = window.setTimeout(() => reject(new Error("Board parsing exceeded 120 seconds.")), 120_000);
      worker.onmessage = event => {
        window.clearTimeout(timeout);
        if (event.data?.ok && event.data.board) resolve(event.data.board as ParsedBoard);
        else reject(new Error(String(event.data?.error || "Board parsing failed.")));
      };
      worker.onerror = event => {
        window.clearTimeout(timeout);
        reject(new Error(event.message || "Board parsing worker failed."));
      };
      worker.postMessage({ sourceFile, source, formatHint });
    });
  } finally {
    worker.terminate();
  }
}
