// SPDX-License-Identifier: Apache-2.0
import { createContext, useContext } from "react";
export type PanelPresentation = { ownerDocument: Document | undefined; ownerWindow: Window | undefined; detached: boolean };
export const PanelPresentationContext = createContext<PanelPresentation | null>(null);
export function usePanelPresentation(): PanelPresentation {
  return useContext(PanelPresentationContext) ?? { ownerDocument: typeof document === "undefined" ? undefined : document, ownerWindow: typeof window === "undefined" ? undefined : window, detached: false };
}
