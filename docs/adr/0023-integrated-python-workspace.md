<!-- SPDX-License-Identifier: MIT -->
# ADR 0023: Integrated Python workspace

- Status: Accepted for the local engineering preview.
- Date: 2026-09-24

## Context

The external extension and automation contracts were callable from Python,
but a desktop user had no integrated place to inspect, edit, and run a script
against the current board and result.

## Decision

The desktop provides a Python editor with `.py` open/save, run/stop, a time
limit, and captured output. `run_python_script` executes code in a separate
local Python child process, not in the webview or resident worker. The child
receives normalized `spike/v1` DesignIR and a bounded current result context.
The injected `spike` facade calls ordinary worker methods. Published results
return to the parent worker, which checks board binding, model status, finite
values, and sample limits before the desktop displays them.
Extensions trusted in the current worker session are made available to the
script child; scripts can invoke them through the same extension contract.

The child is user-authored Python with the user's filesystem and package
access. The process boundary supports worker cancellation and protects the
resident worker from ordinary script exceptions; it is not a security sandbox.
Code, input, output, time, and returned result sizes are bounded. The browser
preview offers editing and download, with execution limited to the desktop.

## Consequences

Interactive scripts and unattended `SpikeAutomation` programs use the same
worker contracts. A script can inspect and exchange board data, automate
worker methods, and publish explicit analysis fields. Publishing a field does
not prove solver validity or imply other field quantities were computed.
