// SPDX-License-Identifier: Apache-2.0
// Independent truth tables, tick-order oracles and bounded-failure checks.
#include "spikes/digital_kernel.hpp"
#include <array>
#include <iostream>

namespace {
using namespace spikes::digital;
using L = LogicValue;
using K = PrimitiveKind;
int checks = 0;
void require(bool condition, const char* message) {
    ++checks;
    if (!condition) throw std::runtime_error(message);
}
template<class Error, class Function> void rejects(Function function) {
    bool caught = false;
    try { function(); } catch (const Error&) { caught = true; }
    require(caught, "expected typed rejection");
}
void signals(DigitalKernel& kernel, std::initializer_list<const char*> names) {
    for (const auto name : names) kernel.add_signal({name});
}

void truth_tables() {
    constexpr std::array states{L::zero, L::one, L::x, L::z};
    constexpr L and_table[4][4] = {
        {L::zero,L::zero,L::zero,L::zero}, {L::zero,L::one,L::x,L::x},
        {L::zero,L::x,L::x,L::x}, {L::zero,L::x,L::x,L::x}};
    constexpr L or_table[4][4] = {
        {L::zero,L::one,L::x,L::x}, {L::one,L::one,L::one,L::one},
        {L::x,L::one,L::x,L::x}, {L::x,L::one,L::x,L::x}};
    constexpr L xor_table[4][4] = {
        {L::zero,L::one,L::x,L::x}, {L::one,L::zero,L::x,L::x},
        {L::x,L::x,L::x,L::x}, {L::x,L::x,L::x,L::x}};
    constexpr L resolve_table[4][4] = {
        {L::zero,L::x,L::x,L::zero}, {L::x,L::one,L::x,L::one},
        {L::x,L::x,L::x,L::x}, {L::zero,L::one,L::x,L::z}};
    constexpr std::array inverted{L::one,L::zero,L::x,L::x};
    constexpr std::array buffered{L::zero,L::one,L::x,L::x};
    for (std::size_t i = 0; i < states.size(); ++i) {
        require(gate_value(K::invert,{states[i]}) == inverted[i], "NOT truth table");
        require(gate_value(K::buffer,{states[i]}) == buffered[i], "BUF truth table");
        for (std::size_t j = 0; j < states.size(); ++j) {
            const auto a = states[i], b = states[j];
            require(gate_value(K::and_gate,{a,b}) == and_table[i][j], "AND truth table");
            require(gate_value(K::or_gate,{a,b}) == or_table[i][j], "OR truth table");
            require(gate_value(K::xor_gate,{a,b}) == xor_table[i][j], "XOR truth table");
            const auto inverse = [](L v) { return v == L::zero ? L::one : v == L::one ? L::zero : L::x; };
            require(gate_value(K::nand_gate,{a,b}) == inverse(and_table[i][j]), "NAND truth table");
            require(gate_value(K::nor_gate,{a,b}) == inverse(or_table[i][j]), "NOR truth table");
            require(resolve_logic({a,b}) == resolve_table[i][j], "driver resolution table");
            const auto expected = j == 0 ? L::z : j == 1 ? a : L::x;
            require(gate_value(K::tristate,{a,b}) == expected, "tristate truth table");
        }
    }
    require(resolve_logic({}) == L::z, "undriven is Z");
    require(resolve_logic({L::one,L::z,L::one}) == L::one, "matching drivers");
    require(resolve_logic({L::one,L::x,L::zero,L::one}) == L::x, "unknown remains absorbing");
    require(gate_value(K::xor_gate,{L::one,L::one,L::one}) == L::one, "multi-input XOR parity");
}

void conflicts_and_release() {
    DigitalKernel kernel;
    kernel.add_signal({"bus", L::one});
    kernel.drive("bus","external",L::zero);
    kernel.run_until(0);
    require(kernel.value("bus") == L::x, "initial driver participates in resolution");
    kernel.release_initial("bus"); kernel.run_until(0);
    require(kernel.value("bus") == L::zero, "initial driver release");
    kernel.drive("bus","external",L::z); kernel.run_until(0);
    require(kernel.value("bus") == L::z, "all drivers released");
    signals(kernel,{"data","enable"});
    kernel.add_primitive({"tri",K::tristate,{"data","enable"},"bus"});
    kernel.drive("data","data_source",L::one); kernel.drive("enable","enable_source",L::one);
    kernel.run_until(0); require(kernel.value("bus") == L::one, "enabled tristate drives data");
    kernel.drive("bus","external",L::zero); kernel.run_until(0);
    require(kernel.value("bus") == L::x, "opposed tristate drivers conflict");
    kernel.drive("enable","enable_source",L::zero); kernel.run_until(0);
    require(kernel.value("bus") == L::zero, "disabled tristate releases bus");
}

void transport_order() {
    DigitalKernel kernel;
    signals(kernel,{"a","y"});
    kernel.add_primitive({"buf",K::buffer,{"a"},"y",3});
    kernel.drive("a","stim",L::zero);
    kernel.drive("a","stim",L::one,1);
    kernel.drive("a","stim",L::zero,2);
    kernel.run_until(2); require(kernel.value("y") == L::z, "delay does not evaluate early");
    kernel.run_until(5);
    std::vector<Transition> output;
    for (const auto& transition : kernel.trace()) if (transition.signal == "y") output.push_back(transition);
    const std::vector<Transition> expected{
        {3,0,"y",L::z,L::x}, {3,0,"y",L::x,L::zero},
        {4,0,"y",L::zero,L::one}, {5,0,"y",L::one,L::zero}};
    require(output == expected, "stable transport heap preserves short pulses and insertion order");

    DigitalKernel sorted;
    signals(sorted,{"input","first","second","last"});
    sorted.add_primitive({"z_gate",K::buffer,{"input"},"second"});
    sorted.add_primitive({"a_gate",K::buffer,{"input"},"first"});
    sorted.add_primitive({"last_gate",K::buffer,{"first"},"last"});
    sorted.run_until(0);
    const auto before = sorted.trace().size();
    sorted.drive("input","stim",L::one); sorted.run_until(0);
    const auto trace = sorted.trace();
    require(trace.size() == before + 4, "one transition per changed signal");
    require(trace[before + 1].signal == "first" && trace[before + 2].signal == "second", "lexically sorted fanout");
    require(trace[before].delta == 1 && trace[before + 1].delta == 2 && trace.back().delta == 3, "delta propagation order");
}

void dff() {
    DigitalKernel kernel;
    signals(kernel,{"d","clk","q"});
    kernel.drive("clk","clock",L::zero); kernel.drive("d","data",L::one); kernel.run_until(0);
    kernel.add_primitive({"ff",K::dff,{"d","clk"},"q",2});
    require(kernel.pending_events() == 0, "DFF has no initialization output event");
    kernel.drive("clk","clock",L::one); kernel.run_until(1);
    require(kernel.value("q") == L::z, "clock-to-Q delay");
    kernel.drive("d","data",L::zero); kernel.run_until(2);
    require(kernel.value("q") == L::one, "DFF captures data at edge, not arrival time");
    kernel.drive("clk","clock",L::x); kernel.run_until(2);
    kernel.drive("clk","clock",L::one); kernel.run_until(4);
    require(kernel.value("q") == L::one, "X-to-one is not a positive edge");
    kernel.drive("clk","clock",L::zero); kernel.drive("d","data",L::z); kernel.run_until(4);
    kernel.drive("clk","clock",L::one); kernel.run_until(6);
    require(kernel.value("q") == L::x, "unknown/Z data captures X");
    kernel.drive("clk","clock",L::zero); kernel.run_until(6);
    kernel.drive("d","data",L::zero); kernel.drive("clk","clock",L::one); kernel.run_until(8);
    require(kernel.value("q") == L::zero, "same-tick data then clock uses stable event order");
}

void bounds_and_validation() {
    rejects<ModelError>([] { DigitalKernel kernel(Limits{0}); });
    rejects<ModelError>([] { gate_value(K::and_gate,{L::one}); });
    rejects<ModelError>([] { gate_value(K::dff,{L::one,L::zero}); });
    rejects<ModelError>([] { resolve_logic({static_cast<L>(99)}); });
    const auto maximum = (std::numeric_limits<Tick>::max)();
    require(checked_tick_add(maximum - 1,1) == maximum, "last signed tick admitted");
    rejects<ModelError>([&] { checked_tick_add(maximum,1); });
    rejects<ModelError>([] { checked_tick_add(0,-1); });
    rejects<ResourceError>([] { checked_increment((std::numeric_limits<std::uint64_t>::max)()); });
    DigitalKernel kernel;
    signals(kernel,{"a","b"});
    rejects<ModelError>([&] { kernel.add_signal({"a"}); });
    rejects<ModelError>([&] { kernel.add_signal({"9invalid"}); });
    rejects<ModelError>([&] { kernel.drive("missing","driver",L::one); });
    rejects<ModelError>([&] { kernel.add_primitive({"bad",K::buffer,{"a","b"},"b"}); });
    kernel.run_until(maximum);
    rejects<ModelError>([&] { kernel.drive("a","driver",L::one,1); });
    rejects<ModelError>([&] { kernel.add_primitive({"late",K::buffer,{"a"},"b",1}); });
    rejects<ModelError>([&] { kernel.run_until(maximum - 1); });
    require(kernel.pending_events() == 0 && !kernel.failed(), "invalid external requests leave instance usable");

    Limits limits; limits.trace_capacity = 2; limits.max_pending_events = 3;
    DigitalKernel bounded(limits); signals(bounded,{"a","b"});
    bounded.drive("a","driver",L::zero); bounded.drive("a","driver",L::one); bounded.drive("a","driver",L::zero);
    rejects<ResourceError>([&] { bounded.drive("b","driver",L::one); });
    rejects<ResourceError>([&] { bounded.add_primitive({"buf",K::buffer,{"a"},"b"}); });
    require(bounded.pending_events() == 3, "queue overflow is nonmutating at admission");
    const auto summary = bounded.run_until(0);
    require(summary.events == 3 && summary.transitions == 3, "run summary captures total counts");
    require(bounded.trace().size() == 2 && bounded.dropped_transitions() == 1, "ring bounded with explicit dropped count");
    require(bounded.trace()[0].value == L::one && bounded.trace()[1].value == L::zero, "ring keeps newest transitions");
    bounded.add_primitive({"buf",K::buffer,{"a"},"b"}); bounded.run_until(0);
    require(bounded.value("b") == L::zero, "failed primitive admission did not reserve id or fanout");

    Limits driver_limits; driver_limits.max_drivers_per_signal = 1;
    DigitalKernel drivers(driver_limits); signals(drivers,{"bus"});
    drivers.drive("bus","left",L::zero); drivers.drive("bus","right",L::one);
    rejects<ResourceError>([&] { drivers.run_until(0); });
    require(drivers.failed() && drivers.value("bus") == L::zero, "driver bound preserves preceding accepted state and fails closed");

    Limits event_limits; event_limits.max_events_per_run = 1;
    DigitalKernel events(event_limits); signals(events,{"a"});
    events.drive("a","driver",L::zero); events.drive("a","driver",L::one);
    rejects<ResourceError>([&] { events.run_until(0); });
    require(events.failed() && events.pending_events() == 1, "per-run work bound");
    rejects<ResourceError>([&] { events.run_until(0); });

    Limits fanout_limits; fanout_limits.max_pending_events = 2;
    DigitalKernel fanout(fanout_limits); signals(fanout,{"input","a","b","c"});
    for (const auto output : {"a","b","c"}) {
        fanout.add_primitive({std::string("gate_") + output,K::buffer,{"input"},output});
        fanout.run_until(0);
    }
    fanout.drive("input","stim",L::one);
    rejects<ResourceError>([&] { fanout.run_until(0); });
    require(fanout.failed() && fanout.pending_events() == 2, "fanout queue exhaustion fails closed without exceeding bound");

    DigitalKernel overflow; signals(overflow,{"input","output"});
    overflow.add_primitive({"gate",K::buffer,{"input"},"output",1});
    overflow.run_until(maximum);
    overflow.drive("input","stim",L::one);
    rejects<ModelError>([&] { overflow.run_until(maximum); });
    require(overflow.failed(), "propagation time overflow fails closed");

    Limits model_limits; model_limits.max_signals = 2; model_limits.max_primitives = 1;
    DigitalKernel model(model_limits); signals(model,{"input","output"});
    rejects<ResourceError>([&] { model.add_signal({"excess"}); });
    model.add_primitive({"first",K::buffer,{"input"},"output"});
    rejects<ResourceError>([&] { model.add_primitive({"excess",K::buffer,{"input"},"output"}); });
    require(!model.failed(), "model admission limits do not poison admitted graph");
}

void oscillation() {
    Limits limits; limits.max_delta_cycles = 16; limits.trace_capacity = 8;
    DigitalKernel kernel(limits);
    kernel.add_signal({"loop",L::zero}); kernel.release_initial("loop");
    kernel.add_primitive({"inv",K::invert,{"loop"},"loop"});
    rejects<ConvergenceError>([&] { kernel.run_until(0); });
    require(kernel.failed() && kernel.trace().size() <= 8, "oscillator fails closed with bounded trace");
    rejects<ResourceError>([&] { kernel.drive("loop","driver",L::zero); });
}
} // namespace

int main() {
    try {
        truth_tables(); conflicts_and_release(); transport_order(); dff(); bounds_and_validation(); oscillation();
        std::cout << "PASS: native four-state digital kernel; " << checks << " checks\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
