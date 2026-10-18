<!-- SPDX-License-Identifier: Apache-2.0 -->
# SPIKE product scope: PCB-focused multiphysics

## Tagline

**PCB-focused multiphysics, from board to complete assembly.**

SPIKE is an open-source, local-first multiphysics simulation workbench for PCBs
and the complete assemblies built around them. The PCB is the starting point;
the system under study can include multiple boards, circuits, connectors,
harnesses, enclosures, heatsinks, mechanical parts and surrounding fluid regions.
Shared geometry, material evidence, study inputs and traceable results should
connect these workflows throughout an engineering project.

## What end-to-end means

1. **Build the assembly:** import electrical and mechanical sources, retain
   stable occurrences and source identity, position parts, and review changes.
2. **Describe the physics:** assign grade-specific materials, orientations,
   sources, loads, ports, contacts, boundaries and operating conditions.
3. **Prepare the study:** select an eligible named solver, inspect geometry
   omissions, create an admitted mesh or reduced model, and resolve missing data.
4. **Run and couple:** execute supported steady or transient studies, with
   explicitly implemented exchanges between domains rather than inferred links.
5. **Review and collaborate:** examine results in assembly context, compare
   revisions, preserve evidence and return reviewed mechanical changes.

These steps describe the intended integrated product workflow. Each step has
partial implementations with its own admission and validation boundaries.
End-to-end does not imply automatic arbitrary CAD-to-solver translation,
manufacturing authoring, or a qualified solver for every possible assembly.

## Domains and present boundaries

| Area | Present foundations | Expansion direction |
| --- | --- | --- |
| PCB, PI and SI | Board import, conductor networks, bounded field/network and channel workflows | Broader geometry, material laws, reference paths and independently correlated cases |
| Circuits and controls | SPIKES circuit execution, explicit component mappings and supported co-simulation | More device coverage and reviewed field/circuit feedback |
| Thermal and fluid | Board/solid thermal, bounded native CFD and optional external CHT workflows | General admitted assembly cooling, robust airflow/temperature coupling and convergence evidence |
| EM and RF | Selected native field models, sampled networks and optional external engines | Broader supported field formulations, geometry and material dispersion |
| Mechanical | Retained CAD geometry, reviewed FreeCAD placements and bounded static/thermoelastic solvers | Richer geometry change proposals, structural interfaces and additional mechanics |
| Materials | Versioned thermal/electrical/mechanical evidence and occurrence/layer snapshots | Reviewed grade coverage and explicit solver consumption of supported constitutive laws |
| Scale and collaboration | Occurrence-based assemblies, reusable assets and bounded background/parallel workflows | Larger admitted models, measured resource budgets, scalable meshing and coordinated execution |

For current mathematical scope and reference checks, use
[Solver Status](SOLVER_STATUS.md). A product description, menu entry or installed
external engine cannot expand those claims.

## Large assemblies

Large-scale assembly simulation is a product objective. Scale depends on geometry
complexity, mesh size, unknown count, coupling schedule, memory and the selected
backend. There is no universal supported assembly-size claim. Every scaling claim
needs a reproducible benchmark with hardware, runtime versions, resource usage,
convergence and accuracy evidence. Independent parallel jobs are distinct from
accelerating one coupled solve; an assembly preview is distinct from a solved
assembly.

## Language for GitHub and the community

Short description:

> PCB-focused multiphysics simulation, from board to complete assembly: PI, SI,
> circuits, thermal, EM/RF and mechanical workflows, with MCAD collaboration and
> a roadmap toward large-scale coupled assemblies.

Use the same focus across GitHub, Discord and product documentation. Describe
capabilities as implemented, approximate, experimental, external or planned
according to their actual evidence. Retain PCB specialization while welcoming
mechanical and cross-domain system studies.

Related workflows: [assembly CLI](ASSEMBLY_CLI.md),
[FreeCAD collaboration](FREECAD_COLLABORATION.md),
[material evidence](MATERIAL_LIBRARY.md),
[material assignments](MCAD_MATERIAL_WORKFLOW.md), and
[Solver Manager](SOLVER_SUITE.md).
