// SPDX-License-Identifier: Apache-2.0
import { runLocalWorker, selectNativeImportFile } from "./workerBridge";
import type { ContextScript } from "./contextScript";

export const WORK_FOLDER_COMMAND = "assistant_choose_work_folder";
export const WORK_FILES_COMMAND = "assistant_work_files";
export const SCRIPT_DRAFT_COMMAND = "assistant_stage_script";

/** The owning workspace holds folder authority; model requests only name children. */
export function createAssistantTaskHarness() {
  let root = "", owner = "", epoch = 0;
  const synchronize = (identity: string) => {
    if (identity !== owner) { owner = identity; root = ""; epoch += 1; }
  };
  return {
    context(identity: string) {
      synchronize(identity);
      return { revision: epoch, workFolderSelected: Boolean(root), workFolderName: root.split(/[\\/]/).pop() || null,
        fileOperations: ["list", "read", "csv_summary"], scripts: "reviewed_unsaved_python_drafts", scriptExecution: false };
    },
    async command(command: string, args: Record<string, unknown>, identity: string,
      stage: (draft: ContextScript) => void, currentIdentity: () => string) {
      synchronize(identity);
      const ticket = epoch;
      if (command === WORK_FOLDER_COMMAND) {
        if (Object.keys(args).length) throw new Error("Choose the work folder using the native picker.");
        const selected = await selectNativeImportFile("script", true);
        if (identity !== currentIdentity() || ticket !== epoch) throw new Error("Project changed while choosing the work folder.");
        if (selected) { root = selected.path; epoch += 1; }
        return { ...this.context(identity), cancelled: !selected };
      }
      if (command === WORK_FILES_COMMAND) {
        if (!root) throw new Error("Choose a work folder in Assistant settings before using work-file tools.");
        if ("root" in args) throw new Error("Models cannot choose the work-folder root.");
        const reply = await runLocalWorker({ method: "assistant_work_files", params: { ...args, root } });
        if (identity !== currentIdentity() || ticket !== epoch) throw new Error("Work folder or project changed during file inspection.");
        if (!reply.ok) throw new Error(reply.error ?? "Work-file request failed.");
        return reply.result;
      }
      if (command === SCRIPT_DRAFT_COMMAND) {
        if (Object.keys(args).some(key => !["title", "source"].includes(key)) || typeof args.title !== "string" || !/^[a-zA-Z0-9][a-zA-Z0-9 _-]{0,79}$/.test(args.title)
          || typeof args.source !== "string" || !args.source.trim() || new TextEncoder().encode(args.source).length > 65536 || args.source.includes("\0")) {
          throw new Error("Supply a simple draft title and 1–65536 bytes of Python source.");
        }
        const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(args.source));
        if (identity !== currentIdentity() || ticket !== epoch) throw new Error("Project changed while staging the script.");
        const id = crypto.randomUUID(), name = `${args.title}.py`;
        stage({ id, name, code: args.source, ...(root ? { workingDirectory: root } : {}) });
        return { status: "draft_staged", id, name, sha256: Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join(""),
          saved: false, executed: false, next: "Inspect the draft in the Python workspace; use its Save and Run controls after review." };
      }
      throw new Error("Unsupported task harness command.");
    },
  };
}
