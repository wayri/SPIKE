# Interface layouts

The [visual UI map](UI_NAVIGATION.md) explains where sections live, how deep
representative menu paths go, and how search bypasses group browsing.

Choose **Clean** or **Classic** in the top bar, or in **Settings > Interface >
Interface layout**. Universal search also finds **Use clean interface** and
**Use classic interface**. The preference survives restart.

| Layout | Command access |
| --- | --- |
| Clean | Compact camera/selection icons, workspace selector, search and contextual soft menus. The legacy command ribbon is unavailable in Clean, including through saved preferences or shortcuts. |
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

Clean reserves two persistent command rows: the main header and one shared row
for editor/assembly tabs and viewport icons. Scoped board controls use that same
row. Camera presets, selection filters, layout switching and adding views open
from icon triggers into accessible contextual popovers. Inspector sections use
consistent padding and gaps; long property values wrap instead of clipping.
