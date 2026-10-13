# Synthetic co-simulation and recorded twin demo

Run `python examples/cosimulation/run_demo.py` from the repository root.
The replay source and delayed dimensionless gain produce 0,2,4,6 V. A
synthetic telemetry series differs by 0,0.1,-0.3,0 V; its maximum absolute
error is 0.3 V, RMSE is sqrt(0.025) V, and one sample exceeds 0.25 V.
No data here came from hardware. All files are original SPIKE synthetic
fixtures under Apache-2.0. See [workflow and limits](../../docs/COSIMULATION_DIGITAL_TWIN.md).
