/**
 * @file console_dashboard.hpp
 * @brief Compiled interactive monitoring surface for the SPIKES native core.
 */

#pragma once

#include "spikes/transient_session.hpp"

#include <cstddef>
#include <deque>
#include <iosfwd>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace spikes {

enum class DashboardProbeKind {
  node_voltage,
  element_voltage,
  element_current,
  element_power,
  temperature,
  failure_proximity,
};

struct FailureLimits {
  std::optional<double> maximum_absolute_voltage_v;
  std::optional<double> maximum_absolute_current_a;
  std::optional<double> maximum_power_w;
  std::optional<double> maximum_temperature_k;
  std::string thermal_node;
  double ambient_temperature_k{300.15};
  double warning_fraction{0.8};
};

struct DashboardProbe {
  std::string name;
  DashboardProbeKind kind{DashboardProbeKind::node_voltage};
  std::string target;
  FailureLimits limits{};
};

struct DashboardControl {
  std::string key;
  std::string source_id;
  double low_value{0.0};
  double high_value{1.0};
  bool high{false};
};

struct ConsoleProject {
  std::string title{"SPIKES interactive circuit"};
  Circuit circuit;
  TransientOptions transient{};
  double dashboard_step_s{1.0e-6};
  std::vector<DashboardProbe> probes;
  std::vector<DashboardControl> controls;
};

struct DashboardReading {
  double time_s{0.0};
  double value{0.0};
  std::string unit;
  std::optional<double> utilization;
  std::string state{"OK"};
};

/** Parse the bounded native console-deck format. */
[[nodiscard]] ConsoleProject parse_console_project(std::istream &input);

/** Built-in electrothermal circuit used by `spikes_console --demo`. */
[[nodiscard]] ConsoleProject make_console_demo_project();

class ConsoleDashboard {
public:
  explicit ConsoleDashboard(ConsoleProject project,
                            std::size_t rolling_capacity = 256);

  void attach_probe(DashboardProbe probe);
  void detach_probe(std::string_view name);
  [[nodiscard]] std::vector<std::string> probe_names() const;
  [[nodiscard]] DashboardReading reading(std::string_view name) const;
  [[nodiscard]] bool step(std::size_t count = 1,
                          std::optional<double> step_s = std::nullopt);
  void set_source(std::string_view source_id, double value);
  void trigger_control(std::string_view key);
  void checkpoint();
  void restore();
  void render(std::ostream &output) const;
  void render_history(std::string_view name, std::size_t count,
                      std::ostream &output) const;
  void export_csv(const std::string &path) const;

  /** Execute one console command. Returns false for quit/exit. */
  [[nodiscard]] bool execute(std::string_view command, std::ostream &output);
  int run(std::istream &input, std::ostream &output, bool show_prompt = true);

  [[nodiscard]] double time_s() const noexcept { return session_.time_s(); }
  [[nodiscard]] std::size_t step_index() const noexcept {
    return session_.step_index();
  }
  [[nodiscard]] const std::string &title() const noexcept { return title_; }

private:
  struct Sample {
    double time_s{0.0};
    double value{0.0};
    std::optional<double> utilization;
  };
  struct ProbeSeries {
    DashboardProbe descriptor;
    std::deque<Sample> samples;
  };

  [[nodiscard]] ProbeSeries &probe(std::string_view name);
  [[nodiscard]] const ProbeSeries &probe(std::string_view name) const;
  [[nodiscard]] DashboardReading evaluate(const DashboardProbe &probe) const;
  void sample_all();

  std::string title_;
  TransientSession session_;
  double step_s_{1.0e-6};
  std::size_t rolling_capacity_{256};
  std::vector<ProbeSeries> probes_;
  std::vector<DashboardControl> controls_;
  std::optional<TransientSessionCheckpoint> checkpoint_;
};

} // namespace spikes
