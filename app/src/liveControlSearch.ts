// SPDX-License-Identifier: Apache-2.0
/** Search current controls without copying their values or bypassing their handlers. */
export type LiveControlAction = {
  id: string; label: string; category: string; description: string;
  keywords: string; disabled: boolean; kind: "action" | "field";
  run: () => void;
};
const identities = new WeakMap<Element, number>();
let nextIdentity = 0;
const compact = (value: string | null | undefined) => (value ?? "").replace(/\s+/g, " ").trim();
function labelOf(element: HTMLElement): string {
  const labelled = element.getAttribute("aria-labelledby")?.split(/\s+/).map(id => element.ownerDocument.getElementById(id)?.textContent ?? "").join(" ");
  const field = element as HTMLInputElement;
  return compact(element.getAttribute("aria-label") || labelled ||
    (field.labels?.length ? Array.from(field.labels).map(label => label.textContent).join(" ") : "") ||
    element.getAttribute("title") || (element.matches("button,summary,[role=button],[role^=menuitem]") ? element.textContent : "") ||
    element.getAttribute("placeholder") || element.getAttribute("name"));
}
const unavailable = (element: HTMLElement) => element.matches(":disabled") || element.getAttribute("aria-disabled") === "true";

export function liveControlSearch(document: Document, revealPanel?: (id: string) => void): LiveControlAction[] {
  const actions: LiveControlAction[] = [];
  for (const element of document.querySelectorAll<HTMLElement>('button,input:not([type=hidden]),select,textarea,summary,[role=button],[role^=menuitem]')) {
    if (element.closest('.universal-search-shade,[inert],[data-search-ignore]')) continue;
    const slot = element.closest<HTMLElement>('[data-panel-id]');
    const hidden = element.closest<HTMLElement>('[hidden], [aria-hidden="true"]');
    // Retained dock drafts can be revealed; other hidden conditional controls cannot.
    if (hidden && (!slot || !revealPanel || !hidden.matches(".focus-floating-slot,.floating-panel-frame"))) continue;
    if (!hidden && !element.getClientRects().length) continue;
    const label = labelOf(element);
    if (!label) continue;
    if (!identities.has(element)) identities.set(element, ++nextIdentity);
    const id = `live-control:${identities.get(element)}`;
    const panelId = slot?.dataset.panelId;
    const category = slot?.getAttribute("aria-label") || (panelId ? "Retained panel" : document.title?.startsWith("SPIKE | ") ? document.title.slice(8) : "Current workspace");
    const field = element.matches('input:not([type=button]):not([type=submit]):not([type=checkbox]):not([type=radio]):not([type=file]),select,textarea');
    const reveal = (perform: () => void) => {
      if (!element.isConnected) throw new Error("This control changed. Reopen search to refresh it.");
      if (unavailable(element)) throw new Error(`${label} is currently unavailable.`);
      if (panelId) revealPanel?.(panelId);
      // Search owns modal focus until it closes. Then focus the real control.
      element.ownerDocument.defaultView?.requestAnimationFrame(() => {
        if (!element.isConnected || unavailable(element)) return;
        element.ownerDocument.defaultView?.focus(); element.scrollIntoView({block:"nearest"}); element.focus(); perform();
      });
    };
    actions.push({id,label:field ? `Edit ${label}` : label,category,
      description:field ? `Focus the ${label} control; values remain editable in its panel.` : `Activate ${label} using its existing control.`,
      keywords:`${label} ${category} ${field ? "settings input options" : "button action"}`,disabled:unavailable(element),kind:field?"field":"action",
      run:()=>reveal(()=>{if(!field)element.click();})});
    if (element.tagName === "SELECT") {
      const select = element as HTMLSelectElement;
      Array.from(select.options).forEach((option, index) => {
        const text = compact(option.label);
        if (!text || option.hidden) return;
        actions.push({id:`${id}:option:${index}`,label:`${label}: ${text}`,category,
          description:`${select.multiple?"Toggle":"Choose"} ${text} in ${label}.`,keywords:`${label} ${text} ${category} option select`,
          disabled:unavailable(element)||option.disabled||Boolean(option.parentElement?.matches("optgroup:disabled")),kind:"field",
          run:()=>{if(option.disabled||option.parentElement?.matches("optgroup:disabled"))return;reveal(()=>{
            if(select.multiple)option.selected=!option.selected;else select.selectedIndex=index;
            const EventType=select.ownerDocument.defaultView!.Event;
            select.dispatchEvent(new EventType("input",{bubbles:true}));
            select.dispatchEvent(new EventType("change",{bubbles:true}));
          });}});
      });
    }
  }
  return actions;
}
