// SPDX-License-Identifier: Apache-2.0
import type { SpiceModel } from "./spiceWorkspace";

export const MODEL_LIBRARY_MAX_BYTES = 2 * 1024 * 1024;
export type LibraryCandidate = { id: string; subcircuit_name: string; pins: string[]; default_parameters: Record<string, string>; dependency_names: string[]; required_engine: string };
export type LibraryInspection = { contract: string; valid: boolean; source_sha256?: string; candidates: LibraryCandidate[]; diagnostics: { code: string; severity: string; message: string; line: number }[] };
export type LibraryImportState = { text: string; name: string; inspection: LibraryInspection | null; selected: string; busy: boolean; error: string };
type Reply = { ok: boolean; result?: Record<string, unknown>; error?: string; error_detail?: { detail?: string } };
type Request = (request: { method: string; params: Record<string, unknown> }) => Promise<Reply>;
export const emptyLibraryImport = (): LibraryImportState => ({ text: "", name: "User model library", inspection: null, selected: "", busy: false, error: "" });

/** Inert staging; a changed source invalidates every in-flight response. */
export class SpiceModelLibrarySession {
  state = emptyLibraryImport();
  private revision = 0;
  private active = true;
  constructor(private request: Request, private changed: (state: LibraryImportState) => void, private add: (model: SpiceModel) => void) {}
  private emit(patch: Partial<LibraryImportState>) { this.state = { ...this.state, ...patch }; if (this.active) this.changed(this.state); }
  private current(revision: number) { return this.active && revision === this.revision; }
  activate() { this.active = true; this.emit({ busy: false }); }
  dispose() { this.active = false; this.revision++; }
  setSource(text: string, name = this.state.name) {
    this.revision++;
    this.emit({ text, name, inspection: null, selected: "", busy: false, error: "" });
  }
  select(symbol: string) { if (!this.state.busy && this.state.inspection?.candidates.some(row => row.subcircuit_name === symbol)) this.emit({ selected: symbol }); }
  private failure(error: unknown) { return error instanceof Error ? error.message : "Model library request failed"; }
  async readFile(file: Pick<File, "size" | "name" | "text">) {
    const revision = ++this.revision;
    this.emit({ inspection: null, selected: "", busy: true, error: "" });
    try {
      if (file.size > MODEL_LIBRARY_MAX_BYTES) throw new Error("Model libraries are limited to 2 MiB. No file content was read.");
      const text = await file.text();
      if (!this.current(revision)) return;
      this.setSource(text, file.name);
      await this.inspect();
    } catch (error) { if (this.current(revision)) this.emit({ error: this.failure(error), busy: false }); }
  }
  async inspect() {
    if (this.state.busy) return;
    const revision = ++this.revision;
    const { text, name } = this.state;
    this.emit({ inspection: null, selected: "", busy: true, error: "" });
    try {
      if (new TextEncoder().encode(text).byteLength > MODEL_LIBRARY_MAX_BYTES) throw new Error("Model libraries are limited to 2 MiB of UTF-8 text.");
      const reply = await this.request({ method: "inspect_spice_model_library", params: { text, name } });
      if (!this.current(revision)) return;
      if (!reply.ok) throw new Error(reply.error_detail?.detail || reply.error || "Inspection failed");
      const inspection = reply.result as unknown as LibraryInspection;
      if (inspection?.contract !== "spike/spice-model-library-inspection/v1" || !Array.isArray(inspection.candidates) || !Array.isArray(inspection.diagnostics)) throw new Error("Worker returned an incompatible model inspection. Update the worker.");
      this.emit({ inspection, selected: inspection.valid ? inspection.candidates[0]?.subcircuit_name ?? "" : "", busy: false });
    } catch (error) { if (this.current(revision)) this.emit({ error: this.failure(error), busy: false }); }
  }
  async importSelected(sourceLocator: string, licenseNote: string) {
    if (this.state.busy || !this.state.inspection?.valid || !this.state.selected) return;
    const revision = ++this.revision;
    const { text, name, selected, inspection } = this.state;
    this.emit({ busy: true, error: "" });
    try {
      const reply = await this.request({ method: "import_spice_model", params: { text, name, subcircuit_name: selected, source_locator: sourceLocator, license_note: licenseNote } });
      if (!this.current(revision)) return;
      if (!reply.ok) throw new Error(reply.error_detail?.detail || reply.error || "Import failed");
      const model = reply.result?.model as SpiceModel | undefined;
      if (reply.result?.contract !== "spike/spice-model-import/v1" || model?.kind !== "subcircuit" || model.import_provenance?.source_sha256 !== inspection.source_sha256 || model.subcircuit_name !== selected) throw new Error("Imported model does not match the inspected source and selection.");
      this.add(model);
      this.emit({ busy: false });
    } catch (error) { if (this.current(revision)) this.emit({ error: this.failure(error), busy: false }); }
  }
}
