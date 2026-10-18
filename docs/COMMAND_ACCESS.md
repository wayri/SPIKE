# Command and panel access

Use **Menu > All actions** to browse a flat list instead of traversing submenus.
The same menu search searches nested command paths. The Menu and viewport View
buttons open a bounded popup over the canvas; they do not collapse the viewport.

**Ctrl+K** searches the application menus, workspace commands, solver capability
index, board objects and sentence-based setup requests. It also indexes labelled
buttons, fields and individual select choices in currently rendered controls.
This includes retained hidden panel drafts and linked floating panel documents.
Choosing a field reveals its panel and focuses the real editable control. Choosing
a select choice dispatches the normal change event. Buttons use their existing
handlers and admission checks; typing and indexing never execute an action.
Disabled options remain disabled, and stale detached controls require refreshing
search. Values, passwords and field contents are not added as search keywords.

Conditional controls must first be rendered by opening their workflow or tab;
its opening commands remain searchable. Search cannot index external solver
application controls or controls without an accessible label. This is not a
claim that every conditional action in the source has a registered command.

The viewport's **Selection filter** directly chooses all objects, parts or nets.
The separate **View** button opens navigation and display tools. Tool panels have
Expand/Restore, Hide and Detach icons. The visible grip sits on the canvas/panel
boundary; drag or use arrows to resize, Home/End for limits, and double-click to
reset. Drafts remain mounted when hidden. Dock widths are bounded to 280–720 px
and the viewport width; embedded forms scroll within their panel.

Implementation: `focusCommands.ts`, `liveControlSearch.ts`, `UniversalSearch.tsx`,
`FocusCommandPanel.tsx`, `FocusToolDeck.tsx` and the shared App workspace shell.
