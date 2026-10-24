# EBrake PCB thermal projects

Original SPIKE board and example setup, Apache-2.0. The owner's redistribution authorization is recorded in `docs/DEMO_BOARD_PROVENANCE.md`. No third-party component-model binaries are copied by this builder.

Run `.venv/Scripts/python.exe examples/promo_showcase/boards/build.py` from the repository root. It prepares two real native `.spike` packages under `output/promo-showcase-20261023/boards/`, with exact embedded source, explicit inputs, solver results and 16 actual saved transient board frames over 600 seconds. Completed unchanged results from a previous builder invocation are reused only when the exact saved request matches; source hash admission is checked on each invocation.

Open `01-ebrake-transient.spike` in SPIKE. In Thermal workspace, open the layered board thermal panel. Saved request and result are already present. Inspect Board and materials, Heat and contacts, Grid and time, then Review and run. The transient settings use assumed copper/dielectric volumetric capacities, constant Q1/Q2/Q3 loads of 1/0.8/0.6 W and ambient 25 C. Choose Run to rerun, and Play or the frame slider to show saved board temperatures. Colors use a fixed history scale. Part case/junction values remain steady-state estimates, not package transients.

`02-ebrake-transient-virtual-sink.spike` adds the existing explicitly supplied mathematical heatsink boundary. It is a comparison with the same board, grid, loads and time settings: peak board temperature at the end of the saved history is 49.280 C without the sink versus 43.698 C with it. This boundary is not a meshed case or fin/airflow solve. The separate thermal_flow case projects contain actual hollow solid geometry and explicit board/case contact.

Board material conductivities, heat capacities, component losses and thermal resistances are hypothetical illustration inputs, not a measured EBrake operating condition. Layer/copper sampling remains approximate. No mesh/time convergence study was executed for these particular promo inputs. The source board is authentic; a visible package model does not establish package thermal volume participation.

The builder checks completed solver status, multiple actual frames, identical saved/reopened request/result/source and cooling direction. The pack integrator additionally checks steady and step heat-balance errors and frame times. All results remain approximate/not production qualified. No desktop interaction was performed by the builder.
