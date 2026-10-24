// SPDX-License-Identifier: Apache-2.0
import { usePanelPresentation } from "./panelPresentation";

export const OPEN_HELP_SECTION_EVENT = "spike-open-help-section";
export type HelpSectionLocation = { topic: string; anchor?: string };

export function admitHelpSectionLocation(value: unknown): HelpSectionLocation | null {
  if (!value || typeof value !== "object") return null;
  const { topic, anchor } = value as Record<string, unknown>;
  if (typeof topic !== "string" || !topic.trim() || topic.length > 240 || /[\u0000-\u001f]/.test(topic)) return null;
  if (anchor !== undefined && (typeof anchor !== "string" || anchor.length > 240 || /[\u0000-\u001f]/.test(anchor))) return null;
  return { topic, ...(anchor === undefined ? {} : { anchor }) };
}

export default function SectionHelpButton({ topic, anchor, label }: HelpSectionLocation & { label: string }) {
  const { ownerDocument, ownerWindow } = usePanelPresentation();
  return <button type="button" className="spike-control--compact section-help-button" aria-label={`Help: ${label}`} title={`Open help for ${label}`} onClick={event => {
    const view = event.currentTarget.ownerDocument.defaultView ?? ownerDocument?.defaultView ?? ownerWindow;
    const location = admitHelpSectionLocation({ topic, anchor });
    if (!view || !location) return;
    // Detached panels are React portals owned by the main application's realm.
    const target = typeof window === "undefined" ? view : window;
    const request = view.document.createEvent("CustomEvent");
    request.initCustomEvent(OPEN_HELP_SECTION_EVENT, false, false, location);
    target.dispatchEvent(request);
  }}>Help</button>;
}
