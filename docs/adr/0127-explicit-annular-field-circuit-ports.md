<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0127: explicit annular fields and coupled circuit ports

Status: accepted for bounded experimental reference development; not release qualified.
Date: 2026-10-21.

## Decision

Extend the isolated DC references with full-azimuth annular land cells and
independent finite current patches. Reduce each land using fresh unit current
solutions, solve a passive port circuit with explicit incidence, then solve
the actual land currents again. Preserve raw unit and final fields, KCL, KVL,
separately owned land/barrel/resistor heat and source work. Labels never weld
ports. Uniform Neumann patches use conjugate mean potentials; they do not
claim pointwise equipotential metallic interfaces.

Native geometry authentication belongs to an importer-owned evidence adapter.
It supplements the existing normalized importer by explicitly rejecting native
drill-offset and per-layer geometry cases not represented there. It does not
modify existing normalized output or become a solver dependency. The source
wrapper pins file hash, exact pad ID, dimensions, net and layer; explicit slab,
material and electrode choices remain modeling assumptions. Pure field/circuit
kernels accept inert dictionaries and do no filesystem or EDA parsing.

See [field derivation](../DC_ANNULAR_LAND.md),
[port derivation and primary review](../DC_ANNULAR_CIRCUIT.md) and
[importer boundary](../IMPORTER_ARCHITECTURE.md). Original implementation and
fixtures use the existing Python/NumPy/SciPy reference stack. No new dependency,
external implementation or production engine registration is introduced.

## Consequences

This supports one explicitly supplied coaxial stack, circular centered native
pads and current-driven full-azimuth bands. Retained evidence checks local
Ohmic weak law, actual vector fields, conservation and heat rather than pass
flags. Volume identities remain available for subsequent thermal mapping,
which requires separate transfer/units verification. No arbitrary polygon,
angular crowding, general board compiler, AC/SI or board qualification is
inferred. Full PI01-S02 and knowledgeable human numerical release review stay
open until their acceptance conditions are independently satisfied.
