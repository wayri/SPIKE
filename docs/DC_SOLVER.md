# Copper Geometry DC Solver

`spike-hybrid-dc/v4` solves a sparse linear resistive network made from
imported tracks, vias, pads, and polygonal copper zones. It accepts multiple
explicit voltage sources and current loads and produces node voltages,
per-edge current, current density, voltage drop, and the zone mesh.

The solver can also solve an explicit supply/return loop. Supply sinks are
paired with equal return-current injections, while source-positive and
source-return terminals establish the differential source voltage. Supply
drop, return rise, and end-to-end loop drop are reported separately.

## Scope

The solver includes uniform copper conductivity, extracted track and pad
dimensions, copper thickness, via and through-pad barrel resistance,
finite-volume zone current spreading, and explicitly assigned package/contact
resistance. It remains `approximate` until zone mesh convergence is established.
Thermal conductivity changes and unassigned package values are not inferred.

## Command-line run

```text
python -m python.spike_cli --output result.json analyze-dc design.kicad_pcb \
  --net Net_14 \
  --source 165.1,116.3,B.Cu,24,0.002,0.008 \
  --load 149.05,116.3,B.Cu,1 \
  --max-drop-mv 50 \
  --zone-cell-mm 0.5
```

Terminal syntax is `X,Y,LAYER,VALUE[,CONTACT_R[,PACKAGE_R]]`; source value is
volts and load value is amps. Sources, loads, and nets are repeatable.

An explicit return path can be configured from the CLI:

```text
python -m python.spike_cli analyze-dc isolated-board.kicad_pcb \
  --net VCC_ISO --source 10,20,F.Cu,5 --load 80,20,F.Cu,1 \
  --return-net GND_ISO --return-source 10,25,B.Cu,0 \
  --return-load 80,25,B.Cu,1 \
  --return-mode isolated_secondary --domain-id secondary-1
```

`--return-load` is repeated once per `--load`; its current value is replaced
by the equal and opposite paired load current. In `isolated_secondary` mode,
the return terminal is the secondary domain's local numerical reference. It
does not create a galvanic connection to primary ground.

## Transformer boundary limits

The isolated-secondary option is a DC source boundary for secondary-side
copper analysis. It does not model transformer leakage or magnetizing
inductance, saturation, regulation, core/copper loss, isolation breakdown, or
interwinding capacitance. Those effects require a coupled SPICE, PEEC, or
full-wave transformer model and remain capability-gated.

## Validity gate

Reports must always show `Approximate` until the solver passes the permanent
validation corpus against analytical resistor networks, trusted reference
tools, and measured board fixtures. The current e-brake smoke result is a
regression check only, not an accuracy certification.
