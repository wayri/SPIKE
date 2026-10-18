<!-- SPDX-License-Identifier: Apache-2.0 -->
# Shared material evidence library

`python/spike_core/material_library.py` owns inert material records reusable by
MCAD, PCB and analysis workflows. `data/materials/catalog.json` contains 60
records: 32 generic screening examples, 26 selectable evidence placeholders,
and two records of selected manufacturer typical facts. The catalog covers metals, non-copper conductors, ceramics,
polymers, FR4 variants, RF laminates, flex films and metal-clad substrates.

## Use

```python
from python.spike_core.material_library import (
    load_catalog, material_snapshot, project_scalar_properties,
)
materials = load_catalog()
copper = next(m for m in materials if m['id'] == 'generic-copper')
assignment = material_snapshot(copper)
# Explicit screening-only acceptance; never done automatically by the library.
constants = project_scalar_properties(copper, ['density'], allow_estimates=True)
```

Selection retains a complete snapshot, including missing properties and source
metadata. Save that snapshot with the assigned body. `validate_snapshot` checks
its schema, identity, revision and SHA-256 digest on reload. Catalog updates do
not mutate an existing assignment. A caller may explicitly replace an assignment
with a new snapshot. No automatic material-name matching or solver hookup exists.

## Record contract

Version 1 requires stable `id`, textual `revision`, `name`, `family`,
`description` and `properties`; tags, manufacturer, grade and notes are optional.
Property names and SI units are enumerated in `PROPERTY_UNITS`. Mechanical,
thermal and electrical fields remain together even if a consumer only needs one.

Every property requires an evidence status, provenance (source, reviewed scope
and license), applicability notes and optional temperature/frequency bounds.
Values are finite, temperatures are absolute kelvin and frequency is hertz.
Density, heat capacity, conductivity, moduli, expansion and dimensionless fields
retain explicit units. Basic positivity and isotropic Poisson bounds reject
malformed data; they do not qualify a constitutive model.

Supported property shapes are scalar, orthotropic with three distinct named
material axes, samples at temperature and/or frequency coordinates, and
unavailable. Samples retain their exact coordinates and ordering. The library
performs no interpolation, extrapolation, coordinate rotation or homogenization.
Material axes require a downstream orientation assignment before tensor use.
Orthotropic Poisson coupling and full stiffness tensors need a future schema.

`project_scalar_properties` requires an explicit nonempty property list. Missing,
unavailable, sampled and orthotropic fields raise `MaterialError`; estimates
require `allow_estimates=True`. The calling adapter must check applicability and
its solver's constitutive and evidence requirements before execution. Projection
does not certify a user's claimed measured/manufacturer provenance.

## Evidence and limits

The generic numerical values are independently authored, rounded illustrative
assumptions at 293.15 K. They are explicitly estimates, not extracted measurements
or manufacturer specifications. No primary material-property source was reviewed
to qualify these examples. Unknown properties are unavailable, never fabricated
zeros. Named Kapton film is an empty grade-required placeholder, without inferred
properties from a generic polyimide. FR4 grades, RF substrates, metal-clad boards,
flex composites, conductive films and inks require reviewed grade/stackup/cure
data. Conductivity of a metal does not establish RF surface roughness, plating,
magnetic behavior or temperature dependence.

This is an inert evidence and persistence feature. It introduces no numerical
method or validated material law. `NUMERICAL_METHOD_EVIDENCE.md` continues to
govern future solver use, interpolation, rotation, homogenization and constitutive
implementation. No source-dependent product qualification, manufacturer approval
or release gate is satisfied by catalog presence.

Rogers RO4003C and RO4350B records retain selected typical facts from the official
[RO4000 data sheet](https://rogerscorp.com/-/media/project/rogerscorp/documents/advanced-electronics-solutions/english/data-sheets/ro4000-laminates-ro4003c-and-ro4350b---data-sheet.pdf),
revision 1592 080322, PUB 92-004, page 3, reviewed 2026-10-18. Density converts
g/cm^3 to kg/m^3; CTE converts ppm/C to 1/K. Thermal conductivity retains 80 C;
electrical samples retain the Z direction, 10 GHz and 23 C. Process Dk is not
design Dk. The 4 mil RO4350B exception and LoPro variants are excluded. Typical
facts are not guaranteed specifications. Only CTE has complete X/Y/Z evidence;
no missing tensor components are inferred. DuPont Kapton PDF links returned
404 during review, so that placeholder retains no inferred product values.

The catalog arrangement, code, tests and prose are original Apache-2.0 SPIKE
content. Manufacturer factual selections retain source and ownership metadata;
the copyrighted datasheet itself, text, tables and figures are not bundled.

## Verification

Run `python -m unittest tests.python.test_material_library -v`. Checks exercise
catalog family coverage, malformed/nonfinite values, SI units, schema versions,
duplicate IDs, snapshot tampering and detachment, retained axes/samples and
fail-closed scalar admission. These are contract tests, not material validation.
