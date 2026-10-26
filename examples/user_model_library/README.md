# User circuit-model library

`filters.lib` is original Apache-2.0 SPIKE test/example data. It contains a
parameterized RC stage and a second entry that depends on it. It contains no
manufacturer device data and makes no measured or solver-validation claim.

1. Open the circuit workbench and select **Import model**.
2. Choose `filters.lib`, inspect `RC_STAGE` and `TWO_STAGE`, then add one entry.
3. Assign it to an appropriate part, review every physical-pad/circuit-node
   mapping, compose and review the netlist. Select the external ngspice route
   only after checking that runtime and your actual model assumptions.

Adding both entries exercises shared-dependency deduplication. The model
library importer does not start a simulation or infer a model from a footprint.
See the [model and backend guide](../../docs/USER_MODELS_AND_BACKENDS.md).
