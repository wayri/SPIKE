# Open and publicly available model collections

Reviewed 2026-09-06 against primary upstream sources. This is an intake decision
record, not a claim that these collections are bundled or executable in SPIKES.
No largest-library ranking is established: archives, declarations, duplicated
models, process corners and distinct manufacturer parts are different counts.

## Implemented local integration

The optional `model-collections/sky130-f62031a-models` source subset is downloaded
from the official primitive repository at commit
`f62031a1be9aefe902d6d54cddd6f59b57627436`. It retains 1,268 files (51,110,719
bytes), including upstream licenses and attribution. Individual source files are
unmodified. `SPIKES-COLLECTION.json` records their hashes and upstream revision.
This is not a full PDK and is not installed into the release application.

The local index `model-collections/sky130-f62031a.spkindex` contains 6,707 declarations
from 1,232 inspected model files. Variants/corners and repeated names are retained:
this count is **not** a qualified-part count. Static-only helper/include files are
reported without inventing declarations. Initial indexing took 26.8 seconds on
this host; this is one observed scan, not a portable performance benchmark.

In Studio, choose **Manufacturer parts → Browse / index SPICE collection folder**.
Use **Open saved index** for the index above, or **Index folder** for another
legally obtained extracted collection. Search matches names, types, pins, source
paths and detected features. The background scanner has file/byte/entry limits,
does not follow includes or directory links, and reports truncation explicitly.
Double-click a declaration to review source; changed file hashes require rescanning.
Saved indexes refer to local files, so move the source folder only with a rescan.

No declaration is automatically approved for simulation. The native model/parser
compatibility gates still apply. The fetch script is
`scripts/fetch_open_spice_collection.py`, with a pinned revision and bounded safe
extraction. Other collections below remain assessed acquisition candidates.

| Collection | Useful coverage and verified scale | Licensing decision | SPIKES integration priority |
| --- | --- | --- | --- |
| [ngspice model directory](https://ngspice.sourceforge.io/modelparams.html): MicroCap, UGR and special models | Broad vendor active/passive collections; upstream dates MicroCap maintenance to 2019 and UGR approximately 2010. No independently counted current total. | Public download/freeware is not a blanket open-source grant. Review each archive, model header and dependency; do not apply ngspice's engine license to these collections. | High discovery value for jellybean/analog parts. Import locally with provenance and explicit license state; qualify individual models, not entire archives. |
| [KiCad-Spice-Library](https://github.com/kicad-spice-library/KiCad-Spice-Library) | Community aggregation including op-amps and discrete devices. README reports a historical first-run count of 8,004 models; this is not a current, deduplicated or validated part count. | README explicitly restricts its GPL3 claim to Scripts; models retain their own licenses. It is not the official KiCad library. No blanket redistribution approval. | High discovery value; deduplicate declarations and trace them to manufacturers before packaging. Existing labels are insufficient evidence of model origin. |
| [VA-Models](https://github.com/dwarning/VA-Models) | Compact-model equations: BSIM variants, bipolar families, HEMT/GaN, IGBT and nonlinear passives. Upstream lists ngspice/Xyce tests and model versions. These are not thousands of orderable packaged ICs. | [Copyright section](https://github.com/dwarning/VA-Models/blob/main/README.md#copyright) identifies multiple owners; most models use ECL-2.0. Review selected code-directory licenses and includes individually. | High solver-development value, later library execution. Compile selected reviewed sources and implement/test the required OSDI ABI. A compiled plugin for another engine is not automatically compatible. |
| [Qucs](https://github.com/Qucs/qucs) / [Qucs-S](https://github.com/ra3xdh/qucs_s) | Device libraries and example schematics; Qucs-S supports multiple external simulation kernels, while Qucsator is not SPICE. No model count verified. | Open-source application licenses are not evidence that every embedded vendor model has identical terms. Review library-file notices; retain applicable copyleft attribution/source obligations for adapted assets. | Medium: useful symbol/pin and reference-deck sources. Native Qucs formats need conversion and semantic tests, not renaming to `.lib`. |
| [SkyWater SKY130 PDK](https://github.com/google/skywater-pdk) | Foundry primitives and cell libraries for the SKY130 process. [Contents](https://skywater-pdk.readthedocs.io/en/main/contents.html) distinguish primitive, standard-cell and I/O libraries. | Project declares Apache-2.0; preserve LICENSE/NOTICE and inspect selected files/submodules and third-party notices. | Medium for CMOS, process-corner and mixed-signal qualification; not a replacement for LM358/74HC packaged-part models. Requires supported compact models and complete model/include dependency closure. |
| [IHP SG13G2 Open PDK](https://github.com/IHP-GmbH/IHP-Open-PDK) | BiCMOS/RF MOS, HBT and passive models for ngspice/Xyce, plus symbols, testbenches and measurement data. Upstream labels the release preview. | [Apache-2.0 project license](https://github.com/IHP-GmbH/IHP-Open-PDK/blob/main/LICENSE); retain file notices and review external dependencies separately. | Medium/high for future RF/model validation, not board-level product coverage. Native HBT/compact-model support and reference-test execution must precede a runnable badge. |

## Symbol licensing is separate

The [official KiCad library license](https://www.kicad.org/libraries/license/)
is CC-BY-SA 4.0 with a design-use exception. Redistributing a symbol collection
still requires attribution and the applicable share-alike terms. A KiCad symbol
with a manufacturer part name supplies neither SPICE equations nor a model license.

## Proposed integration sequence

1. Index local, user-selected collections without running their contents. Extract
   declarations, pin lists, includes, dialect requirements and hashes. Surface
   duplicate names, unresolved includes and unknown licenses explicitly.
2. Prioritize genuine commonly used manufacturer parts: jellybean BJTs/diodes,
   LM358/LM324-class amplifiers, precision amplifiers/comparators, logic and basic
   regulators. Find the manufacturer's own release when aggregators disagree.
   Do not turn a generic template into a branded part by changing its label.
3. Retain exact upstream bytes and pin order. Display distinct states:
   **discovered**, **imported**, **syntax checked**, **native tested**, and
   **qualified**. License/redistribution status is a separate field, not a runtime
   compatibility badge.
4. Qualify a small reviewed subset with pinned revisions and hashes before scaling:
   dependency-complete native DC/AC/transient decks, documented electrical limits,
   equal-model reference-engine comparisons and datasheet-condition checks.
5. Add reviewed VA-Models and PDK packs when the engine can execute their compact
   models. Keep technology/process identity, corners and validity envelopes visible.

## Release gate

Never automatically execute imported `.control`, shell commands or native plugins.
Never fetch arbitrary `.include` URLs or traverse outside the selected collection.
Encrypted/restricted models remain unsupported unless a permitted supported route
exists; collection size does not justify bypassing restrictions.

Each distributed item needs: source URL, upstream revision, retrieval date, original
and dependency hashes, license text, redistribution decision, manufacturer/model
identity, ordered pins, dialect, required engine features and retained test evidence.
Unresolved licensing is a packaging blocker; unresolved behavior is a circuit-ready
blocker. Neither may be replaced by a silent generic approximation.

This review adds no new qualified manufacturer models. See
[manufacturer-model-qualification.md](manufacturer-model-qualification.md) for the
existing acceptance criteria. A future catalog should report unique qualified
manufacturer identities separately from imported declarations and generic presets.
