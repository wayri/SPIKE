const mock = `export async function invoke(command, args) {
  return globalThis.__spikeWorkerInvoke(command, args);
}`;

const eventMock = `export async function listen(event, listener) {
  return globalThis.__spikeWorkerListen(event, listener);
}`;

export async function resolve(specifier, context, nextResolve) {
  if (specifier === "@tauri-apps/api/core") {
    return { url: `data:text/javascript,${encodeURIComponent(mock)}`, shortCircuit: true };
  }
  if (specifier === "@tauri-apps/api/event") {
    return { url: `data:text/javascript,${encodeURIComponent(eventMock)}`, shortCircuit: true };
  }
  if (specifier.startsWith(".") && !specifier.match(/\.[cm]?[jt]sx?$/) && context.parentURL?.endsWith(".ts")) {
    return nextResolve(`${specifier}.ts`, context);
  }
  return nextResolve(specifier, context);
}
