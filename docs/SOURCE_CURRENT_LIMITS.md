# Source current capacity in DC PI

## Desktop workflow

1. Open PI setup and choose DC resistive-network analysis.
2. Add and anchor each voltage source and current sink to the intended copper.
3. In the source card or table, enter **Current limit (A)**, for example `0.5`
   or `500m` for 500 mA. Leave it blank for an unlimited source.
4. Run preflight and analysis. Source capacity lists each source's demand,
   limit and headroom. Negative headroom means the requested sinks exceed
   that source's capacity. The failed run's capacity table remains in setup.
5. Reduce sink demand or revise the reviewed supply rating and rerun. Successful
   saved results retain the table in the PI result viewer.

Source limits are retained with the PI setup in project snapshots. Current
limits are source ratings; sink rows continue to specify demanded current.

Set a source terminal's optional `current_limit_a` to a finite positive number
in amperes. Omit the key for the existing unlimited ideal voltage boundary.
Zero, negative, null, boolean, string, NaN and infinity are invalid. The DC
resistive-network solver declares `source_current_feasibility`; preflight and
the solver registry reject limits for engines/modes lacking that capability.
The native FEM/PEEC and circuit adapters do not gain a current-limit model.

This is capacity feasibility at the requested regulated voltage. Loads remain
prescribed signed current sinks. An exceeded limit fails the analysis and
withholds voltage, density, loss and visualization fields. It does not clamp
loads, fabricate a lower-voltage operating point, or model CV/CC, foldback,
startup, protection, current sharing control, or load undervoltage behavior.
A feasible result retains the underlying solver's approximate model status.

## Derivation and validity

For each source boundary node, Kirchhoff's current law gives
`I_source = sum(I_outgoing_branch) - I_external_injection`, in amperes.
The solver sums signed solved branch currents, including contact branches and
loads attached directly to the source node. It uses voltage offsets in branch
currents, avoiding cancellation from large absolute source voltages. Source
current is the sum over that source's boundary nodes. It is never total load
demand assigned to every source or domain. Two sources with equal voltage and
1 and 3 ohm contacts feeding a total 1 A therefore supply 0.75 and 0.25 A.

Separate resistive contacts determine sharing. Overlapping ideal source
boundary nodes do not determine individual source currents; a limited source
with any such overlap is unsupported. Reverse current is also unsupported for
a limited source because a forward capacity specifies no absorption rating.
Return terminals invert the signed boundary current for the forward check.
Comparison tolerance is `1e-9 * max(1 A, abs(forward current), limit)`; this
allows solver roundoff at the limit, not engineering operating margin. Extreme
conductance ratios retain the base solver's conditioning and convergence
limitations; capacity is not an independent solver qualification.

Derivation and fixtures are original SPIKE work from circuit conservation,
without external implementation material. No nonlinear model or convergence
claim has been introduced. Knowledgeable numerical review is required before
release under CONTRIBUTING.md.

## Result and recovery contract

`summary.source_capacity_status` is `not_requested`, `feasible`, `infeasible`,
or `unsupported`. `fields.source_current_results` holds one row per source:
`id`, `domain_id`, `role`, signed `required_current_a`, `forward_current_a`,
`current_limit_a`, `headroom_a`, `status` and `current_allocation`. Null currents
mean indeterminate sharing; null limit/headroom means unlimited. Row status is
`unlimited`, `within_limit`, `exceeded`, `indeterminate`, or
`reverse_flow_unsupported`. The failed result retains these diagnostic rows;
they describe the requested ideal-voltage solve, not a feasible limited supply
operating point. Negative headroom indicates insufficient capacity.

| Code | Recovery |
| --- | --- |
| `SPIKE-BE-PI-E-0110` | Enter a finite positive limit or omit it. |
| `SPIKE-BE-PI-E-0111` | Select DC resistive-network analysis; unsupported modes cannot ignore limits. |
| `SPIKE-BE-PI-E-0112` | Reduce sink demand or increase reviewed source capacity. |
| `SPIKE-BE-PI-E-0113` | Provide distinct resistive contacts for source sharing, or a qualified reverse-flow model. |

Run `python -m unittest tests.python.test_source_current_limits
tests.python.test_hybrid_dc_terminal_validation -v` for independent analytic
two-sink below/at/above-capacity checks, current sharing, reverse flow, direct
source-node loading, unlimited compatibility, malformed values and unsupported
engine/mode admission. Exact terminal evidence enumerates source-to-load
voltage references for each matching source; it does not infer current paths
or attribute all sink current to a particular source.
