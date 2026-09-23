# Zone-cell warning masking a failed solve

The 0.2.11 PI Run path displayed the first issue from a failed preflight or
analysis. A leading `ZONE_MESH_COARSENED` warning consequently hid later errors.
This warning is not itself a blocking condition: preflight admits a solve when
its error count is zero.

The source fix selects error-severity diagnostics, including their codes and
suggestions, for single and batch failures. Run also retains its compact
preflight in the setup panel, so all validation issues can be reviewed without
running Preview separately. A failed response containing only warnings now
reports a missing error diagnostic rather than blaming an advisory.

Verification: `node scripts/test-analysis-failure.mjs` and `npx tsc --noEmit`
passed. This change has not been built into an installer. The user's exact
arts-1_irca request is still needed to reproduce and correct its underlying
solver/preflight error; no zone budget or geometry safety gate was removed.
