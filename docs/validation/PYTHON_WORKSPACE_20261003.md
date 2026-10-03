<!-- SPDX-License-Identifier: Apache-2.0 -->
# Python workspace expansion - 2026-10-03

## Implemented scope

- Lazy, root-scoped Python file tree and folder picker.
- Independent editor tabs, Open/New/Close, Save/Save as/Save all, dirty-close
  choices, external edit conflicts, and session-scoped draft restoration.
- Line gutter breakpoints, supervised Python debugging, continue/pause/stop,
  step over/into/out, bounded variables, and source-linked call stacks.
- Dedicated interface/API help and 50 original templates in 18 categories.
  Eleven templates dispatch registered analysis methods after an explicit
  request file is configured. No example silently invents physical inputs.
- Scoped, wrapping controls and collapsible sidebars; browser editing/download
  remains available with execution explicitly restricted to the desktop.

The implementation does not add numerical solver qualification. See
[the user guide](../PYTHON_WORKSPACE.md) for debugger and analysis limits.

## Verification performed

| Check | Observed result |
| --- | --- |
| `npm run test:python-workspace` | Passed: tab/file handlers, dirty-close choices, Save/Save as, conflict preservation, root-relative paths, breakpoint remapping, debug controls/acknowledgments, browser disabled states, unsaved template creation, and isolation from project-level keyboard handlers. |
| Template catalog checks | All 50 Python sources compile; 18 categories; 11 guarded request-file runners. Context scripts and runner guard/dispatch/design mismatch checks passed. Runner dispatch uses a test facade; this is not evidence of a numerical solve. |
| Focused Python workspace/runtime/debugger/file tests | 23 passed, including actual child-process breakpoints, stepping, stop/timeout, sibling imports, service routing, file confinement/conflicts, and result admission. |
| Full Python suite | 2,390 tests in 478.969 seconds: 2,376 passed, 13 skipped, 1 failed. |
| Rust library tests | 35 passed, 1 ignored live OS counter test. |
| TypeScript, frontend production build, native development build | Passed. Vite reports existing large-chunk and mixed import warnings. |
| Architecture guard | Passed. |
| Help generation/checks | Passed: 1,777 control sites, 71 CLI pages, 80 diagnostics. |
| Form contrast and board parser checks | Passed. |

The full-suite failure is
`test_public_release_readiness.PublicReleaseReadinessTests.test_current_candidate_is_technical_but_externally_blocked`:
the expected external blocker set includes
`PUBLIC_RELEASE_DEPENDENCY_APPROVAL_REQUIRED`, while the current release report
omits it. Release readiness files were not changed by this workspace expansion.
The full-suite log is in the local ignored build directory:
`build/python-workspace-full-checks.log`.

## Native visual acceptance remains pending

The updated development app launched and exposed its accessibility tree.
The Windows computer-use helper repeatedly returned
`failed to activate captured window`; the captured pixels showed the desktop
wallpaper rather than SPIKE. After refreshing the returned window and retrying,
app input was stopped. No native editor screenshots, native file-dialog save,
or wide/narrow desktop layout checks are claimed as passed.

Once the development window can be activated, use
`build/python-workspace-acceptance/editor_demo.py` and its `helpers` folder:

1. Open the fixture, expand the folder tree, and open/close a second file tab.
2. Set a breakpoint on `mean = summarize(samples)`, Debug, Step into, Step over,
   and Continue; verify the locals/call stack and `Sample mean: 2.0` output.
3. Edit and Save the fixture, then Save as a new file and compare disk contents.
4. Open Templates and Help; create a template and verify the unsaved-close
   choices.
5. Repeat with the debugger open at wide and narrower supported window sizes,
   checking wrapping, scrolling, file names, focus, and available editor space.

The deliverable is a local development build, not a newly packaged installer.
