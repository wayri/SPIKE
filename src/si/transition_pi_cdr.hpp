// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
#pragma once

#include <cstddef>
#include <span>
#include <stdexcept>
#include <vector>

namespace spike::si {

inline constexpr std::size_t kTransitionPiCdrMaxSymbols = 65'536;
inline constexpr std::size_t kTransitionPiCdrMaxCrossings = 1'048'575;

struct TransitionPiCdrOptions {
    double initial_phase_ui = 0.0;
    double proportional_gain = 0.2;
    double integral_gain = 0.002;
    double max_frequency_offset_ppm = 10'000.0;
    std::size_t max_symbols = kTransitionPiCdrMaxSymbols;
};

struct TransitionPiCdrResult {
    std::vector<double> sample_centers_ui;
    std::vector<double> recovered_periods_ui;
    std::vector<double> phase_errors_ui;
    std::vector<double> accepted_crossings_ui;
    std::size_t detected_transition_count = 0;
    std::size_t accepted_transition_count = 0;
    std::size_t ambiguous_gate_count = 0;
    std::size_t frequency_bound_hit_count = 0;
};

class TransitionPiCdrError final : public std::invalid_argument {
  public:
    using std::invalid_argument::invalid_argument;
};

// Recover sample centers from finite, non-decreasing detected transition
// coordinates normalized to unit intervals (UI). Coincident crossings retain
// their multiplicity so that the timing gate can classify them as ambiguous.
// This bounded behavioral reference kernel does not detect crossings, establish
// protocol lock, or qualify a receiver.
[[nodiscard]] TransitionPiCdrResult recover_transition_pi_cdr(
    std::span<const double> crossings_ui,
    double last_x_ui,
    const TransitionPiCdrOptions& options = {});

}  // namespace spike::si
