// SPDX-License-Identifier: Apache-2.0

/**
 * Retain immutable project domains by reference in undo snapshots. Callers must
 * replace a domain when editing it; mutating a retained domain would corrupt
 * earlier history entries.
 */
export function sharedHistoryDomains<T extends Record<string, unknown>>(domains: T): T {
  return domains;
}

/** Keep the newest 50 pre-change snapshots without copying their domains. */
export function appendHistorySnapshot<T>(history: readonly T[], snapshot: T): T[] {
  return [...history.slice(-49), snapshot];
}
