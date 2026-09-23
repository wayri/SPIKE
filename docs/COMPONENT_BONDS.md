# Component Bond Contract

Component bonds describe the physical connection between a component terminal,
its imported PCB pad, and the copper layers touched by that pad. The project
stores these records independently of any solver so electrical, thermal, and
full-wave adapters consume the same reviewed contact definition.

## Workflow

1. Open **Home > Bonds**, **Thermal > Bonds**, or **EMI > Bonds**.
2. Set the bounded nearest-pad search distance and choose **Auto-connect**.
3. Review the component, pad, net, and connected copper columns. Imported
   footprint ownership is authoritative; distance search is only used when the
   importer did not provide ownership.
4. Edit solder resistance, current limit, thermal conductivity, contact area,
   or material where the assembly differs from the project default.
5. Choose **Validate**. Invalid or stale pad references block solver handoff.

Hovering a row previews both the pad and component in the 2D/3D viewport.
Pads without an electrical net remain available as thermal-only contacts and
are reported as warnings rather than silently treated as conductors.

## Solver Contract

`DesignIR.component_bonds` contains `spike/component-bonds/v1` records with:

- stable component and pad identifiers;
- net name, coordinate, and all connected copper layers;
- inference source and search distance;
- solder/material name;
- electrical resistance and current limit;
- thermal conductivity and contact area;
- enabled and review status.

The same records are saved in the SPIKE project package. The openEMS adapter
adds them to its object map and rejects selected bonds that have not passed
review. Thermal scenario preflight requires positive conductivity and contact
area before preparing a case.

## Validity Boundary

Auto-connect establishes contact topology; it does not calculate package lead,
bond-wire, solder-joint, or interface impedance from first principles. Those
values must come from an assigned model, measurement, supplier data, or a
validated extraction workflow. Defaults are explicit project assumptions and
remain editable and reportable.
