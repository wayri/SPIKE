# Power symbols and battery reference laboratory

Source increment, 2026-10-12. No installed executable or installer update.

## Schematic power markers

The designer palette has a **Power / grounds** group. Double-click a tool or
drag it onto an existing component terminal. Reference ground binds SPICE node
`0`; if the terminal has another net, the existing guarded net-merge workflow
joins that net to an existing node-0 terminal. Invalid shorts, unsupported
hierarchical/node-expression rewrites and controller-bound merges fail without
partially changing the circuit. If no node 0 exists, define it in circuit text.

Signal, chassis and protective-earth symbols retain the attached terminal's
existing named net. They do not automatically short unrelated grounds together.
A power flag marks a terminal; it is not a voltage source or an implemented ERC
power-driver exemption. Markers follow their semantic component/pin anchor,
persist, and participate in undo/redo. Right-click a marker to remove it.
Free-standing unconnected one-pin symbol placement is not implemented.

## Battery studies

Select **Battery laboratory** in the workspace selector. This is a prescribed-
current Python reference study, not a native circuit-connected battery device.
The editable model includes OCV versus SOC, R0 plus one RC polarization state,
coulombic efficiencies, lumped thermal capacity/resistance, optional temperature
coefficients, self-discharge and explicit empirical calendar/cycle aging.
All chemistry templates deliberately contain synthetic illustrative parameters.
Changing the chemistry label does not fit a physical cell.

Set initial SOC/temperature, ambient temperature, duration/current and internal
step limit. Positive current discharges; negative current charges a model
declared rechargeable. Primary templates reject charging. A CSV profile must
have headers `time_s,current_a`; each current is held until the next timestamp,
and the final timestamp ends the run. JSON model import/export does not execute
code. Result export retains inputs, state, units, evidence note and limitations.
Last-run configuration persists in project metadata. Results remain separate
from native circuit runs and are not dashboard channels.

See [equations, units, domain checks and numerical evidence](SPIKES_BATTERY_MODEL.md).
Tests cover charge counting, RC recovery, thermal response, empirical degradation,
energy accounting within the reduced model, invalid domains and bounded execution.
No full chemical-energy balance, runaway/abuse, plating, pack balancing, BMS,
electrochemistry or remaining-life qualification is claimed.

## Market-cell evidence

The expandable browser has 21 exact parts from Energizer, Duracell, Panasonic,
Murata, Saft, Molicel and Yuasa. Search manufacturer/MPN/chemistry/form factor.
Records include official source URLs, nominal voltage, rechargeability and only
explicitly sourced capacity with test conditions. Missing OCV, impedance,
thermal and aging evidence is retained. Selecting a record never silently
assigns synthetic parameters as a manufacturer model. Manufacturer-grade fitted
models and medical/aerospace/automotive certification remain outstanding.

Real GUI captures and executed assertions are in
`artifacts/studio-battery-power-20261012/`. They exercise a synthetic configured
study and analytical aging-aware SOC, not a commercial cell discharge test.
