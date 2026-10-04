import emerge as em
from emerge.plot import plot
import numpy as np


"""In this first example we will generate a verys imple basic heat-conduction simulation.
We will build a teflon rod with a diameter of 10cm and a length of 1meter. We will expose
one side to a fixed temperature of 20 degC (293.15 Kelvin) and one to a constant heat influx of 10 W/m²

Over the length of this rod, we can predict the steady state thermal gradient with the function:

T(z) = Tamb + q*z/⍴
"""

# --- Constants
Tamb = 293.15  # Kelvin
Length = 1.0  # meters
Diam = 0.1  # meters
heatflux = 10  # W/m²
material = em.lib.DIEL_TEFLON
# --- Simulation

sim = em.Simulation("Demo1")

# To just simulate heat conduction we turn only this physics on
sim.set_physics(microwave=False, heatconduction=True)

# Next we create our Copper rod and specify the material as teflon
rod = em.geo.Cylinder(Diam / 2, Length, Nsections=12).set_material(material)

# That is it! To finish modelling we call:
sim.commit_geometry()

# For heat conduction physics, we don't have to specify a simulation setting to get a first basic mesh.
sim.generate_mesh()

# We can view out geometry and mesh
sim.view()
sim.view(plot_mesh=True)

# Now we define our boundary conditions

# For the Fixed temperature  we set:
sim.hc.bc.FixedTemperatureBoundary(rod.face("-z"), Tamb)

# For the heat flux we will use
sim.hc.bc.HeatFluxBoundary(rod.face("+z"), heatflux)

# Finally we can run our simulation
data = sim.hc.run_steady_state()

# Our solved temperature field for steady state is always extracted as following:
field = data.field[0]

# Lets compare the predicted thermal gradient by the theoretical. First we create the coordinates of
# A line through the center of our cyclinder
zs = np.linspace(0, Length, 1001)
xs = 0 * zs
ys = 0 * zs

# Next we compute our temperature from our simulation. We subtract the ambient temperature to remove the offset.
Delta_T_sim = field.interpolate(xs, ys, zs).T - Tamb

# Next we compute the theoretical value
Delta_T_theory = heatflux * zs / material.cond_thermal.value

# and we compare the results
plot(
    zs,
    [Delta_T_sim, Delta_T_theory],
    labels=["EMerge", "Theory"],
    linestyles=["-", "--"],
    xlabel="Z-position [m]",
    ylabel="Δ Temperature[K]",
)

# --- 3D Plot
# We can make a 3D temperature plot as following

sim.display.populate(opacity=0.1)
sim.display.add_field(field.grid(N=20000).scalar("T"))
sim.display.show()
