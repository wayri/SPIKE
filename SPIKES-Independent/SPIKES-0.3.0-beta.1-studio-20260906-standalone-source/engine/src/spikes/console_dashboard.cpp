#include "spikes/console_dashboard.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cctype>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <utility>

namespace spikes {
namespace {

[[nodiscard]] std::string lower(std::string value) {
  std::transform(value.begin(), value.end(), value.begin(),
                 [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
  return value;
}

[[nodiscard]] std::string upper(std::string value) {
  std::transform(value.begin(), value.end(), value.begin(),
                 [](unsigned char ch) { return static_cast<char>(std::toupper(ch)); });
  return value;
}

[[nodiscard]] std::vector<std::string> tokens(std::string_view text) {
  std::istringstream stream{std::string(text)};
  std::vector<std::string> result;
  for (std::string token; stream >> token;) {
    result.push_back(std::move(token));
  }
  return result;
}

[[nodiscard]] double number(std::string_view text) {
  const std::string raw(text);
  std::size_t consumed = 0;
  double value = 0.0;
  try {
    value = std::stod(raw, &consumed);
  } catch (const std::exception &) {
    throw std::invalid_argument("invalid finite numeric value: " + raw);
  }
  std::string suffix = lower(raw.substr(consumed));
  double multiplier = 1.0;
  if (suffix.empty()) {
    multiplier = 1.0;
  } else if (suffix == "t") {
    multiplier = 1.0e12;
  } else if (suffix == "g") {
    multiplier = 1.0e9;
  } else if (suffix == "meg") {
    multiplier = 1.0e6;
  } else if (suffix == "k") {
    multiplier = 1.0e3;
  } else if (suffix == "m") {
    multiplier = 1.0e-3;
  } else if (suffix == "u") {
    multiplier = 1.0e-6;
  } else if (suffix == "n") {
    multiplier = 1.0e-9;
  } else if (suffix == "p") {
    multiplier = 1.0e-12;
  } else if (suffix == "f") {
    multiplier = 1.0e-15;
  } else {
    throw std::invalid_argument("unsupported engineering suffix: " + suffix);
  }
  value *= multiplier;
  if (!std::isfinite(value)) {
    throw std::invalid_argument("numeric value must be finite");
  }
  return value;
}

[[nodiscard]] std::size_t positive_count(std::string_view text,
                                         std::string_view label) {
  const double parsed = number(text);
  if (parsed <= 0.0 || std::floor(parsed) != parsed ||
      parsed > 1'000'000.0) {
    throw std::invalid_argument(std::string(label) +
                                " must be an integer in [1,1000000]");
  }
  return static_cast<std::size_t>(parsed);
}

[[nodiscard]] std::string kind_name(DashboardProbeKind kind) {
  switch (kind) {
  case DashboardProbeKind::node_voltage:
    return "node-V";
  case DashboardProbeKind::element_voltage:
    return "part-V";
  case DashboardProbeKind::element_current:
    return "current";
  case DashboardProbeKind::element_power:
    return "power";
  case DashboardProbeKind::temperature:
    return "temperature";
  case DashboardProbeKind::failure_proximity:
    return "health";
  }
  return "unknown";
}

[[nodiscard]] std::string unit_for(DashboardProbeKind kind) {
  switch (kind) {
  case DashboardProbeKind::node_voltage:
  case DashboardProbeKind::element_voltage:
    return "V";
  case DashboardProbeKind::element_current:
    return "A";
  case DashboardProbeKind::element_power:
    return "W";
  case DashboardProbeKind::temperature:
    return "K";
  case DashboardProbeKind::failure_proximity:
    return "%";
  }
  return "";
}

void validate_limits(const FailureLimits &limits) {
  const auto positive = [](const std::optional<double> &value) {
    return !value || (std::isfinite(*value) && *value > 0.0);
  };
  if (!positive(limits.maximum_absolute_voltage_v) ||
      !positive(limits.maximum_absolute_current_a) ||
      !positive(limits.maximum_power_w) ||
      !positive(limits.maximum_temperature_k) ||
      !std::isfinite(limits.ambient_temperature_k) ||
      limits.ambient_temperature_k <= 0.0 ||
      !std::isfinite(limits.warning_fraction) ||
      limits.warning_fraction <= 0.0 || limits.warning_fraction >= 1.0 ||
      (limits.maximum_temperature_k &&
       *limits.maximum_temperature_k <= limits.ambient_temperature_k)) {
    throw std::invalid_argument("probe limits violate their finite positive envelope");
  }
}

[[nodiscard]] DashboardProbe parse_probe(const std::vector<std::string> &word,
                                         std::size_t first) {
  if (word.size() < first + 3) {
    throw std::invalid_argument(
        "probe requires NAME KIND TARGET and kind-specific limits");
  }
  DashboardProbe probe;
  probe.name = word[first];
  const std::string kind = lower(word[first + 1]);
  probe.target = word[first + 2];
  if (kind == "node" || kind == "node-voltage" || kind == "vnode") {
    probe.kind = DashboardProbeKind::node_voltage;
    if (word.size() > first + 3) {
      probe.limits.maximum_absolute_voltage_v = number(word[first + 3]);
    }
  } else if (kind == "voltage" || kind == "part-voltage" || kind == "velement") {
    probe.kind = DashboardProbeKind::element_voltage;
    if (word.size() > first + 3) {
      probe.limits.maximum_absolute_voltage_v = number(word[first + 3]);
    }
  } else if (kind == "current" || kind == "i") {
    probe.kind = DashboardProbeKind::element_current;
    if (word.size() > first + 3) {
      probe.limits.maximum_absolute_current_a = number(word[first + 3]);
    }
  } else if (kind == "power" || kind == "dissipation" || kind == "p") {
    probe.kind = DashboardProbeKind::element_power;
    if (word.size() > first + 3) {
      probe.limits.maximum_power_w = number(word[first + 3]);
    }
  } else if (kind == "temperature" || kind == "temp" || kind == "t") {
    if (word.size() != first + 5) {
      throw std::invalid_argument(
          "temperature probe requires NAME temperature THERMAL_NODE AMBIENT_K MAX_K");
    }
    probe.kind = DashboardProbeKind::temperature;
    probe.limits.thermal_node = probe.target;
    probe.limits.ambient_temperature_k = number(word[first + 3]);
    probe.limits.maximum_temperature_k = number(word[first + 4]);
  } else if (kind == "health" || kind == "failure") {
    if (word.size() != first + 9) {
      throw std::invalid_argument(
          "health probe requires NAME health ELEMENT VMAX IMAX PMAX "
          "THERMAL_NODE AMBIENT_K MAX_K");
    }
    probe.kind = DashboardProbeKind::failure_proximity;
    probe.limits.maximum_absolute_voltage_v = number(word[first + 3]);
    probe.limits.maximum_absolute_current_a = number(word[first + 4]);
    probe.limits.maximum_power_w = number(word[first + 5]);
    probe.limits.thermal_node = word[first + 6];
    probe.limits.ambient_temperature_k = number(word[first + 7]);
    probe.limits.maximum_temperature_k = number(word[first + 8]);
  } else {
    throw std::invalid_argument("unknown probe kind: " + kind);
  }
  validate_limits(probe.limits);
  return probe;
}

template <typename Samples>
[[nodiscard]] std::string sparkline(const Samples &samples) {
  if (samples.empty()) {
    return "";
  }
  constexpr std::string_view glyphs = ".:-=+*#%@";
  const std::size_t begin = samples.size() > 24 ? samples.size() - 24 : 0;
  double low = samples[begin].value;
  double high = low;
  for (std::size_t index = begin; index < samples.size(); ++index) {
    low = std::min(low, samples[index].value);
    high = std::max(high, samples[index].value);
  }
  std::string result;
  result.reserve(samples.size() - begin);
  for (std::size_t index = begin; index < samples.size(); ++index) {
    const double fraction = high == low ? 0.5 :
        (samples[index].value - low) / (high - low);
    const auto glyph = static_cast<std::size_t>(std::clamp(
        fraction, 0.0, 1.0) * static_cast<double>(glyphs.size() - 1));
    result.push_back(glyphs[glyph]);
  }
  return result;
}

} // namespace

ConsoleProject parse_console_project(std::istream &input) {
  ConsoleProject project;
  bool saw_content = false;
  bool saw_title = false;
  std::string line;
  std::size_t line_number = 0;
  while (std::getline(input, line)) {
    ++line_number;
    if (line_number > 100'000) {
      throw std::length_error("console deck exceeds 100000 lines");
    }
    if (const auto comment = line.find(';'); comment != std::string::npos) {
      line.erase(comment);
    }
    const auto first_nonspace = line.find_first_not_of(" \t\r\n");
    if (first_nonspace == std::string::npos || line[first_nonspace] == '*') {
      continue;
    }
    auto word = tokens(line);
    if (word.empty()) {
      continue;
    }
    const std::string opcode = upper(word[0]);
    try {
      if (opcode == ".END") {
        break;
      }
      if (opcode == ".TITLE") {
        const auto offset = line.find(word[0]) + word[0].size();
        project.title = line.substr(line.find_first_not_of(" \t", offset));
        saw_title = true;
      } else if (opcode == ".TRAN") {
        if (word.size() < 3 || word.size() > 4) {
          throw std::invalid_argument(".tran requires STEP STOP [be|bdf2]");
        }
        project.dashboard_step_s = number(word[1]);
        project.transient.time_step_s = project.dashboard_step_s;
        project.transient.stop_time_s = number(word[2]);
        if (project.dashboard_step_s <= 0.0 ||
            project.transient.stop_time_s <= 0.0) {
          throw std::invalid_argument(".tran times must be positive");
        }
        project.transient.integration_method =
            word.size() == 4 && lower(word[3]) == "bdf2"
                ? TransientIntegrationMethod::bdf2
                : TransientIntegrationMethod::backward_euler;
        if (word.size() == 4 && lower(word[3]) != "bdf2" &&
            lower(word[3]) != "be") {
          throw std::invalid_argument("console .tran supports be or bdf2");
        }
      } else if (opcode == ".PROBE") {
        project.probes.push_back(parse_probe(word, 1));
      } else if (opcode == ".CONTROL") {
        if (word.size() != 5) {
          throw std::invalid_argument(
              ".control requires KEY SOURCE LOW HIGH");
        }
        project.controls.push_back(
            {lower(word[1]), word[2], number(word[3]), number(word[4]), false});
      } else if (opcode == "RET" || opcode.starts_with("RET")) {
        if (word.size() != 11) {
          throw std::invalid_argument(
              "RET requires ID P N THERMAL R ALPHA TAMB RTH CTH TMIN TMAX");
        }
        project.circuit.add_electrothermal_resistor(
            word[0], word[1], word[2], word[3],
            ElectrothermalResistorModel{
                number(word[4]), number(word[5]), number(word[6]),
                number(word[7]), number(word[8]), number(word[9]),
                number(word[10])});
      } else if (opcode == "LSAT" || opcode.starts_with("LSAT")) {
        if (word.size() < 6 || word.size() > 7) {
          throw std::invalid_argument(
              "LSAT requires ID P N L0 LSAT ISAT [I0]");
        }
        project.circuit.add_saturating_inductor(
            word[0], word[1], word[2],
            SaturatingInductorModel{number(word[3]), number(word[4]),
                                      number(word[5]),
                                      word.size() == 7 ? number(word[6]) : 0.0});
      } else if (opcode == "DRR" || opcode.starts_with("DRR")) {
        if (word.size() != 9) {
          throw std::invalid_argument(
              "DRR requires ID A K IS N TEMP TT CJ Q0");
        }
        project.circuit.add_dynamic_diode(
            word[0], word[1], word[2],
            DynamicDiodeModel{
                DiodeModel{number(word[3]), number(word[4]), number(word[5])},
                number(word[6]), number(word[7]), number(word[8])});
      } else if (!opcode.empty() && opcode.front() == 'R') {
        if (word.size() != 4) {
          throw std::invalid_argument("resistor requires ID P N R");
        }
        project.circuit.add_resistor(word[0], word[1], word[2], number(word[3]));
      } else if (!opcode.empty() && opcode.front() == 'C') {
        if (word.size() < 4 || word.size() > 5) {
          throw std::invalid_argument("capacitor requires ID P N C [V0]");
        }
        project.circuit.add_capacitor(
            word[0], word[1], word[2], number(word[3]),
            word.size() == 5 ? number(word[4]) : 0.0);
      } else if (!opcode.empty() && opcode.front() == 'L') {
        if (word.size() < 4 || word.size() > 5) {
          throw std::invalid_argument("inductor requires ID P N L [I0]");
        }
        project.circuit.add_inductor(
            word[0], word[1], word[2], number(word[3]),
            word.size() == 5 ? number(word[4]) : 0.0);
      } else if (!opcode.empty() && opcode.front() == 'V') {
        if (word.size() != 4) {
          throw std::invalid_argument("voltage source requires ID P N VALUE");
        }
        project.circuit.add_voltage_source(word[0], word[1], word[2],
                                           number(word[3]));
      } else if (!opcode.empty() && opcode.front() == 'I') {
        if (word.size() != 4) {
          throw std::invalid_argument("current source requires ID P N VALUE");
        }
        project.circuit.add_current_source(word[0], word[1], word[2],
                                           number(word[3]));
      } else if (!opcode.empty() && opcode.front() == 'D') {
        if (word.size() < 3 || word.size() > 6) {
          throw std::invalid_argument("diode requires ID A K [IS [N [TEMP]]]");
        }
        project.circuit.add_diode(
            word[0], word[1], word[2],
            DiodeModel{word.size() > 3 ? number(word[3]) : 1.0e-14,
                       word.size() > 4 ? number(word[4]) : 1.0,
                       word.size() > 5 ? number(word[5]) : 300.15});
      } else if (!saw_content && !saw_title) {
        project.title = line.substr(first_nonspace);
        saw_title = true;
      } else {
        throw std::invalid_argument("unsupported console-deck line");
      }
      saw_content = true;
    } catch (const std::exception &error) {
      throw std::invalid_argument("console deck line " +
                                  std::to_string(line_number) + ": " +
                                  error.what());
    }
  }
  project.transient.initialize_from_operating_point = false;
  project.transient.max_steps = 1'000'000;
  return project;
}

ConsoleProject make_console_demo_project() {
  ConsoleProject project;
  project.title = "SPIKES electrothermal interactive dashboard";
  project.dashboard_step_s = 1.0e-3;
  project.transient.time_step_s = project.dashboard_step_s;
  project.transient.stop_time_s = 1.0;
  project.transient.initialize_from_operating_point = false;
  project.transient.integration_method = TransientIntegrationMethod::bdf2;
  project.circuit.add_voltage_source("Vbus", "bus", "0", 12.0);
  ElectrothermalResistorModel model;
  model.resistance_ohm = 10.0;
  model.thermal_resistance_k_per_w = 5.0;
  model.thermal_capacitance_j_per_k = 0.1;
  project.circuit.add_electrothermal_resistor("Rload", "bus", "0", "tj", model);
  project.probes = {
      {"VBUS", DashboardProbeKind::node_voltage, "bus",
       FailureLimits{20.0}},
      {"ILOAD", DashboardProbeKind::element_current, "Rload",
       FailureLimits{std::nullopt, 2.0}},
      {"PLOAD", DashboardProbeKind::element_power, "Rload",
       FailureLimits{std::nullopt, std::nullopt, 20.0}},
      {"TEMP", DashboardProbeKind::temperature, "tj",
       FailureLimits{std::nullopt, std::nullopt, std::nullopt, 450.0,
                     "tj", 300.15}},
      {"HEALTH", DashboardProbeKind::failure_proximity, "Rload",
       FailureLimits{20.0, 2.0, 20.0, 450.0, "tj", 300.15}},
  };
  project.controls.push_back({"a", "Vbus", 0.0, 12.0, true});
  return project;
}

ConsoleDashboard::ConsoleDashboard(ConsoleProject project,
                                   std::size_t rolling_capacity)
    : title_(std::move(project.title)),
      session_(std::move(project.circuit), project.transient),
      step_s_(project.dashboard_step_s), rolling_capacity_(rolling_capacity),
      controls_(std::move(project.controls)) {
  if (!std::isfinite(step_s_) || step_s_ <= 0.0 || rolling_capacity_ == 0 ||
      rolling_capacity_ > 1'000'000) {
    throw std::invalid_argument("dashboard step/capacity is outside bounds");
  }
  for (auto &descriptor : project.probes) {
    attach_probe(std::move(descriptor));
  }
}

void ConsoleDashboard::attach_probe(DashboardProbe descriptor) {
  if (descriptor.name.empty() || descriptor.target.empty() ||
      descriptor.name.find(',') != std::string::npos ||
      std::any_of(probes_.begin(), probes_.end(), [&](const ProbeSeries &item) {
        return item.descriptor.name == descriptor.name;
      })) {
    throw std::invalid_argument("probe names/targets must be non-empty, CSV-safe, and unique");
  }
  validate_limits(descriptor.limits);
  if (descriptor.kind == DashboardProbeKind::failure_proximity &&
      !descriptor.limits.maximum_absolute_voltage_v &&
      !descriptor.limits.maximum_absolute_current_a &&
      !descriptor.limits.maximum_power_w &&
      !descriptor.limits.maximum_temperature_k) {
    throw std::invalid_argument("health probe requires at least one failure limit");
  }
  probes_.push_back({std::move(descriptor), {}});
}

void ConsoleDashboard::detach_probe(std::string_view name) {
  const auto found = std::find_if(probes_.begin(), probes_.end(),
                                  [name](const ProbeSeries &item) {
                                    return item.descriptor.name == name;
                                  });
  if (found == probes_.end()) {
    throw std::out_of_range("unknown dashboard probe");
  }
  probes_.erase(found);
}

std::vector<std::string> ConsoleDashboard::probe_names() const {
  std::vector<std::string> result;
  result.reserve(probes_.size());
  for (const auto &item : probes_) {
    result.push_back(item.descriptor.name);
  }
  return result;
}

ConsoleDashboard::ProbeSeries &ConsoleDashboard::probe(std::string_view name) {
  const auto found = std::find_if(probes_.begin(), probes_.end(),
                                  [name](const ProbeSeries &item) {
                                    return item.descriptor.name == name;
                                  });
  if (found == probes_.end()) {
    throw std::out_of_range("unknown dashboard probe");
  }
  return *found;
}

const ConsoleDashboard::ProbeSeries &
ConsoleDashboard::probe(std::string_view name) const {
  const auto found = std::find_if(probes_.begin(), probes_.end(),
                                  [name](const ProbeSeries &item) {
                                    return item.descriptor.name == name;
                                  });
  if (found == probes_.end()) {
    throw std::out_of_range("unknown dashboard probe");
  }
  return *found;
}

DashboardReading ConsoleDashboard::evaluate(const DashboardProbe &descriptor) const {
  DashboardReading result;
  result.time_s = session_.time_s();
  result.unit = unit_for(descriptor.kind);
  const auto &limit = descriptor.limits;
  if (descriptor.kind == DashboardProbeKind::node_voltage) {
    result.value = session_.node_voltage(descriptor.target);
    if (limit.maximum_absolute_voltage_v) {
      result.utilization = std::abs(result.value) /
                           *limit.maximum_absolute_voltage_v;
    }
  } else if (descriptor.kind == DashboardProbeKind::element_voltage) {
    result.value = session_.element_voltage(descriptor.target);
    if (limit.maximum_absolute_voltage_v) {
      result.utilization = std::abs(result.value) /
                           *limit.maximum_absolute_voltage_v;
    }
  } else if (descriptor.kind == DashboardProbeKind::element_current) {
    result.value = session_.element_current(descriptor.target);
    if (limit.maximum_absolute_current_a) {
      result.utilization = std::abs(result.value) /
                           *limit.maximum_absolute_current_a;
    }
  } else if (descriptor.kind == DashboardProbeKind::element_power) {
    result.value = session_.element_power(descriptor.target);
    if (limit.maximum_power_w) {
      result.utilization = std::max(0.0, result.value) /
                           *limit.maximum_power_w;
    }
  } else if (descriptor.kind == DashboardProbeKind::temperature) {
    result.value = limit.ambient_temperature_k +
                   session_.node_voltage(descriptor.target);
    if (limit.maximum_temperature_k) {
      result.utilization = std::max(0.0, result.value -
                                             limit.ambient_temperature_k) /
                           (*limit.maximum_temperature_k -
                            limit.ambient_temperature_k);
    }
  } else {
    double utilization = 0.0;
    if (limit.maximum_absolute_voltage_v) {
      utilization = std::max(
          utilization, std::abs(session_.element_voltage(descriptor.target)) /
                           *limit.maximum_absolute_voltage_v);
    }
    if (limit.maximum_absolute_current_a) {
      utilization = std::max(
          utilization, std::abs(session_.element_current(descriptor.target)) /
                           *limit.maximum_absolute_current_a);
    }
    if (limit.maximum_power_w) {
      utilization = std::max(
          utilization, std::max(0.0, session_.element_power(descriptor.target)) /
                           *limit.maximum_power_w);
    }
    if (limit.maximum_temperature_k) {
      const double temperature = limit.ambient_temperature_k +
          session_.node_voltage(limit.thermal_node);
      utilization = std::max(
          utilization,
          std::max(0.0, temperature - limit.ambient_temperature_k) /
              (*limit.maximum_temperature_k - limit.ambient_temperature_k));
    }
    result.value = 100.0 * utilization;
    result.utilization = utilization;
  }
  if (result.utilization) {
    result.state = *result.utilization >= 1.0
                       ? "TRIP"
                       : *result.utilization >= limit.warning_fraction ? "WARN"
                                                                       : "OK";
  }
  return result;
}

DashboardReading ConsoleDashboard::reading(std::string_view name) const {
  return evaluate(probe(name).descriptor);
}

void ConsoleDashboard::sample_all() {
  for (auto &item : probes_) {
    const auto value = evaluate(item.descriptor);
    item.samples.push_back({value.time_s, value.value, value.utilization});
    if (item.samples.size() > rolling_capacity_) {
      item.samples.pop_front();
    }
  }
}

bool ConsoleDashboard::step(std::size_t count, std::optional<double> step_s) {
  if (count == 0 || count > 1'000'000) {
    throw std::invalid_argument("step count must be in [1,1000000]");
  }
  const double interval = step_s.value_or(step_s_);
  if (!std::isfinite(interval) || interval <= 0.0) {
    throw std::invalid_argument("dashboard step interval must be finite and positive");
  }
  for (std::size_t index = 0; index < count; ++index) {
    if (!session_.step(interval)) {
      return false;
    }
    sample_all();
  }
  return true;
}

void ConsoleDashboard::set_source(std::string_view source_id, double value) {
  session_.set_source_value(source_id, value);
}

void ConsoleDashboard::trigger_control(std::string_view key) {
  const std::string normalized = lower(std::string(key));
  const auto found = std::find_if(controls_.begin(), controls_.end(),
                                  [&](const DashboardControl &control) {
                                    return control.key == normalized;
                                  });
  if (found == controls_.end()) {
    throw std::out_of_range("unknown dashboard control key");
  }
  found->high = !found->high;
  session_.set_source_value(found->source_id,
                            found->high ? found->high_value : found->low_value);
}

void ConsoleDashboard::checkpoint() { checkpoint_ = session_.checkpoint(); }

void ConsoleDashboard::restore() {
  if (!checkpoint_) {
    throw std::logic_error("dashboard has no checkpoint");
  }
  session_.restore(*checkpoint_);
  for (auto &item : probes_) {
    item.samples.clear();
  }
  if (session_.has_point()) {
    sample_all();
  }
}

void ConsoleDashboard::render(std::ostream &output) const {
  output << "\nSPIKES DASHBOARD | " << title_ << "\n"
         << "t=" << std::scientific << std::setprecision(6) << session_.time_s()
         << " s  step=" << session_.step_index() << "  solver="
         << session_.message() << "\n"
         << std::left << std::setw(14) << "probe" << std::setw(13) << "type"
         << std::setw(18) << "target" << std::right << std::setw(16) << "value"
         << std::setw(7) << "unit" << std::setw(9) << "margin" << std::setw(8)
         << "state" << "  trend\n";
  for (const auto &item : probes_) {
    output << std::left << std::setw(14) << item.descriptor.name
           << std::setw(13) << kind_name(item.descriptor.kind)
           << std::setw(18) << item.descriptor.target;
    if (!session_.has_point()) {
      output << std::right << std::setw(16) << "--" << std::setw(7)
             << unit_for(item.descriptor.kind) << std::setw(9) << "--"
             << std::setw(8) << "IDLE" << "\n";
      continue;
    }
    const auto value = evaluate(item.descriptor);
    output << std::right << std::scientific << std::setprecision(6)
           << std::setw(16) << value.value << std::setw(7) << value.unit;
    if (value.utilization) {
      output << std::fixed << std::setprecision(1) << std::setw(8)
             << 100.0 * *value.utilization << "%";
    } else {
      output << std::setw(9) << "--";
    }
    output << std::setw(8) << value.state << "  " << sparkline(item.samples)
           << "\n";
  }
}

void ConsoleDashboard::render_history(std::string_view name, std::size_t count,
                                      std::ostream &output) const {
  const auto &series = probe(name);
  count = std::min(count, series.samples.size());
  const std::size_t begin = series.samples.size() - count;
  output << "time_s,value,unit,utilization\n";
  for (std::size_t index = begin; index < series.samples.size(); ++index) {
    const auto &sample = series.samples[index];
    output << std::setprecision(17) << sample.time_s << ',' << sample.value << ','
           << unit_for(series.descriptor.kind) << ',';
    if (sample.utilization) {
      output << *sample.utilization;
    }
    output << '\n';
  }
}

void ConsoleDashboard::export_csv(const std::string &path) const {
  if (path.empty()) {
    throw std::invalid_argument("CSV path must be non-empty");
  }
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  if (!output) {
    throw std::runtime_error("unable to open CSV output");
  }
  output << "time_s,probe,type,target,value,unit,utilization\n";
  for (const auto &series : probes_) {
    for (const auto &sample : series.samples) {
      output << std::setprecision(17) << sample.time_s << ','
             << series.descriptor.name << ',' << kind_name(series.descriptor.kind)
             << ',' << series.descriptor.target << ',' << sample.value << ','
             << unit_for(series.descriptor.kind) << ',';
      if (sample.utilization) {
        output << *sample.utilization;
      }
      output << '\n';
    }
  }
  if (!output) {
    throw std::runtime_error("CSV write failed");
  }
}

bool ConsoleDashboard::execute(std::string_view command,
                               std::ostream &output) {
  const auto word = tokens(command);
  if (word.empty()) {
    return true;
  }
  const std::string operation = lower(word[0]);
  if (operation == "quit" || operation == "exit") {
    return false;
  }
  if (operation.starts_with("kp-") && operation.size() > 3) {
    trigger_control(operation.substr(3));
    output << "control " << operation.substr(3) << " toggled\n";
  } else if (operation == "help") {
    output <<
        "Commands:\n"
        "  status | probes | step [N] [DT] | watch N [EVERY]\n"
        "  realtime SECONDS [DT] | set SOURCE VALUE | kp-KEY\n"
        "  attach NAME node|voltage|current|power TARGET [MAX]\n"
        "  attach NAME temperature THERMAL_NODE AMBIENT_K MAX_K\n"
        "  attach NAME health ELEMENT VMAX IMAX PMAX THERMAL_NODE AMBIENT_K MAX_K\n"
        "  detach NAME | history NAME [N] | savecsv PATH\n"
        "  checkpoint | restore | quit\n";
  } else if (operation == "status") {
    render(output);
  } else if (operation == "probes") {
    for (const auto &item : probes_) {
      output << item.descriptor.name << ' ' << kind_name(item.descriptor.kind)
             << ' ' << item.descriptor.target << '\n';
    }
  } else if (operation == "step") {
    const std::size_t count = word.size() > 1 ? positive_count(word[1], "step count") : 1;
    const std::optional<double> interval =
        word.size() > 2 ? std::optional<double>(number(word[2])) : std::nullopt;
    if (word.size() > 3) {
      throw std::invalid_argument("step accepts [N] [DT]");
    }
    if (!step(count, interval)) {
      throw std::runtime_error("simulation step failed: " + session_.message());
    }
    render(output);
  } else if (operation == "watch") {
    if (word.size() < 2 || word.size() > 3) {
      throw std::invalid_argument("watch requires N [EVERY]");
    }
    const auto count = positive_count(word[1], "watch count");
    const auto every = word.size() == 3 ? positive_count(word[2], "watch interval") : 1;
    for (std::size_t index = 0; index < count; ++index) {
      if (!step()) {
        throw std::runtime_error("simulation watch failed: " + session_.message());
      }
      if ((index + 1) % every == 0 || index + 1 == count) {
        render(output);
      }
    }
  } else if (operation == "realtime") {
    if (word.size() < 2 || word.size() > 3) {
      throw std::invalid_argument("realtime requires SECONDS [DT]");
    }
    const double duration = number(word[1]);
    const double interval = word.size() == 3 ? number(word[2]) : step_s_;
    if (duration <= 0.0 || duration > 3600.0 || interval <= 0.0) {
      throw std::invalid_argument("realtime duration/step is outside bounds");
    }
    const auto count = static_cast<std::size_t>(std::ceil(duration / interval));
    if (count == 0 || count > 1'000'000) {
      throw std::invalid_argument("realtime request exceeds one million steps");
    }
    const auto started = std::chrono::steady_clock::now();
    for (std::size_t index = 0; index < count; ++index) {
      if (!step(1, interval)) {
        throw std::runtime_error("realtime step failed: " + session_.message());
      }
      std::this_thread::sleep_until(
          started + std::chrono::duration<double>((index + 1) * interval));
    }
    render(output);
  } else if (operation == "set") {
    if (word.size() != 3) {
      throw std::invalid_argument("set requires SOURCE VALUE");
    }
    set_source(word[1], number(word[2]));
    output << word[1] << " updated\n";
  } else if (operation == "attach") {
    attach_probe(parse_probe(word, 1));
    output << "probe attached\n";
  } else if (operation == "detach") {
    if (word.size() != 2) {
      throw std::invalid_argument("detach requires NAME");
    }
    detach_probe(word[1]);
    output << "probe detached\n";
  } else if (operation == "history") {
    if (word.size() < 2 || word.size() > 3) {
      throw std::invalid_argument("history requires NAME [N]");
    }
    render_history(word[1], word.size() == 3 ? positive_count(word[2], "history count") : 32,
                   output);
  } else if (operation == "savecsv") {
    if (word.size() != 2) {
      throw std::invalid_argument("savecsv requires PATH without spaces");
    }
    export_csv(word[1]);
    output << "CSV saved to " << word[1] << '\n';
  } else if (operation == "checkpoint") {
    checkpoint();
    output << "checkpoint saved\n";
  } else if (operation == "restore") {
    restore();
    output << "checkpoint restored\n";
  } else {
    throw std::invalid_argument("unknown console command: " + operation);
  }
  return true;
}

int ConsoleDashboard::run(std::istream &input, std::ostream &output,
                          bool show_prompt) {
  output << "SPIKES native console dashboard\nType 'help' for commands.\n";
  render(output);
  for (std::string line;;) {
    if (show_prompt) {
      output << "spikes> " << std::flush;
    }
    if (!std::getline(input, line)) {
      return 0;
    }
    try {
      if (!execute(line, output)) {
        return 0;
      }
    } catch (const std::exception &error) {
      output << "error: " << error.what() << '\n';
    }
  }
}

} // namespace spikes
