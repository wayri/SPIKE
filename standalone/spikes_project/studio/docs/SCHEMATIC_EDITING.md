<!-- SPDX-License-Identifier: Apache-2.0 -->
# Schematic duplication workflow

Select one or more top-level components, then use **Duplicate selection** on the
schematic toolbar or press `Ctrl+Shift+D`. `Ctrl+C` followed by `Ctrl+V` starts
the same preview when components are selected. Move the pointer to position the
preview, press `Space` to rotate it in 90-degree steps, and click to place. The
preview stays active for repeat placement. Press `Escape` to finish; cancelling
before the first click leaves the document and undo history unchanged.

Each click is one validated undo transaction. References are allocated from the
target sheet. Ground remains ground, while other copied node names are remapped
to fresh names. Shared nodes within the selection stay shared, and drawn wires
whose two component endpoints are both selected are copied with the group.
Routes to components outside the selection and explicit junction branches are
left behind so the duplicate cannot silently connect to the original circuit.
A selection that touches an explicit junction route is rejected because
junction-branch cloning is not part of this workflow.

The operation accepts unique top-level source instances and pastes them back
into the same source sheet. This prevents ambient `.param`, `.model`, and
subcircuit definitions in another document from silently changing the copied
device. Hierarchical flattened instances and dependent `F`, `H`, `K`, `W`, or
behavioral-expression records must be edited with their dependencies in the
Circuit text view. Apply pending Circuit text edits before starting placement.

On Windows, copied text is materialized immediately and remains available after
the copying window closes. Clipboard acquisition is bounded; busy or denied
access reports an error without changing the document. The original transport
implementation follows Microsoft's [clipboard ownership requirements](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-openclipboard)
and [memory transfer contract](https://learn.microsoft.com/en-us/windows/win32/dataxchg/clipboard-operations).
The regression sequence includes a modal editor followed by copy/paste, and a
copy followed by closing and reopening the same document in another window.
