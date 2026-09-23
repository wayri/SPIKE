#include "spikes/console_dashboard.hpp"

#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

#ifndef SPIKES_ENGINE_VERSION
#error "SPIKES_ENGINE_VERSION must be supplied by the build system"
#endif

namespace {

void usage(std::ostream &output) {
  output <<
      "SPIKES native console dashboard\n"
      "Usage:\n"
      "  spikes_console --demo [--script COMMANDS] [--capacity N]\n"
      "  spikes_console CIRCUIT.spkc [--script COMMANDS] [--capacity N]\n"
      "\n"
      "The bounded console deck supports R/C/L/V/I/D, DRR, RET, LSAT,\n"
      ".tran, .probe, .control, and .end records.\n";
}

} // namespace

int main(int argc, char **argv) {
  try {
    if (argc < 2) {
      usage(std::cerr);
      return 2;
    }
    bool demo = false;
    std::string project_path;
    std::string script_path;
    std::size_t capacity = 256;
    for (int index = 1; index < argc; ++index) {
      const std::string argument = argv[index];
      if (argument == "--help" || argument == "-h") {
        usage(std::cout);
        return 0;
      }
      if (argument == "--version") {
        std::cout << "spikes_console " SPIKES_ENGINE_VERSION "\n";
        return 0;
      }
      if (argument == "--demo") {
        demo = true;
      } else if (argument == "--script") {
        if (++index >= argc) {
          throw std::invalid_argument("--script requires a path");
        }
        script_path = argv[index];
      } else if (argument == "--capacity") {
        if (++index >= argc) {
          throw std::invalid_argument("--capacity requires an integer");
        }
        const auto parsed = std::stoull(argv[index]);
        if (parsed == 0 || parsed > 1'000'000) {
          throw std::invalid_argument("capacity must be in [1,1000000]");
        }
        capacity = static_cast<std::size_t>(parsed);
      } else if (!argument.starts_with('-') && project_path.empty()) {
        project_path = argument;
      } else {
        throw std::invalid_argument("unknown or duplicate argument: " + argument);
      }
    }
    if (demo == !project_path.empty()) {
      throw std::invalid_argument("select exactly one of --demo or a circuit file");
    }

    spikes::ConsoleProject project;
    if (demo) {
      project = spikes::make_console_demo_project();
    } else {
      std::ifstream input(project_path, std::ios::binary);
      if (!input) {
        throw std::runtime_error("unable to open circuit project: " + project_path);
      }
      project = spikes::parse_console_project(input);
    }
    spikes::ConsoleDashboard dashboard(std::move(project), capacity);
    if (script_path.empty()) {
      return dashboard.run(std::cin, std::cout, true);
    }
    std::ifstream commands(script_path, std::ios::binary);
    if (!commands) {
      throw std::runtime_error("unable to open command script: " + script_path);
    }
    return dashboard.run(commands, std::cout, false);
  } catch (const std::exception &error) {
    std::cerr << "spikes_console: " << error.what() << '\n';
    return 2;
  }
}
