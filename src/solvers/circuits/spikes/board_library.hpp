// SPDX-License-Identifier: Apache-2.0
#ifndef SPIKES_BOARD_LIBRARY_HPP
#define SPIKES_BOARD_LIBRARY_HPP
#include "board_library.h"
#include <stdexcept>
#include <utility>
namespace spikes {
// Each object owns independent electrical state; serialize access to one object.
class Board {
  spikes_board *handle_ = nullptr;
  void check(int code) const {
    if (code != SPIKES_BOARD_OK) throw std::runtime_error(spikes_board_error(handle_));
  }
public:
  Board() { check(spikes_board_create(&handle_)); }
  ~Board() { spikes_board_destroy(handle_); }
  Board(const Board &) = delete;
  Board &operator=(const Board &) = delete;
  Board(Board &&other) noexcept : handle_(std::exchange(other.handle_, nullptr)) {}
  Board &operator=(Board &&other) noexcept {
    if (this != &other) { spikes_board_destroy(handle_); handle_=std::exchange(other.handle_,nullptr); }
    return *this;
  }
  void drive(const char *pin, double volts) { check(spikes_board_drive(handle_,pin,volts)); }
  void step(double seconds) { check(spikes_board_step(handle_,seconds)); }
  double read(const char *output) { double v=0; check(spikes_board_read(handle_,output,&v)); return v; }
  double time() { double t=0; size_t n=0; check(spikes_board_position(handle_,&t,&n)); return t; }
  double residual() { double r=0; check(spikes_board_residual(handle_,&r)); return r; }
  void save() { check(spikes_board_save(handle_)); }
  void restore() { check(spikes_board_restore(handle_)); }
  void reset() { check(spikes_board_reset(handle_)); }
  void inject_fault(const char *name, double value) {
    check(spikes_board_inject_fault(handle_,name,value));
  }
  void clear_fault(const char *name) { check(spikes_board_clear_fault(handle_,name)); }
  void clear_all() { check(spikes_board_clear_all_faults(handle_)); }
  void clear_all_faults() { check(spikes_board_clear_all_faults(handle_)); }
};
}
#endif
