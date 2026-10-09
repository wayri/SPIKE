// SPDX-License-Identifier: Apache-2.0
/** Main-window close policy. Native shutdown is admitted only after draft checks. */
export type DesktopCloseContext = {
  isClosing: () => boolean;
  draftOwner: () => string | null;
  isDirty: () => boolean;
  showDraft: (owner: string) => void;
  showUnsaved: () => void;
  close: () => void;
};
export function createDesktopCloseHandler(context: DesktopCloseContext) {
  return (preventDefault: () => void) => {
    // Closing only the main window leaves detached tools keeping the process alive.
    preventDefault();
    if (context.isClosing()) return;
    const draft = context.draftOwner();
    if (draft) { context.showDraft(draft); return; }
    if (context.isDirty()) { context.showUnsaved(); return; }
    context.close();
  };
}
