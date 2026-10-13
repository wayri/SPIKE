# SPIKES passive manufacturer sources

SPDX-License-Identifier: Apache-2.0

This seed is original SPIKE catalog metadata independently transcribed from official public manufacturer pages. It contains no manufacturer simulation models, equations, tables, or document copies. Access date: 2026-10-12. An ideal nominal record is a placement convenience, not a manufacturer-qualified behavioral model; sourced ratings remain unenforced metadata.

| Manufacturer | Exact records included | Official evidence and transcribed fields |
| --- | --- | --- |
| Panasonic | `ERA3VEB1002V`, `ERA3AEB1020V`, `ERA3AEB203V`, `ERA2AEB103X`, `ERA2AEB102X`, `ERA3AEB2372V` | [Model pages](https://industrial.panasonic.com/ww/products/pt/high-precision-chip-resistors/models/ERA3VEB1002V): resistance, tolerance, power, case size, thin-film family. |
| KYOCERA AVX | `04025C104KAT2A`, `06033C104KAT2A` | [Product search](https://search.kyocera-avx.com/product/04025C104KAT2A): capacitance, tolerance, voltage, X7R dielectric, case size. |
| Samsung Electro-Mechanics | `CL10B104KB8NNNC` | [Product page](https://product.samsungsem.com/mlcc/CL10B104KB8NNN.do): packaged MPN list, capacitance, tolerance, voltage, X7R range, dimensions. |
| Murata | `GCM188R71C334KA37D` | [Reference sheet](https://search.murata.co.jp/Ceramy/image/img/A01X/G101/ENG/GCM188R71C334KA37-01A.pdf): package suffix, capacitance, tolerance, voltage, X7R, 0603 dimensions. |
| Vishay Dale | `CRCW060310K0FKEA`, `CRCW0603100KFKEA` | [Vishay reference-design BOM](https://www.vishay.com/doc/?63395=): exact MPN, resistance, tolerance, voltage and footprint. These records do not claim broader D/CRCW-family coverage. |
| Isabellenhuette | `BVN-Z-R0005-1.0`, `BVN-Z-R001-1.0` | [BVN datasheet](https://www.isabellenhuette.de/fileadmin/Daten/Praezisionswiderstaende/Datenblaetter/BVN.pdf): ordering-code form, values, tolerance, power, 1216 size and four-terminal configuration. Records are deliberately non-executable and name force/sense terminals physically; the source does not assign numbered circuit pins. |
| Coilcraft | `LPS4018-103MRC`, `LPS4018-223MRC` | [LPS4018 official table](https://www.coilcraft.com/en-us/products/power/shielded-inductors/ferrite-drum/lps/lps4018/): exact MPN, inductance, tolerance, maximum DCR and explicitly conditioned current data. |
| Pulse Electronics | `PA4340.103ANLT`, `PA4340.223ANLT` | [PA4340.XXXANLT datasheet](https://productfinder.pulseelectronics.com/api/open/part-attachments/datasheet/PA4340.153ANLT): exact MPN, inductance, tolerance, rated current, maximum DCR and maximum package dimensions. |

## Visible families not represented as executable seed records

- Stackpole: the public family documentation found in this pass did not give a stable official exact-part page with every required record field. The family remains intentionally absent rather than relying on distributor-only metadata.
- Yageo: exact records found in the official RC product search were already present in the bundled base catalog, so this additive seed intentionally does not duplicate them.

The seed is selective. It does not imply complete manufacturer, value, tolerance, package, availability, lifecycle, automotive, or qualification coverage. Recheck the linked current manufacturer document and application derating before adoption.
