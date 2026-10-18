// SPDX-License-Identifier: Apache-2.0
/** Form guidance only: the worker validates the channel and every assignment. */
type RecordData = Record<string, unknown>;
const record = (value: unknown): RecordData => value && typeof value === "object" && !Array.isArray(value) ? value as RecordData : {};
const rows = (value: unknown): RecordData[] => Array.isArray(value) ? value.map(record) : [];

export function siChannelPortCount(value: unknown): number | null {
  const channel = record(value);
  if (channel.kind === "rlgc") return channel.coupled ? 4 : 2;
  if (channel.kind === "geometry") return record(channel.request).victim_net ? 4 : 2;
  // The filename is a provisional UI hint, never network-data validation.
  if (channel.kind === "touchstone") return Number(String(channel.name).match(/\.s(\d+)p$/i)?.[1]) || null;
  return null;
}

export function changeSiChannel(setup: RecordData, channel: RecordData): { setup: RecordData; notice: string } {
  const previous = record(setup.channel), before = siChannelPortCount(previous), after = siChannelPortCount(channel);
  const next: RecordData = { ...setup, channel };
  const sources = rows(setup.sources), receivers = rows(setup.receivers);
  const simpleThrough = (before === 2 || before === 4) && sources.length === 1 && sources[0].port === 0
    && receivers.length === 1 && receivers[0].port === (before === 4 ? 2 : 1)
    && rows(setup.passives).length === 0 && rows(setup.edits).length === 0;
  const knownFarPort = after === 2 ? 1 : after === 4 && ["rlgc", "geometry"].includes(String(channel.kind)) ? 2 : null;
  if (before !== after && simpleThrough && knownFarPort !== null) {
    next.receivers = [{ ...receivers[0], port: knownFarPort }];
    return { setup: next, notice: `Channel now has ${after} ports. Source stays on port 1; receiver moved from port ${Number(receivers[0].port) + 1} to port ${knownFarPort + 1}. Endpoint model values were preserved. Review Sources / receivers against the channel's physical port order.` };
  }
  const changed = before !== after || previous.kind !== channel.kind || previous.name !== channel.name;
  return { setup: next, notice: changed
    ? "Channel changed. Existing endpoint, passive and network-edit assignments were preserved. Review their physical port order; correct any listed assignments before running."
    : "" };
}

export function siWorkflowPortIssues(setup: RecordData): string[] {
  const count = siChannelPortCount(setup.channel), issues: string[] = [], assigned = new Set<number>();
  const check = (port: unknown, label: string) => {
    if (typeof port !== "number" || !Number.isInteger(port) || port < 0 || (count !== null && port >= count)) {
      issues.push(`${label}: choose a whole-number port ${count === null ? "of at least 1" : `from 1 to ${count}`}.`);
      return false;
    }
    return true;
  };
  for (const key of ["sources", "receivers"] as const) {
    const endpoints = rows(setup[key]);
    if (!endpoints.length) issues.push(`Sources / receivers: add at least one ${key === "sources" ? "source" : "receiver"}.`);
    endpoints.forEach((endpoint, index) => {
      const label = `${key === "sources" ? "Source" : "Receiver"} ${index + 1}`;
      if (check(endpoint.port, label)) {
        const port = endpoint.port as number;
        if (assigned.has(port)) issues.push(`${label}: port ${port + 1} already has an endpoint. Assign each source and receiver to a separate port.`);
        assigned.add(port);
      }
    });
  }
  rows(setup.passives).forEach((passive, index) => check(passive.port, `Passive ${index + 1} (Passives)`));
  rows(setup.edits).forEach((edit, index) => {
    if (count !== null && edit.kind === "reorder") {
      const ports = edit.ports;
      if (!Array.isArray(ports) || ports.length !== count || new Set(ports).size !== count
        || ports.some(port => !Number.isInteger(port) || port < 0 || port >= count)) {
        issues.push(`Network edit ${index + 1}: update the reorder operation to include each of the ${count} channel ports once.`);
      }
    }
  });
  return issues;
}
