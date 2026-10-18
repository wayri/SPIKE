# ADR 0110: explicit native MCU firmware backend

Status: implemented experimental engineering-preview boundary; not hardware qualification.

SPIKES controller pinout templates remain inert. A separate reviewed Renode
1.17.0 process executes admitted nRF52840 and STM32F407 images. The owned C++
circuit solver is unchanged. Python owns image admission, process supervision,
UI lifecycle and explicit sampled DI/DO coupling; it does not interpret CPU
instructions or reimplement peripheral device physics. No new product language
or Qt dependency is introduced.

ELF32 PT_LOAD file bytes are loaded at validated physical addresses explicitly,
preserving flash LMA versus SRAM VMA for initialized data. Images, runtime and
platform resources are hash-identified. Only exact target descriptors are
admitted; unsupported architectures and accesses fail closed. Firmware import
never executes code. Execution requires hash-specific user approval. stdin/stdout
monitor control opens no TCP server; semihosting is disabled. A separately
installed native runtime retains its original third-party licenses and is not
included in the application's proprietary/Apache ownership claims.

Circuit coupling reuses the existing sampled controller boundary: a voltage
threshold produces DI and DO drives an existing ideal voltage source with a
zero-order hold. This is functional software-in-loop, not physical pad, analog
ADC/DAC, cycle-accurate, high-speed bus or certified hardware-in-loop modeling.
Strict peripheral diagnostics deliberately reject some ordinary SDK firmware.

The user guide, exact scope, examples and recovery rules are in
[Controller firmware](../../standalone/spikes_project/studio/docs/CONTROLLER_FIRMWARE.md).
Verification includes original binary GPIO/UARTE fixtures, ELF split VMA/LMA,
native C++ plant pause/resume/cleanup and GUI trust/lifecycle regressions.
Broader peripheral/SDK/firmware portfolios and clean-machine offline first-use
remain future gates. No claim of manufacturer qualification or endorsement.

Primary interface references reviewed: Renode 1.17.0 CLI help and runtime method
signatures; [headless/console control](https://renode.readthedocs.io/en/latest/basic/running.html),
[monitor interfaces](https://renode.readthedocs.io/en/latest/basic/monitor-syntax.html),
[Nordic nRF52840 GPIO](https://docs.nordicsemi.com/r/bundle/ps_nrf52840/page/gpio.html),
[Nordic UARTE specification](https://docs-be.nordicsemi.com/bundle/nRF52840_PS_v1.8/raw/resource/enus/nRF52840_PS_v1.8.pdf),
and ST RM0090 GPIO register maps. Original fixtures and integration are
independently authored; no upstream implementation source was adapted.
