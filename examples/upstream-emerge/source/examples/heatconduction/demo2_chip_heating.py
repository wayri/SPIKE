import emerge as em


"""In this example we will show how we can run a static heat flow simulation for some arbitrary chip.

The geometry is very simplified and elements are introduced only in order to demonstrate how one 
would implement them.

It features a silicon chip connected to a PCB through a thermal interface material.
A 5mm x 5mm square surface is unsed to inject 5W of power.

The bottom of the PCB is connected to ambient temperature via a Convection boundary condition
which is a 1000 W/m²K to ambient.

A simple single copper trace is added to demonstrate how the ThinConductor boundary condition can be used to transport heat without modeling it as a 3D material.
"""

mm = 0.001

Wchip = 8 * mm
Dchip = 8 * mm
thchip = 0.5 * mm

W_TIM = 10 * mm
D_TIM = 10 * mm
th_TIM = 0.05 * mm

wline = 1.5 * mm
Lline = 5 * mm

thpcb = 1.6 * mm
Wpcb = 20 * mm
Dpcb = 20 * mm

W_heatsource = 5 * mm
D_heatsource = 5 * mm
Power = 5  # Watts

T_ambient = 293.15

mat_tim = em.Material(cond_thermal=2.0, color="#ababab")
mat_silicon = em.Material(cond_thermal=150, color="#46496e", _metal=True)


# --- Simulation setup

sim = em.Simulation("Demo2")
sim.set_physics(microwave=False, heatconduction=True)

pcb = em.geo.Box(
    Wpcb, Dpcb, thpcb, position=(-Wpcb / 2, -Dpcb / 2, -thpcb)
).set_material(em.lib.DIEL_FR4)
tim = em.geo.Box(
    W_TIM, D_TIM, th_TIM, position=(-W_TIM / 2, -D_TIM / 2, 0)
).set_material(mat_tim)
chip = em.geo.Box(
    Wchip, Dchip, thchip, position=(-Wchip / 2, -Dchip / 2, th_TIM)
).set_material(mat_silicon)

via = (
    em.geo.Cylinder(
        0.2 * mm, thpcb, em.cs(origin=(-Lline - 2 * mm, 0, -thpcb)), Nsections=8
    )
    .set_material(em.lib.AIR)
    .foreground()
)

trace1 = em.geo.XYPlate(Lline, wline, (-Lline - Wchip / 2, -wline / 2, 0)).set_material(
    em.lib.MET_COPPER
)

heatsource = em.geo.XYPlate(
    W_heatsource, W_heatsource, (-W_heatsource / 2, -W_heatsource / 2, th_TIM + thchip)
)


# Finally we complete our geometry setup
sim.commit_geometry()

# We can view our geometry like this
sim.view()

# Turn the following on (True) to refine the mesh
if False:
    sim.mesher.set_domain_size(chip, 1 * mm)
    sim.mesher.set_domain_size(tim, 1 * mm)
    sim.mesher.set_face_size(via.boundary(), 0.25 * mm)
    sim.mesher.set_domain_size(pcb, 1 * mm)

sim.generate_mesh()
sim.view(plot_mesh=True)
# --- Boundary Conditions

# If we assume that the PCB is pressed to some heat-sink we may
# assume a finite thermal contact to an ambient temperature
# This is done with the convection boundary condition
# If sufficiently well attached, 1000 W/m²K is a good assumption.

sim.hc.bc.Convection(pcb.bottom, 1000, T_ambient)

# For the chips heat dissipation we assume a power density per square meters.
sim.hc.bc.HeatFluxBoundary(heatsource, Power / (W_heatsource**2))

# We can model the thermal conductivity of our copper trace as well
sim.hc.bc.ThinConductor(trace1, em.lib.MET_COPPER, 30e-6)
sim.hc.bc.ThinConductor(via.shell, em.lib.MET_COPPER, 30e-6)

sim.view(bc=True)
# ---- Simulation
data = sim.hc.run_steady_state()

field = data.field[0]

d = sim.display
d.populate(opacity=0.1)
d.add_field(field.cutplane(y=0, ds=0.1 * mm).scalar("TdegC"), opacity=1.0)
d.add_field(field.cutplane(y=0, ds=0.3 * mm).vector("q"), scale="log", color="green")
d.show()
