# Application menus

Commands are grouped by task under File, Edit, View, Analysis, Reports,
Project, Tools, Extensions and Help. Common File commands remain directly
available; imports, saved results and export actions have separate submenus.
Existing command callbacks and project/result admission rules are preserved.

## Keyboard and dismissal

Use Alt plus F, E, V, A, R, P, T, X or H to select the corresponding menu.
Alt alone or F10 focuses the menu bar. Use left/right arrows between top
menus, up/down within a menu, and Home/End for the first/last enabled item.
Right enters a submenu; Left returns. Enter or Space activates the focused
command. Escape closes the current level and restores its trigger.
Tab leaves the menu; clicking outside dismisses it without stealing focus.
Menus also close when focus leaves or the application loses focus.

Global menu shortcuts yield to text editors, IME composition, AltGraph and
modal dialogs. Ctrl shortcuts continue to use the existing application
command handlers. Pointer users can click or hover between open menus.

## Ownership and checks

`app/src/ApplicationMenu.tsx` owns interaction and accessibility semantics;
its scoped CSS owns popup placement. `App.tsx` owns command grouping and
callbacks. Run `npm run test:application-menu`, editable shortcut checks,
TypeScript, the shared button standard and the production build.

The interaction follows the
[WAI-ARIA menu bar pattern](https://www.w3.org/WAI/ARIA/apg/patterns/menubar/).
Runtime keyboard and narrow-screen acceptance must be checked separately
from source and component tests.
