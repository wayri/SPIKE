<!-- SPDX-License-Identifier: Apache-2.0 -->
# Two-application ASIC foundation: development checkpoint

Date: 2026-10-13. Windows, Python 3.14, actual installed KLayout 0.30.5 at
`C:/Users/yawar/AppData/Roaming/KLayout/klayout_app.exe`.

Executed 23 focused tests, all passed, no skips:

```powershell
$env:SPIKES_TEST_KLAYOUT='C:/Users/yawar/AppData/Roaming/KLayout/klayout_app.exe'
$env:SPIKES_TEST_NGSPICE=(Resolve-Path runtime/external/Spice64/bin/ngspice_con.exe).Path
python -m unittest tests.python.test_spikes_asic_project tests.python.test_spikes_klayout_bridge tests.python.test_spikes_pdk_inventory tests.python.test_spikes_pdk_workflow -v
```

After adding explicit mixed-signal macro-view requirements, the final combined
ASIC/KLayout/PDK and existing CLI regression run passed 62 tests with no skips
or failures. This also included `test_spikes_cli_slice`, `test_spikes_native_cli`
and `test_spikes_smps_cli` against the existing owned native DLL.

Coverage includes actual native hierarchical GDS creation/inspection, 0.001 um
database units, rotated/translated child and top bounding boxes, layer/shape/
hierarchy counts, version and executable/layout/script hashes, original-file
preservation, timeout/malformed-report handling and kill-on-output-overflow.
Geometry limits apply after native `layout.read`; this is not a hard parser
memory bound or hostile-input sandbox.

ASIC project checks cover missing resources, changed hashes, root containment,
CLI project preservation and the distinction between ready-for-review identity
checks and unexecuted/qualified stage results. Existing PDK corner preparation
and actual ngspice execution use original synthetic model fixtures, not a real
foundry IC.

The actual CLI inspected the original geometric demo in
`artifacts/spikes-asic-handoff-20261013.gds` and exported
`artifacts/spikes-asic-handoff-20261013.json`. It contains two cell definitions,
one top, two layers, two directly defined shapes and one hierarchical
occurrence. This is a geometric handoff fixture, not an extracted transistor,
ASIC, PDK-compliant layout or fabrication design. The minimal project's honest
blocked stages are recorded in `artifacts/spikes-asic-preflight-20261013.json`.

Architecture and focused whitespace checks passed. No new engines/PDKs were
downloaded or bundled. No DRC/LVS/PEX rule execution, routed ASIC, technology-
mapped synthesis, static-timing closure or sign-off was established. Native
KLayout inspection remains a separate-process, Qt-free-to-SPIKES interface.
The installed SPIKES application and installers were not updated.
