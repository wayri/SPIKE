#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <variant>
#include <vector>

namespace spikes {

/** OSDI noise-source endpoint sentinel representing the global reference. */
inline constexpr std::size_t osdi_reference_node =
    static_cast<std::size_t>(-1);

struct OsdiJacobianStamp {
  std::size_t row{0};
  std::size_t column{0};
  double value{0.0};
  std::uint32_t flags{0};
};

struct OsdiDcEvaluation {
  std::vector<double> residual;
  std::vector<OsdiJacobianStamp> jacobian;
  std::uint32_t evaluation_flags{0};
};

struct OsdiTransientState {
  std::vector<double> device_state;
  std::vector<double> reactive_residual;
};

struct OsdiTransientEvaluation {
  std::vector<double> residual;
  std::vector<OsdiJacobianStamp> jacobian;
  OsdiTransientState next;
  std::uint32_t evaluation_flags{0};
};

enum class OsdiNoiseType : std::uint32_t {
  white = 0,
  flicker = 1,
  table = 2,
  unspecified = 0xffffffffU,
};

struct OsdiNoiseContribution {
  std::string name;
  std::size_t positive_node{0};
  std::size_t negative_node{0};
  double density_a2_per_hz{0.0};
  OsdiNoiseType type{OsdiNoiseType::unspecified};
  double power{0.0};
  double exponent{0.0};
};

struct OsdiNoiseEvaluation {
  std::vector<OsdiNoiseContribution> contributions;
  std::uint32_t evaluation_flags{0};
};

enum class OsdiParameterType : std::uint32_t {
  real = 0,
  integer = 1,
  string = 2,
};

enum class OsdiParameterKind : std::uint32_t {
  model = 0,
  instance = 1,
  operating_variable = 2,
};

/** Immutable parameter metadata exported by an OSDI descriptor. */
struct OsdiParameterInfo {
  std::vector<std::string> names;
  std::string description;
  std::string units;
  OsdiParameterType type{OsdiParameterType::real};
  OsdiParameterKind kind{OsdiParameterKind::model};
  std::size_t array_length{0};
};

/** One scalar model or instance parameter supplied before OSDI setup. */
struct OsdiParameterAssignment {
  std::string name;
  std::variant<double, std::int32_t, std::string> value;
  bool instance{false};
};

/**
 * One initialized OSDI 0.3/0.4 model/instance registered with the C++ solver.
 *
 * Loading a native module executes its process-level initialization code.
 * This class is therefore deliberately named by the trusted loader below and
 * must only be used for digest-reviewed modules unless the whole solver is
 * already running inside an OS-enforced hostile-code sandbox.
 */
class OsdiDeviceInstance {
public:
  ~OsdiDeviceInstance();
  OsdiDeviceInstance(const OsdiDeviceInstance &) = delete;
  OsdiDeviceInstance &operator=(const OsdiDeviceInstance &) = delete;

  [[nodiscard]] std::string_view module_name() const noexcept;
  [[nodiscard]] std::uint32_t abi_minor() const noexcept;
  [[nodiscard]] std::size_t node_count() const noexcept;
  [[nodiscard]] std::size_t terminal_count() const noexcept;
  [[nodiscard]] std::vector<OsdiParameterInfo> parameter_info() const;
  [[nodiscard]] std::span<const std::pair<std::size_t, std::size_t>>
  jacobian_pattern() const noexcept;
  [[nodiscard]] OsdiDcEvaluation
  evaluate_dc(std::span<const double> node_voltages_v);
  [[nodiscard]] OsdiTransientState initial_transient_state(
      std::span<const double> node_voltages_v, double absolute_time_s = 0.0);
  [[nodiscard]] OsdiTransientEvaluation evaluate_transient_backward_euler(
      std::span<const double> node_voltages_v,
      std::span<const double> previous_node_voltages_v,
      double absolute_time_s, double time_step_s,
      const OsdiTransientState &previous);
  [[nodiscard]] OsdiNoiseEvaluation evaluate_noise(
      std::span<const double> node_voltages_v, double frequency_hz);

private:
  struct Impl;
  explicit OsdiDeviceInstance(std::unique_ptr<Impl> implementation);
  std::unique_ptr<Impl> impl_;

  friend std::shared_ptr<OsdiDeviceInstance> load_trusted_osdi_device(
      const std::filesystem::path &, std::string_view, double,
      std::span<const OsdiParameterAssignment>);
};

/** Load one default-parameter OSDI 0.3 or 0.4 instance. */
[[nodiscard]] std::shared_ptr<OsdiDeviceInstance>
load_trusted_osdi_device(const std::filesystem::path &artifact,
                         std::string_view module_name,
                         double temperature_k = 300.15,
                         std::span<const OsdiParameterAssignment> parameters = {});

/** Compatibility spelling retained for callers that only supplied 0.3 modules. */
[[nodiscard]] std::shared_ptr<OsdiDeviceInstance>
load_trusted_osdi_0_3_device(const std::filesystem::path &artifact,
                             std::string_view module_name,
                             double temperature_k = 300.15);

} // namespace spikes
