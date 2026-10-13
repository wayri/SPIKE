# SPDX-License-Identifier: Apache-2.0
"""Deterministic communication-boundary fault schedules for native/compiled boards."""
from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType

from .fault_injection import FaultSite, apply_fault
from .reliability import BathtubHazard, failure_delay_hours, finite


@dataclass(frozen=True)
class FaultEvent:
    time_s: float
    site: str
    value: float | None  # None clears to the site's immutable healthy value.

    def __post_init__(self):
        object.__setattr__(self, "time_s", finite(self.time_s, "fault time_s"))
        if not isinstance(self.site, str) or not self.site or "\x00" in self.site:
            raise ValueError("Fault event requires a named site")
        if self.value is not None and (isinstance(self.value, bool) or not isinstance(self.value, (int, float)) or not math.isfinite(self.value)):
            raise ValueError("Fault event value must be finite or None to clear")


class NativeFaultTarget:
    """Adapt a native session to the compiled Board named-fault boundary.

    The supplied sites must describe the circuit's actual healthy parameters.
    This object owns one saved native checkpoint and does not own the session.
    """
    def __init__(self, session, sites):
        self.session = session
        records = tuple(sites)
        if not records or any(not isinstance(s, FaultSite) for s in records):
            raise ValueError("Supply typed fault sites")
        self.fault_sites = MappingProxyType({s.name: s for s in records})
        bindings = {(s.element_id, s.parameter) for s in records}
        if len(self.fault_sites) != len(records) or len(bindings) != len(records):
            raise ValueError("Fault names and parameter bindings must be unique")
        self._saved = None

    @property
    def time_s(self):
        return self.session.time_s

    def inject_fault(self, name, value):
        try:
            site = self.fault_sites[name]
        except (KeyError, TypeError) as exc:
            raise ValueError("Unknown fault site") from exc
        apply_fault(self.session, site, value)

    def clear_fault(self, name):
        try:
            site = self.fault_sites[name]
        except (KeyError, TypeError) as exc:
            raise ValueError("Unknown fault site") from exc
        self.inject_fault(name, site.healthy_value)

    def step(self, seconds):
        if not self.session.step(seconds):
            raise RuntimeError(f"Native fault step rejected: {self.session.message}")

    def save(self):
        saved = self.session.checkpoint()
        if self._saved is not None:
            self._saved.close()
        self._saved = saved

    def restore(self):
        if self._saved is None:
            raise RuntimeError("No native fault checkpoint saved")
        self.session.restore(self._saved)

    def close(self):
        if self._saved is not None:
            self._saved.close()
            self._saved = None


class FaultCampaign:
    """Own the target's save slot and apply a fixed, validated schedule.

    Events execute before the next solve at their communication boundary.
    Observations remain the last accepted electrical solution until a step.
    A failure preserves prior accepted steps/events and exposes the error; the
    whole campaign is not an atomic transaction. Save/restore replays its cursor
    along with the solver. Consumers must not replace the target save slot.
    """
    def __init__(self, target, sites, events, *, minimum_step_s=1e-12, maximum_step_s=1e-5,
                 maximum_steps=100_000):
        self.target = target
        self.minimum_step_s = finite(minimum_step_s, "minimum_step_s", positive=True)
        self.maximum_step_s = finite(maximum_step_s, "maximum_step_s", positive=True)
        if self.minimum_step_s > self.maximum_step_s:
            raise ValueError("Minimum step exceeds maximum step")
        if type(maximum_steps) is not int or not 1 <= maximum_steps <= 1_000_000:
            raise ValueError("Campaign step count must be bounded")
        self.maximum_steps = maximum_steps
        records = tuple(sites)
        if not 1 <= len(records) <= 256 or any(not isinstance(s, FaultSite) for s in records):
            raise ValueError("Campaign requires 1..256 typed sites")
        self.sites = {s.name: s for s in records}
        if len(self.sites) != len(records):
            raise ValueError("Campaign sites must be unique")
        self.events = tuple(events)
        if len(self.events) > 10_000 or any(not isinstance(e, FaultEvent) for e in self.events):
            raise ValueError("Campaign requires at most 10000 typed events")
        time_s = finite(target.time_s, "target time_s")
        previous, identities = time_s, set()
        for event in self.events:
            if event.time_s < previous or event.site not in self.sites:
                raise ValueError("Events must be ordered, not in the past, and bind known sites")
            gap = event.time_s-previous
            if 0 < gap < self.minimum_step_s:
                raise ValueError("Fault event interval is below the declared time resolution")
            identity = event.time_s, event.site
            if identity in identities:
                raise ValueError("Duplicate event for one fault site/time")
            identities.add(identity)
            if event.value is not None:
                self.sites[event.site].validate(event.value)
            previous = event.time_s
        self.cursor = 0
        self.completed_steps = 0
        self.trace = []
        self._saved = None

    def _due(self):
        while self.cursor < len(self.events):
            event = self.events[self.cursor]
            actual = self.target.time_s
            tolerance = 8*math.ulp(max(abs(actual), abs(event.time_s), 1e-300))
            if event.time_s > actual+tolerance:
                break
            if actual > event.time_s+tolerance:
                raise RuntimeError("Target advanced past a campaign event outside the scheduler")
            value = self.sites[event.site].healthy_value if event.value is None else event.value
            self.target.inject_fault(event.site, value)
            self.trace.append({"scheduled_time_s": event.time_s, "applied_time_s": actual,
                "site": event.site, "value": value, "operation": "clear" if event.value is None else "inject"})
            self.cursor += 1

    def advance_to(self, stop_time_s):
        stop = finite(stop_time_s, "stop_time_s")
        now = finite(self.target.time_s, "target time_s")
        if stop < now:
            raise ValueError("Campaign cannot move time backwards without restore")
        if 0 < stop-now < self.minimum_step_s:
            raise ValueError("Requested interval is below declared time resolution")
        self._due()
        while self.target.time_s < stop:
            if self.completed_steps >= self.maximum_steps:
                raise RuntimeError("Campaign step limit reached")
            now = self.target.time_s
            boundary = min(stop, self.events[self.cursor].time_s) if self.cursor < len(self.events) else stop
            remaining = boundary-now
            if remaining <= 8*math.ulp(max(abs(boundary), abs(now), 1e-300)):
                self._due()
                if abs(stop-now) <= 8*math.ulp(max(abs(stop), abs(now), 1e-300)):
                    break
                continue
            step = min(remaining, self.maximum_step_s)
            # Avoid leaving a sub-resolution last step after a maximum-size step.
            rounding = 8*math.ulp(max(abs(boundary), abs(now), 1e-300))
            if rounding < remaining-step < self.minimum_step_s:
                step = remaining/2
            if step < self.minimum_step_s or now+step == now:
                raise ValueError("Boundary cannot be represented within campaign step bounds")
            self.target.step(step)
            accepted_time = finite(self.target.time_s, "accepted target time_s")
            if accepted_time <= now or abs(accepted_time-(now+step)) > 8*math.ulp(max(abs(now+step), 1e-300)):
                raise RuntimeError("Target violated accepted-step time contract")
            self.completed_steps += 1
            self._due()
        return tuple(self.trace)

    def save(self):
        self.target.save()
        self._saved = self.cursor, self.completed_steps, len(self.trace)

    def restore(self):
        if self._saved is None:
            raise RuntimeError("No campaign checkpoint saved")
        self.target.restore()
        self.cursor, self.completed_steps, length = self._saved
        del self.trace[length:]


def event_from_hazard(site: FaultSite, value: float, hazard: BathtubHazard, *, age_hours: float,
                      quantile: float, start_time_s: float, horizon_s: float) -> FaultEvent | None:
    """Map a specified mode's device-hour hazard to electrical-clock seconds.

    The hazard must already be allocated to this mode, not an unexplained total
    part FIT. No accelerated simulation-clock scaling is silently introduced.
    """
    checked = site.validate(value)
    start = finite(start_time_s, "start_time_s")
    horizon = finite(horizon_s, "horizon_s", positive=True)
    delay = failure_delay_hours(hazard, age_hours=age_hours, quantile=quantile, horizon_hours=horizon/3600)
    if delay is None:
        return None
    seconds = delay*3600
    if not math.isfinite(start+seconds) or start+seconds == start:
        raise ValueError("Sampled event cannot be represented on the electrical time axis")
    return FaultEvent(start+seconds, site.name, checked)
