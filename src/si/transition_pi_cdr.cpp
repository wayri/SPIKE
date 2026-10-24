// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
#include "src/si/transition_pi_cdr.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <string>

namespace spike::si {
namespace {

static_assert(std::numeric_limits<double>::is_iec559,
              "transition PI CDR requires IEEE-754 binary64");

[[noreturn]] void reject(const char* message) {
    throw TransitionPiCdrError(message);
}

void require_finite(double value, const char* name) {
    if (!std::isfinite(value)) {
        throw TransitionPiCdrError(std::string{name} + " must be finite");
    }
}

void validate_input(std::span<const double> crossings_ui,
                    double last_x_ui,
                    const TransitionPiCdrOptions& options) {
    require_finite(last_x_ui, "last_x_ui");
    require_finite(options.initial_phase_ui, "initial_phase_ui");
    require_finite(options.proportional_gain, "proportional_gain");
    require_finite(options.integral_gain, "integral_gain");
    require_finite(options.max_frequency_offset_ppm,
                   "max_frequency_offset_ppm");

    if (last_x_ui < 0.0) {
        reject("last_x_ui must be non-negative");
    }
    if (options.initial_phase_ui < 0.0 || options.initial_phase_ui >= 1.0) {
        reject("initial_phase_ui must be in [0, 1)");
    }
    if (options.proportional_gain <= 0.0 ||
        options.proportional_gain > 0.5) {
        reject("proportional_gain must be in (0, 0.5]");
    }
    if (options.integral_gain <= 0.0 ||
        options.integral_gain > options.proportional_gain / 4.0) {
        reject("integral_gain must be in (0, proportional_gain / 4]");
    }
    if (options.max_frequency_offset_ppm <= 0.0 ||
        options.max_frequency_offset_ppm > 100'000.0) {
        reject("max_frequency_offset_ppm must be in (0, 100000]");
    }
    if (options.max_symbols == 0 ||
        options.max_symbols > kTransitionPiCdrMaxSymbols) {
        reject("max_symbols must be in [1, 65536]");
    }
    if (crossings_ui.size() > kTransitionPiCdrMaxCrossings) {
        reject("crossing count exceeds the bounded input limit");
    }

    double previous = -1.0;
    for (const double crossing : crossings_ui) {
        require_finite(crossing, "crossing coordinate");
        if (crossing < 0.0 || crossing > last_x_ui) {
            reject("crossing coordinates must lie in [0, last_x_ui]");
        }
        if (crossing < previous) {
            reject("crossing coordinates must be non-decreasing");
        }
        previous = crossing;
    }
}

void require_finite_state(double value) {
    if (!std::isfinite(value)) {
        reject("transition PI CDR state overflowed");
    }
}

}  // namespace

TransitionPiCdrResult recover_transition_pi_cdr(
    std::span<const double> crossings_ui,
    double last_x_ui,
    const TransitionPiCdrOptions& options) {
    validate_input(crossings_ui, last_x_ui, options);

    const double relative_bound = options.max_frequency_offset_ppm * 1.0e-6;
    const double minimum_period = 1.0 / (1.0 + relative_bound);
    const double maximum_period = 1.0 / (1.0 - relative_bound);
    require_finite_state(minimum_period);
    require_finite_state(maximum_period);

    const double bounded_interval =
        (static_cast<double>(options.max_symbols) + 1.0) * maximum_period;
    require_finite_state(bounded_interval);
    if (last_x_ui > bounded_interval) {
        reject("requested interval exceeds the bounded symbol budget");
    }

    TransitionPiCdrResult result;
    result.detected_transition_count = crossings_ui.size();
    if (options.max_symbols > result.sample_centers_ui.max_size() ||
        options.max_symbols > result.recovered_periods_ui.max_size()) {
        reject("requested output allocation is not representable");
    }
    const std::size_t event_capacity = std::min(
        crossings_ui.size(), options.max_symbols + std::size_t{1});
    if (event_capacity > result.phase_errors_ui.max_size() ||
        event_capacity > result.accepted_crossings_ui.max_size()) {
        reject("requested event allocation is not representable");
    }
    result.sample_centers_ui.reserve(options.max_symbols);
    result.recovered_periods_ui.reserve(options.max_symbols);
    result.phase_errors_ui.reserve(event_capacity);
    result.accepted_crossings_ui.reserve(event_capacity);

    double boundary = options.initial_phase_ui;
    double period = 1.0;
    std::size_t next_crossing = 0;

    while (boundary + 0.5 * minimum_period <= last_x_ui) {
        require_finite_state(boundary);
        require_finite_state(period);
        const double gate_left = boundary - 0.45 * period;
        const double gate_right = boundary + 0.45 * period;
        require_finite_state(gate_left);
        require_finite_state(gate_right);

        const auto begin = crossings_ui.begin();
        const auto end = crossings_ui.end();
        const auto left_search =
            std::lower_bound(begin + static_cast<std::ptrdiff_t>(next_crossing),
                             end,
                             gate_left);
        const std::size_t left = static_cast<std::size_t>(left_search - begin);
        const auto right_search = std::upper_bound(left_search, end, gate_right);
        const std::size_t right = static_cast<std::size_t>(right_search - begin);
        const std::size_t gated_count = right - left;

        if (gated_count == 1) {
            if (result.phase_errors_ui.size() >=
                options.max_symbols + std::size_t{1}) {
                reject("accepted event count exceeds the bounded symbol budget");
            }
            const double error = crossings_ui[left] - boundary;
            const double proposed_period = period + options.integral_gain * error;
            require_finite_state(error);
            require_finite_state(proposed_period);
            const double clipped_period =
                std::clamp(proposed_period, minimum_period, maximum_period);
            if (clipped_period != proposed_period) {
                ++result.frequency_bound_hit_count;
            }
            period = clipped_period;
            boundary += options.proportional_gain * error;
            require_finite_state(boundary);
            result.phase_errors_ui.push_back(error);
            result.accepted_crossings_ui.push_back(crossings_ui[left]);
        } else if (gated_count > 1) {
            ++result.ambiguous_gate_count;
        }
        next_crossing = std::max(next_crossing, right);

        const double center = boundary + 0.5 * period;
        require_finite_state(center);
        if (center > last_x_ui) {
            break;
        }
        if (center >= 0.0) {
            if (result.sample_centers_ui.size() >= options.max_symbols) {
                reject("recovered symbol count exceeds max_symbols");
            }
            result.sample_centers_ui.push_back(center);
            result.recovered_periods_ui.push_back(period);
        }
        boundary += period;
        require_finite_state(boundary);
    }

    result.accepted_transition_count = result.accepted_crossings_ui.size();
    return result;
}

}  // namespace spike::si
