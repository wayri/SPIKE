// SPDX-License-Identifier: Apache-2.0
import {Copy,RotateCcw,Settings2,X} from "./icons";
import "./buttonStandard.css";
import "./appRecovery.css";
import React from "react";
import SupportReportPreview from "./SupportReportPreview";
import { createDiagnosticReport } from "./reportPrivacy";

type State = {
  error: Error | null;
  componentStack: string;
  previewReport: boolean;
  confirmClose: boolean;
  closing: boolean;
  closeError: string;
};

export default class AppErrorBoundary extends React.Component<React.PropsWithChildren, State> {
  state: State = { error: null, componentStack: "", previewReport: false, confirmClose:false, closing:false, closeError:"" };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    this.setState({ componentStack: info.componentStack ?? "" });
    // React may log errors itself; do not add raw exception or project data to logs.
    void error;
  }

  private reload = (): void => window.location.reload();

  private resetInterface = (): void => {
    try {
      Object.keys(localStorage)
        .filter(key => key.startsWith("spike.panel.") || key === "spike.shortcuts" || key === "spike.application.settings.v1")
        .forEach(key => localStorage.removeItem(key));
    } finally {
      window.location.reload();
    }
  };

  private close = async (): Promise<void> => {
    if (!this.state.confirmClose || this.state.closing) return;
    this.setState({closing:true,closeError:""});
    try { const bridge=await import("./workerBridge"); await bridge.closeDesktopWindow(); }
    catch { this.setState({closing:false,closeError:"Could not close SPIKE. Try the native window close button or retry."}); }
  };

  render(): React.ReactNode {
    if (!this.state.error) return this.props.children;
    return <main className="fatal-recovery" role="alert">
      <section>
        <span>SPIKE UI RECOVERY</span>
        <h1>The workspace encountered an unexpected interface error.</h1>
        <p>Reloading or closing may discard unsaved edits. These recovery controls do not modify saved project files. Reset clears only local panel, shortcut, and preference state.</p>
        <code>{createDiagnosticReport(this.state.error, this.state.componentStack).error_class}</code>
        <div>
          <button type="button" disabled={this.state.closing} onClick={this.reload}><RotateCcw size={14}/>Reload SPIKE</button>
          <button type="button" disabled={this.state.closing} onClick={this.resetInterface}><Settings2 size={14}/>Reset interface state</button>
          <button type="button" disabled={this.state.closing} onClick={() => this.setState({previewReport: !this.state.previewReport})}><Copy size={14}/>{this.state.previewReport ? "Hide report" : "Preview report"}</button>
          {typeof window !== "undefined" && "__TAURI_INTERNALS__" in window && !this.state.confirmClose && <button type="button" onClick={()=>this.setState({confirmClose:true})}><X size={14}/>Close SPIKE</button>}
        </div>
        {this.state.previewReport && <SupportReportPreview error={this.state.error} componentStack={this.state.componentStack}/>}
        {this.state.confirmClose && <aside aria-label="Confirm closing after interface failure"><p>Close SPIKE and discard any unsaved edits? Saved project files will remain on disk.</p><div><button type="button" className="spike-control--danger" disabled={this.state.closing} onClick={()=>void this.close()}>{this.state.closing?"Closing...":"Close and discard unsaved edits"}</button><button type="button" disabled={this.state.closing} onClick={()=>this.setState({confirmClose:false,closeError:""})}>Keep SPIKE open</button></div></aside>}
        {this.state.closeError && <p role="alert">{this.state.closeError}</p>}
      </section>
    </main>;
  }
}
