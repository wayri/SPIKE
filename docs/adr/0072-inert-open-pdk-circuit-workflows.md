<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0072: Explicit open-PDK circuit preparation and backend routing

Status: implemented experimental foundation; real PDK qualification pending.

Decision: separate inert PDK discovery from compact-model execution. Default
profiles identify installed SKY130, GF180MCU and IHP SG13G2 model entries. The
inventory exposes pin/parameter declarations, sections, licences and file hashes
without importing executable code. Selected-corner textual expansion is bounded
and root-contained; external commands and dynamic model loading remain rejected.

The workflow prepares self-contained decks for the existing explicitly selected
ngspice C backend. Exact run-digest approval precedes execution. No native SPIKES
parity is assumed for BSIM/PSP/VBIC, and no unsupported device is approximated.
Device mathematics remain compiled; Python owns contracts and orchestration.

Consequences: PDK libraries are local separately installed dependencies, not
redistributed bundles or production-qualified models. Synthetic tests exercise
the full adapter lifecycle, but each real PDK revision still needs device/corner
qualification. OSDI loading, native PDK GUI, layout/DRC/LVS/extraction and TCAD
remain separate capability gates. See SPIKES_OPEN_PDK_WORKFLOW.md.
