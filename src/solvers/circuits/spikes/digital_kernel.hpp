// SPDX-License-Identifier: Apache-2.0
// Original SPIKE four-state discrete-event kernel. Behavior follows the owned
// python/spikes/digital.py reference; no third-party source was used.
#pragma once

#include <algorithm>
#include <cstdint>
#include <deque>
#include <initializer_list>
#include <limits>
#include <map>
#include <queue>
#include <span>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace spikes::digital {

using Tick = std::int64_t;
enum class LogicValue { zero, one, x, z };
enum class PrimitiveKind { buffer, invert, and_gate, or_gate, xor_gate, nand_gate, nor_gate, tristate, dff };

class ModelError : public std::invalid_argument { using std::invalid_argument::invalid_argument; };
class ConvergenceError : public std::runtime_error { using std::runtime_error::runtime_error; };
class ResourceError : public std::runtime_error { using std::runtime_error::runtime_error; };

inline void validate_logic(LogicValue value) {
    switch (value) {
    case LogicValue::zero: case LogicValue::one: case LogicValue::x: case LogicValue::z: return;
    }
    throw ModelError("invalid four-state logic value");
}

inline Tick checked_tick_add(Tick time, Tick delay) {
    if (time < 0 || delay < 0 || delay > (std::numeric_limits<Tick>::max)() - time)
        throw ModelError("nonnegative signed-64 simulation tick overflow");
    return time + delay;
}

inline std::uint64_t checked_increment(std::uint64_t value) {
    if (value == (std::numeric_limits<std::uint64_t>::max)())
        throw ResourceError("digital event sequence/counter overflow");
    return value + 1;
}

inline LogicValue resolve_logic(std::span<const LogicValue> drivers) {
    LogicValue result = LogicValue::z;
    for (const auto value : drivers) {
        validate_logic(value);
        if (value == LogicValue::z) continue;
        if (result == LogicValue::z) result = value;
        else if (result != value) result = LogicValue::x;
    }
    return result;
}

inline LogicValue resolve_logic(std::initializer_list<LogicValue> values) {
    return resolve_logic(std::span<const LogicValue>(values.begin(), values.size()));
}

inline void validate_arity(PrimitiveKind kind, std::size_t count) {
    std::size_t low = 2, high = 64;
    switch (kind) {
    case PrimitiveKind::buffer: case PrimitiveKind::invert: low = high = 1; break;
    case PrimitiveKind::tristate: case PrimitiveKind::dff: high = 2; break;
    case PrimitiveKind::and_gate: case PrimitiveKind::or_gate: case PrimitiveKind::xor_gate:
    case PrimitiveKind::nand_gate: case PrimitiveKind::nor_gate: break;
    default: throw ModelError("unsupported primitive kind");
    }
    if (count < low || count > high) throw ModelError("primitive input arity out of range");
}

inline LogicValue invert(LogicValue value) {
    return value == LogicValue::zero ? LogicValue::one :
           value == LogicValue::one ? LogicValue::zero : LogicValue::x;
}

inline LogicValue gate_value(PrimitiveKind kind, std::span<const LogicValue> values) {
    validate_arity(kind, values.size());
    for (const auto value : values) validate_logic(value);
    if (kind == PrimitiveKind::dff) throw ModelError("DFF evaluation requires clock history");
    if (kind == PrimitiveKind::buffer)
        return values[0] == LogicValue::z ? LogicValue::x : values[0];
    if (kind == PrimitiveKind::invert) return invert(values[0]);
    if (kind == PrimitiveKind::tristate)
        return values[1] == LogicValue::zero ? LogicValue::z :
               values[1] == LogicValue::one ? values[0] : LogicValue::x;
    const auto contains = [&values](LogicValue value) {
        return std::find(values.begin(), values.end(), value) != values.end();
    };
    const bool unknown = contains(LogicValue::x) || contains(LogicValue::z);
    if (kind == PrimitiveKind::xor_gate) {
        if (unknown) return LogicValue::x;
        return std::count(values.begin(), values.end(), LogicValue::one) % 2 ? LogicValue::one : LogicValue::zero;
    }
    const bool conjunction = kind == PrimitiveKind::and_gate || kind == PrimitiveKind::nand_gate;
    const auto controlling = conjunction ? LogicValue::zero : LogicValue::one;
    const auto result = contains(controlling) ? controlling : unknown ? LogicValue::x : invert(controlling);
    return kind == PrimitiveKind::nand_gate || kind == PrimitiveKind::nor_gate ? invert(result) : result;
}

inline LogicValue gate_value(PrimitiveKind kind, std::initializer_list<LogicValue> values) {
    return gate_value(kind, std::span<const LogicValue>(values.begin(), values.size()));
}

struct SignalDescriptor { std::string name; LogicValue initial = LogicValue::z; };
struct PrimitiveDescriptor {
    std::string id;
    PrimitiveKind kind;
    std::vector<std::string> inputs;
    std::string output;
    Tick delay_ticks = 0;
};
struct Transition {
    Tick time_tick;
    std::uint32_t delta;
    std::string signal;
    LogicValue previous;
    LogicValue value;
    bool operator==(const Transition&) const = default;
};
struct Limits {
    std::uint32_t max_delta_cycles = 1024;
    std::size_t trace_capacity = 100000;
    std::size_t max_pending_events = 1000000;
    std::size_t max_events_per_run = 1000000;
    std::size_t max_signals = 100000;
    std::size_t max_primitives = 100000;
    std::size_t max_drivers_per_signal = 1024;
};
struct RunSummary { std::uint64_t events = 0; std::uint64_t transitions = 0; };

// Typed header-only SDK: descriptors are inert; add_* admits them explicitly.
// Equal-strength transport delays, integer virtual time, no HDL parser, analog
// thresholds, metastability, setup/hold checks, or physical gate qualification.
// No mutable globals. One kernel instance is single-threaded; separate instances
// are independent. run_until returns counts, not an unbounded transition vector.
// Runtime failure retains inspectable accepted state but permanently fails the
// instance; create a new kernel rather than resume an incomplete propagation.
class DigitalKernel {
public:
    explicit DigitalKernel(Limits limits = {}) : limits_(limits) {
        if (limits.max_delta_cycles < 1 || limits.max_delta_cycles > 1000000 ||
            limits.trace_capacity < 1 || limits.trace_capacity > 10000000 ||
            limits.max_pending_events < 1 || limits.max_pending_events > 10000000 ||
            limits.max_events_per_run < 1 || limits.max_events_per_run > 100000000 ||
            limits.max_signals < 1 || limits.max_signals > 1000000 ||
            limits.max_primitives < 1 || limits.max_primitives > 1000000 ||
            limits.max_drivers_per_signal < 1 || limits.max_drivers_per_signal > 1000000)
            throw ModelError("digital resource limits out of range");
    }

    void add_signal(SignalDescriptor descriptor) {
        require_healthy();
        descriptor.name = name(descriptor.name);
        validate_logic(descriptor.initial);
        if (signals_.contains(descriptor.name)) throw ModelError("duplicate digital signal");
        if (signals_.size() == limits_.max_signals) throw ResourceError("signal limit exceeded");
        Signal signal{descriptor.initial, {}, {}};
        if (descriptor.initial != LogicValue::z) signal.drivers.emplace("$initial", descriptor.initial);
        signals_.emplace(descriptor.name, std::move(signal));
    }

    void add_primitive(PrimitiveDescriptor descriptor) {
        require_healthy();
        descriptor.id = name(descriptor.id);
        if (primitives_.contains(descriptor.id)) throw ModelError("duplicate digital primitive");
        if (primitives_.size() == limits_.max_primitives) throw ResourceError("primitive limit exceeded");
        validate_arity(descriptor.kind, descriptor.inputs.size());
        for (auto& input : descriptor.inputs) { input = trim(input); require_signal(input); }
        require_signal(descriptor.output);
        checked_tick_add(time_tick_, descriptor.delay_ticks);
        // Preflight ordinary admission errors before changing the model.
        if (descriptor.kind != PrimitiveKind::dff) check_queue_room();
        const auto clock = descriptor.kind == PrimitiveKind::dff ? value(descriptor.inputs[1]) : LogicValue::x;
        auto [position, inserted] = primitives_.emplace(descriptor.id, Primitive{descriptor, clock});
        (void)inserted;
        for (const auto& input : descriptor.inputs) {
            auto& fanout = signals_.at(input).fanout;
            fanout.insert(std::upper_bound(fanout.begin(), fanout.end(), descriptor.id), descriptor.id);
        }
        if (descriptor.kind != PrimitiveKind::dff) schedule(position->second, time_tick_, 0);
    }

    void drive(const std::string& signal, std::string driver, LogicValue value, Tick delay_ticks = 0) {
        require_healthy(); require_signal(signal); validate_logic(value);
        if (driver != "$initial") driver = name(driver);
        const Tick target = checked_tick_add(time_tick_, delay_ticks);
        push(target, delay_ticks == 0 ? 1U : 0U, signal, std::move(driver), value);
    }

    void release_initial(const std::string& signal) { drive(signal, "$initial", LogicValue::z); }

    RunSummary run_until(Tick stop_tick) {
        require_healthy();
        if (stop_tick < time_tick_) throw ModelError("stop tick precedes current time");
        RunSummary result;
        try {
            while (!events_.empty() && events_.top().time <= stop_tick) {
                if (result.events == limits_.max_events_per_run) throw ResourceError("per-run event limit exceeded");
                const auto event = events_.top();
                if (event.delta > limits_.max_delta_cycles)
                    throw ConvergenceError("delta-cycle limit exceeded; possible zero-delay oscillation");
                auto& signal = signals_.at(event.signal);
                if (event.value != LogicValue::z && !signal.drivers.contains(event.driver) &&
                    signal.drivers.size() == limits_.max_drivers_per_signal)
                    throw ResourceError("signal driver limit exceeded");
                events_.pop(); ++result.events; time_tick_ = event.time;
                if (event.value == LogicValue::z) signal.drivers.erase(event.driver);
                else signal.drivers[event.driver] = event.value;
                LogicValue resolved = LogicValue::z;
                for (const auto& [driver, level] : signal.drivers) {
                    (void)driver;
                    if (resolved == LogicValue::z) resolved = level;
                    else if (resolved != level) resolved = LogicValue::x;
                }
                if (resolved == signal.value) continue;
                Transition transition{event.time, event.delta, event.signal, signal.value, resolved};
                signal.value = resolved; ++result.transitions;
                if (trace_.size() == limits_.trace_capacity) {
                    trace_.pop_front(); dropped_ = checked_increment(dropped_);
                }
                trace_.push_back(std::move(transition));
                for (const auto& id : signal.fanout) schedule(primitives_.at(id), event.time, event.delta);
            }
        } catch (...) { failed_ = true; throw; }
        time_tick_ = stop_tick;
        return result;
    }

    LogicValue value(const std::string& signal) const { require_signal(signal); return signals_.at(signal).value; }
    Tick time_tick() const noexcept { return time_tick_; }
    bool failed() const noexcept { return failed_; }
    std::size_t pending_events() const noexcept { return events_.size(); }
    std::uint64_t dropped_transitions() const noexcept { return dropped_; }
    std::vector<Transition> trace() const { return {trace_.begin(), trace_.end()}; }

private:
    struct Signal {
        LogicValue value;
        std::map<std::string, LogicValue> drivers;
        std::vector<std::string> fanout;
    };
    struct Primitive { PrimitiveDescriptor descriptor; LogicValue last_clock; };
    struct Event { Tick time; std::uint32_t delta; std::uint64_t sequence; std::string signal, driver; LogicValue value; };
    struct Later {
        bool operator()(const Event& a, const Event& b) const {
            return std::tie(a.time, a.delta, a.sequence) > std::tie(b.time, b.delta, b.sequence);
        }
    };

    static std::string trim(const std::string& text) {
        const auto first = text.find_first_not_of(" \t\r\n\f\v");
        if (first == std::string::npos) return {};
        return text.substr(first, text.find_last_not_of(" \t\r\n\f\v") - first + 1);
    }
    static std::string name(const std::string& text) {
        const auto result = trim(text);
        const auto alpha = [](char c) { return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z'); };
        if (result.empty() || result.size() > 128 || !alpha(result[0])) throw ModelError("invalid portable identifier");
        for (char c : result)
            if (!alpha(c) && !(c >= '0' && c <= '9') && std::string("_.$:-").find(c) == std::string::npos)
                throw ModelError("invalid portable identifier");
        return result;
    }
    void require_healthy() const { if (failed_) throw ResourceError("digital kernel failed; create a new instance"); }
    void require_signal(const std::string& id) const { if (!signals_.contains(id)) throw ModelError("unknown digital signal"); }
    void check_queue_room() const {
        if (events_.size() == limits_.max_pending_events) throw ResourceError("pending event limit exceeded");
        (void)checked_increment(sequence_);
    }
    void push(Tick time, std::uint32_t delta, std::string signal, std::string driver, LogicValue value) {
        check_queue_room();
        const auto next = checked_increment(sequence_);
        events_.push(Event{time, delta, next, std::move(signal), std::move(driver), value});
        sequence_ = next;
    }
    void schedule(Primitive& primitive, Tick time, std::uint32_t delta) {
        const auto& descriptor = primitive.descriptor;
        std::vector<LogicValue> inputs;
        inputs.reserve(descriptor.inputs.size());
        for (const auto& input : descriptor.inputs) inputs.push_back(value(input));
        LogicValue output;
        if (descriptor.kind == PrimitiveKind::dff) {
            const bool rising = primitive.last_clock == LogicValue::zero && inputs[1] == LogicValue::one;
            primitive.last_clock = inputs[1];
            if (!rising) return;
            output = inputs[0] == LogicValue::zero || inputs[0] == LogicValue::one ? inputs[0] : LogicValue::x;
        } else output = gate_value(descriptor.kind, inputs);
        push(checked_tick_add(time, descriptor.delay_ticks), descriptor.delay_ticks ? 0U : delta + 1,
             descriptor.output, descriptor.id, output);
    }

    Limits limits_;
    Tick time_tick_ = 0;
    bool failed_ = false;
    std::uint64_t sequence_ = 0, dropped_ = 0;
    std::map<std::string, Signal> signals_;
    std::map<std::string, Primitive> primitives_;
    std::priority_queue<Event, std::vector<Event>, Later> events_;
    std::deque<Transition> trace_;
};

} // namespace spikes::digital
