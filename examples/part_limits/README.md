<!-- SPDX-License-Identifier: Apache-2.0 -->
# Original part-limit reporting example

[part-limits.json](part-limits.json) contains SPIKE-authored synthetic voltage,
temperature and current checks for `board-a/u1`. It deliberately includes an
over-current failure. Values are arithmetic fixtures, not real ratings or solved
board data. Original example data is Apache-2.0 licensed.

Import only into a project with that exact occurrence/component identity, or
replace both IDs with your project's retained identities and provide actual
rating sources and reviewed observations. Use **Engineering review → Part limits
& stress → Run review**. See [the workflow and equations](../../docs/PART_LIMITS.md).
