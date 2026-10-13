// SPDX-License-Identifier: Apache-2.0
// Original SPIKE board co-simulation ABI. Units: seconds, volts, amperes.
#ifndef SPIKES_BOARD_LIBRARY_H
#define SPIKES_BOARD_LIBRARY_H
#include <stddef.h>
#include <stdint.h>
#if defined(_WIN32)
#if defined(SPIKES_BOARD_BUILD)
#define SPIKES_BOARD_API __declspec(dllexport)
#else
#define SPIKES_BOARD_API __declspec(dllimport)
#endif
#else
#define SPIKES_BOARD_API __attribute__((visibility("default")))
#endif
#ifdef __cplusplus
extern "C" {
#endif
typedef struct spikes_board spikes_board;
typedef struct spikes_board_fault_descriptor {
  const char *name;
  const char *element_id;
  const char *parameter;
  double healthy_value;
  double minimum;
  double maximum;
  const char *mechanism;
} spikes_board_fault_descriptor;
enum { SPIKES_BOARD_OK=0, SPIKES_BOARD_INVALID=1, SPIKES_BOARD_SOLVER=2,
       SPIKES_BOARD_FAILURE=3 };
SPIKES_BOARD_API uint32_t spikes_board_abi_version(void);
/* Actual imported engine function address, for dependency identity checks. */
SPIKES_BOARD_API uintptr_t spikes_board_engine_identity(void);
SPIKES_BOARD_API int spikes_board_create(spikes_board **out_board);
SPIKES_BOARD_API void spikes_board_destroy(spikes_board *board);
/* Error text valid until the next operation on this instance (thread for NULL). */
SPIKES_BOARD_API const char *spikes_board_error(const spikes_board *board);
/* Drive takes effect on the next accepted step; pin name is case-sensitive. */
SPIKES_BOARD_API int spikes_board_drive(spikes_board *, const char *pin, double volts);
/* One backward-Euler step; rejected steps leave time/state/source values intact. */
SPIKES_BOARD_API int spikes_board_step(spikes_board *, double seconds);
SPIKES_BOARD_API int spikes_board_read(spikes_board *, const char *output, double *value);
SPIKES_BOARD_API int spikes_board_position(spikes_board *, double *seconds, size_t *steps);
SPIKES_BOARD_API int spikes_board_residual(spikes_board *, double *residual);
/* One saved checkpoint per instance. Save replaces it; reset clears it. */
SPIKES_BOARD_API int spikes_board_save(spikes_board *);
SPIKES_BOARD_API int spikes_board_restore(spikes_board *);
SPIKES_BOARD_API int spikes_board_reset(spikes_board *);
/* Additive ABI-1 feature. Descriptor strings have process lifetime. */
SPIKES_BOARD_API uint32_t spikes_board_fault_api_version(void);
SPIKES_BOARD_API size_t spikes_board_fault_count(void);
SPIKES_BOARD_API int spikes_board_fault_descriptor_at(
    size_t index, spikes_board_fault_descriptor *out_descriptor);
/* Changes affect the next step; last accepted outputs remain unchanged. */
SPIKES_BOARD_API int spikes_board_inject_fault(
    spikes_board *, const char *name, double value);
SPIKES_BOARD_API int spikes_board_clear_fault(spikes_board *, const char *name);
SPIKES_BOARD_API int spikes_board_clear_all_faults(spikes_board *);
#ifdef __cplusplus
}
#endif
#endif
