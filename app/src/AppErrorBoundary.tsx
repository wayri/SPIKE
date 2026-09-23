import React from "react";

type State = {
  error: Error | null;
  componentStack: string;
  copied: boolean;
};

function diagnostics(error: Error, componentStack: string): string {
  return JSON.stringify({
    contract: "spike/crash-diagnostic/v1",
    generated_at: new Date().toISOString(),
    message: error.message,
    name: error.name,
    stack: error.stack ?? "",
    component_stack: componentStack,
    location: window.location.href,
    desktop_shell: "__TAURI_INTERNALS__" in window,
    user_agent: navigator.userAgent,
  }, null, 2);
}

export default class AppErrorBoundary extends React.Component<React.PropsWithChildren, State> {
  state: State = { error: null, componentStack: "", copied: false };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    this.setState({ componentStack: info.componentStack ?? "" });
    console.error("SPIKE UI recovery boundary", error, info);
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

  private copyDiagnostics = async (): Promise<void> => {
    if (!this.state.error) return;
    try {
      await navigator.clipboard.writeText(diagnostics(this.state.error, this.state.componentStack));
      this.setState({ copied: true });
    } catch {
      this.setState({ copied: false });
    }
  };

  render(): React.ReactNode {
    if (!this.state.error) return this.props.children;
    return <main className="fatal-recovery" role="alert">
      <section>
        <span>SPIKE UI RECOVERY</span>
        <h1>The workspace encountered an unexpected interface error.</h1>
        <p>Your project files were not modified. Reload the interface first; reset only clears local panel, shortcut, and preference state.</p>
        <code>{this.state.error.message}</code>
        <div>
          <button onClick={this.reload}>Reload SPIKE</button>
          <button onClick={this.resetInterface}>Reset interface state</button>
          <button onClick={() => void this.copyDiagnostics()}>{this.state.copied ? "Diagnostics copied" : "Copy diagnostics"}</button>
        </div>
      </section>
    </main>;
  }
}
