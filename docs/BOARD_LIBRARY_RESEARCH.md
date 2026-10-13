# Executable board models and software co-simulation

Research reviewed on 2026-10-10. An executable board model is a useful form of
virtual peripheral or digital twin: software drives named ports, a circuit solver
advances electrical state, and software observes the resulting voltages/currents.
Its fidelity depends on the supplied models, integration method and coupling
schedule. Compiling a schematic does not discover missing device physics, PCB
parasitics, sensor behavior or firmware timing.

## Existing concepts and recent work

| Concept | Relevant evidence | Implication for SPIKES |
| --- | --- | --- |
| FMI co-simulation | [FMI 3.0.2 specification](https://fmi-standard.org/docs/3.0.2/) defines instantiated models, communication steps, optional state rollback and early return. | Use explicit simulation time, instance ownership and restart semantics. A shared library alone is not an FMU or evidence of FMI conformance. |
| Firmware plus virtual peripherals | [Renode HDL integration](https://renode.readthedocs.io/en/latest/advanced/co-simulating-with-an-hdl-simulator.html) supports separately simulated peripherals; [Renode SystemC integration](https://renode.io/news/systemc-co-simulation-in-renode/) maps peripheral transactions into SystemC models. | Separate CPU instruction execution and bus transactions from electrical state. A host C++ HAL example demonstrates the latter boundary without emulating an MCU. |
| Analog/mixed-signal system models | [SystemC AMS overview](https://systemc.org/overview/systemc-ams/) describes system-level analog and mixed-signal modeling. | Choose the abstraction explicitly; system-level behavioral models and transistor-level models provide different accuracy and cost. |
| Cross-tool virtual prototypes | [FMI Meets SystemC](https://arxiv.org/abs/2507.18339), revised October 2025, combines virtual platforms running software with external models through FMI. | Future adapters can reuse the board boundary while keeping software execution in a virtual platform. The paper's sensor case does not qualify arbitrary board physics. |
| TLM and FMI synchronization | [Integrating SystemC TLM into FMI 3.0 Co-Simulations](https://arxiv.org/abs/2508.20223), August 2025, studies transaction payload mapping, wrappers and synchronized execution. | Future bus adapters need declared transaction direction, ownership and time semantics; wrapping a DLL is insufficient. |
| Networked virtual ECUs | [FMI layered network standard](https://fmi-standard.org/fmi-ls-bus/1.0.0/) and [2025 ECU development study](https://ecp.ep.liu.se/index.php/modelica/article/view/1356) describe clocked network models and protocol abstractions. | Treat CAN/I2C/SPI/network adapters as separate protocol contracts rather than silently translating them into voltage pins. |
| Coupling error estimation | [Energy conservation and power bonds in co-simulations](https://arxiv.org/abs/1602.06434) estimates interface errors using exchanged power variables. | Voltage/current ports could support future power residual diagnostics and adaptive coupling. This increment does not implement or validate those algorithms. |

These are primary specifications, project documentation and research papers.
Research informs interface choices; no third-party implementation, generated
wrapper or paper code has been copied into this increment.

## Implemented boundary

The [compiled board library](COMPILED_BOARD_LIBRARY.md) exports an internal-engine
circuit snapshot as a board-specific native shared library, a C ABI, a C++ object
header and provenance metadata. Python supplies compilation/orchestration and an
explicit loader. The native numerical engine owns persistent electrical state.
Each object has independent state, declared input voltage bounds and source
resistance, named outputs, bounded time advancement and save/restore/reset.

Firmware drives a voltage held constant until the next drive operation. A step
then solves the declared network and returns observations at its end. The DAQ
example samples an RC network, detects a sampled threshold crossing and converts
the voltage to a 12-bit ADC code in the host firmware layer. ADC conversion timing,
quantization, comparator hysteresis, interrupts and MCU execution belong to that
layer or to explicit additional models. The sampled threshold time is bounded by
the chosen step; it is not an exact continuous event location.

The first exporter admits a bounded RLC network with constant independent
sources. It rejects unsupported elements instead of substituting ideal devices.
This intentionally narrows the compiler below the broader internal engine: every
new exported device requires persistent-state and restart evidence. It cannot
yet compile an arbitrary populated acquisition card with op-amps, converters,
digital buses and firmware into a fully faithful hardware replacement.

## Extension order

1. Extend board device admission with explicit model parameters and numerical
   reference/restart checks, then integrate reviewed Studio export workflows.
2. Add scheduled digital events and threshold refinement with rollback, declared
   detection bounds and transactional observations. Repeated crossings within a
   macro step must have an explicit policy.
3. Add a firmware emulator/HAL adapter with an agreed clock and peripheral
   protocol; qualify instruction timing separately from circuit accuracy.
4. Implement and validate FMI packaging and state capabilities against the
   specification and an independent importer before claiming FMI support.
5. Add external-engine adapters for ngspice/Xyce/LTspice/QSPICE only after checking
   their actual runtime APIs, redistribution terms and persistent stepping/state
   capabilities. No engine equivalence is assumed.

Connecting two arbitrary board objects through prescribed voltages is not an
acausal circuit composition algorithm. Shared electrical networks should first
be assembled in one solver, or coupled through a validated iterative master with
effort/flow consistency, convergence and energy/error checks. Wall-clock speed,
hardware correlation and complete ngspice parity remain separate qualification
tasks.
