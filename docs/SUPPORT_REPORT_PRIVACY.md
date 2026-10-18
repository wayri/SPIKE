<!-- SPDX-License-Identifier: Apache-2.0 -->
# Reviewing and sharing support reports

Use **Report bug** or the interface recovery screen's **Preview report**.
Add optional reproduction steps and expected behavior, then inspect the exact
export preview. Select JSON or Markdown, **Copy report**, or **Save report**.
On desktop, Save opens the native Save As dialog for a JSON or Markdown file.
SPIKE confirms success only after the host reports a completed save; canceling
the dialog is reported as cancellation. Save errors omit the destination path.
The preview and report controls are locked while the dialog/save is pending,
and repeated save requests are ignored until it finishes. In browser preview,
Save requests a download; check the downloads destination. If that download is
unavailable, copy the preview instead. Failed clipboard or save actions display
recovery guidance; the buttons become available to retry.
Opening the issue form sends fixed application metadata in its URL. Paste the
reviewed report manually before submitting the issue.

Reports are generated locally. SPIKE does not automatically upload reports,
attach projects, capture screenshots or collect console logs. Notes live only in
the open report view; **Clear notes** removes them. A copied or downloaded report
is managed by your clipboard or filesystem. Closing/reloading the interface can
discard unsaved project edits; the recovery screen retains its warning and
explicit native close confirmation. Report actions do not modify project files.

The default crash report omits the raw exception message, function/component
names, source filenames and paths, location URLs, exact times and user agent.
It retains the release version/channel, allowlisted JavaScript error class and
common OS error code, anonymous source line/column positions and component depth.
Unknown error classes become `Error`; unknown codes are omitted. Message text is
omitted because a project name or secret can appear as arbitrary ordinary words.

Optional notes are scrubbed for common paths, emails, quoted text, project/file
labels, URLs and credential formats. This is best-effort removal, not a guarantee
of anonymity: arbitrary names, unusual credentials and proprietary details may
remain. Review the preview and remove private details from the notes before
sharing. Raw notes and crash exceptions are never included in the export.
The export preview contains only the scrubbed notes; the editable notes field
continues to show what you typed until cleared or the view is closed.

## Developer contract and maintenance

`app/src/reportPrivacy.ts` constructs `spike/support-report/v1`. Its
`redaction_version` identifies the privacy rules independently from the release.
Changes to the scrubber or exported fields must update this version and the
adversarial regression fixtures. The bounded input policy limits notes to
12,000 characters, stack input to 24,000 characters and 20 anonymous frames.
No automatic report history or raw diagnostics are written to localStorage.

`report_id` is a deterministic noncryptographic grouping hint computed only from
the release, report kind, allowlisted class/code and anonymous frames. It never
hashes project information or raw messages and is not a user/device identifier.
It may group different failures together; maintainers should compare reviewed
reproduction steps. User reports without crash frames share an ID per release.

`SupportReportPreview.tsx` owns review, optional notes, local copy/download and explicit
issue-form handoff. Both JSON and Markdown carry the same fields. Markdown wraps
the JSON in a fenced block and escapes backticks so notes cannot terminate it.
`bugReport.ts` keeps its fixed metadata allowlist: unknown workspaces become
`Other`, and only the broad platform family is derived from user agent. Do not
add project state, notes, errors, logs or document names to that URL.

The recovery boundary does not add raw errors to the console. React/development
tools may independently log caught errors; this report workflow does not collect
or export those logs. The boundary covers React rendering failures, not every
native process, worker or asynchronous failure.

Run from `app`:

```text
node scripts/test-report-privacy.mjs
node scripts/test-app-recovery.mjs
node scripts/test-bug-report.mjs
npm run test:button-standard
npm exec tsc -- --noEmit
```

The tests execute adversarial export cases, grouping invariants, preview/copy
behavior, clipboard/download failure recovery, native save success/cancellation/
failure and duplicate-request admission, and native close confirmation.
Native Save As availability and visual layout require runtime UI acceptance.
