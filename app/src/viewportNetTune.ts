// SPDX-License-Identifier: Apache-2.0
/** Wheel edits carry occurrence identity independently of a net's display name. */
export type ViewportNetTune = { net: string; occurrenceId?: string; terminalId?: string; deltaY: number; altKey: boolean };
export type ViewportNetTuneHandler = (event: ViewportNetTune) => boolean;
