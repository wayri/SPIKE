# Linked KiCad and mechanical sources

SPIKE can retain a link from an imported board or mechanical model to its original
local CAD file. Saved placement, routing and model changes can then be reviewed
and brought into the same SPIKE project.

## 1. Link the imported revision

Open **Project manager → Linked CAD sources**, or search for **Linked CAD sources**.
Save the SPIKE project first. Find the board or model by name; `*` and `?` work
in the target search. Select it and choose **Link source**.

Select the original `.kicad_pcb`, `.step` / `.stp`, `.glb`, or self-contained
`.gltf` file. Its bytes must match the revision already retained in SPIKE. Link
before editing the source. If the source has already changed, restore the
imported revision to establish the link, or import the new revision separately.

Links are saved in the project. **Relocate source** reconnects an identical
revision at another local path; **Unlink** keeps the embedded geometry intact.
A shared design or model link applies to every occurrence using that source.
An independent board copy has a separate retained design and can be linked separately.

## 2. Save changes in the source tool

Edit component placements and routing in KiCad, or geometry in the mechanical
CAD tool, then save the linked file. SPIKE reads the saved file; it does not
read unsaved editor buffers or send edits back to KiCad / MCAD.

Choose **Check changes**. The target shows `unchanged`, `changed`, or `missing`.
Optional checking runs every 15 seconds while Project manager is open and the
window is visible. Closing the manager stops that check. Checking never applies
geometry automatically. Source files are bounded to 64 MiB each.

## 3. Review and apply

Select **Review update** to import a candidate through SPIKE's existing CAD
adapters. Review the target, instance count and source fingerprint, then choose
**Apply update and invalidate results**.

```mermaid
flowchart LR
    A[Save in KiCad or MCAD] --> B[Check source changes]
    B --> C[Review imported revision]
    C --> D[Apply exact reviewed revision]
    D --> E[Review setup and rerun studies]
```

| Data | Sync behavior |
| --- | --- |
| PCB component placements, pads and routing | Reimported from the saved KiCad board |
| Shared board instances | All receive the updated retained design |
| Mechanical source geometry | Replaced for every occurrence using that model |
| SPIKE occurrence IDs and placements | Retained |
| Study definitions and bindings | Preserved where safe; removed referenced entities block sync |
| Saved simulation results and reports | Invalidated by a geometry change; rerun required |
| STEP visuals and exact topology | May require preparation again; stale constrained topology blocks sync |
| Original CAD files | Read only; never overwritten by SPIKE |

## Recovery and limits

- Save or discard local SPIKE changes and assembly drafts, and finish active runs
  before syncing. Sync updates the saved package and reloads it.
- A changed source after review or changed SPIKE package rejects the operation.
  Check/review again; failed updates leave the previous package in place.
- A missing or unreadable file does not remove the embedded design. Restore the
  file or relocate the link to an identical retained revision.
- Broken geometry identities are not guessed from similar names. Review or
  remove affected references before retrying. Recheck retained setup assumptions
  even when identities survive: dimensions and physical meaning can change.
- The link covers the selected file, not a whole project dependency graph.
  External footprints, component libraries, linked CAD assemblies and external
  glTF resources are not automatically watched. Use self-contained model files.
- This is saved-file synchronization, not live KiCad IPC or a bidirectional CAD
  editor. Updating geometry does not establish numerical validation.

See [UI navigation](UI_NAVIGATION.md) and [assembly workflows](ASSEMBLY_CLI.md).
