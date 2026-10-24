# Guided simulation runs

The header **Run** and **Tutor** controls are available across workspaces. They
open a simulation guide beside the current editor and viewport. Choose the
analysis you intend to run; being in Home, Mesh or Results does not itself select
a physical problem or supply its missing inputs.

## Run in three steps

| Step | What you do | What SPIKE does |
| --- | --- | --- |
| **1 · Run and check** | Click **Run** and choose the simulation target. | Check the current setup through that target's adapter. Show the next required item and why it is required. |
| **2 · Resolve and recheck** | Click **Resolve this item**, edit the indicated setup and apply/save it. Click **Recheck setup**. | Read the current inputs again. Keep the run blocked until required items are resolved, then show the next item. |
| **3 · Review and run** | Review warnings and click **Run simulation** when setup is ready. | Recheck before submitting the request to the existing solver run path. Its final admission and runtime checks still apply. |

For example, if an object thermal study lacks an explicit thermal connection,
the guide directs you to its setup. Define the physical connection and its
required properties, apply it and recheck. SPIKE does not invent a contact,
thermal resistance, material, power, port or boundary condition to clear a step.
The exact requirements depend on the selected analysis and its existing
validator; every study does not require the same links or values.

```text
Run → Check current inputs → Next required item
                               ↓ Resolve
                         Edit existing setup
                               ↓ Recheck
                     Ready + warnings reviewed
                               ↓ Run simulation
                     Fresh check → Solver admission → Run progress
```

The guide shows one blocking requirement at a time. Fixing an early problem can
reveal a later one, so a shorter list does not mean that every downstream check
has already run. Errors remain visible; a failed check never becomes a ready
badge. A failed backend request returns an error rather than a successful result.

## Learn with Tutor

Click **Tutor** to walk through the selected target's setup sequence. Use
**Back**, **Next** and **Open this step** to review its geometry, inputs and
execution preparation. Moving to the next tutor page does not mark an input
valid or bypass a required check.

The tutor uses the same live setup and Run checks. You can learn the sequence
first, or switch directly to resolving the next required item. The final
**Run simulation** action remains explicit.

## Choose the intended analysis

| Target | Setup reviewed | Boundary |
| --- | --- | --- |
| **PI** | Current single-net, path or batch study, selected nets, terminals, values and the existing analysis preflight. | DC, AC and transient support follows the selected solver and admitted request. |
| **SI channel** | Current geometry/channel setup and its existing preparation checks. | Declared geometry and supported channel model remain required. |
| **Loaded SI** | Current source/load/network setup and its admission checks. | A tutorial does not supply missing source or termination data. |
| **Thermal** | Object-level materials, heat inputs, contacts and boundary setup as required by the selected model. | Visual contact alone is not a physical thermal connection. |
| **Board thermal** | Current board/part heat inputs, thermal paths and transient settings when used. | The selected board thermal model retains its documented approximation limits. |
| **CFD / airflow** | Optional OpenFOAM setup, boundary compatibility, runtime preparation and the prepared current case. | Required runtime and supported boundary physics remain admission gates. |
| **EMI screen** | The current screening study's required inputs. | A screening result is not a general full-wave EM solution or qualification. |
| **Extension engine** | Selected declared route, trust/enabled status, required board and scalar parameters or dedicated GUI setup. | The extension performs authoritative numerical/runtime admission on Run. Some engines require their own dedicated run controls. |

The header offers a common entry point. It does not make every module runnable
through a generic engine or imply that every workspace contains a solver. For an
extension with structured inputs or dedicated execution, open its configuration
and follow its own controls. Missing runtime support remains a blocker.

## Keep your place while editing

The helper occupies a reserved, nonmodal dock. It does not cover the application
with a blocking dialog: the viewport and current setup editor remain available.
At narrower supported widths the guide moves below the main content. Its close
control stays at the top right.

Use **Resolve this item** or **Open this step** to reach the existing editor.
Apply the change there, then return to **Recheck setup**. The guide coordinates
the flow; the original editor owns the values and the original solver owns the
run. Closing the guide does not discard applied setup changes. Once a solver
request has been accepted, closing the helper is not a substitute for the
solver's Stop or Cancel control.

## Current setup, warnings and validity

- Project, target or setup-revision changes invalidate previous readiness.
  Checks from an older context cannot authorize a new run.
- A Run click performs a fresh check and prevents duplicate submissions while
  that request is being checked or launched.
- Runtime busy indicators are separate from setup values. Existing run locks
  remain authoritative.
- Warnings remain visible for review. The guide distinguishes warnings from
  requirements that prevent execution.
- **Setup ready** means the adapter's required inputs passed its current checks.
  It does not establish physical fidelity, convergence, numerical accuracy or
  solver qualification. Consult [solver status](SOLVER_STATUS.md) and the
  target's evidence and limitations.
- Extensions without a pure numerical preflight explicitly warn that engine
  admission occurs on Run. The guide does not claim that those checks already
  passed.

## Related help and acceptance

Continue with [basic solver setup flows](SOLVER_SETUP_FLOWS.md),
[UI navigation](UI_NAVIGATION.md), [workspace panels](WORKSPACE_PANELS.md) and
[solver capability status](SOLVER_STATUS.md).

This page describes the source implementation. Installed desktop interaction
and native screenshot acceptance remain separate from automated controller,
adapter and UI checks; no installed-screen capture is claimed here.
