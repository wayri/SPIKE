<!-- SPDX-License-Identifier: Apache-2.0 -->
# IRIS PCB drone preparation

[START_HERE.md](START_HERE.md) distinguishes the executed PCB PI/SI/thermal
examples from unsupported integrated flight and rotating-propeller CFD.
The requested 2 x 2 x 1.5 m volume is supplied as original geometry only.

The pinned upstream KiCad/BOM/frame source is staged in
`output/promo-drone-20261023/source`. Run the thermal builder and the analytics
verification commands described in their READMEs, then run:

```powershell
.venv/Scripts/python.exe examples/promo_showcase/drone/package.py
```

That creates the ready project collection and archive with source notices and
byte-hash checks. Native code, firmware and unresolved third-party motor/propeller
models are excluded. No numerical implementation is added by this example.
The whole-drone objective remains blocked by the capability and input gaps in
`flight-scenario.json`, not completed by these independent board studies.
