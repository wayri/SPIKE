#include "spikes/osdi_device.hpp"

#include <charconv>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

double number(std::string_view text) {
  double value = 0.0;
  const auto parsed = std::from_chars(text.data(), text.data() + text.size(),
                                      value, std::chars_format::general);
  if (parsed.ec != std::errc{} || parsed.ptr != text.data() + text.size() ||
      !std::isfinite(value)) {
    throw std::invalid_argument("invalid finite numeric worker argument");
  }
  return value;
}

std::string escaped(std::string_view value) {
  std::string result;
  for (const char character : value) {
    if (character == '\\' || character == '"') {
      result.push_back('\\');
    }
    result.push_back(character);
  }
  return result;
}

} // namespace

int main(int argc, char **argv) {
  try {
    if (argc < 6) {
      throw std::invalid_argument(
          "usage: worker ARTIFACT MODULE TEMPERATURE OUTPUT VOLTAGE...");
    }
    const std::filesystem::path artifact = argv[1];
    const std::string module_name = argv[2];
    const double temperature = number(argv[3]);
    const std::filesystem::path output = argv[4];
    std::vector<double> terminal_voltages;
    terminal_voltages.reserve(static_cast<std::size_t>(argc - 5));
    for (int index = 5; index < argc; ++index) {
      terminal_voltages.push_back(number(argv[index]));
    }
    auto device = spikes::load_trusted_osdi_0_3_device(
        artifact, module_name, temperature);
    if (terminal_voltages.size() != device->terminal_count()) {
      throw std::invalid_argument("worker terminal count does not match descriptor");
    }
    std::vector<double> all_voltages(device->node_count(), 0.0);
    std::copy(terminal_voltages.begin(), terminal_voltages.end(),
              all_voltages.begin());
    const auto result = device->evaluate_dc(all_voltages);
    std::ofstream stream(output, std::ios::binary | std::ios::trunc);
    if (!stream) {
      throw std::runtime_error("cannot create worker result");
    }
    stream << std::setprecision(17)
           << "{\"status\":\"completed\",\"osdi_abi\":\"0.3\","
              "\"module_name\":\""
           << escaped(module_name) << "\",\"num_nodes\":" << device->node_count()
           << ",\"num_terminals\":" << device->terminal_count()
           << ",\"residual\":[";
    for (std::size_t index = 0; index < result.residual.size(); ++index) {
      stream << (index == 0 ? "" : ",") << result.residual[index];
    }
    stream << "],\"jacobian\":[";
    for (std::size_t index = 0; index < result.jacobian.size(); ++index) {
      const auto &entry = result.jacobian[index];
      stream << (index == 0 ? "" : ",") << "{\"row\":" << entry.row
             << ",\"column\":" << entry.column << ",\"value\":"
             << entry.value << ",\"flags\":" << entry.flags << "}";
    }
    stream << "],\"eval_flags\":" << result.evaluation_flags
           << ",\"logs\":[]}";
    return stream ? 0 : 74;
  } catch (const std::exception &error) {
    std::ofstream diagnostic("osdi-error.txt", std::ios::binary | std::ios::trunc);
    diagnostic << error.what();
    std::cerr << error.what() << '\n';
    return 2;
  }
}
