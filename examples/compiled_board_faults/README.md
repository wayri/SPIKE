# Compiled-board fault example

This original Apache-2.0 fixture demonstrates only explicit circuit
approximations: finite gate-source and drain-source shunt resistors and an NMOS
Level-1 threshold change. It does not infer damage physics or claim that these
parameters reproduce a particular damaged component.

From a C++ developer environment, build a fresh package and run both actual
consumers:

```powershell
python -m examples.compiled_board_faults.build_and_run `
  --engine build-spikes-faults-20261010/Release/spikes_c_api.dll `
  --output build/compiled-board-fault-demo
```

The C++ consumer checks normal, 0.01 ohm gate-source shunt, 0.01 ohm
drain-source/body-diode shunt, 10 ohm degraded drain-source path, 6 V threshold,
object isolation, and checkpoint replay. The Python consumer compares every
scenario with a separately constructed native internal session at `1e-10 V`.

Compare the same five static scenarios against an installed ngspice executable:

```powershell
python -m examples.compiled_board_faults.qualify_ngspice `
  --engine build-spikes-faults-20261010/Release/spikes_c_api.dll `
  --ngspice runtime/external/Spice64/bin/ngspice_con.exe `
  --manifest build/compiled-board-fault-demo/fault_board/manifest.json `
  --output build/spice-fault-checks/fault-ngspice46.json
```

This records both executable hashes, exact reference decks and a 1 microvolt
absolute tolerance. It covers this static fixture, not transient fault timing,
arbitrary damage physics or whole-engine parity.
