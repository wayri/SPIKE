// SPDX-License-Identifier: Apache-2.0
import {readFileSync,writeFileSync} from 'node:fs';
import ts from 'typescript';
import {posix} from 'node:path';
const source=readFileSync(new URL('../src/solverSuiteCatalog.ts',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {solverSuiteCatalog:catalog,solverSuiteGroups}=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
let output=`<!-- SPDX-License-Identifier: Apache-2.0 -->
# Integrated solver capabilities

This is a generated index of the development source, not an installed-release qualification statement. Regenerate with \`node app/scripts/generate-solver-integration.mjs\`.

## 1. Find the capability

Open **Solver manager → Capabilities and evidence**, or search the command bar for the capability name. The index contains **${catalog.length} capability scopes** across PI, SI, circuits/SPIKES, thermal/CFD, EM, structural mechanics and execution/coupling. Blocks and install groups describe dependencies; they do not install or qualify solvers.

## 2. Open its exact setup

- Dedicated workflows open their existing setup panel. Propulsion opens the coupled benchmark; multiport fixture removal opens its dedicated SI tool and uses the common guided Run/Tutor checks.
- **Open reviewed runner** stages the named Python template as a new unsaved script. Choose a reviewed request JSON file, inspect requirements, then Run. Merely opening a capability or running an unset template launches no numerical job.
- External engine workflows retain runtime registration, trust, setup and execution admission. A missing requested extension is reported; another extension is not silently substituted.
- **Source/API evidence only** identifies implemented reference code without an admitted desktop runner. Use its documented source workflow. Planned entries have no execution route.

## 3. Review results and limits

The owning workflow retains its existing result viewer, provenance checks and export contracts. Request runners print evidence and can export complete records to a new file; only a matching spike/v1 result can be published to the active design. Typed study records are not mislabeled as generic field results. Main-viewport geometry/field views remain dependent on supported result formats.

Automatic backups and normal project saving retain project-owned states. An unsaved Python script or a result exported outside the project needs its own save. Numerical failure, unavailable runtime and incompatible installed-worker errors remain visible.

## Current integration boundaries

Ten additional guarded runners connect already implemented worker methods: resistor CHT, EM/SPICE coupling, EM body heating, generic PAM3, tetrahedral CHT, PDN electrostatic extraction, dielectric AC, admittance reduction, structural and thermomechanical studies. No numerical kernel, constitutive law, solver tolerance, source authority or validation gate was changed.

Board-volume RT0/full-board production dispatch, the trusted development AMI DLL host, the native CDR reference, arbitrary full-wave/MoM, full-speed actual-air propulsion closure and general reacting flow are not promoted by these links. Source experiments, installed runtime availability, executed transport tests, physical validation and release qualification remain separate.

## Capability map

`;
const clean=value=>String(value).replaceAll('|','/').replaceAll('\n',' ');
for(const group of solverSuiteGroups){output+=`### ${group}\n\n| Capability | State | Destination | Evidence |\n| --- | --- | --- | --- |\n`;for(const item of catalog.filter(row=>row.group===group)){const destination=item.sourceOnly?'Source/API reference':item.templateId?`Python: ${item.templateId}`:item.action?`${item.action}${item.extensionId?` / ${item.extensionId}`:''}`:'Unavailable';output+=`| ${clean(item.title)} (\`${item.id}\`) | ${item.status} | ${clean(destination)} | [Scope and limits](${posix.relative('docs',item.reference)}) |\n`;}output+='\n';}
const target=new URL('../../docs/SOLVER_INTEGRATION.md',import.meta.url);
if(process.argv.includes('--check')){if(readFileSync(target,'utf8').replaceAll('\r\n','\n')!==output)throw Error('Solver integration guide is stale; regenerate it.');}else writeFileSync(target,output);
console.log(`${catalog.length} solver capability destinations documented.`);
