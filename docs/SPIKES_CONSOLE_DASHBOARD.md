# SPIKES native console dashboard

`spikes_console` is a compiled, toolkit-independent interactive front end for
the persistent SPIKES C++ transient engine. The same implementation is also
available as the `spikes_dashboard` static library, so a later GUI or embedded
host can reuse the probe, limit, rolling-history, control, and checkpoint
semantics without parsing console output.

This is an engineering-preview interface. `realtime` provides best-effort
wall-clock pacing; it is not a deterministic hard-real-time or physical-HIL
qualification claim.

## Build and start

```powershell
cmake -S . -B build-spikes -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-spikes --target spikes_console spikes_dashboard spikes_c_api
build-spikes\spikes_console.exe --demo
```

Run the checked-in electrothermal example interactively:

```powershell
build-spikes\spikes_console.exe examples\spikes\electrothermal_dashboard.spkc
```

Or run a repeatable command stream:

```powershell
build-spikes\spikes_console.exe examples\spikes\electrothermal_dashboard.spkc `
  --script examples\spikes\dashboard_commands.txt --capacity 256
```

## Interactive commands

- `status` renders every probe with value, engineering unit, limit
  utilization, state, and an ASCII rolling trend.
- `step [count] [dt]` advances persistent native state without rebuilding the
  circuit. `watch count [every]` advances and refreshes the dashboard.
- `realtime seconds [dt]` advances with best-effort wall-clock pacing.
- `set source value` changes a constant independent source.
- `kp-a` toggles the source assigned to control key `a`.
- `attach name node node max`, `voltage element max`, `current element max`,
  or `power element max` adds a live electrical probe.
- `attach name temperature thermal_node ambient_k maximum_k` adds a
  temperature probe. Thermal nodes carry temperature rise; the display adds
  the declared ambient temperature.
- `attach name health element vmax imax pmax thermal_node ambient_k tmax`
  creates a multi-criterion failure-margin probe. Its utilization is the
  largest absolute voltage, current, dissipation, or temperature fraction.
- `detach name`, `history name [count]`, and `savecsv path` manage bounded
  capture. CSV export contains only the rolling samples currently retained.
- `checkpoint` and `restore` preserve and replay electrical, magnetic,
  electrothermal, waveform-clock, and integration history.

At less than 80% utilization a limited probe is `OK`; at 80% to below 100% it
is `WARN`; at or above 100% it is `TRIP`. This reports declared scalar model
limits. Corona, flashover, SOA, insulation geometry, or any other failure mode
is reported only when a qualified model supplies the corresponding observable
and limit; the dashboard never infers those phenomena from a component name.

## Console project format

The bounded `.spkc` format is intentionally smaller than the general SPICE
language. The first non-comment line may be a title. Elements use ordinary
SPICE-like `R`, `C`, `L`, `V`, `I`, and `D` records, plus these native records:

```text
DRRname anode cathode IS N TEMP_K TT_S CJ_F INITIAL_Q_C
RETname p n thermal R0 TC_PER_K TREF_K RTH_K_PER_W CTH_J_PER_K AMBIENT_K VMAX IMAX PMAX TMAX_K
LSATname p n L0_H LSAT_H ISAT_A [I0_A]
```

Dashboard records are:

```text
.tran STEP_S
.control KEY SOURCE LOW HIGH [INITIAL_HIGH]
.probe NAME node NODE MAX_ABS_V
.probe NAME voltage ELEMENT MAX_ABS_V
.probe NAME current ELEMENT MAX_ABS_A
.probe NAME power ELEMENT MAX_W
.probe NAME temperature THERMAL_NODE AMBIENT_K MAX_K
.probe NAME health ELEMENT VMAX IMAX PMAX THERMAL_NODE AMBIENT_K MAX_K
.end
```

Numeric values accept common engineering suffixes. Input size, element,
probe, command, history, and rolling-buffer counts are bounded and invalid or
non-finite values fail closed. See
`examples/spikes/electrothermal_dashboard.spkc` for an executable deck.

## Native embedding

Installable public headers are under `include/spikes`. C++ applications link
`spikes_dashboard` for `ConsoleDashboard` or `spikes_core` for the lower-level
`TransientSession`. C, Python, and other FFI hosts load `spikes_c_api`; its
persistent session exposes source updates, stepping, node and element values,
diagnostics, and owner-bound checkpoints. The Python bridge exposes the same
session as `NativeTransientSession`.

