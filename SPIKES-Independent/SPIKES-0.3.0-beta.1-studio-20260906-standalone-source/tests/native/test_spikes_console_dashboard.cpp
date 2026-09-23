#include "spikes/console_dashboard.hpp"

#include <cassert>
#include <cmath>
#include <sstream>
#include <stdexcept>
#include <string>

namespace {

const char *deck = R"(
SPIKES dashboard unit fixture
Vbus bus 0 0
RETload bus 0 tj 10 3.9m 300.15 5 100m 200 600
.tran 1m 1 bdf2
.probe VBUS node bus 20
.probe PLOAD power RETload 20
.probe TEMP temperature tj 300.15 450
.probe HEALTH health RETload 20 2 20 tj 300.15 450
.control a Vbus 0 12
.end
)";

void parser_and_live_probes_are_native_and_bounded() {
  std::istringstream input(deck);
  auto project = spikes::parse_console_project(input);
  assert(project.title == "SPIKES dashboard unit fixture");
  assert(project.probes.size() == 4);
  assert(project.controls.size() == 1);
  assert(std::abs(project.dashboard_step_s - 1.0e-3) < 1.0e-15);

  spikes::ConsoleDashboard dashboard(std::move(project), 8);
  std::ostringstream output;
  assert(dashboard.execute("kp-a", output));
  assert(dashboard.step(10));
  assert(std::abs(dashboard.reading("VBUS").value - 12.0) < 1.0e-10);
  const auto power = dashboard.reading("PLOAD");
  assert(power.value > 14.0 && power.value < 14.5);
  const auto health = dashboard.reading("HEALTH");
  assert(health.utilization.has_value());
  assert(*health.utilization > 0.70 && *health.utilization < 0.75);
  assert(health.state == "OK");
  assert(dashboard.reading("TEMP").value > 300.15);

  dashboard.attach_probe({
      "TIGHT", spikes::DashboardProbeKind::failure_proximity, "RETload",
      spikes::FailureLimits{10.0, 1.0, 10.0, 310.0, "tj", 300.15}});
  assert(dashboard.step());
  assert(dashboard.reading("TIGHT").state == "TRIP");

  dashboard.checkpoint();
  const double saved_time = dashboard.time_s();
  assert(dashboard.execute("kp-a", output));
  assert(dashboard.step(2));
  assert(std::abs(dashboard.reading("VBUS").value) < 1.0e-12);
  dashboard.restore();
  assert(std::abs(dashboard.time_s() - saved_time) < 1.0e-15);
  assert(std::abs(dashboard.reading("VBUS").value - 12.0) < 1.0e-10);

  assert(dashboard.step(12));
  std::ostringstream history;
  dashboard.render_history("HEALTH", 100, history);
  std::size_t lines = 0;
  for (const char ch : history.str()) {
    lines += ch == '\n';
  }
  assert(lines == 9); // header plus the eight-sample rolling capacity

  std::ostringstream rendered;
  dashboard.render(rendered);
  assert(rendered.str().find("SPIKES DASHBOARD") != std::string::npos);
  assert(rendered.str().find("TRIP") != std::string::npos);
  assert(rendered.str().find("trend") != std::string::npos);
}

void malformed_decks_and_commands_fail_closed() {
  {
    std::istringstream bad("title\nX1 a b unsupported\n");
    bool rejected = false;
    try {
      (void)spikes::parse_console_project(bad);
    } catch (const std::invalid_argument &) {
      rejected = true;
    }
    assert(rejected);
  }
  std::istringstream input(deck);
  spikes::ConsoleDashboard dashboard(spikes::parse_console_project(input));
  std::ostringstream output;
  bool rejected = false;
  try {
    (void)dashboard.execute("attach bad temperature tj 300 299", output);
  } catch (const std::invalid_argument &) {
    rejected = true;
  }
  assert(rejected);
  rejected = false;
  try {
    (void)dashboard.execute("realtime 5000", output);
  } catch (const std::invalid_argument &) {
    rejected = true;
  }
  assert(rejected);
}

} // namespace

int main() {
  parser_and_live_probes_are_native_and_bounded();
  malformed_decks_and_commands_fail_closed();
}
