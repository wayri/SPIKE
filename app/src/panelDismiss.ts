// SPDX-License-Identifier: Apache-2.0
/** Inspect only the owning surface; hidden steps and nested tools cannot veto it. */
export function panelControlAvailable(node: HTMLElement, content: HTMLElement): boolean {
  for (let current: HTMLElement | null = node; current && current !== content; current = current.parentElement) {
    if (current.hidden || current.hasAttribute("inert")) return false;
    // The duplicate button itself is intentionally hidden by the shared header.
    if (current === node && current.dataset.spikeInnerDismiss === "true") continue;
    const style = current.ownerDocument.defaultView?.getComputedStyle(current);
    if (style?.display === "none" || style?.visibility === "hidden") return false;
  }
  return true;
}
export function panelDismissControl(content: HTMLElement, title: string): HTMLButtonElement | null {
  const primaryHeader = content.querySelector("header,.floating-heading,.modal-heading,.floating-panel-title");
  const candidates = Array.from(content.querySelectorAll<HTMLButtonElement>("button")).filter(button => {
    if (!panelControlAvailable(button, content)) return false;
    const dialog = button.closest('[role="dialog"],[role="alertdialog"],dialog');
    const outer = dialog?.parentElement?.closest('[role="dialog"],[role="alertdialog"],dialog');
    if (dialog?.getAttribute("role") === "alertdialog" || (outer && content.contains(outer))) return false;
    if (button.hasAttribute("data-panel-close")) return true;
    const name = (button.getAttribute("aria-label") ?? button.getAttribute("title") ?? button.textContent ?? "").trim().toLowerCase();
    if (name === "close" || name === "close panel" || name === `close ${title.toLowerCase()}`) return true;
    return Boolean(primaryHeader?.contains(button) && ((/^close\b/.test(name) && name !== "close project") || (!name && button.querySelector("svg.lucide-x,svg.lucide-circle-x"))));
  });
  return candidates.find(button => primaryHeader?.contains(button)) ?? candidates[0] ?? null;
}
export function panelCloseState(content: HTMLElement, title: string) {
  const confirmation = Array.from(content.querySelectorAll<HTMLElement>('[role="alertdialog"]')).some(node => panelControlAvailable(node, content));
  const control = panelDismissControl(content, title);
  const reason = confirmation ? "Respond to the open confirmation before closing this panel" : control?.matches(":disabled") ? "This panel is busy. Finish or stop its active operation before closing" : "";
  return { control, reason };
}
