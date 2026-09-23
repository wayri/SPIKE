# Portable simulation results and board visuals

Status: accepted for 0.2.10.

The v3 ZIP64 container remains the public project format. Complete simulation
objects are content-addressed JSON artifacts, deduplicated across active results,
history, and legacy UI state. Imported GLB scenes and all SVG layers are separate
content-addressed members. Their index retains layer names, view box, model
quality, and whether the board scene includes copper.

Python validates and writes artifacts atomically with the project. Native Rust
enforces approved paths and the exact opened manifest identity for targeted reads.
The UI reads result artifacts sequentially and visual artifacts by import stage.
There is no 12-result retention cap. Current transport limits are explicit:
96 MiB per result artifact and 96 MiB aggregate encoded-input visual content;
oversized writes fail without replacing the existing project.

ODB++ archives reopen via the saved canonical design and normalized desktop
projection. They are never decoded as UTF-8 board source. Unknown canonical and
UI snapshot fields survive edits; list deletions and explicit nulls remain edits.

The standalone `spike/result-package/v2` JSON format embeds design and workspace
context with simulation state and available PCB visuals. The matching Load
results command restores visualizer inputs. Legacy v1 results require their
original board open. Result files do not change solver validation status.

Packages using these artifacts declare minimum reader 0.2.10. Older projects
remain readable; Python clients can request fully hydrated state or opt into
deferred artifacts. This does not add new solver physics or manufacture missing
component models. Existing assembly/model artifacts remain in the v3 package.
