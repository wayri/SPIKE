import emerge as em
from emerge.plot import plot
import numpy as np

"""
Transient analysis

In this simple exmaple we will look at the heating of a coke can on a warm day.

The goal of this example is just to demonstrate how the transient solve is to be setup.
Since there is no non-linear transient solver and no fluid simulation we will assume a
rather windy warm day using a convection boundary condition with a heat flux of 22 W/m²K
to 30 degree weather.


"""

############################################################
#                        PARAMETERS                       #
############################################################

R = 0.0662 / 2
H = 0.122
th = 0.0005

degC = 273.15

# Outside profile of the Coke can
xpts = [0, 0.9 * R, 0.91 * R, 0.92 * R, 0.93 * R, R, R, 0.93 * R, 0.93 * R, 0]
ypts = [0.02 * H, 0.02 * H, 0, 0, 0.05 * H, 0.1 * H, 0.9 * H, 0.99 * H, H, H]

# Inside profile of the Coke can
xpts2 = [0, 0.93 * R, R - th, R - th, 0.93 * R - th, 0]
ypts2 = [0.05 * H + th, 0.05 * H + th, 0.1 * H, 0.9 * H, 0.99 * H - th, H - th]

# --- Materials
cola = em.Material(
    cond_thermal=0.598, specific_heat=4.184, density=998, color="#371403", opacity=0.3
)

sim = em.Simulation("Can")
sim.set_physics(False, True)


############################################################
#                        GEOMETRIES                       #
############################################################

can_outside = em.geo.XYPolygon(xpts, ypts).revolve(
    em.XZPLANE.cs(), (0, 0, 0), (0, 0, 1)
)
can_inside = (
    em.geo.XYPolygon(xpts2, ypts2)
    .revolve(em.XZPLANE.cs(), (0, 0, 0), (0, 0, 1))
    .set_material(cola)
)

can = em.geo.subtract(can_outside, can_inside, remove_tool=False).set_material(
    em.lib.MET_ALUMINUM
)

# --- Finalize the geometry.
sim.commit_geometry()

# Improve the mesh quality to make sure the thin layer is properly resolved
sim.mesher.set_curved_boundary_meshing(20)
sim.mesher.set_domain_size(can, 0.01)
sim.generate_mesh()

# We use face_labels=True to see the names of the outside faces which we will assign
# to our thermal convection boundary condition.
sim.view(face_labels=True)

sel_outside = can.faces("Face2", "Face3", "Face11", "+z")

# we can view our made selection
sim.view(
    selections=[
        sel_outside,
    ],
    plot_mesh=True,
)

# ---- Define our boundary conditions

# As the can came from a fridge, we will assume 5 degrees celsius

sim.hc.set_initial_temperature(5 + degC)

# Our heat flux is 8 W/m²K to 30 degree temperature
sim.hc.bc.Convection(sel_outside, 22.0, 30 + degC)

# --- Heating

# One hour total time
time = 15 * 60

# Simulate in 41 steps. Backward Euler for better stability
data = sim.hc.run_transient(time, time / 41, stepping_algorithm="BackwardEuler")

# --- Post Process

times = []
temps_center = []
temps_edge = []

x = 0
y = 0
z = H / 2

# We will iterate through our solutions and monitor the temperature
# in side and on the outside of our coke can.
for solution in data.field.iter():
    times.append(solution.time)
    T = solution.interpolate(x, y, z)
    temps_center.append(T.T[0])
    T = solution.interpolate(0.99 * R, y, z)
    temps_edge.append(T.T[0])

# Convert to arrays
times = np.array(times)
temps_center = np.array(temps_center) - degC
temps_edge = np.array(temps_edge) - degC

# Plot!
plot(
    times / 60,
    [temps_center, temps_edge],
    labels=["Center", "Edge"],
    xlabel="Time [minutes]",
    ylabel="Temperature [degC]",
)

sim.reset(data=True)
