<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI material scenarios

`prepare_si_material_scenario(design, request)` creates an immutable,
source-bound SpiDeR v2 design for SI analysis when an imported design does not
carry a required physical material property. It does not infer copper
conductivity, revise native source identity, or claim that a value came from
the board file. The first contract supports only conductor
`conductivity_s_per_m`.

This boundary is intended for workflows such as the pinned Marble import,
whose copper material correctly has `conductivity_s_per_m: null`. A solver must
continue to reject that base design. Execution becomes possible only after an
engineer supplies an explicit scenario value and its provenance.

## Request

The exact `spike/si-material-scenario-request/v1` fields are:

```json
{
  "contract": "spike/si-material-scenario-request/v1",
  "design_digest_sha256": "<SHA-256 of canonical input-design JSON>",
  "source_digest": "<unchanged native source SHA-256>",
  "material_overrides": [
    {
      "material_id": "material-copper",
      "material_type": "conductor",
      "conductivity_s_per_m": 58000000.0,
      "provenance": {
        "source": "engineer-supplied scenario input",
        "model": "constant isotropic conductivity",
        "temperature_k": 293.15,
        "assumption_status": "assumed"
      }
    }
  ]
}
```

`assumption_status` is exactly `assumed`, `reported`, or `measured`. These are
requester declarations, not SPIKE verification or qualification. `source` and
`model` must name the basis clearly enough for human review. Numeric strings,
booleans, non-finite values, non-positive values and values above the contract
bounds are rejected. Arrays contain 1 through 256 unique material IDs. Unknown
fields, missing fields, unknown materials and non-conductive targets fail
closed. `material_type` must match the target material's retained class; the
admitted classes are `conductor` and `copper`. Marble imports retain the latter,
rather than being silently relabeled.

Request control data is limited to 8 MiB. The retained in-process design has a
separate 128 MiB and 250,000-entity admission bound so complete public boards
such as Marble are not confused with the smaller inline interoperability API.
The shared SpiDeR validator and its transport limits are not weakened.

The design digest is SHA-256 over UTF-8 canonical JSON with sorted keys, compact
separators and ASCII escaping, matching `spider_v2_schema.content_digest`. Both
that digest and `source_digest` must match, so a request cannot be replayed onto
a stale design revision or different source artifact.

## Result and identity

The function returns `spike/si-material-scenario-result/v1` with a new `design`
and `provenance`. The input dictionary is not mutated. The new design retains
the input `source` object exactly; it does not assign a digest to bytes that
were not imported. Applied values are recorded separately at:

```text
design.metadata["spike.si_material_scenario"]
```

That record binds the base design SHA-256, original source digest, normalized
overrides and their prior values. `scenario_sha256` hashes those non-recursive
fields. Result provenance also supplies `prepared_design_sha256`, which hashes
the complete prepared design including the scenario record. SI extraction now
hashes the actual physical parameters in `material_parameters_digest` and the
entire declared scenario record in `declared_material_scenario_context_digest`.
Both enter `geometry_digest` and hence the derived network identity. Changing
conductivity or only its declared context cannot silently reuse that result.
Context hashing proves identity, not manufacturer or measurement authenticity.

A prepared design is not accepted as another base design. To revise a scenario,
prepare again from the original bound design. This keeps scenario replacement
explicit and avoids layering values whose provenance could be confused.

## Limits

The boundary decision is recorded in [ADR 0133](adr/0133-explicit-si-material-and-reference-scenarios.md).

Worker method `prepare_si_material_scenario` accepts exactly `{design, request}`
for inline cases, with an 8 MiB combined input and 8 MiB result limit. Larger
retained designs use the in-process API and its separate explicit limits; they
must not be truncated or split into a synthetic replacement to pass IPC.
The self-contained control schema is registered in `schemas/manifest.json`.
This is analysis preparation, not a DLL loader or a physical qualification.

- The API supplies a constant scalar conductivity; it does not implement a
  temperature law, anisotropy, surface roughness, skin-effect calibration or
  frequency-dependent material model.
- A reported or measured declaration is not independently authenticated.
- Supplying conductivity does not resolve White Rabbit reference-zone
  ambiguity, Marble bends, ports, return-path completeness, AMI model quality,
  or board-level validation and release gates.
- This preparation step adds no governing mathematics. Existing SI extraction
  remains experimental and retains its current applicability limits.

## Real-board diagnostic run

With the pinned local Marble and legacy White Rabbit fixtures available:

```powershell
.venv/Scripts/python.exe scripts/verify_si_real_boards.py --output build/si-board-check.json --copper-conductivity-s-per-m 58000000 --temperature-k 293.15 --conductivity-source https://www.npl.co.uk/products-services/magnetics/ac-and-dc-conductivity --reference-zone white_rabbit=b4ae1c1d-464f-5047-a0fd-ca183b7f23b8
```

Use a fresh output filename. The command supplies a nominal scenario explicitly;
it is not a hidden copper default or measured foil data. The current diagnostic
admits Marble's selected piecewise path while retaining bend/discontinuity and
quasi-TEM limitations. It still rejects the legacy White Rabbit case and returns
nonzero overall; do not treat one admitted case as an all-board pass.
See [the executed record](validation/SI_BOARD_SCENARIOS_20261023.md).
