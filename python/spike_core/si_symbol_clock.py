# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Sample continuous-time piecewise-linear NRZ edges on an unrelated FFT grid.

Symbol boundaries are delay + k/rate, never k*round(UI/dt)*dt. Ramp state
advances to the physical end of each UI, not the final sampled point in it.
"""
import numpy as np


def sample_nrz_clock(sequence, times, rate, source):
    low, high = source["low_v"], source["high_v"]
    delay = source["delay_s"]
    waveform = np.full(len(times), low, dtype=float)
    previous = low
    ui = 1.0 / rate
    for index, bit in enumerate(sequence):
        start, end = delay + index * ui, delay + (index + 1) * ui
        left, right = np.searchsorted(times, [start, end], side="left")
        target = high if bit else low
        edge = source["rise_time_s"] if target > previous else source["fall_time_s"]
        delta = abs(target - previous)
        if edge == 0:
            waveform[left:right] = target
            previous = target
        else:
            # User-supplied edge duration is 10--90% of the full swing.
            slew = .8 * (high - low) / edge
            moved = np.minimum((times[left:right] - start) * slew, delta)
            waveform[left:right] = previous + np.sign(target - previous) * moved
            previous += np.sign(target - previous) * min(ui * slew, delta)
    return waveform
