# Inter-board openEMS spatial E/H capture

`run_interboard_field_capture.py` runs one actual openEMS excitation of the
same original two-board box fixture used by `scripts/run_crossboard_openems.py`.
It records co-located cell-centre electric and magnetic phasors at 0.5, 1.5,
and 2.5 GHz for the `A.near` lumped port.

The default result is `actual_capture/field-samples.json`. Positions are stored
as SI-metre Cartesian axes; each frequency frame contains flattened complex
`x,y,z` vectors suitable for an offline 3D viewer or nearest-sample probe.
`simulation/*.h5` remains the authoritative native solver output.

Run with the ordinary SPIKE development environment, which launches the
configured openEMS runtime through the same isolated process adapter as other
external-engine examples:

```powershell
.venv\Scripts\python.exe `
  examples\high_speed_si\field\run_interboard_field_capture.py --timeout 300
```

The case spans 0.2 to 3 GHz excitation bandwidth and is unvalidated. It does
not qualify Ethernet, LVDS, SerDes, a cable/harness, or 10/100G operation.
