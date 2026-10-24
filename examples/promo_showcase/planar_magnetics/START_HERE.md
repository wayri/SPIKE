<!-- SPDX-License-Identifier: Apache-2.0 -->
# PCB inductors, stacked planar transformer and 48 V → 1.8 V / 50 W study

This collection contains four original native KiCad projects, native SPIKE
assemblies, a full transformer STEP with pins, a Studio converter simulation,
actual air-core PEEC extraction and two core-only temperature transients.
The target is 50 W at 1.8 V (27.78 A), following the requested operating point.
It is a simulation/geometry demonstrator, not a qualified CPU supply.

**The requested full 3D electromagnetic → loss → temperature → converter
feedback simulation is not implemented by this pack.** SPIKE's current magnetic
FEM workflow is planar and does not solve these STEP/PCB windings as a coupled
nonlinear 3D transformer. Native SPIKES lacks K-coupled inductors; this converter
uses supported ideal source equations plus a linear magnetizing inductance.
No synthetic magnetic field or inferred ferrite temperature fills that gap.

## Open in this order

| Project | What to demonstrate |
| --- | --- |
| `KiCad/windings/aircore_inductor/aircore_inductor.kicad_pro` | Actual four-turn copper spiral, back-layer return, pads, stackup and schematic equivalent |
| `KiCad/windings/primary/primary.kicad_pro` | Four-layer, eight-effective-turn primary PCB and core-leg slots |
| `KiCad/windings/secondary/secondary.kicad_pro` | Separate four-layer parallel one-turn secondary and two 16-pin banks |
| `KiCad/converter/carrier.kicad_pro` | Routed bridge/rectifier/LC carrier, empty transformer mounting cutout and custom T1 footprint carrying the full local STEP |
| `SPIKE/stacked-planar-transformer.spike` | Separate winding boards, retained core/pin STEP parts and assigned material evidence |
| `SPIKE/converter-and-stacked-transformer.spike` | Carrier plus both winding boards; all 34 physical terminal mates checked and saved |
| `SPIKE/pcb-aircore-inductor.spike` | Actual spiral source; run the supplied Python PEEC template on it |
| `Studio/converter.spksch` | Executable ideal converter circuit, saved probes and dashboard scopes |
| `SPIKE/core-supplied-1w.spike` and `core-reference-supplied-2p6w.spike` | Actual core-only solid-thermal transients, each with 25 saved frames |

The winding schematic L1 is excluded from board population and represents the
routed conductor. These diagrams are not directly synchronized pad-net designs:
each physical PCB winding is one continuous net. Do not Update PCB from the
equivalent schematic without reviewing that boundary. The converter carrier is
a separate conventional schematic/board pair with native parity checked.

## The real core and its properties

Use **two** TDK **B66287G0000X197** ELP32/6/20 N97 halves, an EELP32 pair.
DigiKey listing: https://www.digikey.com/en/products/detail/tdk/B66287G0000X197/3914613 .
This is a listed purchase candidate; no stock or delivery guarantee is inferred.
Supplier sources and review hashes are in `core/source-manifest.json`.

The original simplified STEP follows nominal drawing dimensions, not an official
supplier CAD model. The full module includes both actual exported PCB/copper
geometries and 34 original square Berg-style pin solids. Import/readback and
core-versus-PCB collision checks passed; tolerances, assembly retention, solder,
inter-board insulation and pin ampacity are not qualified. The 0.2 mm gap is
empty geometric space, not a modelled insulating film or an isolation rating.

Magnetic facts include AL=5700 nH/turn² ±25%, Ae=130 mm² and N97 properties with
their stated test conditions. Effective set permeability and material initial
permeability are kept distinct. The project stores a validated material snapshot
on the core occurrence; use MCAD assembly > Material library to inspect it.
Assignment is inert evidence and does not automatically activate a magnetic law.

N97-specific thermal conductivity, heat capacity, Young modulus and Poisson
ratio are not supplied by the reviewed N97 datasheet. A separate explicitly
estimated material selects generic TDK ferrite E=150 GPa, k=5.5 W/(m K),
cp=700 J/(kg K), and CTE=8.5e-6/K; density is N97's typical 4850 kg/m³.
Poisson ratio remains unknown, so a complete structural solve is not admitted.
There is no invented B-H table, hysteresis/Steinmetz fit or saturation curve.

## Executed electrical results

Open Studio with the owned native library described in `KiCad/converter/README.md`.
Run the saved converter and inspect output, ripple and currents. With a
64.8 mΩ resistive load and a 50 ns step, the ideal fixed-duty model gives:

- Mean output **1.800051 V**, current **27.77857 A**, power **50.00289 W**.
- Output ripple **6.706 mV peak-to-peak** over the stated final measurement window.
- A 100 ns comparison and independent discrete energy/power audits are retained.

These are actual native circuit outputs under ideal assumptions. The PWM is
prescribed, duty is tuned for this load, transformer and rectifier are ideal,
and capacitance is 1000 µF with zero ESR. The model is **not feedback-regulated**
and contains no CPU load transients, actual gate drivers, switching devices,
core loss, thermal feedback or leakage/copper-loss extraction. The KiCad bridge
contains generic device placeholders. Its 0.5 mm routed tracks are geometric
examples, not a 27.8 A power layout or a fabrication-ready converter.

The air-core template `Python/02_aircore_peec_gui.py` runs registered native
PEEC on actual spiral copper, with F.Cu entry and B.Cu exit surface contacts.
Open its native board, Tools > Python workspace, then Run. At 3 mm mesh the
partial inductance is 425.90 nH and R at 1 kHz is 0.15885 Ω; at 1.5 mm it is
428.58 nH with unchanged R. This is a port-referred **partial** inductance, not
a closed external-loop or ferrite-core inductance. Capacitance is omitted and
proximity effect is unsupported. Two levels are not general convergence proof.

The first all-front contact attempt failed because the native mesher disconnected
the unused top pad annulus from the back-layer return; exact evidence is retained.
The final ports explicitly address the actual connected copper surfaces, not a
qualified through-pin terminal. Python result-overlay publication also rejected
the native result's missing host binding; the final template publishes a table
and retains the unchanged raw result rather than bypass that gate. The separate
eight-turn primary air-winding PEEC attempt failed inductance-passivity admission;
its failure is retained and no primary extraction is claimed as complete.

## Core temperature demos

Open either core thermal native project and its Assembly volume field study;
inspect the exact request and scrub 0–120 s frames. At 120 s, the supplied 1 W
case reaches about **30.60°C**, and supplied 2.6 W reaches **39.55°C** with the
documented generic material estimates and prescribed convection/contact.
These are real thermal solves with independently checked energy/storage/scaling.

The heat is imposed, **not calculated from the converter**. The 2.6 W value is
only a reference load matching a datasheet set-loss ceiling at 200 mT, 100 kHz,
100°C; the demo's evolving temperature/excitation does not satisfy that condition.
Do not label these frames as predicted operating core temperatures at 50 W.

## Checks, sharing and replay

KiCad 10.0.6 checks: all four projects have zero reported ERC/DRC violations and
zero unconnected PCB items. Carrier schematic parity is zero; winding-equivalent
parity is deliberately not claimed. Installed default ignored-check categories
are retained in the reports; no new finding exclusions were added. Actual native
renders were reviewed. Source hashes, geometry/linkage tests, STEP readback,
material admission, explicit mates and numerical results are in EVIDENCE.

All original scripts/designs/CAD are Apache-2.0 with their notices. Standard
KiCad library references retain their upstream terms; stock header models are
not bundled in the full module. Supplier PDFs/images are excluded from the ZIP
because their reproduction rights are not granted. Facts have source URLs,
conditions and hashes. No upstream endorsement or compliance claim is implied.

Use these as separate labelled takes for a promo: native copper → stacked
assembly/material evidence → ideal converter ripple → supplied-heat core
transient. Do not present that edit as a synchronized full multiphysics solve.
No desktop recording was performed during preparation.
