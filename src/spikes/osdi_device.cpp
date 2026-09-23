#include "spikes/osdi_device.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <mutex>
#include <stdexcept>
#include <unordered_set>

#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#else
#include <dlfcn.h>
#endif

namespace spikes {
namespace {

constexpr std::uint32_t calculate_resistive_residual = 1U;
constexpr std::uint32_t calculate_reactive_residual = 2U;
constexpr std::uint32_t calculate_resistive_jacobian = 4U;
constexpr std::uint32_t calculate_reactive_jacobian = 8U;
constexpr std::uint32_t calculate_noise = 16U;
constexpr std::uint32_t calculate_operating_point = 32U;
constexpr std::uint32_t analysis_noise = 1024U;
constexpr std::uint32_t analysis_dc = 2048U;
constexpr std::uint32_t analysis_transient = 8192U;
constexpr std::uint32_t fatal_evaluation_mask = 2U | 4U | 8U;
constexpr std::uint32_t jacobian_entry_reactive_constant = 2U;
constexpr std::uint32_t jacobian_entry_reactive = 8U;
constexpr std::uint32_t parameter_type_mask = 3U;
constexpr std::uint32_t parameter_kind_mask = 3U << 30U;
constexpr std::uint32_t parameter_kind_instance = 1U << 30U;
constexpr std::uint32_t parameter_kind_operating_variable = 2U << 30U;
constexpr std::uint32_t access_flag_set = 1U;
constexpr std::uint32_t access_flag_instance = 4U;
constexpr std::size_t max_osdi_parameters = 100'000;
constexpr std::uint32_t log_format_error = 16U;

struct OsdiSimParameters {
  const char **names;
  double *values;
  const char **string_names;
  const char **string_values;
};

struct OsdiSimInfo {
  OsdiSimParameters parameters;
  double absolute_time;
  double *previous_solution;
  double *previous_state;
  double *next_state;
  std::uint32_t flags;
};

union OsdiInitErrorPayload {
  std::uint32_t parameter_id;
};
struct OsdiInitError {
  std::uint32_t code;
  OsdiInitErrorPayload payload;
};
struct OsdiInitInfo {
  std::uint32_t flags;
  std::uint32_t error_count;
  OsdiInitError *errors;
};
struct OsdiNodePair {
  std::uint32_t first;
  std::uint32_t second;
};
struct OsdiJacobianEntry {
  OsdiNodePair nodes;
  std::uint32_t reactive_pointer_offset;
  std::uint32_t flags;
};
struct OsdiNode {
  const char *name;
  const char *units;
  const char *residual_units;
  std::uint32_t resistive_residual_offset;
  std::uint32_t reactive_residual_offset;
  std::uint32_t resistive_limit_rhs_offset;
  std::uint32_t reactive_limit_rhs_offset;
  bool is_flow;
};
struct OsdiNoiseSource {
  const char *name;
  OsdiNodePair nodes;
};
struct OsdiParameterOrOperatingVariable {
  const char **names;
  std::uint32_t alias_count;
  const char *description;
  const char *units;
  std::uint32_t flags;
  std::uint32_t length;
};

using SetupModel = void (*)(void *, void *, OsdiSimParameters *, OsdiInitInfo *);
using SetupInstance = void (*)(void *, void *, void *, double, std::uint32_t,
                               OsdiSimParameters *, OsdiInitInfo *);
using Access = void *(*)(void *, void *, std::uint32_t, std::uint32_t);
using Evaluate = std::uint32_t (*)(void *, void *, void *, OsdiSimInfo *);
using LoadNoise03 = void (*)(void *, void *, double, double *, double *);
using LoadNoise04 = void (*)(void *, void *, double, double *);
using LoadResidual = void (*)(void *, void *, double *);
using LoadJacobian = void (*)(void *, void *);
using LoadReactiveJacobian = void (*)(void *, void *, double);
using LoadNoiseParameters = void (*)(void *, void *, double *, double *);
using OsdiLog = void (*)(void *, char *, std::uint32_t);

void osdi_log_sink(void *, char *message, std::uint32_t flags) noexcept {
  // OSDI transfers ownership for successfully formatted messages.  The
  // LOG_FMT_ERR path passes a string literal and must not be released.
  if (message != nullptr && (flags & log_format_error) == 0) {
    std::free(message);
  }
}

bool ascii_case_equal(std::string_view left, std::string_view right) {
  return left.size() == right.size() &&
         std::equal(left.begin(), left.end(), right.begin(),
                    [](char a, char b) {
                      return std::tolower(static_cast<unsigned char>(a)) ==
                             std::tolower(static_cast<unsigned char>(b));
                    });
}

struct OsdiDescriptor03 {
  const char *name;
  std::uint32_t node_count;
  std::uint32_t terminal_count;
  OsdiNode *nodes;
  std::uint32_t jacobian_count;
  OsdiJacobianEntry *jacobian_entries;
  std::uint32_t collapsible_count;
  OsdiNodePair *collapsible;
  std::uint32_t collapsed_offset;
  OsdiNoiseSource *noise_sources;
  std::uint32_t noise_source_count;
  std::uint32_t parameter_count;
  std::uint32_t instance_parameter_count;
  std::uint32_t operating_variable_count;
  void *parameter_or_operating_variable;
  std::uint32_t node_mapping_offset;
  std::uint32_t resistive_jacobian_pointer_offset;
  std::uint32_t state_count;
  std::uint32_t state_index_offset;
  std::uint32_t bound_step_offset;
  std::uint32_t instance_size;
  std::uint32_t model_size;
  Access access;
  SetupModel setup_model;
  SetupInstance setup_instance;
  Evaluate evaluate;
  void *load_noise;
  LoadResidual load_residual_resistive;
  LoadResidual load_residual_reactive;
  void *load_limit_rhs_resistive;
  void *load_limit_rhs_reactive;
  void *load_spice_rhs_dc;
  void *load_spice_rhs_transient;
  LoadJacobian load_jacobian_resistive;
  LoadReactiveJacobian load_jacobian_reactive;
  LoadReactiveJacobian load_jacobian_transient;
};

struct OsdiDescriptor04 {
  OsdiDescriptor03 prefix;
  void *given_flag_model;
  void *given_flag_instance;
  std::uint32_t resistive_jacobian_entry_count;
  std::uint32_t reactive_jacobian_entry_count;
  void *write_jacobian_array_resistive;
  void *write_jacobian_array_reactive;
  std::uint32_t input_count;
  OsdiNodePair *inputs;
  void *load_jacobian_with_offset_resistive;
  void *load_jacobian_with_offset_reactive;
  void *unknown_nature;
  void *residual_nature;
  std::uint32_t *noise_source_type;
  LoadNoiseParameters load_noise_parameters;
  std::uint32_t absolute_delay_count;
  const void *absolute_delay_information;
};

class SharedLibrary {
public:
  explicit SharedLibrary(const std::filesystem::path &path) {
#ifdef _WIN32
    handle_ = LoadLibraryW(path.c_str());
    if (handle_ == nullptr) {
      throw std::runtime_error("failed to load trusted OSDI module");
    }
#else
    handle_ = dlopen(path.c_str(), RTLD_NOW | RTLD_LOCAL);
    if (handle_ == nullptr) {
      throw std::runtime_error("failed to load trusted OSDI module");
    }
#endif
  }
  ~SharedLibrary() {
#ifdef _WIN32
    if (handle_ != nullptr) {
      FreeLibrary(handle_);
    }
#else
    if (handle_ != nullptr) {
      dlclose(handle_);
    }
#endif
  }
  SharedLibrary(const SharedLibrary &) = delete;
  SharedLibrary &operator=(const SharedLibrary &) = delete;

  [[nodiscard]] void *symbol(const char *name) const {
#ifdef _WIN32
    return reinterpret_cast<void *>(GetProcAddress(handle_, name));
#else
    return dlsym(handle_, name);
#endif
  }

private:
#ifdef _WIN32
  HMODULE handle_{nullptr};
#else
  void *handle_{nullptr};
#endif
};

template <typename Type>
Type *required_symbol(const SharedLibrary &library, const char *name) {
  auto *result = static_cast<Type *>(library.symbol(name));
  if (result == nullptr) {
    throw std::invalid_argument(std::string("OSDI module omits symbol ") + name);
  }
  return result;
}

void validate_descriptor(const OsdiDescriptor03 &descriptor,
                         bool require_transient_or_noise = false) {
  if (descriptor.name == nullptr || descriptor.node_count == 0 ||
      descriptor.node_count > 4096 || descriptor.terminal_count == 0 ||
      descriptor.terminal_count > descriptor.node_count ||
      descriptor.jacobian_count > 1'000'000 || descriptor.instance_size == 0 ||
      descriptor.instance_size > 256U * 1024U * 1024U ||
      descriptor.model_size == 0 ||
      descriptor.model_size > 256U * 1024U * 1024U ||
      descriptor.setup_model == nullptr || descriptor.setup_instance == nullptr ||
      descriptor.access == nullptr ||
      descriptor.evaluate == nullptr ||
      descriptor.load_residual_resistive == nullptr ||
      descriptor.load_jacobian_resistive == nullptr ||
      (descriptor.jacobian_count != 0 && descriptor.jacobian_entries == nullptr)) {
    throw std::invalid_argument("OSDI descriptor violates the bounded callback contract");
  }
  const auto metadata_count = static_cast<std::uint64_t>(descriptor.parameter_count) +
                              descriptor.operating_variable_count;
  if (descriptor.parameter_count > max_osdi_parameters ||
      descriptor.instance_parameter_count > descriptor.parameter_count ||
      descriptor.operating_variable_count > max_osdi_parameters ||
      metadata_count > max_osdi_parameters ||
      (metadata_count != 0 &&
       descriptor.parameter_or_operating_variable == nullptr)) {
    throw std::invalid_argument("OSDI parameter metadata violates its bounded contract");
  }
  const auto mapping_end =
      static_cast<std::uint64_t>(descriptor.node_mapping_offset) +
      static_cast<std::uint64_t>(descriptor.node_count) * sizeof(std::uint32_t);
  const auto pointer_end =
      static_cast<std::uint64_t>(descriptor.resistive_jacobian_pointer_offset) +
      static_cast<std::uint64_t>(descriptor.jacobian_count) * sizeof(double *);
  if (mapping_end > descriptor.instance_size || pointer_end > descriptor.instance_size) {
    throw std::invalid_argument("OSDI descriptor instance offsets are out of bounds");
  }
  for (std::size_t index = 0; index < descriptor.jacobian_count; ++index) {
    if (descriptor.jacobian_entries[index].nodes.first >= descriptor.node_count ||
        descriptor.jacobian_entries[index].nodes.second >= descriptor.node_count) {
      throw std::invalid_argument("OSDI Jacobian node index is out of bounds");
    }
    const auto &entry = descriptor.jacobian_entries[index];
    if (entry.reactive_pointer_offset !=
        std::numeric_limits<std::uint32_t>::max()) {
      const auto reactive_pointer_end =
          static_cast<std::uint64_t>(entry.reactive_pointer_offset) +
          sizeof(double *);
      if (reactive_pointer_end > descriptor.instance_size) {
        throw std::invalid_argument(
            "OSDI reactive Jacobian pointer offset is out of bounds");
      }
    }
  }
  if (require_transient_or_noise && descriptor.load_residual_reactive == nullptr &&
      descriptor.load_noise == nullptr) {
    throw std::invalid_argument(
        "OSDI descriptor exposes neither transient nor noise callbacks");
  }
}

} // namespace

struct OsdiDeviceInstance::Impl {
  std::shared_ptr<SharedLibrary> library;
  const OsdiDescriptor03 *descriptor{nullptr};
  const OsdiDescriptor04 *descriptor04{nullptr};
  std::uint32_t abi_minor{0};
  std::uint32_t descriptor_stride{0};
  std::string module_name;
  std::vector<std::byte> model;
  std::vector<std::byte> instance;
  std::vector<double> resistive_jacobian_values;
  std::vector<double> reactive_jacobian_values;
  std::vector<std::pair<std::size_t, std::size_t>> pattern;
  OsdiSimParameters parameters{};
  std::array<const char *, 3> simulator_parameter_names{{"gmin", "minr", nullptr}};
  std::array<double, 2> simulator_parameter_values{{1.0e-12, 1.0e-3}};
  std::array<const char *, 1> simulator_string_names{{nullptr}};
  std::array<const char *, 1> simulator_string_values{{nullptr}};
  std::vector<std::unique_ptr<std::string>> assigned_strings;
  std::mutex mutex;
};

OsdiDeviceInstance::OsdiDeviceInstance(std::unique_ptr<Impl> implementation)
    : impl_(std::move(implementation)) {}
OsdiDeviceInstance::~OsdiDeviceInstance() = default;

std::string_view OsdiDeviceInstance::module_name() const noexcept {
  return impl_->module_name;
}
std::uint32_t OsdiDeviceInstance::abi_minor() const noexcept {
  return impl_->abi_minor;
}
std::size_t OsdiDeviceInstance::node_count() const noexcept {
  return impl_->descriptor->node_count;
}
std::size_t OsdiDeviceInstance::terminal_count() const noexcept {
  return impl_->descriptor->terminal_count;
}

std::vector<std::size_t> OsdiDeviceInstance::node_aliases() const {
  std::scoped_lock lock(impl_->mutex);
  const auto& d=*impl_->descriptor;
  if(d.collapsible_count>1'000'000 || (d.collapsible_count && (!d.collapsible ||
      static_cast<std::uint64_t>(d.collapsed_offset)+d.collapsible_count*sizeof(bool)>d.instance_size)))
    throw std::invalid_argument("Invalid OSDI collapse metadata");
  std::vector<std::size_t> aliases(d.node_count+1);
  for(std::size_t i=0;i<aliases.size();++i)aliases[i]=i;
  auto root=[&](std::size_t i){while(aliases[i]!=i)i=aliases[i];return i;};
  const auto* collapsed=reinterpret_cast<const bool*>(impl_->instance.data()+d.collapsed_offset);
  for(std::size_t i=0;i<d.collapsible_count;++i)if(collapsed[i]){
    const auto pair=d.collapsible[i];
    const auto a=pair.first==UINT32_MAX?d.node_count:pair.first;
    const auto b=pair.second==UINT32_MAX?d.node_count:pair.second;
    if(a>d.node_count||b>d.node_count)throw std::invalid_argument("Invalid collapsed OSDI node");
    auto ra=root(a),rb=root(b);
    if(ra==d.node_count||rb==d.node_count)aliases[ra==d.node_count?rb:ra]=d.node_count;
    else aliases[std::max(ra,rb)]=std::min(ra,rb);
  }
  std::vector<std::size_t> result(d.node_count);
  for(std::size_t i=0;i<d.node_count;++i){auto r=root(i);result[i]=r==d.node_count?osdi_reference_node:r;}
  return result;
}

std::vector<OsdiParameterInfo> OsdiDeviceInstance::parameter_info() const {
  std::scoped_lock lock(impl_->mutex);
  const auto &descriptor = *impl_->descriptor;
  const auto count = static_cast<std::size_t>(descriptor.parameter_count) +
                     descriptor.operating_variable_count;
  const auto *metadata = static_cast<const OsdiParameterOrOperatingVariable *>(
      descriptor.parameter_or_operating_variable);
  std::vector<OsdiParameterInfo> result;
  result.reserve(count);
  for (std::size_t index = 0; index < count; ++index) {
    const auto &entry = metadata[index];
    if (entry.names == nullptr || entry.names[0] == nullptr ||
        entry.alias_count > 1024 || entry.length > 1'000'000) {
      throw std::runtime_error("OSDI parameter metadata is malformed");
    }
    OsdiParameterInfo info;
    info.names.reserve(static_cast<std::size_t>(entry.alias_count) + 1);
    for (std::size_t alias = 0; alias <= entry.alias_count; ++alias) {
      if (entry.names[alias] == nullptr) {
        throw std::runtime_error("OSDI parameter alias is null");
      }
      info.names.emplace_back(entry.names[alias]);
    }
    info.description = entry.description == nullptr ? "" : entry.description;
    info.units = entry.units == nullptr ? "" : entry.units;
    const auto type = entry.flags & parameter_type_mask;
    if (type > static_cast<std::uint32_t>(OsdiParameterType::string)) {
      throw std::runtime_error("OSDI parameter type is unsupported");
    }
    info.type = static_cast<OsdiParameterType>(type);
    const auto kind = entry.flags & parameter_kind_mask;
    if (kind == parameter_kind_instance) {
      info.kind = OsdiParameterKind::instance;
    } else if (kind == parameter_kind_operating_variable) {
      info.kind = OsdiParameterKind::operating_variable;
    } else if (kind == 0) {
      info.kind = OsdiParameterKind::model;
    } else {
      throw std::runtime_error("OSDI parameter kind is unsupported");
    }
    info.array_length = entry.length;
    result.push_back(std::move(info));
  }
  return result;
}
std::span<const std::pair<std::size_t, std::size_t>>
OsdiDeviceInstance::jacobian_pattern() const noexcept {
  return impl_->pattern;
}

OsdiDcEvaluation
OsdiDeviceInstance::evaluate_dc(std::span<const double> node_voltages_v) {
  std::scoped_lock lock(impl_->mutex);
  const auto &descriptor = *impl_->descriptor;
  if (node_voltages_v.size() != descriptor.node_count ||
      !std::all_of(node_voltages_v.begin(), node_voltages_v.end(),
                   [](double value) { return std::isfinite(value); })) {
    throw std::invalid_argument("OSDI DC node voltages violate the descriptor contract");
  }
  std::vector<double> solution(node_voltages_v.begin(), node_voltages_v.end());
  std::vector<double> previous_state(std::max(1U, descriptor.state_count), 0.0);
  std::vector<double> next_state(previous_state.size(), 0.0);
  OsdiSimInfo information{
      impl_->parameters, 0.0, solution.data(), previous_state.data(),
      next_state.data(),
      calculate_resistive_residual | calculate_resistive_jacobian |
          calculate_operating_point | analysis_dc};
  const auto flags = descriptor.evaluate(
      nullptr, impl_->instance.data(), impl_->model.data(), &information);
  if ((flags & fatal_evaluation_mask) != 0) {
    throw std::runtime_error("OSDI DC evaluation returned a fatal flag");
  }
  OsdiDcEvaluation result;
  result.residual.assign(descriptor.node_count, 0.0);
  descriptor.load_residual_resistive(impl_->instance.data(), impl_->model.data(),
                                     result.residual.data());
  descriptor.load_jacobian_resistive(impl_->instance.data(), impl_->model.data());
  if (!std::all_of(result.residual.begin(), result.residual.end(),
                   [](double value) { return std::isfinite(value); })) {
    throw std::runtime_error("OSDI DC residual contains a non-finite value");
  }
  result.jacobian.reserve(descriptor.jacobian_count);
  for (std::size_t index = 0; index < descriptor.jacobian_count; ++index) {
    const double value = impl_->resistive_jacobian_values[index];
    if (!std::isfinite(value)) {
      throw std::runtime_error("OSDI DC Jacobian contains a non-finite value");
    }
    const auto &entry = descriptor.jacobian_entries[index];
    result.jacobian.push_back({entry.nodes.first, entry.nodes.second, value,
                               entry.flags});
  }
  result.evaluation_flags = flags;
  return result;
}

OsdiTransientState OsdiDeviceInstance::initial_transient_state(
    std::span<const double> node_voltages_v, double absolute_time_s) {
  std::scoped_lock lock(impl_->mutex);
  const auto &descriptor = *impl_->descriptor;
  if (descriptor.load_residual_reactive == nullptr ||
      node_voltages_v.size() != descriptor.node_count ||
      !std::isfinite(absolute_time_s) ||
      !std::all_of(node_voltages_v.begin(), node_voltages_v.end(),
                   [](double value) { return std::isfinite(value); })) {
    throw std::invalid_argument(
        "OSDI transient initialization violates the reactive callback contract");
  }
  std::vector<double> solution(node_voltages_v.begin(), node_voltages_v.end());
  OsdiTransientState state;
  state.device_state.assign(std::max(1U, descriptor.state_count), 0.0);
  std::vector<double> next_state(state.device_state.size(), 0.0);
  OsdiSimInfo information{impl_->parameters,
                          absolute_time_s,
                          solution.data(),
                          state.device_state.data(),
                          next_state.data(),
                          calculate_reactive_residual | analysis_transient};
  const auto flags = descriptor.evaluate(
      nullptr, impl_->instance.data(), impl_->model.data(), &information);
  if ((flags & fatal_evaluation_mask) != 0) {
    throw std::runtime_error(
        "OSDI transient initialization returned a fatal flag");
  }
  state.device_state = std::move(next_state);
  state.reactive_residual.assign(descriptor.node_count, 0.0);
  descriptor.load_residual_reactive(impl_->instance.data(), impl_->model.data(),
                                    state.reactive_residual.data());
  if (!std::all_of(state.reactive_residual.begin(),
                   state.reactive_residual.end(),
                   [](double value) { return std::isfinite(value); })) {
    throw std::runtime_error(
        "OSDI transient initialization produced a non-finite charge residual");
  }
  return state;
}

OsdiTransientEvaluation OsdiDeviceInstance::evaluate_transient_backward_euler(
    std::span<const double> node_voltages_v,
    std::span<const double> previous_node_voltages_v, double absolute_time_s,
    double time_step_s, const OsdiTransientState &previous) {
  std::scoped_lock lock(impl_->mutex);
  const auto &descriptor = *impl_->descriptor;
  const auto state_count = std::max<std::size_t>(1, descriptor.state_count);
  if (descriptor.load_residual_reactive == nullptr ||
      descriptor.load_jacobian_reactive == nullptr ||
      node_voltages_v.size() != descriptor.node_count ||
      previous_node_voltages_v.size() != descriptor.node_count ||
      previous.device_state.size() != state_count ||
      previous.reactive_residual.size() != descriptor.node_count ||
      !std::isfinite(absolute_time_s) || !std::isfinite(time_step_s) ||
      !(time_step_s > 0.0)) {
    throw std::invalid_argument(
        "OSDI backward-Euler inputs violate the transient callback contract");
  }
  const auto finite = [](double value) { return std::isfinite(value); };
  if (!std::all_of(node_voltages_v.begin(), node_voltages_v.end(), finite) ||
      !std::all_of(previous_node_voltages_v.begin(),
                   previous_node_voltages_v.end(), finite) ||
      !std::all_of(previous.device_state.begin(), previous.device_state.end(),
                   finite) ||
      !std::all_of(previous.reactive_residual.begin(),
                   previous.reactive_residual.end(), finite)) {
    throw std::invalid_argument("OSDI backward-Euler inputs must be finite");
  }
  std::vector<double> solution(node_voltages_v.begin(), node_voltages_v.end());
  std::vector<double> previous_solution(previous_node_voltages_v.begin(),
                                        previous_node_voltages_v.end());
  std::vector<double> previous_state = previous.device_state;
  std::vector<double> next_state(state_count, 0.0);
  OsdiSimInfo information{
      impl_->parameters,
      absolute_time_s,
      previous_solution.data(),
      previous_state.data(),
      next_state.data(),
      calculate_resistive_residual | calculate_reactive_residual |
          calculate_resistive_jacobian | calculate_reactive_jacobian |
          calculate_operating_point | analysis_transient};
  // OSDI evaluates unknowns through the node mapping in instance storage.  The
  // current candidate is therefore the simulator solve vector supplied here.
  information.previous_solution = solution.data();
  const auto flags = descriptor.evaluate(
      nullptr, impl_->instance.data(), impl_->model.data(), &information);
  if ((flags & fatal_evaluation_mask) != 0) {
    throw std::runtime_error("OSDI transient evaluation returned a fatal flag");
  }

  OsdiTransientEvaluation result;
  result.residual.assign(descriptor.node_count, 0.0);
  descriptor.load_residual_resistive(impl_->instance.data(), impl_->model.data(),
                                     result.residual.data());
  result.next.device_state = std::move(next_state);
  result.next.reactive_residual.assign(descriptor.node_count, 0.0);
  descriptor.load_residual_reactive(impl_->instance.data(), impl_->model.data(),
                                    result.next.reactive_residual.data());
  const double alpha = 1.0 / time_step_s;
  for (std::size_t index = 0; index < descriptor.node_count; ++index) {
    result.residual[index] +=
        alpha * (result.next.reactive_residual[index] -
                 previous.reactive_residual[index]);
  }
  std::fill(impl_->resistive_jacobian_values.begin(),
            impl_->resistive_jacobian_values.end(), 0.0);
  std::fill(impl_->reactive_jacobian_values.begin(),
            impl_->reactive_jacobian_values.end(), 0.0);
  descriptor.load_jacobian_resistive(impl_->instance.data(), impl_->model.data());
  descriptor.load_jacobian_reactive(impl_->instance.data(), impl_->model.data(),
                                    1.0);
  result.jacobian.reserve(descriptor.jacobian_count);
  for (std::size_t index = 0; index < descriptor.jacobian_count; ++index) {
    const double value = impl_->resistive_jacobian_values[index] +
                         alpha * impl_->reactive_jacobian_values[index];
    if (!std::isfinite(value)) {
      throw std::runtime_error(
          "OSDI transient Jacobian contains a non-finite value");
    }
    const auto &entry = descriptor.jacobian_entries[index];
    result.jacobian.push_back({entry.nodes.first, entry.nodes.second, value,
                               entry.flags});
  }
  if (!std::all_of(result.residual.begin(), result.residual.end(), finite) ||
      !std::all_of(result.next.reactive_residual.begin(),
                   result.next.reactive_residual.end(), finite) ||
      !std::all_of(result.next.device_state.begin(),
                   result.next.device_state.end(), finite)) {
    throw std::runtime_error(
        "OSDI transient callback produced a non-finite result");
  }
  result.evaluation_flags = flags;
  return result;
}

OsdiNoiseEvaluation OsdiDeviceInstance::evaluate_noise(
    std::span<const double> node_voltages_v, double frequency_hz) {
  std::scoped_lock lock(impl_->mutex);
  const auto &descriptor = *impl_->descriptor;
  if (descriptor.load_noise == nullptr || descriptor.noise_source_count == 0 ||
      descriptor.noise_sources == nullptr ||
      node_voltages_v.size() != descriptor.node_count ||
      !std::isfinite(frequency_hz) || !(frequency_hz > 0.0) ||
      !std::all_of(node_voltages_v.begin(), node_voltages_v.end(),
                   [](double value) { return std::isfinite(value); })) {
    throw std::invalid_argument(
        "OSDI noise inputs violate the noise callback contract");
  }
  std::vector<double> solution(node_voltages_v.begin(), node_voltages_v.end());
  std::vector<double> previous_state(std::max(1U, descriptor.state_count), 0.0);
  std::vector<double> next_state(previous_state.size(), 0.0);
  OsdiSimInfo information{
      impl_->parameters,
      0.0,
      solution.data(),
      previous_state.data(),
      next_state.data(),
      calculate_resistive_residual | calculate_resistive_jacobian |
          calculate_noise | calculate_operating_point | analysis_noise};
  const auto flags = descriptor.evaluate(
      nullptr, impl_->instance.data(), impl_->model.data(), &information);
  if ((flags & fatal_evaluation_mask) != 0) {
    throw std::runtime_error("OSDI noise evaluation returned a fatal flag");
  }
  std::vector<double> densities(descriptor.noise_source_count, 0.0);
  if (impl_->abi_minor == 3) {
    std::vector<double> logarithmic_densities(descriptor.noise_source_count,
                                              0.0);
    reinterpret_cast<LoadNoise03>(descriptor.load_noise)(
        impl_->instance.data(), impl_->model.data(), frequency_hz,
        densities.data(), logarithmic_densities.data());
  } else {
    reinterpret_cast<LoadNoise04>(descriptor.load_noise)(
        impl_->instance.data(), impl_->model.data(), frequency_hz,
        densities.data());
  }
  std::vector<double> powers(descriptor.noise_source_count, 0.0);
  std::vector<double> exponents(descriptor.noise_source_count, 0.0);
  if (impl_->descriptor04 != nullptr &&
      impl_->descriptor04->load_noise_parameters != nullptr) {
    impl_->descriptor04->load_noise_parameters(
        impl_->instance.data(), impl_->model.data(), powers.data(),
        exponents.data());
  }
  OsdiNoiseEvaluation result;
  result.contributions.reserve(descriptor.noise_source_count);
  for (std::size_t index = 0; index < descriptor.noise_source_count; ++index) {
    const auto &source = descriptor.noise_sources[index];
    const auto valid_endpoint = [&descriptor](std::uint32_t node) {
      return node < descriptor.node_count ||
             node == std::numeric_limits<std::uint32_t>::max();
    };
    if (!valid_endpoint(source.nodes.first) ||
        !valid_endpoint(source.nodes.second) ||
        !std::isfinite(densities[index]) || densities[index] < 0.0) {
      throw std::runtime_error("OSDI noise callback produced invalid metadata");
    }
    auto type = OsdiNoiseType::unspecified;
    if (impl_->descriptor04 != nullptr &&
        impl_->descriptor04->noise_source_type != nullptr) {
      const auto raw = impl_->descriptor04->noise_source_type[index];
      if (raw <= static_cast<std::uint32_t>(OsdiNoiseType::table)) {
        type = static_cast<OsdiNoiseType>(raw);
      }
    }
    result.contributions.push_back(
        {source.name == nullptr ? std::string{} : std::string(source.name),
         source.nodes.first == std::numeric_limits<std::uint32_t>::max()
             ? osdi_reference_node
             : source.nodes.first,
         source.nodes.second == std::numeric_limits<std::uint32_t>::max()
             ? osdi_reference_node
             : source.nodes.second,
         densities[index], type,
         powers[index], exponents[index]});
  }
  result.evaluation_flags = flags;
  return result;
}

std::shared_ptr<OsdiDeviceInstance>
load_trusted_osdi_device(const std::filesystem::path &artifact,
                         std::string_view module_name, double temperature_k,
                         std::span<const OsdiParameterAssignment> parameters) {
  if (module_name.empty() || !std::isfinite(temperature_k) ||
      temperature_k < 1.0 || temperature_k > 2000.0) {
    throw std::invalid_argument("OSDI module name or temperature is invalid");
  }
  // Do not canonicalize here: a correctly isolated AppContainer is granted
  // the staged file itself, not enumeration rights on every host ancestor.
  // The OS loader receives the caller-supplied absolute path and enforces its
  // DACL; relative paths are resolved before native loading.
  const auto load_path = std::filesystem::absolute(artifact).lexically_normal();
  auto library = std::make_shared<SharedLibrary>(load_path);
  if (auto *raw_log_slot = library->symbol("osdi_log"); raw_log_slot != nullptr) {
    auto *log_slot = reinterpret_cast<OsdiLog *>(raw_log_slot);
    *log_slot = &osdi_log_sink;
  }
  const auto major = *required_symbol<std::uint32_t>(*library, "OSDI_VERSION_MAJOR");
  const auto minor = *required_symbol<std::uint32_t>(*library, "OSDI_VERSION_MINOR");
  const auto descriptor_count =
      *required_symbol<std::uint32_t>(*library, "OSDI_NUM_DESCRIPTORS");
  if (major != 0 || (minor != 3 && minor != 4) || descriptor_count == 0 ||
      descriptor_count > 4096) {
    throw std::invalid_argument(
        "trusted C++ loader requires bounded OSDI ABI 0.3 or 0.4");
  }
  const std::uint32_t descriptor_stride =
      minor == 3
          ? static_cast<std::uint32_t>(sizeof(OsdiDescriptor03))
          : *required_symbol<std::uint32_t>(*library, "OSDI_DESCRIPTOR_SIZE");
  if (descriptor_stride < sizeof(OsdiDescriptor03) ||
      descriptor_stride > 64U * 1024U) {
    throw std::invalid_argument("OSDI descriptor stride is outside bounds");
  }
  const auto *descriptors =
      required_symbol<std::byte>(*library, "OSDI_DESCRIPTORS");
  const OsdiDescriptor03 *selected = nullptr;
  const OsdiDescriptor04 *selected04 = nullptr;
  for (std::size_t index = 0; index < descriptor_count; ++index) {
    const auto *candidate = reinterpret_cast<const OsdiDescriptor03 *>(
        descriptors + index * descriptor_stride);
    if (candidate->name != nullptr && module_name == candidate->name) {
      selected = candidate;
      constexpr std::size_t osdi04_noise_prefix_size =
          offsetof(OsdiDescriptor04, load_noise_parameters) +
          sizeof(LoadNoiseParameters);
      if (minor >= 4 && descriptor_stride >= osdi04_noise_prefix_size) {
        selected04 = reinterpret_cast<const OsdiDescriptor04 *>(candidate);
      }
      break;
    }
  }
  if (selected == nullptr) {
    throw std::invalid_argument("requested OSDI descriptor is absent");
  }
  validate_descriptor(*selected);

  auto implementation = std::make_unique<OsdiDeviceInstance::Impl>();
  implementation->library = std::move(library);
  implementation->descriptor = selected;
  implementation->descriptor04 = selected04;
  implementation->abi_minor = minor;
  implementation->descriptor_stride = descriptor_stride;
  implementation->module_name = std::string(module_name);
  implementation->model.resize(selected->model_size);
  implementation->instance.resize(selected->instance_size);
  implementation->resistive_jacobian_values.assign(selected->jacobian_count, 0.0);
  implementation->reactive_jacobian_values.assign(selected->jacobian_count, 0.0);
  implementation->parameters.names = implementation->simulator_parameter_names.data();
  implementation->parameters.values = implementation->simulator_parameter_values.data();
  implementation->parameters.string_names =
      implementation->simulator_string_names.data();
  implementation->parameters.string_values =
      implementation->simulator_string_values.data();
  implementation->pattern.reserve(selected->jacobian_count);
  for (std::size_t index = 0; index < selected->jacobian_count; ++index) {
    implementation->pattern.emplace_back(
        selected->jacobian_entries[index].nodes.first,
        selected->jacobian_entries[index].nodes.second);
  }

  const auto metadata_count = static_cast<std::size_t>(selected->parameter_count) +
                              selected->operating_variable_count;
  const auto *metadata = static_cast<const OsdiParameterOrOperatingVariable *>(
      selected->parameter_or_operating_variable);
  std::unordered_set<std::string> assigned;
  implementation->assigned_strings.reserve(parameters.size());
  for (const auto &assignment : parameters) {
    if (assignment.name.empty() || !assigned.insert(assignment.name).second) {
      throw std::invalid_argument("OSDI parameter names must be nonempty and unique");
    }
    std::size_t selected_parameter = metadata_count;
    for (std::size_t index = 0; index < metadata_count; ++index) {
      const auto &entry = metadata[index];
      if (entry.names == nullptr || entry.names[0] == nullptr) {
        throw std::invalid_argument("OSDI parameter metadata is malformed");
      }
      for (std::size_t alias = 0; alias <= entry.alias_count; ++alias) {
        if (entry.names[alias] != nullptr &&
            ascii_case_equal(assignment.name, entry.names[alias])) {
          selected_parameter = index;
          break;
        }
      }
      if (selected_parameter != metadata_count) {
        break;
      }
    }
    if (selected_parameter == metadata_count) {
      throw std::invalid_argument("unknown OSDI parameter: " + assignment.name);
    }
    const auto &entry = metadata[selected_parameter];
    if ((entry.flags & parameter_kind_mask) == parameter_kind_operating_variable) {
      throw std::invalid_argument("OSDI operating variables are read-only");
    }
    if (entry.length != 0) {
      throw std::invalid_argument("OSDI array parameter assignment is not implemented");
    }
    const auto declared_type = entry.flags & parameter_type_mask;
    std::uint32_t access_flags = access_flag_set;
    if (assignment.instance) {
      if ((entry.flags & parameter_kind_mask) != parameter_kind_instance) {
        throw std::invalid_argument(
            "OSDI model-only parameter cannot be assigned per instance");
      }
      access_flags |= access_flag_instance;
    }
    void *destination = selected->access(
        implementation->instance.data(), implementation->model.data(),
        static_cast<std::uint32_t>(selected_parameter), access_flags);
    if (destination == nullptr) {
      throw std::invalid_argument("OSDI access rejected parameter: " + assignment.name);
    }
    if (declared_type == static_cast<std::uint32_t>(OsdiParameterType::real) &&
        std::holds_alternative<double>(assignment.value)) {
      const double value = std::get<double>(assignment.value);
      if (!std::isfinite(value)) {
        throw std::invalid_argument("OSDI real parameter must be finite");
      }
      *static_cast<double *>(destination) = value;
    } else if (declared_type == static_cast<std::uint32_t>(OsdiParameterType::integer) &&
               std::holds_alternative<std::int32_t>(assignment.value)) {
      *static_cast<std::int32_t *>(destination) =
          std::get<std::int32_t>(assignment.value);
    } else if (declared_type == static_cast<std::uint32_t>(OsdiParameterType::string) &&
               std::holds_alternative<std::string>(assignment.value)) {
      implementation->assigned_strings.push_back(
          std::make_unique<std::string>(std::get<std::string>(assignment.value)));
      *static_cast<const char **>(destination) =
          implementation->assigned_strings.back()->c_str();
    } else {
      throw std::invalid_argument("OSDI parameter value type does not match metadata");
    }
  }

  OsdiInitInfo initialization{};
  selected->setup_model(nullptr, implementation->model.data(),
                        &implementation->parameters, &initialization);
  if (initialization.error_count != 0) {
    throw std::invalid_argument("OSDI model setup reported initialization errors");
  }
  initialization = {};
  selected->setup_instance(nullptr, implementation->instance.data(),
                           implementation->model.data(), temperature_k,
                           selected->terminal_count, &implementation->parameters,
                           &initialization);
  if (initialization.error_count != 0) {
    throw std::invalid_argument("OSDI instance setup reported initialization errors");
  }
  auto *mapping = reinterpret_cast<std::uint32_t *>(
      implementation->instance.data() + selected->node_mapping_offset);
  for (std::uint32_t index = 0; index < selected->node_count; ++index) {
    mapping[index] = index;
  }
  auto **jacobian_pointers = reinterpret_cast<double **>(
      implementation->instance.data() +
      selected->resistive_jacobian_pointer_offset);
  for (std::size_t index = 0; index < selected->jacobian_count; ++index) {
    jacobian_pointers[index] =
        &implementation->resistive_jacobian_values[index];
    const auto &entry = selected->jacobian_entries[index];
    if (entry.reactive_pointer_offset !=
        std::numeric_limits<std::uint32_t>::max()) {
      auto **reactive_pointer = reinterpret_cast<double **>(
          implementation->instance.data() + entry.reactive_pointer_offset);
      *reactive_pointer = &implementation->reactive_jacobian_values[index];
    }
  }
  return std::shared_ptr<OsdiDeviceInstance>(
      new OsdiDeviceInstance(std::move(implementation)));
}

std::shared_ptr<OsdiDeviceInstance>
load_trusted_osdi_0_3_device(const std::filesystem::path &artifact,
                             std::string_view module_name,
                             double temperature_k) {
  return load_trusted_osdi_device(artifact, module_name, temperature_k);
}

} // namespace spikes
