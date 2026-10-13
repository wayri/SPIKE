<!-- SPDX-License-Identifier: Apache-2.0 -->
# SMPS analytical studies, not construction-ready power supplies

These independently authored configurations exercise the ideal CCM reference
with few-watt, kilowatt and megawatt operating points, plus an isolated flyback.
They supply model parameters, not a schematic, BOM, controller recommendation,
magnetic design or ratings. No vendor device model or hardware is qualified.

```powershell
python -m python.spikes smps-stability --backend reference --config examples/spikes/smps_stability/buck_5w.json -o buck-study.json
python -m python.spikes smps-stability --backend reference --config examples/spikes/smps_stability/buck_1kw.json -o kilowatt-study.json
python -m python.spikes smps-stability --backend reference --config examples/spikes/smps_stability/buck_1mw.json -o megawatt-study.json
python -m python.spikes smps-stability --backend reference --config examples/spikes/smps_stability/flyback_24w.json -o isolated-study.json
```

At fixed duty the ideal equilibria are respectively 12 V / 5 W, 200 V / 1 kW,
750 V / 1 MW, and 12 V / 24 W. At 1 MW the reference output current is about
1333 A: this demonstrates why numerical power scaling is not component,
interconnect, cooling or insulation qualification. The mathematical CCM and
loop results must be inspected; no example is promoted as a safe design.

Missing JSON fields use the explicitly recorded default configuration, retained
in every result. See `docs/SPIKES_SMPS_STABILITY.md` for equations, definitions,
frequency guidance and exclusions. Human numerical review remains required.
