// SPDX-License-Identifier: Apache-2.0
// Actual host-compiled fault consumer; circuit faults are explicit approximations.
#include "board_library.hpp"
#include <cmath>
#include <iostream>
#include <stdexcept>

static double sample(spikes::Board &board) { board.step(1e-6); return board.read("drain_v"); }

int main() {
  try {
    spikes::Board board;
    spikes::Board independent;
    const double normal=sample(board);
    const double independent_normal=sample(independent);
    board.reset(); board.inject_fault("gate_source_shunt",0.01); const double gs=sample(board);
    board.reset(); board.inject_fault("drain_source_shunt",0.01); const double ds=sample(board);
    board.reset(); board.inject_fault("drain_source_shunt",10.0); const double degraded=sample(board);
    board.reset(); board.inject_fault("shifted_vto",6.0); const double vto=sample(board);

    board.reset(); sample(board); board.save();
    board.inject_fault("gate_source_shunt",0.01); sample(board);
    board.restore(); const double replay=sample(board);
    independent.reset(); sample(independent); const double reference_replay=sample(independent);
    board.clear_all();

    if(std::abs(normal-independent_normal)>1e-10 || gs<4.9 || ds>0.01 ||
       !(degraded>ds && degraded<normal) || vto<4.9 || std::abs(replay-reference_replay)>1e-10)
      throw std::runtime_error("Compiled fault scenarios violated fixture tolerances");
    std::cout << "normal_v=" << normal << " gs_short_v=" << gs << " ds_short_v=" << ds
              << " degraded_10ohm_v=" << degraded << " shifted_vto_v=" << vto
              << " independent_normal_v=" << independent_normal << " replay_v=" << replay << '\n';
    return 0;
  } catch(const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
}
