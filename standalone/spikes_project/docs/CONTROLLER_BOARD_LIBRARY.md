# Controller board library

Open **Libraries → Controller board library** (also available in the Controller
panel). Search by board, MCU, manufacturer or pin label. Select a board to inspect
its labeled symbol, connector coverage, revision and official source references.
Choose **Place labeled block**, then click the schematic. Drag the block to move
it; double-click to edit its pin bindings. Placement and movement are undoable.
Saved projects retain a complete pinout snapshot rather than silently adopting
future catalog changes.

## Included templates

| Family | Boards | Connector coverage |
| --- | --- | --- |
| Arduino | UNO R3, Mega 2560 R3, classic Nano, Leonardo, Micro, Nano 33 BLE | Declared board headers; see per-board exclusions |
| STM32 | NUCLEO-F401RE | Arduino and Morpho CN7/CN10 |
| STM32 | NUCLEO-F446RE | Arduino CN5/CN6/CN8/CN9 only |
| STM32 | STM32F407G-DISC1 MB997 | P1/P2 expansion headers |
| Espressif | ESP32 DevKitC V4 WROOM-32E, ESP32-S3 DevKitC-1 v1.1, ESP32-C3-DevKitM-1, ESP32-C6-DevKitC-1 v1.2 | Declared external headers |
| Nordic | nRF52840 DK PCA10056 | Arduino signal headers P2/P3/P4 only; power/auxiliary headers excluded |
| Nordic | nRF5340 DK PCA10095 | P24 only; other headers excluded |
| Raspberry Pi | Pico, Pico W | Declared external headers |

These seventeen sourced templates are an initial library, **not complete manufacturer
portfolios**. The preview is a readable logical block, not a physical connector
layout. Each pin includes its connector position, label, role and aliases.

## Sampled C/C++ control

Pins start **NC**. Placement never silently connects power or creates circuit
nets. In **Pins & sampled bindings**, select AI/DI to read an existing node relative
to another node, or AO/DO to drive an existing independent DC voltage source.
Only declared I/O directions are offered; ESP32 input-only pins cannot drive.
Power, reset and debug pins are visual metadata, not electrical models.

For a placed block, **Load C/C++ sampled adapter** prepares the existing controller
editor with stable pin identifiers. Review the code, explicitly approve trust,
compile and enable coupling using the Controller panel. The sample interval must
be compatible with the transient run. Only one compiled adapter is active per run.
Changing a linked pin map detaches it and retains the previous code as an inert
draft; review and compile again before execution.

This is **not firmware, CPU, peripheral, ADC, SPI, RF or binary emulation**. An
Arduino sketch or MCU `.bin` cannot be uploaded to these blocks. Timing is the
generic sampled controller contract, not hardware instruction timing. Compiled
callbacks require explicit trust and are not a hostile-code security sandbox.

A separate native Renode manager now runs admitted binaries on three exact
Cortex-M targets. It is not the sampled C/C++ callback path described above.
See [native firmware workflow and limitations](../studio/docs/CONTROLLER_FIRMWARE.md).

The browser can export a pinout as `.spkboard`; project persistence includes all
pins and bindings. Standalone `.spkboard` import and custom board GUI authoring are
not yet implemented.
