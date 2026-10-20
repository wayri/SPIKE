<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Retained-PCB profiler evidence persistence

Date: 2026-10-13. Status: profiler persistence verified; the post-import-fix
Marble diagnostic completed and directly classified the five omitted zones.

## Change and focused verification

`scripts/profile_retained_board_mesher.py` now requires an explicit output
under the repository and derives three adjacent sidecars: an atomic phase
marker, a raw five-second faulthandler stack log, and the importer-normalized
filled polygon coordinates for the seven selected zones. The result and all
sidecars refuse replacement. The staged 44.99 MB board copy remains temporary;
diagnostic evidence no longer shares its lifecycle.

Every mesher `ValidationIssue` is serialized as a complete dictionary,
including warnings, message, path, suggestion, and status. Missing source IDs
also map to the complete issue dictionaries that mention them. The selected
zone artifact records the pinned board SHA-256 and CERN-OHL-1.2 fixture scope;
capturing these seven polygons does not filter or mutate the design passed to
the mesher.

Four focused tests passed in 0.050 seconds. They cover sidecar derivation,
repository confinement, replacement refusal, complete warning retention,
missing-ID association, selected-zone coordinates, and phase/stack survival.
`git diff --check` also passed.

| File | SHA-256 |
| --- | --- |
| `scripts/profile_retained_board_mesher.py` | `592a509d5a61ebe8116ad09ecf5d7c9bea4755d9c877fed6226874e162728738` |
| `tests/python/test_profile_retained_board_mesher.py` | `ecee71d871d81e200c0b420a20fdc9d5adab441c5aac0c387fa84e6d0c55db8e` |

## Single bounded run

The one authorized command used the pinned Marble source and the 180-second,
4,096 MiB bounds. It stopped after 7.9670606 seconds, before import completed:

```text
AttributeError: 'str' object has no attribute 'get'
python/spike_core/kicad_importer.py:120
arc_diagnostics = [item for item in parser.diagnostics
                   if item.get("code") == "KICAD_ARC_LINEARIZED"]
```

The working-tree importer change assumes every legacy parser diagnostic is a
dictionary. This Marble parse produced at least one string diagnostic. The
profiler did not cause or modify that production failure, and the run was not
retried.

| Retained artifact | SHA-256 |
| --- | --- |
| Unbundled local `baseline-profile.json` | `66bcf863fe3e2893193c7ae6560336ec773a94415e12289a125e2c596ee4570d` |
| Unbundled local `baseline-profile.phase.json` | `8369cf568f69cd6fe6070d5227e65febd8239556b856843244cdf690934a7170` |

The phase marker records `controller_started` at `2026-10-12T19:06:06Z`.
The result records failure at `2026-10-12T19:06:14Z`. No raw stack or selected
zone artifact was created because the importer failed before those phases.

After the importer owner added a minimal mapping guard and passed its four
focused diagnostic tests, one changed-condition run was authorized at a new
path. It completed in 145.5702571 seconds, including a 7.2304906-second import
and 136.7047789-second mesh. The process-tree memory limit was enforced and the
worker was suspended before Windows Job assignment. The mesher returned an
untruncated partial mesh with 1,572 nodes, 1,586 branches, and 6,387 cells.

| Post-fix artifact | SHA-256 |
| --- | --- |
| Unbundled local `baseline-after-import-fix.json` | `283edb56f846dbfc5867124222f4fecc9d158cc7f1509bb36bb9491691edaac9` |
| Unbundled local `baseline-after-import-fix.phase.json` | `d97c5108f3d8a6e8f6216d15ca53ed602cddb4a991ffa7109393d1b61a6ad650` |
| Unbundled local `baseline-after-import-fix.mesh-wall-stacks.log` | `d1ee732d3358a2473ad6fe3445139416e4cee71ffe9d395e21f5a80206c3f34d` |
| Unbundled local `baseline-after-import-fix.selected-zone-polygons.json` | `bb0fd8887cf45135211c9334132eb737d947bc9c74615e059b214c0d8bdd7df5` |

The selected-zone artifact contains seven source polygons and 20,866 total
points. It is bound to Marble source SHA-256
`3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512`
and retains the CERN-OHL-1.2 fixture scope.

## Missing-zone diagnosis available without a rerun

The previous successful import requested seven `+1V0` zones but the mesher's
`geometry_counts["zone"]` was two. That count alone cannot distinguish the two
ordinary per-zone paths that skip the final increment. Initial normalized
polygon validation can emit this warning shape:

```json
{
  "code": "SPIKE-BE-MESH-W-0002",
  "severity": "warning",
  "message": "<source_id> has no usable simple filled copper polygon.",
  "path": "design.zones[<source_id>]",
  "suggestion": "Repair the imported zone outline before using it for a conductor solve.",
  "status": "approximate"
}
```

After a valid boundary produces no grid fragments, failure to find an interior
polygon point can instead emit the same code and metadata with this message:

```text
<source_id> could not be triangulated into usable filled copper.
```

The five previously retained missing IDs requiring discrimination are:

- `zone-13:F.Cu:1`
- `zone-39:In2.Cu:1`
- `zone-43:In4.Cu:1`
- `zone-57:In5.Cu:1`
- `zone-61:In6.Cu:1`

The count by itself did not establish which message applied. The post-fix
result now provides direct evidence: all five IDs emitted the first complete
warning dictionary, `has no usable simple filled copper polygon.` None emitted
the triangulation/no-fragments message. The result contains those five full
dictionaries in both `worker.mesh.issues` and the per-source mapping. It also
retains a sixth complete warning: `SPIKE-BE-MESH-W-0003` reports that one
roundrect pad was meshed from extracted bounding dimensions.

The requested/meshed counts were respectively 122/122 tracks, 7/2 zones,
58/58 vias, and 43/43 pads. There were no error-severity issues, but geometry
completeness is false because source validation omitted the five zones. The
partial mesh hashes remain diagnostic only:

- complete mesh: `4450c8d71767b5745fbb74572ad4cfdc39efa28a68b275d6cd89255b2494d744`
- topology and cells: `e88da443cf3dc565bcc55adbf3fb8ea4b56a308b296677f4316987bfa5985b32`
- node/branch connectivity: `cca33728ead4053be06dca3415974ec9994ec89af49c883ce143b097e81462c3`
