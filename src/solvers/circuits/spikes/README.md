<!-- SPDX-License-Identifier: Apache-2.0 -->
# Circuits / Spikes

[Methods, setup routes, validity and evidence](../../../../docs/solvers/circuits/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [appcontainer_launcher.cpp](appcontainer_launcher.cpp)
- [behavioral_expression.hpp](behavioral_expression.hpp)
- [board_library.h](board_library.h)
- [board_library.hpp](board_library.hpp)
- [board_library_runtime.cpp](board_library_runtime.cpp)
- [c_api.cpp](c_api.cpp)
- [c_api.h](c_api.h)
- [console_dashboard.cpp](console_dashboard.cpp)
- [console_dashboard.hpp](console_dashboard.hpp)
- [console_main.cpp](console_main.cpp)
- [dc_solver.cpp](dc_solver.cpp)
- [dc_solver.hpp](dc_solver.hpp)
- [digital_kernel.hpp](digital_kernel.hpp)
- [io_pad.cpp](io_pad.cpp)
- [io_pad.hpp](io_pad.hpp)
- [io_pad_events.cpp](io_pad_events.cpp)
- [io_pad_events.hpp](io_pad_events.hpp)
- [osdi_device.cpp](osdi_device.cpp)
- [osdi_device.hpp](osdi_device.hpp)
- [osdi_worker_main.cpp](osdi_worker_main.cpp)
- [peripheral_c_api.cpp](peripheral_c_api.cpp)
- [peripheral_c_api.h](peripheral_c_api.h)
- [peripheral_registers.cpp](peripheral_registers.cpp)
- [peripheral_registers.hpp](peripheral_registers.hpp)
- [peripheral_timing.cpp](peripheral_timing.cpp)
- [peripheral_timing.hpp](peripheral_timing.hpp)
- [smps_stability.cpp](smps_stability.cpp)
- [smps_stability.hpp](smps_stability.hpp)
- [tcad_console.cpp](tcad_console.cpp)
- [tcad_equilibrium.cpp](tcad_equilibrium.cpp)
- [tcad_equilibrium.hpp](tcad_equilibrium.hpp)
- [transient_session.cpp](transient_session.cpp)
- [transient_session.hpp](transient_session.hpp)
- [transient_solver.cpp](transient_solver.cpp)
- [transient_solver.hpp](transient_solver.hpp)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
