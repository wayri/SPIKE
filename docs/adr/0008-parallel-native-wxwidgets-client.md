# ADR 0008: Parallel Native wxWidgets Client

- Status: Retired on 2026-09-28
- Date: 2026-08-31
- Supersedes: the C++ UI prohibition in ADR 0007 for the isolated client only

The `wx_desktop/` implementation was removed after an unsuccessful UI and
runtime trial. This ADR remains as the historical boundary for that client;
it does not approve a replacement for release.

## Context

SPIKE needs a parallel, compiled Windows workbench for high-volume geometry
interaction and native VTK result rendering. The frozen wxPython UI is not a
safe base because it owns duplicate behavior and reparents a PyVista window.

## Decision

`wx_desktop/` is an independently built C++20 wxWidgets application using
native controls, wxAUI, and VTK C++ rendering. It consumes only versioned
project and worker JSON contracts. It must not link solver kernels into the UI
process or reuse the frozen Python UI.

The Tauri application remains supported and unchanged. The native client is
an engineering preview until Windows packaging, full project round-trip and
interaction acceptance, and DC/AC/transient qualification pass. Both clients invoke the same isolated
Python worker and share DesignIR, AnalysisSpec, AnalysisResult, and `.spike`
package authority.

Plotly is embedded only in generated offline HTML reports. Matplotlib remains
worker-side for static publication figures; the native UI process embeds
neither Python nor Matplotlib. VTK renders through a wxGLCanvas-owned context so
wxWidgets, rather than VTK, owns the Win32 window and OpenGL lifetime.

The 0.2.5 native workspaces preserve AssemblyIR and retained DesignIR sets,
perform resource admission, plan independent multi-board PI/SI work, execute
explicit sequential SI batches, and expose current SI and thermal contracts.
Coupled multi-board solving stays fail-closed: harness compilation and reduced
network binding are preparation artifacts, not evidence of a qualified solver.

## Consequences

- C++ owns numerical kernels and one isolated native presentation client.
- Cross-client behavior is shared through contracts rather than UI code.
- The Windows package carries wxWidgets, VTK, WebView integration, and the
  isolated worker runtime.
- A feature is not ported until it uses real worker output and preserves model
  status, issues, and provenance.
