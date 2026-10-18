// SPDX-License-Identifier: Apache-2.0

export const SEARCH_PREFERENCES_KEY = "spike.universal-search.preferences.v1";
const MAX_PINS = 24;
const MAX_USAGE = 120;
const MAX_COUNT = 10_000;

export type SearchActionUsage = { count: number; lastUsed: number };
export type SearchPreferences = { version: 1; pins: string[]; usage: Record<string, SearchActionUsage> };
type StorageLike = Pick<Storage, "getItem" | "setItem">;

export const emptySearchPreferences = (): SearchPreferences => ({ version: 1, pins: [], usage: {} });

const validId = (value: unknown): value is string => typeof value === "string" && value.length > 0 && value.length <= 256;

export function parseSearchPreferences(raw: string | null): SearchPreferences {
  if (!raw) return emptySearchPreferences();
  try {
    const value = JSON.parse(raw) as { version?: unknown; pins?: unknown; usage?: unknown };
    if (value.version !== 1 || !Array.isArray(value.pins) || !value.usage || typeof value.usage !== "object" || Array.isArray(value.usage)) return emptySearchPreferences();
    const pins = [...new Set(value.pins.filter(validId))].slice(0, MAX_PINS);
    const rows = Object.entries(value.usage).flatMap(([id, row]) => {
      if (!validId(id) || !row || typeof row !== "object" || Array.isArray(row)) return [];
      const { count, lastUsed } = row as { count?: unknown; lastUsed?: unknown };
      if (!Number.isInteger(count) || (count as number) < 1 || !Number.isFinite(lastUsed) || (lastUsed as number) < 0) return [];
      return [[id, { count: Math.min(count as number, MAX_COUNT), lastUsed: lastUsed as number }] as const];
    }).sort((a, b) => b[1].lastUsed - a[1].lastUsed).slice(0, MAX_USAGE);
    return { version: 1, pins, usage: Object.fromEntries(rows) };
  } catch { return emptySearchPreferences(); }
}

export function loadSearchPreferences(storage?: StorageLike | null): SearchPreferences {
  try { return parseSearchPreferences(storage?.getItem(SEARCH_PREFERENCES_KEY) ?? null); }
  catch { return emptySearchPreferences(); }
}

function saveSearchPreferences(value: SearchPreferences, storage?: StorageLike | null) {
  try { storage?.setItem(SEARCH_PREFERENCES_KEY, JSON.stringify(value)); } catch { /* Search stays usable when local storage is unavailable. */ }
  return value;
}

export function recordSearchAction(current: SearchPreferences, id: string, now = Date.now(), storage?: StorageLike | null) {
  if (!validId(id)) return current;
  const usage = { ...current.usage, [id]: { count: Math.min((current.usage[id]?.count ?? 0) + 1, MAX_COUNT), lastUsed: Math.max(0, now) } };
  const retained = Object.entries(usage).sort((a, b) => b[1].lastUsed - a[1].lastUsed).slice(0, MAX_USAGE);
  return saveSearchPreferences({ ...current, usage: Object.fromEntries(retained) }, storage);
}

export function toggleSearchPin(current: SearchPreferences, id: string, storage?: StorageLike | null) {
  if (!validId(id)) return current;
  const pins = current.pins.includes(id) ? current.pins.filter(value => value !== id) : [id, ...current.pins].slice(0, MAX_PINS);
  return saveSearchPreferences({ ...current, pins }, storage);
}

export function searchPreferenceRank(preferences: SearchPreferences, id: string, now = Date.now()) {
  const usage = preferences.usage[id];
  const ageDays = usage ? Math.max(0, now - usage.lastUsed) / 86_400_000 : Infinity;
  const recency = Number.isFinite(ageDays) ? Math.max(0, 18 - Math.log2(ageDays + 1) * 4) : 0;
  const frequency = usage ? Math.min(24, Math.log2(usage.count + 1) * 6) : 0;
  return (preferences.pins.includes(id) ? 36 : 0) + recency + frequency;
}

export function recentSearchActionIds(preferences: SearchPreferences, limit = 5) {
  return Object.entries(preferences.usage).sort((a, b) => b[1].lastUsed - a[1].lastUsed).slice(0, limit).map(([id]) => id);
}

export function frequentSearchActionIds(preferences: SearchPreferences, limit = 5) {
  return Object.entries(preferences.usage).sort((a, b) => b[1].count - a[1].count || b[1].lastUsed - a[1].lastUsed).slice(0, limit).map(([id]) => id);
}
