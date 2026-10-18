# Interface layouts

Choose **Clean** or **Classic** in the top bar, or in **Settings > Interface >
Interface layout**. Universal search also finds **Use clean interface** and
**Use classic interface**. The preference survives restart.

| Layout | Command access |
| --- | --- |
| Clean | Context quick tools, workspace selector, search, and compact soft menus. The Tools control can show the ribbon when needed. |
| Classic | Persistent application menus, all workspace tabs, and the command ribbon. The ribbon can still be collapsed. |

Both layouts share projects, solver inputs, panels, selection and viewports.
Switching layout does not reload the project or start a simulation. Classic
restores dense command access using the current components; it is not a copy
of a historical SPIKE binary.

Graphite and teal control tokens apply to both layouts. Native operating-system
window borders and third-party solver interfaces can use their own styling.
Each solver retains its documented status and limits regardless of layout.

Study dialogs bound their height and scroll internally; action rows wrap at
small widths. A narrow panel must retain reachable actions instead of enlarging
buttons to fill its height.
