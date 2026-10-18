// SPDX-License-Identifier: Apache-2.0
import { createContext, useContext, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { LucideIcon } from "./icons";
import "./ApplicationMenu.css";

type Icon = LucideIcon;
type MenuContextValue = { close: () => void };
const MenuContext = createContext<MenuContextValue>({ close: () => {} });

const editable = (target: EventTarget | null) => Boolean((target as Element | null)?.closest?.('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"],[role="combobox"],.monaco-editor,.cm-editor'));
const modalOpen = () => Boolean(document.querySelector('[aria-modal="true"]'));
const enabled = (element: HTMLElement) => element.getAttribute("aria-disabled") !== "true" && !(element as HTMLButtonElement).disabled;
const directItems = (menu: HTMLElement) => Array.from(menu.querySelectorAll<HTMLElement>('[role="menuitem"]')).filter(item => item.closest('[role="menu"]') === menu && enabled(item));
const topItems = (bar: HTMLElement) => Array.from(bar.querySelectorAll<HTMLElement>(':scope > .application-menu-entry > [role="menuitem"]')).filter(enabled);
const focusAt = (items: HTMLElement[], index: number) => { if (!items.length) return; items.forEach((item, at) => item.tabIndex = at === index ? 0 : -1); items[index]?.focus(); };
const move = (items: HTMLElement[], current: HTMLElement, delta: number) => focusAt(items, Math.max(0, items.indexOf(current) + items.length + delta) % items.length);

function fitFlyout(element: HTMLElement, nested: boolean) {
  element.style.maxHeight = `${Math.max(120, window.innerHeight - 16)}px`;
  element.style.overflowY = "auto";
  element.classList.remove("application-menu--flip");
  if (nested) {
    const owner = element.parentElement?.getBoundingClientRect();
    const measured = element.getBoundingClientRect();
    if (!owner) return;
    element.style.position = "fixed";
    element.style.top = `${Math.max(8, Math.min(owner.top, window.innerHeight - measured.height - 8))}px`;
    const openLeft = owner.right + measured.width > window.innerWidth - 8;
    element.classList.toggle("application-menu--flip", openLeft);
    element.style.left = `${Math.max(8, openLeft ? owner.left - measured.width : owner.right)}px`;
    element.style.right = "auto";
    return;
  }
  const rect = element.getBoundingClientRect();
  if (rect.right > window.innerWidth - 8) {
    element.style.left = `${Math.min(0, window.innerWidth - 8 - rect.right)}px`;
  } else element.style.left = "0px";
  const adjusted = element.getBoundingClientRect();
  if (adjusted.bottom > window.innerHeight - 8) element.style.top = `${Math.max(0, -(adjusted.bottom - window.innerHeight + 8))}px`;
}

export function MenuBar({ children, onClose, open }: { children: ReactNode; onClose: () => void; open: boolean }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const bar = ref.current; if (!bar) return;
    const items = topItems(bar); items.forEach((item, index) => item.tabIndex = index === 0 ? 0 : -1);
  }, []);
  useEffect(() => {
    const bar = ref.current;
    if (!bar) return;
    const onDocumentKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing || event.key === "Process" || event.getModifierState?.("AltGraph") || modalOpen() || editable(event.target)) return;
      const items = topItems(bar);
      if ((event.key === "F10" && !event.ctrlKey && !event.metaKey && !event.shiftKey) || (event.key === "Alt" && !event.ctrlKey && !event.metaKey)) {
        event.preventDefault(); onClose(); focusAt(items, 0); return;
      }
      if (event.altKey && !event.ctrlKey && !event.metaKey && event.key.length === 1) {
        const match = items.find(item => item.dataset.mnemonic === event.key.toLowerCase());
        if (match) { event.preventDefault(); match.focus(); match.click(); }
      }
    };
    const onPointer = (event: PointerEvent) => { if (open && !bar.contains(event.target as Node)) onClose(); };
    const onWindowBlur = () => { if (open) onClose(); };
    document.addEventListener("keydown", onDocumentKey, true);
    document.addEventListener("pointerdown", onPointer, true);
    window.addEventListener("blur", onWindowBlur);
    return () => { document.removeEventListener("keydown", onDocumentKey, true); document.removeEventListener("pointerdown", onPointer, true); window.removeEventListener("blur", onWindowBlur); };
  }, [onClose, open]);
  const onKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    const bar = ref.current!; const target = event.target as HTMLElement; const tops = topItems(bar); const top = target.closest<HTMLElement>('.application-menu-entry > [role="menuitem"]');
    const menu = target.closest<HTMLElement>('[role="menu"]');
    if (event.key === "Tab") { onClose(); return; }
    if (event.key === "Escape") {
      event.preventDefault();
      if (menu?.parentElement?.classList.contains("application-submenu")) { const trigger = menu.parentElement.querySelector<HTMLElement>(':scope > [role="menuitem"]'); trigger?.click(); trigger?.focus(); }
      else { onClose(); (top ?? menu?.closest<HTMLElement>(".application-menu-entry")?.querySelector<HTMLElement>(':scope > [role="menuitem"]'))?.focus(); }
      return;
    }
    if (top && ["ArrowLeft", "ArrowRight"].includes(event.key)) { event.preventDefault(); const next = tops[(tops.indexOf(top) + (event.key === "ArrowRight" ? 1 : -1) + tops.length) % tops.length]; next?.focus(); if (open && next !== top) next?.click(); return; }
    if (top && ["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault(); if (!top.getAttribute("aria-expanded") || top.getAttribute("aria-expanded") === "false") top.click();
      queueMicrotask(() => { const popup = top.parentElement?.querySelector<HTMLElement>(':scope > [role="menu"]'); const items = popup ? directItems(popup) : []; focusAt(items, event.key === "ArrowUp" || event.key === "End" ? items.length - 1 : 0); }); return;
    }
    if (!menu) return;
    const items = directItems(menu);
    if (event.key === "ArrowDown") { event.preventDefault(); move(items, target, 1); }
    else if (event.key === "ArrowUp") { event.preventDefault(); move(items, target, -1); }
    else if (event.key === "Home") { event.preventDefault(); focusAt(items, 0); }
    else if (event.key === "End") { event.preventDefault(); focusAt(items, items.length - 1); }
    else if (event.key === "ArrowRight") {
      event.preventDefault(); const submenu = target.parentElement?.classList.contains("application-submenu") ? target : null;
      if (submenu) { if (submenu.getAttribute("aria-expanded") !== "true") submenu.click(); queueMicrotask(() => { const child = submenu.parentElement?.querySelector<HTMLElement>(':scope > [role="menu"]'); if (child) focusAt(directItems(child), 0); }); }
      else if (!menu.parentElement?.classList.contains("application-submenu")) {
        const owner = menu.parentElement?.querySelector<HTMLElement>(':scope > [role="menuitem"]');
        const index = tops.indexOf(owner!); const next = tops[(index + 1 + tops.length) % tops.length]; next?.focus(); next?.click();
      }
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      if (menu.parentElement?.classList.contains("application-submenu")) { const trigger = menu.parentElement.querySelector<HTMLElement>(':scope > [role="menuitem"]'); trigger?.click(); trigger?.focus(); }
      else { const owner = menu.parentElement?.querySelector<HTMLElement>(':scope > [role="menuitem"]'); const index = tops.indexOf(owner!); const next = tops[(index - 1 + tops.length) % tops.length]; next?.focus(); next?.click(); }
    }
  };
  const onBlur = (event: React.FocusEvent<HTMLElement>) => { if (open && !event.currentTarget.contains(event.relatedTarget as Node | null)) onClose(); };
  return <MenuContext.Provider value={{ close: onClose }}><nav ref={ref} className="menu-bar application-menu-bar" role="menubar" aria-label="Application menu" onKeyDown={onKeyDown} onBlur={onBlur}>{children}</nav></MenuContext.Provider>;
}

export function MenuButton({ label, open, onClick, children, mnemonic }: { label: string; open: boolean; onClick: () => void; children: ReactNode; mnemonic: string }) {
  const flyout = useRef<HTMLDivElement>(null);
  const identity = useId(), triggerId = `${identity}-trigger`, menuId = `${identity}-menu`;
  useLayoutEffect(() => { if (open && flyout.current) fitFlyout(flyout.current, false); }, [open]);
  return <div className="menu-entry application-menu-entry" onPointerEnter={event => { if (event.currentTarget.parentElement?.querySelector('[aria-expanded="true"]') && !open) onClick(); }}>
    <button id={triggerId} type="button" role="menuitem" aria-haspopup="menu" aria-controls={menuId} aria-expanded={open} data-mnemonic={mnemonic.toLowerCase()} tabIndex={-1} className={open ? "menu-button selected" : "menu-button"} onClick={onClick} onKeyDown={event => { if (event.key !== "Enter" && event.key !== " ") return; event.preventDefault(); const trigger = event.currentTarget; if (!open) onClick(); requestAnimationFrame(() => { const popup = trigger.parentElement?.querySelector<HTMLElement>(':scope > [role="menu"]'); if (popup) focusAt(directItems(popup), 0); }); }}>{label}</button>
    {open && <div id={menuId} aria-labelledby={triggerId} ref={flyout} className="menu-dropdown application-menu-popup" role="menu">{children}</div>}
  </div>;
}

export function MenuItem({ icon: Icon, label, shortcut, onClick, disabled = false }: { icon: Icon; label: string; shortcut?: string; onClick: () => void; disabled?: boolean }) {
  const { close } = useContext(MenuContext);
  return <button type="button" role="menuitem" tabIndex={-1} className="menu-item" disabled={disabled} aria-disabled={disabled || undefined} onClick={() => { if (disabled) return; close(); onClick(); }}><Icon size={14} aria-hidden={true}/><span>{label}</span>{shortcut && <small>{shortcut}</small>}</button>;
}

export function MenuSubmenu({ label, icon: Icon, children }: { label: string; icon?: Icon; children: ReactNode }) {
  const [open, setOpen] = useState(false); const flyout = useRef<HTMLDivElement>(null);
  const identity = useId(), triggerId = `${identity}-trigger`, menuId = `${identity}-menu`;
  useLayoutEffect(() => { if (open && flyout.current) fitFlyout(flyout.current, true); }, [open]);
  return <div className="application-submenu" onPointerEnter={() => setOpen(true)} onPointerLeave={() => setOpen(false)}>
    <button id={triggerId} type="button" role="menuitem" tabIndex={-1} className="menu-item" aria-haspopup="menu" aria-controls={menuId} aria-expanded={open} onClick={event => setOpen(value => event.detail === 0 ? !value : true)} onKeyDown={event => { if (event.key !== "Enter" && event.key !== " ") return; event.preventDefault(); const trigger = event.currentTarget; if (!open) setOpen(true); requestAnimationFrame(() => { const popup = trigger.parentElement?.querySelector<HTMLElement>(':scope > [role="menu"]'); if (popup) focusAt(directItems(popup), 0); }); }}>{Icon && <Icon size={14} aria-hidden={true}/>}<span>{label}</span><small aria-hidden="true">›</small></button>
    {open && <div id={menuId} aria-labelledby={triggerId} ref={flyout} className="menu-dropdown application-menu-popup application-submenu-popup" role="menu">{children}</div>}
  </div>;
}
