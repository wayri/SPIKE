// SPDX-License-Identifier: GPL-2.0-or-later

#include "sparselizard.h"
#include "universe.h"

#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

struct Arguments {
    std::string command;
    std::string mesh_path;
    std::string output_path;
};

Arguments parse_arguments(int argc, char** argv) {
    if (argc < 2) {
        throw std::runtime_error("usage: spike-sparselizard-runtime self-test --mesh PATH --output PATH");
    }
    Arguments result{argv[1], "", ""};
    for (int index = 2; index < argc; ++index) {
        const std::string argument = argv[index];
        if ((argument == "--mesh" || argument == "--output") && index + 1 < argc) {
            const std::string value = argv[++index];
            if (argument == "--mesh") {
                result.mesh_path = value;
            } else {
                result.output_path = value;
            }
        } else {
            throw std::runtime_error("unknown or incomplete argument: " + argument);
        }
    }
    if (result.command != "self-test" || result.mesh_path.empty() || result.output_path.empty()) {
        throw std::runtime_error("self-test requires --mesh and --output");
    }
    return result;
}

int run_dc_conduction_self_test(const Arguments& arguments) {
    using namespace sl;

    constexpr int all = 1;
    constexpr int left = 2;
    constexpr int right = 3;
    constexpr double conductivity_s_per_m = 0.005;
    constexpr double expected_resistance_ohm = 200.0;
    constexpr double relative_tolerance = 1e-10;

    // MSYS2's PETSc package does not register MUMPS. The small deterministic
    // reference fixture uses PETSc's built-in LU backend explicitly; large
    // production cases remain gated on a separately validated MUMPS build.
    universe::solvertype = MATSOLVERPETSC;

    mesh model_mesh(arguments.mesh_path);
    PetscOptionsSetValue(nullptr, "-pc_factor_nonzeros_along_diagonal", "1e-12");
    field voltage("h1");
    voltage.setorder(all, 2);
    voltage.setconstraint(left, 1.0);
    voltage.setconstraint(right, 0.0);

    formulation electrical;
    electrical += integral(all, conductivity_s_per_m * grad(dof(voltage)) * grad(tf(voltage)));
    electrical.solve();

    const double conductance_s =
        (conductivity_s_per_m * grad(voltage) * grad(voltage)).integrate(all, 5);
    const double resistance_ohm = 1.0 / conductance_s;
    const double resistance_error = std::abs(resistance_ohm - expected_resistance_ohm) /
        expected_resistance_ohm;
    const bool passed = std::isfinite(resistance_ohm) && resistance_error <= relative_tolerance;

    std::ofstream output(arguments.output_path, std::ios::binary | std::ios::trunc);
    if (!output) {
        throw std::runtime_error("cannot create self-test output: " + arguments.output_path);
    }
    output << std::setprecision(17)
           << "{\n"
           << "  \"contract\": \"spike/sparselizard-runtime-self-test/v1\",\n"
           << "  \"status\": \"" << (passed ? "passed" : "failed") << "\",\n"
           << "  \"platform\": \"windows-ucrt64\",\n"
           << "  \"linear_solver\": \"petsc-lu\",\n"
           << "  \"zero_diagonal_policy\": \"reorder-1e-12\",\n"
           << "  \"fixture\": \"unit-square-dc-conduction\",\n"
           << "  \"validation_scope\": \"native-dc-fem-runtime-only\",\n"
           << "  \"conductivity_s_per_m\": " << conductivity_s_per_m << ",\n"
           << "  \"resistance_ohm\": " << resistance_ohm << ",\n"
           << "  \"expected_resistance_ohm\": " << expected_resistance_ohm << ",\n"
           << "  \"maximum_relative_error\": " << resistance_error << ",\n"
           << "  \"relative_tolerance\": " << relative_tolerance << "\n"
           << "}\n";
    return passed ? 0 : 2;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        return run_dc_conduction_self_test(parse_arguments(argc, argv));
    } catch (const std::exception& error) {
        std::cerr << "sparseLizard runtime error: " << error.what() << '\n';
        return 1;
    }
}
