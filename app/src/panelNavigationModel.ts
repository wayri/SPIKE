// SPDX-License-Identifier: Apache-2.0

export type PanelNavigationLocation = string | null;
export type PanelNavigationPanel = { id: string; aliases?: readonly string[]; open: boolean };
export type PanelNavigationHistory = { entries: readonly PanelNavigationLocation[]; index: number };

export const PANEL_NAVIGATION_HISTORY_LIMIT = 50;

export function canonicalPanelLocation(
  panels: readonly PanelNavigationPanel[],
  location: PanelNavigationLocation,
): PanelNavigationLocation {
  if (location === null) return null;
  return panels.find(panel => panel.id === location || panel.aliases?.includes(location))?.id ?? location;
}

export function isPanelLocationAvailable(
  panels: readonly PanelNavigationPanel[],
  location: PanelNavigationLocation,
): boolean {
  if (location === null) return true;
  const canonical = canonicalPanelLocation(panels, location);
  return panels.some(panel => panel.open && panel.id === canonical);
}

export function createPanelNavigationHistory(
  panels: readonly PanelNavigationPanel[],
  activeId: PanelNavigationLocation,
): PanelNavigationHistory {
  return { entries: [canonicalPanelLocation(panels, activeId)], index: 0 };
}

export function recordPanelNavigation(
  history: PanelNavigationHistory,
  panels: readonly PanelNavigationPanel[],
  activeId: PanelNavigationLocation,
  limit = PANEL_NAVIGATION_HISTORY_LIMIT,
): PanelNavigationHistory {
  const location = canonicalPanelLocation(panels, activeId);
  if (history.entries[history.index] === location) return history;
  const branched = [...history.entries.slice(0, history.index + 1), location];
  const boundedLimit = Math.max(1, Math.floor(limit));
  const entries = branched.slice(-boundedLimit);
  return { entries, index: entries.length - 1 };
}

export function findPanelNavigationTarget(
  history: PanelNavigationHistory,
  panels: readonly PanelNavigationPanel[],
  direction: -1 | 1,
): { history: PanelNavigationHistory; target: PanelNavigationLocation } | null {
  for (let index = history.index + direction; index >= 0 && index < history.entries.length; index += direction) {
    const target = canonicalPanelLocation(panels, history.entries[index]);
    if (!isPanelLocationAvailable(panels, target) || target === canonicalPanelLocation(panels, history.entries[history.index])) continue;
    return { history: { entries: history.entries, index }, target };
  }
  return null;
}
