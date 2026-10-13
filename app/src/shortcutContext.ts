// SPDX-License-Identifier: Apache-2.0
/** Inputs and nested editor surfaces own keyboard events, including clipboard and undo. */
export function ownsKeyboardInput(target: EventTarget | null): boolean {
  const element = target as (Element & { isContentEditable?: boolean }) | null;
  return Boolean(element?.isContentEditable || element?.closest?.('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"], [role="combobox"], [role="slider"], [role="spinbutton"], .monaco-editor, .cm-editor'));
}

/** Viewport keys must not operate behind dialogs, menus or nested editors. */
export function blocksViewportShortcut(target:EventTarget|null,modalOpen=false):boolean {
 const element=target as Element|null;
 return modalOpen||ownsKeyboardInput(target)||Boolean(element?.closest?.('[role="menu"], [role="dialog"], .modal-backdrop, .topology-editor, .spike-action-context-menu, .viewport-action-menu, .python-workspace'));
}
