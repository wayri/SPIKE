// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 SigHarmonic
// One-shot development ABI host. Never link this loader into the application.
#include <algorithm>
#include <bit>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#else
#include <dlfcn.h>
#endif

namespace {
constexpr std::uint32_t max_samples = 65536;
constexpr std::uint32_t max_string = 16384;
using Init = long (*)(double*, long, long, double, double, char*, char**, void**, char**);
using Wave = long (*)(double*, long, double*, char**, void*);
using Close = long (*)(void*);

template<class T> T read(std::istream& in) {
    T value{};
    if (!in.read(reinterpret_cast<char*>(&value), sizeof(value)))
        throw std::runtime_error("truncated request");
    return value;
}
template<class T> void write(std::ostream& out, T value) {
    out.write(reinterpret_cast<const char*>(&value), sizeof(value));
}
void text(std::ostream& out, const std::string& value) {
    write(out, static_cast<std::uint32_t>(value.size()));
    out.write(value.data(), static_cast<std::streamsize>(value.size()));
}
std::string copy_string(const char* pointer, bool required = false) {
    if (!pointer) {
        if (required) throw std::runtime_error("missing AMI output parameter string");
        return {};
    }
    std::string result;
    for (std::uint32_t i = 0; i <= max_string; ++i) {
        const auto c = pointer[i]; // Faults stay in this disposable child.
        if (!c) return result;
        if (i == max_string) throw std::runtime_error("AMI output string exceeds budget");
        if (static_cast<unsigned char>(c) > 126 || (c < 32 && c != '\n' && c != '\r' && c != '\t'))
            throw std::runtime_error("non-ASCII AMI output string");
        result.push_back(c);
    }
    throw std::runtime_error("unterminated AMI output string");
}
std::vector<double> samples(std::istream& in, std::uint32_t n) {
    if (!n || n > max_samples) throw std::runtime_error("invalid sample count");
    std::vector<double> values(n);
    for (auto& value : values) {
        value = read<double>(in);
        if (!std::isfinite(value)) throw std::runtime_error("non-finite input");
    }
    return values;
}
void finite(const std::vector<double>& values) {
    for (double value : values)
        if (!std::isfinite(value)) throw std::runtime_error("non-finite model output");
}
void array(std::ostream& out, const std::vector<double>& values) {
    write(out, static_cast<std::uint32_t>(values.size()));
    for (double value : values) write(out, value);
}
struct Library {
#ifdef _WIN32
    HMODULE handle;
    explicit Library(const std::filesystem::path& path) {
        SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
        if (!SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32))
            throw std::runtime_error("DLL search confinement failed");
        handle = LoadLibraryExW(path.c_str(), nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
        if (!handle) throw std::runtime_error("model load failed");
    }
    ~Library() { FreeLibrary(handle); }
    template<class T> T symbol(const char* name) {
        return reinterpret_cast<T>(GetProcAddress(handle, name));
    }
#else
    void* handle;
    explicit Library(const std::filesystem::path& path) {
        handle = dlopen(path.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!handle) throw std::runtime_error("model load failed");
    }
    ~Library() { dlclose(handle); }
    template<class T> T symbol(const char* name) { return reinterpret_cast<T>(dlsym(handle, name)); }
#endif
};
struct Session {
    Close close;
    void* memory = nullptr;
    bool initialized = false;
    ~Session() { if (initialized) close(memory); }
    void finish() {
        initialized = false; // Do not call twice if Close reports failure.
        if (close(memory) != 1) throw std::runtime_error("AMI_Close failed");
    }
};
struct Block { std::vector<double> wave, clocks; std::string parameters; };

void execute(const std::filesystem::path& library, std::istream& in, std::ostream& out) {
    static_assert(sizeof(double) == 8 && std::numeric_limits<double>::is_iec559);
    static_assert(std::endian::native == std::endian::little);
    char magic[8];
    in.read(magic, 8);
    if (std::string(magic, 8) != std::string("SPKAMI1\0", 8)) throw std::runtime_error("request version");
    const auto rows = read<std::uint32_t>(in), count = read<std::uint32_t>(in);
    const auto direction = read<std::uint32_t>(in);
    const auto dt = read<double>(in), ui = read<double>(in);
    const auto length = read<std::uint32_t>(in);
    if (count > 64 || direction > 1 || !length || length > max_string ||
        !std::isfinite(dt) || !std::isfinite(ui) || dt <= 0 || ui < dt)
        throw std::runtime_error("request bounds");
    std::string parameters(length, '\0');
    if (!in.read(parameters.data(), length) || parameters.find('\0') != std::string::npos)
        throw std::runtime_error("invalid parameters");
    auto impulse = samples(in, rows);
    std::vector<Block> blocks;
    std::uint32_t total = 0;
    for (std::uint32_t i = 0; i < count; ++i) {
        const auto n = read<std::uint32_t>(in);
        if (n > max_samples - total) throw std::runtime_error("wave sample budget");
        total += n;
        blocks.push_back({samples(in, n), {}, {}});
    }
    if (in.peek() != std::char_traits<char>::eof()) throw std::runtime_error("trailing request bytes");
    Library model(library);
    auto init = model.symbol<Init>("AMI_Init");
    auto wave = model.symbol<Wave>("AMI_GetWave");
    auto close = model.symbol<Close>("AMI_Close");
    if (!init || !close || (count && !wave)) throw std::runtime_error("required AMI export absent");
    Session session{close};
    char* returned = nullptr;
    char* message = nullptr;
    if (init(impulse.data(), rows, 0, dt, ui, parameters.data(), &returned, &session.memory, &message) != 1)
        throw std::runtime_error("AMI_Init failed");
    session.initialized = true;
    const auto init_parameters = copy_string(returned, true);
    const auto init_message = copy_string(message);
    finite(impulse);
    double last_clock = -1;
    for (auto& block : blocks) {
        // Single-input Rx subset, at most one returned clock per input sample.
        std::vector<double> clocks(block.wave.size() + 1, std::numeric_limits<double>::quiet_NaN());
        returned = nullptr;
        if (wave(block.wave.data(), static_cast<long>(block.wave.size()), direction ? clocks.data() : nullptr,
                 &returned, session.memory) != 1) throw std::runtime_error("AMI_GetWave failed");
        block.parameters = copy_string(returned, true);
        finite(block.wave);
        if (direction) {
            bool terminated = false;
            for (double clock : clocks) {
                if (clock == -1) { terminated = true; break; }
                if (!std::isfinite(clock) || clock < 0 || clock <= last_clock)
                    throw std::runtime_error("invalid or nonmonotonic clock output");
                last_clock = clock;
                block.clocks.push_back(clock);
            }
            if (!terminated) throw std::runtime_error("unterminated clock output");
        }
    }
    session.finish();
    out.write("SPKAMO1\0", 8);
    write<std::uint32_t>(out, 0);
    text(out, ""); text(out, init_parameters); text(out, init_message);
    array(out, impulse);
    write(out, count);
    for (const auto& block : blocks) {
        text(out, block.parameters); array(out, block.wave); array(out, block.clocks);
    }
}
} // namespace

int main(int argc, char** argv) {
    if (argc != 4) return 64;
    std::ofstream out(argv[3], std::ios::binary | std::ios::trunc);
    if (!out) return 65;
    try {
        std::ifstream in(argv[2], std::ios::binary);
        execute(std::filesystem::absolute(argv[1]), in, out);
        out.flush();
        return out ? 0 : 66;
    } catch (const std::exception& error) {
        out.seekp(0);
        out.write("SPKAMO1\0", 8);
        write<std::uint32_t>(out, 1);
        text(out, error.what());
        return 1;
    }
}
