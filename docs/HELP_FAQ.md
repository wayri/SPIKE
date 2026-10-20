# Frequently asked questions

## Why is Run disabled?

Check for an active job, missing design/net/endpoints, failed preflight, or an unavailable compatible solver. Read the nearby validation message and the Issues/Console output. The control reference records which controls have conditional availability; resolve the workflow prerequisites before retrying.

## Why can I configure a feature that cannot run?

Configuration, runtime discovery, preparation and execution are separate states. Some controls capture intent for physics that the selected runtime does not support. Read capability status in Solver Manager and [Solver status](SOLVER_STATUS.md).

## Why does browser preview fail to open a file or run a solver?

Native dialogs and the local worker belong to the installed Tauri desktop. Browser preview can show configuration and saved output but does not provide that host. Use the desktop for native operations; do not diagnose the preview's missing bridge as numerical failure.

## Why does help show an unknown error code?

Search the complete code, including the four-digit suffix. If no registered entry matches, preserve the exact code, message, operation ID and app/worker versions. A newer worker or third-party adapter may use a code this installed help does not contain. Do not use the remedy for a different suffix just because its domain matches.

## Can I retry every error?

No. The exact diagnostic entry identifies recoverable and retryable states and gives the issued recovery action. Correct invalid inputs first. Preserve critical-failure diagnostics before restart. Repeatedly retrying a malformed package, unsupported model or exhausted resource budget does not correct it.

## Why did opening a project lose the original CAD connection?

A project retains an embedded board snapshot and object identities. It is not a continuously synchronized CAD session. Review the board source, import diagnostics, and active design before importing a changed board. Save an independent revision if you need a baseline.

## Why is the 3D board blank or slow?

Use Fit; check visible layers, opacity, clipping and models. Reduce visual detail for large scenes and review renderer diagnostics. Confirm that the import produced actual geometry. For misalignment inspect source units/origin, instance transform and model side before changing electrical inputs.

## Why does selecting one visible layer still solve several layers?

Visible layers constrain presentation. Electrically connected copper, vias and through-pads define the analysis topology. Review terminal connectivity and return policy in preflight.

## Why does a mesh preview pass but the solver fail?

Preflight checks admissibility and geometry; it does not prove convergence. Inspect the solver's residual, matrix/conditioning detail, mesh connectivity and resource limits. Use a reproducible request and change one assumption at a time.

## How do I reduce memory use without changing the question?

Inspect mesh counts and budgets before solving. Refine only where needed, reduce retained transient frames, hide expensive visualization detail, and compare convergence at multiple resolutions. Decimation reduces output storage; it does not fix an invalid integration step. Do not increase budgets beyond available resources.

## What do approximate, validated, unsupported and failed_to_converge mean?

They describe different numerical/model outcomes. Approximate carries stated assumptions; validated applies only within its evidence and applicability range; unsupported has no supported result for the requested behavior; failed_to_converge has not met the required convergence criterion. Operation completion and a colorful plot do not override these states.

## Why is an eye or TDR result missing while S-parameters appear?

Time-domain analysis requires explicit DC, a suitable uniform frequency grid and sufficient bandwidth/sample density. Frequency results can remain available when time-domain prerequisites fail. Review the SI diagnostic instead of inventing DC or extrapolating silently.

## Does importing IBIS or a SPICE model make the model accurate?

No. Check where the model came from, its pin mapping, supported syntax, corners, and operating conditions. The SI endpoint reduction has explicit approximation limits. Nonlinear switching and protocol-compliance claims require the corresponding supported model and independent evidence.

## Why is my prepared thermal or EMI case not a result?

Preparation writes a case. Execution requires a ready compatible adapter and successful completion; acceptance also checks actual returned fields and convergence. Missing physics or an iteration ceiling remains visible in status.

## Does the thermal color map contain all solver samples?

The visualization may use a bounded sample preview. Check the field sample count and saved result details. The UI must not manufacture unsampled values. See [Thermal workflow](THERMAL_WORKFLOW.md) for the exact display limit and unit conversions.

## Why are probes empty or in different units?

Check the selected result kind, field availability, layer, physical location and quantity. Current and current density differ. AC impedance and transient voltage differ. Compare results using the same physical units and operating conditions.

## How do I preserve a reproducible failure?

Save the project or request, complete code, operation ID, versions, selected solver, resource settings, model status, convergence evidence and safe log detail. Include a minimal input if possible. Do not include private keys or license secrets. Follow [Troubleshooting](../TROUBLESHOOTING.md).

## Can I use help offline?

Yes. Topics, controls, CLI help, diagnostics and shipped evidence are bundled with the app. Links to outside websites need connectivity. Bookmarks and checked workflow steps are local conveniences; they do not change the project or prove a test passed.

## How do I navigate help quickly?

Use search for a symptom, button label, command or full diagnostic code. Select a category to narrow the results. Use Back/Forward for article history, bookmark useful pages, and use the article contents links for long references. Ctrl+F focuses help search, Escape closes help, and Tab moves through controls. Copy link produces an internal help address that can be pasted into help search. Screenshots can be enlarged. Use Print for the current article.

## Where did the ribbon and familiar workspace tabs go?

Clean is the default interface. It keeps the command ribbon and optional quick-tools bar hidden until requested. Use **Workspaces: ...** to change workspaces, **Menu** for categorized commands, or **Search commands, parts, nets...** (Ctrl+K) for global search. Choose **Classic** from the interface selector or **Settings > Interface > Interface layout** to restore the menu bar, workspace tabs and ribbon. The layout change retains project and solver inputs.

## How do I restore a tool that I hid or minimized?

Use the eye-shaped **Show hidden tools** control. The same tools are available under **Menu > Tools > Open panels** or **Windows & tools**. Editors may also be open as document tabs beside **Board & results**. A hidden panel or inactive document tab retains its draft; it has not been applied merely because it remains open.

## Can the workspace and viewport use different colors?

Yes. **Settings > Interface > Theme** controls the application chrome: Graphite + Teal, Light + Teal, High contrast or Follow system. **Viewport background** independently selects Graphite, Light or AMOLED true black. These settings change presentation only and do not change result values.

## Which analysis workflow should I start with?

Search Help for **Analysis workflows and evidence**. It links the authored PI, SI, EM, Thermal, hybrid/multi-solve, CHT, CFD and multi-board workflows. Each topic states prerequisites, returned outputs, diagnostics, convergence or conservation checks and current model limits. The analysis gallery distinguishes workflow diagrams, observed browser screenshots and plots from executed results.

## Does a prepared CHT or CFD case prove that the solver ran?

No. Runtime discovery, preflight, case preparation, execution and result admission are separate states. Interpret only worker-imported output with the matching run identity, solver/version provenance, fields, residuals and limitations. The compact thermal Screen action is an RC estimate, not CFD. Current native/SU2 cavity and SU2 CHT evidence is bounded reference-case evidence rather than general assembly, turbulence or production qualification.

## Is multi-solve the same as a distributed coupled solve?

No. Parallel workers schedule independent bounded jobs under concurrency and resource limits. They do not provide single-solve MPI or automatically couple physics. A hybrid study must explicitly map quantities between domains, preserve geometry and revision identity, and pass each domain's residual plus the declared coupling and energy-balance checks.
