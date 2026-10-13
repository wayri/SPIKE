// SPDX-License-Identifier: Apache-2.0
// Original correctness, concurrency, allocation, and performance qualification.
#include "spikes/behavioral_expression.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <functional>
#include <iomanip>
#include <iostream>
#include <new>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {

std::atomic<std::size_t> allocation_count{};

void require(bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

void near(double actual, double expected, double relative_tolerance, const char* message) {
    const double scale = std::max({1.0, std::abs(actual), std::abs(expected)});
    require(std::isfinite(actual) && std::abs(actual - expected) <= relative_tolerance * scale, message);
}

// This is the pre-optimization implementation retained only as a test oracle
// and benchmark baseline. Production code does not call it.
class LegacyBehavioralProgram {
    struct Node {
        std::string op;
        int a;
        int b;
        int c;
        double value;
    };
    std::vector<Node> nodes_;

public:
    explicit LegacyBehavioralProgram(const std::string& text) {
        std::istringstream input(text);
        Node n;
        while (input >> n.op) {
            if (!(input >> n.a >> n.b >> n.c >> n.value) || !std::isfinite(n.value)) {
                throw std::invalid_argument("invalid behavioral instruction");
            }
            nodes_.push_back(n);
        }
    }

    spikes::BehavioralValue evaluate(const std::vector<double>& signals, double time = 0.0) const {
        std::vector<spikes::BehavioralValue> cache(nodes_.size());
        std::vector<bool> ready(nodes_.size(), false);
        std::function<spikes::BehavioralValue(int)> eval = [&](int i) -> spikes::BehavioralValue {
            if (ready[i]) {
                return cache[i];
            }
            const auto& n = nodes_[i];
            spikes::BehavioralValue r;
            if (n.op == "const") {
                r.value = n.value;
            } else if (n.op == "time") {
                r.value = time;
            } else if (n.op == "signal") {
                const auto k = static_cast<std::size_t>(n.value);
                r.value = signals.at(k);
                r.gradient[k] = 1.0;
            } else {
                const auto a = eval(n.a);
                const double x = a.value;
                if (n.op == "if") {
                    r = eval(x != 0.0 ? n.b : n.c);
                } else {
                    const auto b = n.b >= 0 ? eval(n.b) : spikes::BehavioralValue{};
                    const double y = b.value;
                    double da = 0.0;
                    double db = 0.0;
                    if (n.op == "limit") {
                        const auto c = eval(n.c);
                        if (y >= c.value) {
                            throw std::invalid_argument("limit lower bound must be smaller");
                        }
                        r = x < y ? b : (x > c.value ? c : a);
                    } else {
                        if (n.op == "add") { r.value = x + y; da = 1.0; db = 1.0; }
                        else if (n.op == "sub") { r.value = x - y; da = 1.0; db = -1.0; }
                        else if (n.op == "mul") { r.value = x * y; da = y; db = x; }
                        else if (n.op == "div") { r.value = x / y; da = 1.0 / y; db = -x / (y * y); }
                        else if (n.op == "mod") { r.value = x - std::floor(x / y) * y; da = 1.0; db = -std::floor(x / y); }
                        else if (n.op == "pow") {
                            r.value = std::pow(x, y);
                            da = y == 0.0 ? 0.0 : y * std::pow(x, y - 1.0);
                            if (x > 0.0) {
                                db = r.value * std::log(x);
                            } else if (std::any_of(b.gradient.begin(), b.gradient.end(), [](double d) { return d != 0.0; })) {
                                throw std::invalid_argument("nonpositive power base with variable exponent");
                            }
                        }
                        else if (n.op == "max" || n.op == "min") { r = (n.op == "max" ? x >= y : x <= y) ? a : b; }
                        else if (n.op == "gt" || n.op == "ge" || n.op == "lt" || n.op == "le") {
                            r.value = n.op == "gt" ? x > y : n.op == "ge" ? x >= y : n.op == "lt" ? x < y : x <= y;
                        }
                        else if (n.op == "atan2") { r.value = std::atan2(x, y); da = y / (x * x + y * y); db = -x / (x * x + y * y); }
                        else if (n.op == "hypot") { r.value = std::hypot(x, y); da = r.value == 0.0 ? 0.0 : x / r.value; db = r.value == 0.0 ? 0.0 : y / r.value; }
                        else if (n.op == "neg") { r.value = -x; da = -1.0; }
                        else if (n.op == "abs") { r.value = std::abs(x); da = x > 0.0 ? 1.0 : x < 0.0 ? -1.0 : 0.0; }
                        else if (n.op == "sin") { r.value = std::sin(x); da = std::cos(x); }
                        else if (n.op == "cos") { r.value = std::cos(x); da = -std::sin(x); }
                        else if (n.op == "tan") { r.value = std::tan(x); da = 1.0 + r.value * r.value; }
                        else if (n.op == "atanh") {
                            if (std::abs(x) >= 1.0) throw std::invalid_argument("atanh requires absolute argument below one");
                            r.value = std::atanh(x); da = 1.0 / (1.0 - x * x);
                        }
                        else if (n.op == "sinh") { r.value = std::sinh(x); da = std::cosh(x); }
                        else if (n.op == "cosh") { r.value = std::cosh(x); da = std::sinh(x); }
                        else if (n.op == "tanh") { r.value = std::tanh(x); da = 1.0 - r.value * r.value; }
                        else if (n.op == "exp") { r.value = std::exp(x); da = r.value; }
                        else if (n.op == "log" || n.op == "log10") { r.value = n.op == "log" ? std::log(x) : std::log10(x); da = (n.op == "log" ? 1.0 : 1.0 / std::log(10.0)) / x; }
                        else if (n.op == "sqrt") { r.value = std::sqrt(x); da = 0.5 / r.value; }
                        else if (n.op == "atan") { r.value = std::atan(x); da = 1.0 / (1.0 + x * x); }
                        else if (n.op == "asin") { r.value = std::asin(x); da = 1.0 / std::sqrt(1.0 - x * x); }
                        else if (n.op == "acos") { r.value = std::acos(x); da = -1.0 / std::sqrt(1.0 - x * x); }
                        else if (n.op == "asinh") { r.value = std::asinh(x); da = 1.0 / std::sqrt(1.0 + x * x); }
                        else if (n.op == "acosh") { r.value = std::acosh(x); da = 1.0 / std::sqrt(x * x - 1.0); }
                        else if (n.op == "floor") r.value = std::floor(x);
                        else if (n.op == "ceil") r.value = std::ceil(x);
                        else if (n.op == "int") r.value = std::trunc(x);
                        else if (n.op == "sgn") r.value = x > 0.0 ? 1.0 : x < 0.0 ? -1.0 : 0.0;
                        else if (n.op == "u") r.value = x >= 0.0 ? 1.0 : 0.0;
                        else if (n.op == "uramp") { r.value = std::max(0.0, x); da = x > 0.0 ? 1.0 : 0.0; }
                        for (std::size_t k = 0; k < signals.size(); ++k) {
                            r.gradient[k] += (a.gradient[k] == 0.0 ? 0.0 : da * a.gradient[k])
                                + (b.gradient[k] == 0.0 ? 0.0 : db * b.gradient[k]);
                        }
                    }
                }
            }
            if (!std::isfinite(r.value)
                || std::any_of(r.gradient.begin(), r.gradient.end(), [](double d) { return !std::isfinite(d); })) {
                throw std::invalid_argument("behavioral value/derivative outside finite mathematical domain");
            }
            ready[i] = true;
            return cache[i] = r;
        };
        return eval(static_cast<int>(nodes_.size() - 1));
    }
};

struct ProgramBuilder {
    std::ostringstream text;
    int count{};

    int node(const char* op, int a = -1, int b = -1, int c = -1, double value = 0.0) {
        text << op << ' ' << a << ' ' << b << ' ' << c << ' ' << std::setprecision(17) << value << '\n';
        return count++;
    }
};

std::string benchmark_program_text() {
    ProgramBuilder p;
    const int s0 = p.node("signal", -1, -1, -1, 0.0);
    const int s1 = p.node("signal", -1, -1, -1, 1.0);
    const int s2 = p.node("signal", -1, -1, -1, 2.0);
    const int s3 = p.node("signal", -1, -1, -1, 3.0);
    const int time = p.node("time");
    const int zero = p.node("const", -1, -1, -1, 0.0);
    const int one = p.node("const", -1, -1, -1, 1.0);
    const int scale = p.node("const", -1, -1, -1, 0.035);
    int value = p.node("add", s0, s1);
    for (int iteration = 0; iteration < 16; ++iteration) {
        const int scaled = p.node("mul", value, scale);
        const int sine = p.node("sin", scaled);
        const int cosine = p.node("cos", s1);
        const int product = p.node("mul", sine, cosine);
        const int magnitude = p.node("hypot", s2, s3);
        const int positive = p.node("add", magnitude, one);
        const int logarithm = p.node("log", positive);
        const int nonlinear = p.node("add", product, logarithm);
        const int timed = p.node("add", time, scaled);
        const int bounded = p.node("tanh", timed);
        const int condition = p.node("gt", s0, zero);
        const int selected = p.node("if", condition, nonlinear, bounded);
        value = p.node("add", value, selected);
    }
    return p.text.str();
}

void compare_values(const spikes::BehavioralValue& actual,
                    const spikes::BehavioralValue& expected,
                    std::size_t signal_count) {
    require(actual.value == expected.value, "optimized value differs from legacy evaluator");
    for (std::size_t i = 0; i < signal_count; ++i) {
        require(actual.gradient[i] == expected.gradient[i], "optimized gradient differs from legacy evaluator");
    }
}

void all_opcode_legacy_equivalence() {
    const auto check = [](const std::string& text, const std::vector<double>& signals, double time) {
        const spikes::BehavioralProgram optimized(text);
        const LegacyBehavioralProgram legacy(text);
        compare_values(optimized.evaluate(signals, time), legacy.evaluate(signals, time), signals.size());
    };
    check("const -1 -1 -1 2.5\n", {}, 0.3);
    check("time -1 -1 -1 0\n", {}, 0.3);
    check("signal -1 -1 -1 0\n", {0.25}, 0.3);

    const std::array<const char*, 21> ordinary_unary{
        "neg", "abs", "asin", "asinh", "atan", "atanh", "cos", "cosh", "ceil",
        "exp", "floor", "int", "sgn", "sin", "sinh", "tan", "tanh", "u", "uramp",
        "acos", "sqrt",
    };
    for (const char* op : ordinary_unary) {
        check(std::string("signal -1 -1 -1 0\n") + op + " 0 -1 -1 0\n", {0.25}, 0.3);
    }
    for (const char* op : {"acosh", "log", "log10"}) {
        check(std::string("signal -1 -1 -1 0\n") + op + " 0 -1 -1 0\n", {2.0}, 0.3);
    }

    const std::array<const char*, 14> binary{
        "add", "sub", "mul", "div", "mod", "pow", "atan2", "hypot", "max", "min",
        "gt", "ge", "lt", "le",
    };
    for (const char* op : binary) {
        check(std::string("signal -1 -1 -1 0\nsignal -1 -1 -1 1\n") + op + " 0 1 -1 0\n",
              {0.75, 1.25}, 0.3);
    }
    check("signal -1 -1 -1 0\nconst -1 -1 -1 -1\nconst -1 -1 -1 1\nlimit 0 1 2 0\n", {0.25}, 0.3);
    check("signal -1 -1 -1 0\nconst -1 -1 -1 2\nconst -1 -1 -1 3\nif 0 1 2 0\n", {1.0}, 0.3);
    check("signal -1 -1 -1 0\nconst -1 -1 -1 2\nconst -1 -1 -1 3\nif 0 1 2 0\n", {0.0}, 0.3);
}

void legacy_equivalence_and_finite_difference() {
    const auto text = benchmark_program_text();
    const spikes::BehavioralProgram optimized(text);
    const LegacyBehavioralProgram legacy(text);
    for (int iteration = 0; iteration < 256; ++iteration) {
        std::vector<double> signals{
            (iteration & 1) == 0 ? 0.3 + iteration * 1.0e-4 : -0.4 - iteration * 1.0e-4,
            -0.6 + iteration * 2.0e-4,
            0.7 + iteration * 3.0e-4,
            -0.8 + iteration * 1.0e-4,
        };
        const double time = 1.0e-3 * iteration;
        compare_values(optimized.evaluate(signals, time), legacy.evaluate(signals, time), signals.size());
    }

    const std::string analytical =
        "signal -1 -1 -1 0\n"
        "sin 0 -1 -1 0\n"
        "signal -1 -1 -1 1\n"
        "exp 2 -1 -1 0\n"
        "mul 1 3 -1 0\n"
        "signal -1 -1 -1 2\n"
        "signal -1 -1 -1 3\n"
        "hypot 5 6 -1 0\n"
        "add 4 7 -1 0\n"
        "time -1 -1 -1 0\n"
        "tanh 9 -1 -1 0\n"
        "add 8 10 -1 0\n";
    const spikes::BehavioralProgram program(analytical);
    std::vector<double> signals{0.37, -0.21, 3.0, 4.0};
    const auto result = program.evaluate(signals, 0.4);
    const double expected = std::sin(signals[0]) * std::exp(signals[1]) + 5.0 + std::tanh(0.4);
    near(result.value, expected, 2.0e-15, "analytical value oracle");
    near(result.gradient[0], std::cos(signals[0]) * std::exp(signals[1]), 2.0e-15, "analytical x gradient");
    near(result.gradient[1], std::sin(signals[0]) * std::exp(signals[1]), 2.0e-15, "analytical y gradient");
    near(result.gradient[2], 3.0 / 5.0, 2.0e-15, "analytical hypot x gradient");
    near(result.gradient[3], 4.0 / 5.0, 2.0e-15, "analytical hypot y gradient");
    for (std::size_t signal = 0; signal < signals.size(); ++signal) {
        constexpr double step = 1.0e-6;
        auto lower = signals;
        auto upper = signals;
        lower[signal] -= step;
        upper[signal] += step;
        const double finite_difference = (program.evaluate(upper, 0.4).value - program.evaluate(lower, 0.4).value) / (2.0 * step);
        near(result.gradient[signal], finite_difference, 2.0e-9, "finite-difference gradient oracle");
    }
}

template <typename Function>
void rejected(Function&& function, const char* message) {
    try {
        function();
    } catch (const std::invalid_argument&) {
        return;
    }
    throw std::runtime_error(message);
}

void lazy_branch_and_domain_errors() {
    const spikes::BehavioralProgram lazy(
        "signal -1 -1 -1 0\n"
        "const -1 -1 -1 -1\n"
        "log 1 -1 -1 0\n"
        "const -1 -1 -1 7\n"
        "if 0 3 2 0\n");
    near(lazy.evaluate({1.0}).value, 7.0, 0.0, "inactive invalid branch was evaluated");
    rejected([&] { (void)lazy.evaluate({0.0}); }, "active invalid branch was admitted");

    const spikes::BehavioralProgram atanh_domain(
        "signal -1 -1 -1 0\n"
        "atanh 0 -1 -1 0\n");
    rejected([&] { (void)atanh_domain.evaluate({1.0}); }, "atanh endpoint was admitted");

    const spikes::BehavioralProgram invalid_limit(
        "signal -1 -1 -1 0\n"
        "const -1 -1 -1 2\n"
        "const -1 -1 -1 1\n"
        "limit 0 1 2 0\n");
    rejected([&] { (void)invalid_limit.evaluate({1.5}); }, "reversed limit bounds were admitted");

    const spikes::BehavioralProgram invalid_power(
        "const -1 -1 -1 -2\n"
        "signal -1 -1 -1 0\n"
        "pow 0 1 -1 0\n");
    rejected([&] { (void)invalid_power.evaluate({2.0}); }, "variable exponent on negative base was admitted");
}

void thread_safety_and_program_isolation() {
    const spikes::BehavioralProgram first(benchmark_program_text());
    const spikes::BehavioralProgram second(
        "signal -1 -1 -1 0\n"
        "signal -1 -1 -1 1\n"
        "mul 0 1 -1 0\n"
        "time -1 -1 -1 0\n"
        "add 2 3 -1 0\n");
    std::atomic<bool> valid{true};
    std::array<std::thread, 4> workers;
    for (std::size_t worker = 0; worker < workers.size(); ++worker) {
        workers[worker] = std::thread([&, worker] {
            std::vector<double> signals{0.2 + 0.1 * worker, -0.4 - 0.05 * worker, 0.8, -0.7};
            const double time = 0.01 * static_cast<double>(worker + 1);
            const auto expected_first = first.evaluate(signals, time);
            const auto expected_second = second.evaluate(signals, time);
            for (int iteration = 0; iteration < 2000; ++iteration) {
                const auto a = first.evaluate(signals, time);
                const auto b = second.evaluate(signals, time);
                if (a.value != expected_first.value || b.value != expected_second.value
                    || a.gradient[0] != expected_first.gradient[0]
                    || b.gradient[1] != expected_second.gradient[1]) {
                    valid.store(false, std::memory_order_relaxed);
                    return;
                }
            }
        });
    }
    for (auto& worker : workers) {
        worker.join();
    }
    require(valid.load(std::memory_order_relaxed), "thread-local evaluation state leaked across programs or threads");
}

template <typename Program>
double timed_run(const Program& program, int repetitions, double& checksum) {
    std::vector<double> signals{0.31, -0.47, 0.82, -0.63};
    double sum = 0.0;
    const auto start = std::chrono::steady_clock::now();
    for (int iteration = 0; iteration < repetitions; ++iteration) {
        signals[0] = (iteration & 1) == 0 ? 0.31 + iteration * 1.0e-8 : -0.29 - iteration * 1.0e-8;
        signals[1] += 1.0e-9;
        const auto result = program.evaluate(signals, iteration * 1.0e-7);
        sum += result.value + result.gradient[0] * 1.0e-6;
    }
    const auto elapsed = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count();
    checksum += sum;
    return elapsed;
}

struct TimingSummary {
    double mean_ms{};
    double standard_deviation_ms{};
    double minimum_ms{};
    double maximum_ms{};
};

TimingSummary summarize(const std::array<double, 5>& times) {
    TimingSummary result;
    result.mean_ms = std::accumulate(times.begin(), times.end(), 0.0) / times.size();
    result.minimum_ms = *std::min_element(times.begin(), times.end());
    result.maximum_ms = *std::max_element(times.begin(), times.end());
    for (const double time : times) {
        result.standard_deviation_ms += (time - result.mean_ms) * (time - result.mean_ms);
    }
    result.standard_deviation_ms = std::sqrt(result.standard_deviation_ms / times.size());
    return result;
}

void allocation_and_speed_evidence() {
    const auto text = benchmark_program_text();
    const spikes::BehavioralProgram optimized(text);
    const LegacyBehavioralProgram legacy(text);
    const std::vector<double> signals{0.31, -0.47, 0.82, -0.63};
    (void)optimized.evaluate(signals, 0.01);
    (void)legacy.evaluate(signals, 0.01);

    const auto before_optimized = allocation_count.load(std::memory_order_relaxed);
    for (int iteration = 0; iteration < 100; ++iteration) {
        (void)optimized.evaluate(signals, iteration * 1.0e-6);
    }
    const auto optimized_allocations = allocation_count.load(std::memory_order_relaxed) - before_optimized;
    const auto before_legacy = allocation_count.load(std::memory_order_relaxed);
    for (int iteration = 0; iteration < 100; ++iteration) {
        (void)legacy.evaluate(signals, iteration * 1.0e-6);
    }
    const auto legacy_allocations = allocation_count.load(std::memory_order_relaxed) - before_legacy;
    constexpr int repetitions = 10000;
    std::array<double, 5> optimized_times{};
    std::array<double, 5> legacy_times{};
    double optimized_checksum = 0.0;
    double legacy_checksum = 0.0;
    for (std::size_t trial = 0; trial < optimized_times.size(); ++trial) {
        if ((trial & 1U) == 0U) {
            legacy_times[trial] = timed_run(legacy, repetitions, legacy_checksum);
            optimized_times[trial] = timed_run(optimized, repetitions, optimized_checksum);
        } else {
            optimized_times[trial] = timed_run(optimized, repetitions, optimized_checksum);
            legacy_times[trial] = timed_run(legacy, repetitions, legacy_checksum);
        }
    }
    require(optimized_checksum == legacy_checksum, "benchmark workload diverged from legacy evaluator");
    const auto optimized_summary = summarize(optimized_times);
    const auto legacy_summary = summarize(legacy_times);
    std::cout << std::fixed << std::setprecision(3)
              << "Behavioral benchmark (5 trials x " << repetitions << " evaluations, "
              << "strict FP, " << 217 << " nodes): legacy "
              << legacy_summary.mean_ms << " ms +/- " << legacy_summary.standard_deviation_ms
              << " [" << legacy_summary.minimum_ms << ", " << legacy_summary.maximum_ms << "], optimized "
              << optimized_summary.mean_ms << " ms +/- " << optimized_summary.standard_deviation_ms
              << " [" << optimized_summary.minimum_ms << ", " << optimized_summary.maximum_ms << "], speedup "
              << legacy_summary.mean_ms / optimized_summary.mean_ms << "x; warm allocations "
              << legacy_allocations << " -> " << optimized_allocations << " per 100 evaluations\n";
    require(optimized_allocations == 0, "optimized evaluation allocated after thread-local scratch warm-up");
    require(legacy_allocations >= 200, "legacy allocation counter did not observe both per-call vectors");
}

} // namespace

void* operator new(std::size_t size) {
    allocation_count.fetch_add(1, std::memory_order_relaxed);
    if (void* memory = std::malloc(size)) {
        return memory;
    }
    throw std::bad_alloc();
}

void* operator new[](std::size_t size) {
    return ::operator new(size);
}

void operator delete(void* memory) noexcept {
    std::free(memory);
}

void operator delete[](void* memory) noexcept {
    std::free(memory);
}

void operator delete(void* memory, std::size_t) noexcept {
    std::free(memory);
}

void operator delete[](void* memory, std::size_t) noexcept {
    std::free(memory);
}

int main() {
    try {
        all_opcode_legacy_equivalence();
        legacy_equivalence_and_finite_difference();
        lazy_branch_and_domain_errors();
        thread_safety_and_program_isolation();
        allocation_and_speed_evidence();
        std::cout << "Native behavioral evaluator tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Native behavioral evaluator test failed: " << error.what() << '\n';
        return 1;
    }
}
