# Work example library

Open **Menu > Work examples** or search **Examples** with Ctrl+K. Individual
cases also appear in global search. The library contains **38 curated cases**
and **76 bounded text assets**, available offline after the frontend is bundled.
Its categories and readiness filters keep setup drafts separate from runnable
source workflows and retained evidence.

## Choose a task

| Work area | Cases | Examples of work |
| --- | ---: | --- |
| Power integrity | 5 | DC IR drop, AC/PDN, decoupling and transient setup |
| Signal integrity | 7 | Simple and loaded channels, coupled networks, IBIS driver/Input sink, spatial victim voltage and eye/TDR inputs |
| EM / RF | 3 | Antenna/radiation, near-field probing and RF/filter workflows through the existing EMerge library |
| Thermal / CFD | 4 | Thermal models, cavity flow, solid/fluid and CHT setup |
| Assemblies / harness | 3 | Multi-board, retained assembly and harness inputs |
| Coupled / automation | 3 | Coupled electrical/thermal workflows and parallel automation |
| Reviews / mechanics | 3 | Part limits/headroom, mechanical inputs and thermomechanical refinement |
| Promo: PCB temperature and case cooling | 3 | Complete EBrake thermal history and good/poor case-contact volume evidence |
| Promo: magnetic machines | 5 | Planar PM, reduced motor, core/air electromagnet comparison and solenoid setup |
| Promo: viewport capture guides | 2 | Original E/H browser-preview pictures with exact capture provenance |

```mermaid
flowchart LR
  A[Menu or global search] --> B[Choose work area and readiness]
  B --> C[1 Inspect exact inputs and prerequisites]
  C --> D[2 Stage a supported setup or save companion files]
  D --> E[3 Explicitly compile, bind or run]
  E --> F[Review returned diagnostics and evidence]
  F --> G[Save project or export results]
```

Each card has three steps, engine/runtime prerequisites, a source command where
applicable, license information and explicit limitations. **Inspect text** opens
the exact bundled file. **Save selected file** preserves its extension and uses
the desktop artifact-save boundary with UTF-8/digest verification. In a browser
it downloads the file. No script executes through these actions.

## Readiness means something specific

| Label | Meaning |
| --- | --- |
| Runnable | Existing executable source workflow with its listed dependencies; not a check that this installation has its engine |
| Setup only | Input draft needing identities, geometry, values or runtime preparation |
| Saved evidence | Historical input/result material with its original scope and limitations |
| Guide | Entry to an existing library whose individual cases have their own prerequisites |

Source Python runners require the source checkout and original relative file
layout. Saving one runner does not install its implementation or companions.
Optional engines are not downloaded or trusted by the library. The precise
[catalog and asset contract](../examples/catalog/README.md) lists these limits.

## Promo project opening

Seven complete saved-project snapshots are available through **Open project** on their cards. The normal unsaved-project guard remains in control, and no simulation starts automatically. The original ZIP hashes and manifest digests are retained beside each snapshot. EBrake retains its full 6.29 MB input/history; it is an explicit exception to the ordinary 512 KiB text asset limit, with an 8 MiB project cap. The complete case volume meshes/results are retained; their STEP companion requires explicit CAD relinking. The two pictures are original browser-preview captures and do not establish installed-desktop acceptance. See [promo provenance and limits](../examples/promo_release/README.md).

## Direct SI staging and project persistence

**Stage IBIS example** opens the existing SI workbench at IBIS models. Review and
explicitly apply the staged request; the prior draft is retained until then.
Compile before inspecting/trusting a local ngspice executable and explicitly
running. An optional executable path provides recovery when discovery finds no
engine. This path and native-code trust are session-only.

**Stage spatial SI example** opens its normalized two-trace board through the
normal unsaved-project guard. Apply the staged files, select the actual aggressor
and victim identities and request ID, then bind the exact saved samples or
explicitly run the supplied coupled-line pair. The same main 3D viewport displays
returned sample values. Port crosstalk metrics never become an invented E-field.

Both workspaces now save under `analysis.si.deployment_workspaces`. Saved IBIS
results retain an exact request snapshot and are displayed as unverified saved
evidence. Reopening restores neither compiled readiness nor native runtime
trust. Spatial input, samples, independent net/request controls and display
settings reopen as an **unadmitted candidate**; current worker context must be
checked again. Save without results removes IBIS results and spatial sample
data while retaining setup inputs. Undo/project replacement remounts the panels
so a late response cannot restore an earlier project's authority.

## Deployment and qualification

The build now requires all IBIS/spatial SI owners in the frozen worker, compares
their frozen source to the intended source snapshot, bundles SI fixtures and
runs a fresh worker IPC probe. See the
[actual frozen candidate receipt](validation/SI_IBIS_SPATIAL_PACKAGING_20261025.md).
Frontend assets load lazily from a fixed allowlist; no arbitrary example-tree
scan or large external dataset is bundled by this library.

These are experimental workflows. The IBIS voltage-refinement gate is still
unmet at three probes. Native wide/narrow UI acceptance, installed lifecycle,
real-model/measurement and human numerical release review remain separate
gates. USB 3.2 Gen 1 and 10GBASE-KR remain selected compliance targets, not claimed
certifications. The library does not advertise unavailable physics as completed.
