// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
#include "src/si/transition_pi_cdr.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <initializer_list>
#include <limits>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {

using spike::si::TransitionPiCdrError;
using spike::si::TransitionPiCdrOptions;
using spike::si::TransitionPiCdrResult;
using spike::si::recover_transition_pi_cdr;

[[noreturn]] void fail(const std::string& message) {
    throw std::runtime_error(message);
}

void require(bool condition, const std::string& message) {
    if (!condition) {
        fail(message);
    }
}

void require_near(double actual,
                  double expected,
                  double tolerance,
                  const std::string& message) {
    if (!std::isfinite(actual) || std::abs(actual - expected) > tolerance) {
        fail(message + ": actual=" + std::to_string(actual) +
             " expected=" + std::to_string(expected));
    }
}

template <typename Function>
void require_rejected(Function&& function, const std::string& message) {
    try {
        function();
    } catch (const TransitionPiCdrError&) {
        return;
    }
    fail(message);
}

TransitionPiCdrResult recover_values(std::initializer_list<double> crossings,
                                     double last_x_ui,
                                     const TransitionPiCdrOptions& options) {
    return recover_transition_pi_cdr(
        std::span<const double>{crossings.begin(), crossings.size()},
        last_x_ui,
        options);
}

void test_hand_calculated_update() {
    TransitionPiCdrOptions options;
    options.initial_phase_ui = 0.2;
    options.proportional_gain = 0.25;
    options.integral_gain = 0.05;
    options.max_frequency_offset_ppm = 100'000.0;
    options.max_symbols = 4;
    const std::vector<double> crossings{0.1};
    const TransitionPiCdrResult result =
        recover_transition_pi_cdr(crossings, 1.0, options);

    // Hand recurrence: e=-0.1, P'=1+0.05e=0.995,
    // B'=0.2+0.25e=0.175, center=B'+P'/2=0.6725.
    require(result.phase_errors_ui.size() == 1, "one error expected");
    require_near(result.phase_errors_ui[0], -0.1, 1.0e-15,
                 "hand phase error");
    require(result.sample_centers_ui.size() == 1 &&
                result.recovered_periods_ui.size() == 1,
            "hand fixture must emit one complete sample");
    require_near(result.recovered_periods_ui[0], 0.995, 1.0e-15,
                 "hand period update");
    require_near(result.sample_centers_ui[0], 0.6725, 1.0e-15,
                 "hand sample center");
    require(result.detected_transition_count == 1,
            "detected counter must preserve input size");
    require(result.accepted_transition_count == 1,
            "accepted counter must match accepted coordinates");
}

void test_no_transition_free_run() {
    TransitionPiCdrOptions options;
    options.initial_phase_ui = 0.25;
    options.max_symbols = 4;
    const TransitionPiCdrResult result = recover_transition_pi_cdr({}, 3.0, options);
    const std::vector<double> expected{0.75, 1.75, 2.75};
    require(result.sample_centers_ui == expected,
            "no-transition centers must free-run exactly");
    require(std::all_of(result.recovered_periods_ui.begin(),
                        result.recovered_periods_ui.end(),
                        [](double period) { return period == 1.0; }),
            "no-transition periods must remain nominal");
    require(result.accepted_transition_count == 0,
            "no transition may be accepted from an empty input");
}

void test_inclusive_right_gate_and_consumption() {
    TransitionPiCdrOptions options;
    options.proportional_gain = 0.2;
    options.integral_gain = 0.01;
    options.max_symbols = 3;
    const std::vector<double> crossings{0.45, 0.55};
    const TransitionPiCdrResult result =
        recover_transition_pi_cdr(crossings, 2.0, options);
    require(result.accepted_crossings_ui.size() == 1,
            "right-edge transition must be consumed once");
    require(result.accepted_crossings_ui[0] == 0.45,
            "the +0.45P gate edge is inclusive");
    require(result.ambiguous_gate_count == 0,
            "a later out-of-gate crossing is not an ambiguity");
}

void test_inclusive_left_gate() {
    TransitionPiCdrOptions options;
    options.initial_phase_ui = 0.5;
    options.max_symbols = 2;
    const double left_edge = options.initial_phase_ui - 0.45;
    const std::vector<double> crossings{left_edge};
    const TransitionPiCdrResult result =
        recover_transition_pi_cdr(crossings, 1.2, options);
    require(result.accepted_transition_count == 1,
            "the -0.45P gate edge must be inclusive");
    require(result.accepted_crossings_ui[0] == left_edge,
            "the exact binary64 left edge must be retained");
    require_near(result.phase_errors_ui[0], left_edge - options.initial_phase_ui,
                 1.0e-15,
                 "left-edge phase error");
}

std::size_t accepted_at_first_gate(double crossing) {
    TransitionPiCdrOptions options;
    options.initial_phase_ui = 0.5;
    options.max_symbols = 2;
    const std::vector<double> crossings{crossing};
    const TransitionPiCdrResult result =
        recover_transition_pi_cdr(crossings, 1.0, options);
    require(result.detected_transition_count == 1,
            "one-ULP gate fixture must retain its detected count");
    require(result.ambiguous_gate_count == 0,
            "one crossing cannot create an ambiguous gate");
    require(result.accepted_crossings_ui.size() ==
                result.accepted_transition_count,
            "accepted history and counter must agree");
    return result.accepted_transition_count;
}

void test_gate_edges_one_ulp_inside_and_outside() {
    constexpr double phase = 0.5;
    const double left_edge = phase - 0.45;
    const double right_edge = phase + 0.45;
    const double negative_infinity = -std::numeric_limits<double>::infinity();
    const double positive_infinity = std::numeric_limits<double>::infinity();

    require(accepted_at_first_gate(std::nextafter(left_edge, positive_infinity)) ==
                1,
            "one ULP inside the left edge must be accepted");
    require(accepted_at_first_gate(std::nextafter(left_edge, negative_infinity)) ==
                0,
            "one ULP outside the left edge must be rejected");
    require(accepted_at_first_gate(std::nextafter(right_edge, negative_infinity)) ==
                1,
            "one ULP inside the right edge must be accepted");
    require(accepted_at_first_gate(std::nextafter(right_edge, positive_infinity)) ==
                0,
            "one ULP outside the right edge must be rejected");
}

void test_center_equal_to_record_end_is_retained() {
    TransitionPiCdrOptions options;
    options.initial_phase_ui = 0.5;
    options.max_symbols = 1;
    const TransitionPiCdrResult result = recover_transition_pi_cdr({}, 1.0, options);
    require(result.sample_centers_ui.size() == 1,
            "a center equal to last_x_ui must not be discarded");
    require(result.sample_centers_ui[0] == 1.0,
            "the final center must equal the record endpoint exactly");
    require(result.recovered_periods_ui.size() == 1 &&
                result.recovered_periods_ui[0] == 1.0,
            "endpoint equality must preserve the nominal period");
}

void test_ambiguous_gate_is_skipped_and_consumed() {
    TransitionPiCdrOptions options;
    options.max_symbols = 3;
    const std::vector<double> crossings{0.1, 0.2};
    const TransitionPiCdrResult result =
        recover_transition_pi_cdr(crossings, 2.0, options);
    require(result.ambiguous_gate_count == 1,
            "two crossings in one gate must count as one ambiguity");
    require(result.accepted_transition_count == 0,
            "ambiguous transitions must not update the loop later");
}

TransitionPiCdrResult duplicate_crossing_fixture() {
    const TransitionPiCdrOptions options;
    const std::vector<double> crossings{0.25, 0.25};
    return recover_transition_pi_cdr(crossings, 2.0, options);
}

void test_duplicate_crossings_preserve_ambiguity() {
    const TransitionPiCdrResult result = duplicate_crossing_fixture();
    require(result.detected_transition_count == 2,
            "coincident crossings must preserve their input multiplicity");
    require(result.ambiguous_gate_count == 1,
            "two coincident crossings must make the gate ambiguous");
    require(result.accepted_transition_count == 0,
            "coincident ambiguous crossings must not update the loop");
    require(result.sample_centers_ui == std::vector<double>({0.5, 1.5}),
            "an ambiguous duplicate event must leave the nominal clock in holdover");
}

void test_period_saturation() {
    TransitionPiCdrOptions options;
    options.proportional_gain = 0.5;
    options.integral_gain = 0.125;
    options.max_frequency_offset_ppm = 1'000.0;
    options.max_symbols = 2;
    const std::vector<double> crossings{0.4};
    const TransitionPiCdrResult result =
        recover_transition_pi_cdr(crossings, 1.0, options);
    const double maximum_period = 1.0 / (1.0 - 0.001);
    require(result.frequency_bound_hit_count == 1,
            "clipped proposal must increment the bound-hit counter");
    require_near(result.recovered_periods_ui[0], maximum_period, 1.0e-15,
                 "period must clip at the declared offset bound");
}

void test_malformed_inputs_fail_closed() {
    const auto defaults = TransitionPiCdrOptions{};
    require_rejected(
        [&] { (void)recover_values({0.2, 0.1}, 1.0, defaults); },
        "reversed crossings must be rejected");
    require_rejected(
        [&] {
            (void)recover_values(
                {std::numeric_limits<double>::quiet_NaN()}, 1.0, defaults);
        },
        "non-finite crossings must be rejected");
    require_rejected(
        [&] { (void)recover_values({-0.1}, 1.0, defaults); },
        "crossings before the normalized record must be rejected");
    require_rejected(
        [&] { (void)recover_values({1.1}, 1.0, defaults); },
        "crossings after the normalized record must be rejected");
    require_rejected(
        [&] { (void)recover_transition_pi_cdr({}, -1.0, defaults); },
        "negative last coordinate must be rejected");
    require_rejected(
        [&] {
            (void)recover_transition_pi_cdr(
                {}, std::numeric_limits<double>::infinity(), defaults);
        },
        "non-finite last coordinate must be rejected");

    TransitionPiCdrOptions invalid = defaults;
    invalid.initial_phase_ui = 1.0;
    require_rejected(
        [&] { (void)recover_transition_pi_cdr({}, 1.0, invalid); },
        "phase outside [0,1) must be rejected");
    invalid = defaults;
    invalid.proportional_gain = 0.0;
    require_rejected(
        [&] { (void)recover_transition_pi_cdr({}, 1.0, invalid); },
        "zero proportional gain must be rejected");
    invalid = defaults;
    invalid.integral_gain = invalid.proportional_gain / 4.0 + 0.001;
    require_rejected(
        [&] { (void)recover_transition_pi_cdr({}, 1.0, invalid); },
        "excess integral gain must be rejected");
    invalid = defaults;
    invalid.integral_gain = 0.0;
    require_rejected(
        [&] { (void)recover_transition_pi_cdr({}, 1.0, invalid); },
        "zero integral gain must be rejected");
    invalid = defaults;
    invalid.max_frequency_offset_ppm = 100'001.0;
    require_rejected(
        [&] { (void)recover_transition_pi_cdr({}, 1.0, invalid); },
        "excess offset bound must be rejected");
    invalid = defaults;
    invalid.max_frequency_offset_ppm = 0.0;
    require_rejected(
        [&] { (void)recover_transition_pi_cdr({}, 1.0, invalid); },
        "zero offset bound must be rejected");
    invalid = defaults;
    invalid.max_symbols = 0;
    require_rejected(
        [&] { (void)recover_transition_pi_cdr({}, 1.0, invalid); },
        "zero output budget must be rejected");
    invalid = defaults;
    invalid.max_symbols = spike::si::kTransitionPiCdrMaxSymbols + 1;
    require_rejected(
        [&] { (void)recover_transition_pi_cdr({}, 1.0, invalid); },
        "excess output budget must be rejected");
    invalid = defaults;
    invalid.max_symbols = 2;
    require_rejected(
        [&] { (void)recover_transition_pi_cdr({}, 4.0, invalid); },
        "an interval beyond the declared budget must be rejected");

    const std::vector<double> excessive_crossings(
        spike::si::kTransitionPiCdrMaxCrossings + 1, 0.0);
    require_rejected(
        [&] {
            (void)recover_transition_pi_cdr(excessive_crossings, 1.0, defaults);
        },
        "excess crossing storage must be rejected before content traversal");
}

void test_output_budget_fails_closed() {
    TransitionPiCdrOptions options;
    options.max_symbols = 1;
    require_rejected(
        [&] { (void)recover_transition_pi_cdr({}, 2.0, options); },
        "a second recovered center must fail rather than truncate");
}

TransitionPiCdrResult parity_fixture() {
    TransitionPiCdrOptions options;
    options.initial_phase_ui = 0.13;
    options.proportional_gain = 0.24;
    options.integral_gain = 0.03;
    options.max_frequency_offset_ppm = 20'000.0;
    options.max_symbols = 8;
    const std::vector<double> crossings{0.09, 1.08, 1.11, 2.17, 3.22, 4.20,
                                        5.26, 6.30, 7.31};
    return recover_transition_pi_cdr(crossings, 7.8, options);
}

void write_array(std::ostream& output, std::span<const double> values) {
    output << '[';
    for (std::size_t index = 0; index < values.size(); ++index) {
        if (index != 0) {
            output << ',';
        }
        output << values[index];
    }
    output << ']';
}

void dump_result_json(const TransitionPiCdrResult& result) {
    std::cout << std::setprecision(17) << '{';
    std::cout << "\"centers\":";
    write_array(std::cout, result.sample_centers_ui);
    std::cout << ",\"periods\":";
    write_array(std::cout, result.recovered_periods_ui);
    std::cout << ",\"errors\":";
    write_array(std::cout, result.phase_errors_ui);
    std::cout << ",\"accepted\":";
    write_array(std::cout, result.accepted_crossings_ui);
    std::cout << ",\"detected_transition_count\":"
              << result.detected_transition_count;
    std::cout << ",\"accepted_transition_count\":"
              << result.accepted_transition_count;
    std::cout << ",\"ambiguous_gate_count\":" << result.ambiguous_gate_count;
    std::cout << ",\"frequency_bound_hit_count\":"
              << result.frequency_bound_hit_count << "}\n";
}

void dump_parity_json() {
    dump_result_json(parity_fixture());
}

void dump_duplicate_parity_json() {
    dump_result_json(duplicate_crossing_fixture());
}

void run_benchmark(std::size_t symbol_count) {
    if (symbol_count == 0 ||
        symbol_count > spike::si::kTransitionPiCdrMaxSymbols) {
        fail("benchmark symbol count is outside [1, 65536]");
    }
    std::vector<double> crossings;
    crossings.reserve(symbol_count);
    for (std::size_t index = 0; index < symbol_count; ++index) {
        const double cycle = static_cast<double>(index % 17U) - 8.0;
        crossings.push_back(static_cast<double>(index) + 0.08 + cycle * 0.001);
    }
    TransitionPiCdrOptions options;
    options.initial_phase_ui = 0.08;
    options.proportional_gain = 0.2;
    options.integral_gain = 0.002;
    options.max_frequency_offset_ppm = 10'000.0;
    options.max_symbols = symbol_count;
    const double last_x_ui = static_cast<double>(symbol_count) - 0.01;

    const auto warmup = recover_transition_pi_cdr(crossings, last_x_ui, options);
    std::size_t checksum = warmup.sample_centers_ui.size();
    std::vector<double> milliseconds;
    milliseconds.reserve(5);
    for (int repeat = 0; repeat < 5; ++repeat) {
        const auto start = std::chrono::steady_clock::now();
        const auto result =
            recover_transition_pi_cdr(crossings, last_x_ui, options);
        const auto stop = std::chrono::steady_clock::now();
        checksum = checksum + result.sample_centers_ui.size() +
                   result.accepted_transition_count;
        const std::chrono::duration<double, std::milli> elapsed = stop - start;
        milliseconds.push_back(elapsed.count());
    }

    std::cout << std::setprecision(17) << "{\"symbols\":" << symbol_count
              << ",\"warmup_runs\":1,\"measured_runs\":5,\"milliseconds\":";
    write_array(std::cout, milliseconds);
    std::cout << ",\"checksum\":" << checksum << "}\n";
}

void run_tests() {
    test_hand_calculated_update();
    test_no_transition_free_run();
    test_inclusive_right_gate_and_consumption();
    test_inclusive_left_gate();
    test_gate_edges_one_ulp_inside_and_outside();
    test_center_equal_to_record_end_is_retained();
    test_ambiguous_gate_is_skipped_and_consumed();
    test_duplicate_crossings_preserve_ambiguity();
    test_period_saturation();
    test_malformed_inputs_fail_closed();
    test_output_budget_fails_closed();
    const TransitionPiCdrResult fixture = parity_fixture();
    require(!fixture.sample_centers_ui.empty(), "parity fixture must exercise output");
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc == 1) {
            run_tests();
            std::cout << "transition_pi_cdr standalone tests passed\n";
            return EXIT_SUCCESS;
        }
        if (argc == 2 && std::string_view{argv[1]} == "--dump-parity") {
            dump_parity_json();
            return EXIT_SUCCESS;
        }
        if (argc == 2 &&
            std::string_view{argv[1]} == "--dump-duplicate-parity") {
            dump_duplicate_parity_json();
            return EXIT_SUCCESS;
        }
        if (argc == 3 && std::string_view{argv[1]} == "--benchmark") {
            const unsigned long parsed = std::stoul(argv[2]);
            run_benchmark(static_cast<std::size_t>(parsed));
            return EXIT_SUCCESS;
        }
        std::cerr << "usage: test_si_transition_pi_cdr "
                     "[--dump-parity | --dump-duplicate-parity | "
                     "--benchmark SYMBOLS]\n";
        return EXIT_FAILURE;
    } catch (const std::exception& error) {
        std::cerr << "failure: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
