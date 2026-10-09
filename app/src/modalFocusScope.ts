// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, type KeyboardEvent as ReactKeyboardEvent } from "react";

const FOCUSABLE = 'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, a[href], [tabindex]:not([tabindex="-1"])';

function controls(scope: HTMLElement) {
  return [...scope.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(item =>
    !item.closest('[inert], [hidden], [aria-hidden="true"]') &&
    item.getAttribute("type") !== "hidden" &&
    !item.matches?.(":disabled") &&
    item.getClientRects().length > 0);
}

export function useModalFocusScope(onClose: () => void, closeDisabled = false, selector?: string, label?: string) {
  const scopeRef = useRef<HTMLElement>(null);
  const closeRef = useRef(onClose), disabledRef = useRef(closeDisabled);
  closeRef.current = onClose; disabledRef.current = closeDisabled;
  useEffect(() => {
    const scope = scopeRef.current ?? (selector ? document.querySelector<HTMLElement>(selector) : null);
    const previous = document.activeElement as HTMLElement | null;
    if (scope && label) { scope.setAttribute("role", "dialog"); scope.setAttribute("aria-modal", "true"); scope.setAttribute("aria-label", label); scope.tabIndex = -1; }
    const frame = requestAnimationFrame(() => {
      const preferred = scope?.querySelector<HTMLElement>("[data-modal-initial-focus]");
      (preferred ?? (scope ? controls(scope)[0] : null) ?? scope)?.focus({ preventScroll: true });
    });
    const nativeKey = (event: KeyboardEvent) => handleKey(event, scope);
    if (!scopeRef.current) scope?.addEventListener("keydown", nativeKey);
    return () => {
      cancelAnimationFrame(frame);
      scope?.removeEventListener("keydown", nativeKey);
      const active = document.activeElement;
      if (previous?.isConnected && (active === document.body || Boolean(scope?.contains(active)))) previous.focus({ preventScroll: true });
    };
  }, []);
  const handleKey = (event: Pick<ReactKeyboardEvent<HTMLElement>, "key" | "shiftKey" | "preventDefault" | "stopPropagation">, scope = scopeRef.current) => {
    if (event.key === "Escape") {
      event.preventDefault(); event.stopPropagation();
      if (!disabledRef.current) closeRef.current();
      return;
    }
    if (event.key !== "Tab") return;
    if (!scope) return;
    const items = controls(scope), first = items[0], last = items[items.length - 1];
    if (!first || !last) { event.preventDefault(); scope.focus({ preventScroll: true }); return; }
    if (event.shiftKey && (document.activeElement === first || !scope.contains(document.activeElement))) { event.preventDefault(); last.focus({ preventScroll: true }); }
    else if (!event.shiftKey && (document.activeElement === last || !scope.contains(document.activeElement))) { event.preventDefault(); first.focus({ preventScroll: true }); }
  };
  const onKeyDown = (event: ReactKeyboardEvent<HTMLElement>) => handleKey(event);
  return { scopeRef, onKeyDown };
}
