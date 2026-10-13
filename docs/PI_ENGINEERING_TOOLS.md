<!-- SPDX-License-Identifier: Apache-2.0 -->
# PI converter, return and capacitor tools

Open PI setup. Three expandable tools are available below the source and sink
controls. Their numerical work runs in the local worker, with the same read-only
operations exposed through the local MCP server.

1. **Switching converter loss block:** select actual component references on
   the active retained board occurrence, declare the topology and operating
   values, and calculate. The panel shows input/output power, losses, duty,
   ripple and component loss ownership. Its request and admitted result are
   retained in the project PI setup. Changing any input makes the result stale.
2. **Plan explicit return terminals:** choose a return net and exact source/load
   pads. Plan routes through admitted copper. Inspect the returned routes and
   diagnostics, then apply the selection. The load-pad count must match the
   current sinks; selected load order determines sink pairing. Disconnected or
   incomplete copper cannot be applied as a connected result.
3. **Capacitor placement / sampled impedance:** paste a versioned supplied
   multiport Z request with frequency samples, an explicit reference return,
   capacitor models and candidate coordinates. Compare candidates, select a
   map point or table row, and inspect its frequency curve and rating checks.
   The labeled synthetic example demonstrates the interface without claiming
   impedance extraction from the loaded PCB. The admitted request and matching
   result are retained in the project PI setup and shown when the tool reopens.

The capacitor map colors the supplied locations by worst sampled impedance
divided by the target. It does not interpolate an uncomputed board field.
Use load **ripple RMS current** in this request, rather than the rail's DC
current. Candidate ranking covers one added capacitor at a time and separate
single-tone load scenarios. Refine frequency samples around resonances and
compare additional mounting locations before drawing physical conclusions.

At 3.3 V and 1--4 kA, output power is 3.3--13.2 kW. The tools do not infer
busbar, connector, package, capacitor mounting, nonlinear magnetics or thermal
parameters. Supplied voltage and ripple ratings determine capacitor eligibility;
supplied MOSFET and inductor ratings bound the converter estimate. Software
oracles do not establish hardware qualification.

## API and recovery

| Worker method | MCP tool | Inputs |
| --- | --- | --- |
| `run_smps_converter` | `spike_run_smps_converter` | `request` |
| `plan_pi_return_path` | `spike_plan_pi_return_path` | `design`, `request` |
| `evaluate_capacitor_placement` | `spike_evaluate_capacitor_placement` | `request` |

Requests with additional transport fields fail with `PI_ENGINEERING_FIELDS`.
The public transport envelope uses `SPIKE-BE-PI-E-0120`; converter/capacitor
admission failures use `SPIKE-BE-PI-E-0121` and retain the kernel diagnostic.
Kernel admission retains its own coded errors. Missing worker availability
disables execution while preserving editable inputs. Failed recalculation keeps
the previous result and identifies it as stale when its input differs. Saved
converter and capacitor results must include the complete matching request
snapshot; mismatched saved results are discarded while valid inputs remain.

See the [converter derivation](SMPS_CONVERTER_BLOCKS.md),
[return-route contracts](PI_RETURN_PATH_ASSISTANT.md), and
[capacitor comparison derivation](CAPACITOR_PLACEMENT.md) for equations,
conditioning, independent oracles and limits.

Developer checks: run the four Python modules `test_smps_converter`,
`test_capacitor_placement`, `test_pi_return_path` and `test_pi_engineering_worker`
under `tests.python`, plus `npm run test:pi-engineering-tools` from `app`.
`SPIKE_TEST_PYTHON` selects the Python interpreter for the capacitor UI test;
CI uses its configured Python with the installed numerical dependencies.

These tools do not yet execute a switching controller, deposit converter heat
into a thermal solve, or solve distributed electromagnetic transients. Those
capabilities require the queued integrations and their numerical validation.
