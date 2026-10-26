// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
// Original ABI/fault fixtures; no vendor or specification example code.
#include <cmath>
#include <cstdlib>
#include <limits>
#include <thread>
#include <chrono>
#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#define EXPORT extern "C" __declspec(dllexport)
#else
#define EXPORT extern "C" __attribute__((visibility("default")))
#endif
#ifndef FIXTURE_MODE
#define FIXTURE_MODE 0
#endif
namespace {
struct State { double previous = 0; double time = 0; double dt = 0; };
char root[] = "(CopperFox)";
char wrong_root[] = "(AnotherRoot)";
char malformed_parameters[] = "(CopperFox (Gain 1)";
char message[] = "original SPIKE synthetic fixture";
char child_denied[] = "(CopperFox (ChildDenied True))";
double apply(double input, double& previous) {
    double value = input;
    if constexpr (FIXTURE_MODE == 1) { value = .75 * input + .25 * previous; previous = input; }
    if constexpr (FIXTURE_MODE == 2) { value = .5 * input + .5 * previous; previous = value; }
    if constexpr (FIXTURE_MODE == 15) value = 2 * input;
    return value;
}
}
EXPORT long AMI_Init(double* impulse, long rows, long aggressors, double dt, double,
                     char*, char** output, void** memory, char** msg) {
    if constexpr (FIXTURE_MODE == 3) return 0;
    if constexpr (FIXTURE_MODE == 6) std::abort();
    if constexpr (FIXTURE_MODE == 7) std::this_thread::sleep_for(std::chrono::seconds(60));
#ifdef _WIN32
    if constexpr (FIXTURE_MODE == 13) {
        wchar_t executable[32768];
        if (!GetModuleFileNameW(nullptr, executable, 32768)) return 0;
        STARTUPINFOW startup{};
        startup.cb = sizeof(startup);
        PROCESS_INFORMATION child{};
        if (CreateProcessW(executable, nullptr, nullptr, nullptr, FALSE, CREATE_NO_WINDOW,
                           nullptr, nullptr, &startup, &child)) {
            WaitForSingleObject(child.hProcess, 1000);
            CloseHandle(child.hThread); CloseHandle(child.hProcess);
            return 0; // The supervisor must prevent a second process.
        }
        if (GetLastError() != ERROR_NOT_ENOUGH_QUOTA) return 0;
    }
#endif
    if (aggressors != 0 || !impulse || rows <= 0 || !output || !memory || !msg) return 0;
    auto* state = new State;
    state->dt = dt;
    *memory = state;
    *output = FIXTURE_MODE == 11 ? wrong_root : root;
    if constexpr (FIXTURE_MODE == 13) *output = child_denied;
    if constexpr (FIXTURE_MODE == 14) *output = malformed_parameters;
    *msg = message;
    double previous = 0;
    for (long i = 0; i < rows; ++i) impulse[i] = apply(impulse[i], previous);
    if constexpr (FIXTURE_MODE == 8) impulse[0] = std::numeric_limits<double>::quiet_NaN();
    return 1;
}
#if FIXTURE_MODE != 12
EXPORT long AMI_GetWave(double* wave, long size, double* clocks, char** output, void* memory) {
    if constexpr (FIXTURE_MODE == 4) return 0;
    auto* state = static_cast<State*>(memory);
    if (!state || !wave || !output) return 0;
    for (long i = 0; i < size; ++i) wave[i] = apply(wave[i], state->previous);
    *output = root;
    if constexpr (FIXTURE_MODE == 16) *output = malformed_parameters;
    if (clocks) {
        if constexpr (FIXTURE_MODE == 9) { clocks[0] = 1; clocks[1] = 1; clocks[2] = -1; }
        else if constexpr (FIXTURE_MODE == 10) {
            for (long i = 0; i <= size; ++i) clocks[i] = state->time + state->dt * i;
        } else { clocks[0] = state->time; clocks[1] = -1; }
    }
    state->time += state->dt * size;
    return 1;
}
#endif
EXPORT long AMI_Close(void* memory) {
    if (!memory) return 0;
    delete static_cast<State*>(memory);
    if constexpr (FIXTURE_MODE == 5) return 0;
    return 1;
}
