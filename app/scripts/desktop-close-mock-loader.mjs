// SPDX-License-Identifier: Apache-2.0
import { resolve as workerResolve } from "./worker-bridge-mock-loader.mjs";

export async function resolve(specifier, context, nextResolve) {
  if (specifier === "@tauri-apps/api/window") {
    const mock = "export function getCurrentWindow() { return globalThis.__spikeCloseWindow; }";
    return { url: `data:text/javascript,${encodeURIComponent(mock)}`, shortCircuit: true };
  }
  return workerResolve(specifier, context, nextResolve);
}
