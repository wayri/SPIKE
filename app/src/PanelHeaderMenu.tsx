// SPDX-License-Identifier: Apache-2.0
import { createContext, useContext, useState, type KeyboardEvent, type MouseEvent } from "react";
import ActionContextMenu, { type ContextAction } from "./ActionContextMenu";

export const PanelHeaderActionsContext = createContext<ContextAction[]>([]);

/** Shared pointer and keyboard access to the actions actually owned by a panel. */
export function usePanelHeaderMenu(title: string, actions: ContextAction[]) {
  const inherited = useContext(PanelHeaderActionsContext);
  const labels = new Set(inherited.map(action => action.label.trim().toLowerCase()));
  const available = [...inherited, ...actions.filter(action => !labels.has(action.label.trim().toLowerCase()))];
  const [point, setPoint] = useState<{ x: number; y: number } | null>(null);
  return {
    headerProps: {
      tabIndex: 0,
      onContextMenu: (event: MouseEvent<HTMLElement>) => {
        event.preventDefault(); event.stopPropagation();
        setPoint({ x: event.clientX, y: event.clientY });
      },
      onKeyDown: (event: KeyboardEvent<HTMLElement>) => {
        if (event.key !== "ContextMenu" && !(event.shiftKey && event.key === "F10")) return;
        event.preventDefault(); event.stopPropagation();
        const bounds = event.currentTarget.getBoundingClientRect();
        setPoint({ x: bounds.left + 12, y: bounds.bottom });
      },
    },
    menu: point && <ActionContextMenu title={title} actions={available} x={point.x} y={point.y} onClose={() => setPoint(null)} />,
  };
}
