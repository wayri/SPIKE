// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, ArrowUp, Home } from "./icons";
import type { FocusToolPanel } from "./FocusToolDeck";
import {
  canonicalPanelLocation,
  isPanelLocationAvailable,
  createPanelNavigationHistory,
  findPanelNavigationTarget,
  recordPanelNavigation,
  type PanelNavigationHistory,
} from "./panelNavigationModel";
import "./PanelNavigation.css";

export type PanelNavigationProps = {
  panels: readonly FocusToolPanel[];
  activeId: string | null;
  onActivate: (id: string | null) => void;
  controller?: PanelNavigationController;
  noBreadcrumb?: boolean;
};

export type PanelNavigationController = {
  canGoBack: boolean;
  canGoForward: boolean;
  goBack: () => void;
  goForward: () => void;
  goUp: () => void;
  goHome: () => void;
};

export function usePanelNavigation(
  panels: readonly FocusToolPanel[],
  activeId: string | null,
  onActivate: (id: string | null) => void,
): PanelNavigationController {
  const historyRef = useRef<PanelNavigationHistory>(createPanelNavigationHistory(panels, activeId));
  const [history, setHistory] = useState(historyRef.current);
  const panelsRef = useRef(panels);
  const activateRef = useRef(onActivate);
  panelsRef.current = panels;
  activateRef.current = onActivate;
  const canonicalActive = isPanelLocationAvailable(panels, activeId) ? canonicalPanelLocation(panels, activeId) : null;
  const panelSignature = panels.map(panel => `${panel.id}:${panel.open ? 1 : 0}:${panel.aliases?.join(",") ?? ""}`).join("|");

  useEffect(() => {
    const next = recordPanelNavigation(historyRef.current, panelsRef.current, canonicalActive);
    if (next !== historyRef.current) {
      historyRef.current = next;
      setHistory(next);
    }
  }, [canonicalActive, panelSignature]);

  const navigate = useCallback((direction: -1 | 1) => {
    const result = findPanelNavigationTarget(historyRef.current, panelsRef.current, direction);
    if (!result) return;
    historyRef.current = result.history;
    setHistory(result.history);
    activateRef.current(result.target);
  }, []);
  const board = useCallback(() => activateRef.current(null), []);
  return {
    canGoBack: Boolean(findPanelNavigationTarget(history, panels, -1)),
    canGoForward: Boolean(findPanelNavigationTarget(history, panels, 1)),
    goBack: useCallback(() => navigate(-1), [navigate]),
    goForward: useCallback(() => navigate(1), [navigate]),
    goUp: board,
    goHome: board,
  };
}

export default function PanelNavigation({ panels, activeId, onActivate, controller, noBreadcrumb = false }: PanelNavigationProps) {
  if (!controller) return <StandalonePanelNavigation panels={panels} activeId={activeId} onActivate={onActivate} noBreadcrumb={noBreadcrumb}/>;
  const navigation = controller;
  const canonicalActive = isPanelLocationAvailable(panels, activeId) ? canonicalPanelLocation(panels, activeId) : null;
  const activePanel = panels.find(panel => panel.open && panel.id === canonicalActive);

  return <nav className="panel-navigation" aria-label="Panel navigation">
    <span className="panel-navigation-controls">
      <button type="button" className="spike-control--icon" disabled={!navigation.canGoBack} onClick={navigation.goBack} aria-label="Go back to previous panel" title="Back"><ArrowLeft size={14}/></button>
      <button type="button" className="spike-control--icon" disabled={!navigation.canGoForward} onClick={navigation.goForward} aria-label="Go forward to next panel" title="Forward"><ArrowRight size={14}/></button>
      <button type="button" className="spike-control--icon" disabled={canonicalActive === null} onClick={navigation.goUp} aria-label="Go up to board and results" title="Up to board and results"><ArrowUp size={14}/></button>
      <button type="button" className="spike-control--icon" disabled={canonicalActive === null} onClick={navigation.goHome} aria-label="Go home to board and results" title="Home"><Home size={14}/></button>
    </span>
    {!noBreadcrumb && <span className="panel-navigation-breadcrumb" aria-label={activePanel ? `Board and results, ${activePanel.title}` : "Board and results"}>
      <span>Board &amp; results</span>{activePanel && <><span aria-hidden="true">›</span><strong title={activePanel.title}>{activePanel.title}</strong></>}
    </span>}
  </nav>;
}

function StandalonePanelNavigation(props: PanelNavigationProps) {
  const controller = usePanelNavigation(props.panels, props.activeId, props.onActivate);
  return <PanelNavigation {...props} controller={controller}/>;
}
