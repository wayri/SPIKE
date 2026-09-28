# OpenEMS Suite extension

This bundled SPIKE extension provides two optional full-wave workflows:
high-frequency PI port sweeps and SI interconnect port sweeps. The engine,
CSXCAD adapter, case integrity checks, validation, benchmark fixture, and
reference evidence live in this package. SPIKE's former `python/spike_core`
module names remain import bridges for existing CLI and desktop requests.

Open **Extension manager** and select **OpenEMS Suite**. Enter JSON options for
one of the contributions, for example:

```json
{
  "operation": "preflight",
  "analysis": {
    "net_names": ["SIGNAL", "GND"],
    "frequency_start_hz": 1000000,
    "frequency_stop_hz": 1000000000,
    "frequency_points": 101,
    "options": {"ports": []}
  },
  "engine_options": {"mesh_resolution_mm": 0.5}
}
```

`preflight` reports geometry, material, resource, and port readiness. `prepare`
creates an authenticated private case for inspection. `run` prepares a new case
and executes the installed OpenEMS/CSXCAD Python runtime if all gates pass.
Full execution needs explicit lumped ports with exactly one excited port. A
prepared case and result retain the adapter's artifact and version provenance.
The existing `spike openems-run` CLI command can run a previously prepared
case. Optional runtime installation is separate; the extension does not
download or bundle OpenEMS.

Undrilled rectangular, circular, oval, and rounded rectangular surface pads
are translated; curved contours are faceted and identified as approximate.
Drilled pads, via padstacks, zones without verified filled copper, and copper
cutouts block a field solve until their topology can be preserved. Imported
boards also need a physical stackup and reviewed signal/return port locations.

The PI contribution is for high-frequency PDN behavior, not DC voltage drop.
SI results are single-excitation S-parameters; a full matrix requires one run
per excited port. Arbitrary PCB results are unvalidated until independent
convergence and correlation evidence is supplied. OpenEMS has no thermal solver
in this suite. Its electromagnetic results are not converted into heat sources.

The host renders this package's menu and title bar. Both can be toggled from
the Extension manager and the preference persists locally.
