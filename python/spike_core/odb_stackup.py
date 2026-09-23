"""Resolve ODB++ stackup XML material references without choosing alternatives."""
from .ipc2581_importer import _parse_bounded_xml, _UNSAFE_XML
from .odb_features import number


def parse_stackup(text, issue):
    payload = text.encode("utf-8")
    if _UNSAFE_XML.search(payload): raise ValueError("Unsafe ODB++ stackup XML declaration.")
    root = _parse_bounded_xml(payload)
    def name(e): return e.tag.rsplit("}", 1)[-1]
    def children(e, tag): return [c for c in e if name(c) == tag]
    def one(e, tag):
        rows = children(e, tag)
        if len(rows) != 1: raise ValueError(f"Expected a unique {tag} in stackup.")
        return rows[0]
    def factor(unit):
        factors = {"MM": 1, "MIL": .0254, "MICRON": .001, "INCH": 25.4}
        if unit not in factors: raise ValueError(f"Unknown stackup units: {unit}")
        return factors[unit]
    if name(root) != "StackupFile": raise ValueError("Expected ODB++ StackupFile root.")
    default_units = root.get("DefaultUnits", "MIL")
    factor(default_units)
    try:
        eda = one(root, "EdaData")
        stack = one(eda, "Stackup")
        specs = one(eda, "Specs")
    except ValueError as exc:
        issue("ODB_STACKUP_UNRESOLVED", str(exc), severity="warning")
        return []
    materials = {}
    for spec in children(specs, "Spec"):
        for material in children(spec, "Material"):
            key = (spec.get("SpecName"), material.get("MaterialName"))
            if None in key or key in materials: raise ValueError("Duplicate/unnamed stackup material definition.")
            materials[key] = material
    result = []
    seen = set()
    for group in children(stack, "Group"):
        for layer in children(group, "Layer"):
            layer_name = layer.get("LayerName", "")
            if not layer_name or layer_name in seen: raise ValueError("Duplicate/unnamed physical stackup layer.")
            seen.add(layer_name)
            try:
                ref = one(layer, "SpecRef")
                selected = one(ref, "Material")
                material = materials[(ref.get("MaterialSpecName"), selected.get("MaterialName"))]
                dielectric = children(material, "Dielectric")
                conductor = children(material, "Conductor")
                if len(dielectric) + len(conductor) != 1: raise ValueError("Material must resolve as dielectric or conductor.")
                kind = "dielectric" if dielectric else "copper"
                body = (dielectric or conductor)[0]
                properties = children(body, "Properties")
                if selected.get("PropertyName"):
                    properties = [p for p in properties if p.get("PropertyName") == selected.get("PropertyName")]
                prop = None
                if properties:
                    if len(properties) != 1: raise ValueError("Multiple material property sets require explicit selection.")
                    values = children(properties[0], "Property")
                    if len(values) != 1: raise ValueError("Frequency-dependent material tables are retained without selecting an operating frequency.")
                    prop = values[0]
                defaults = one(material, "Default_Thickness")
                thickness_value = defaults.get("Finished_Thickness", defaults.get("Thickness"))
                thickness_unit = defaults.get("Units", default_units)
                if prop is not None and (prop.get("Finished_Thickness") or prop.get("Thickness")):
                    thickness_value = prop.get("Finished_Thickness", prop.get("Thickness"))
                    thickness_unit = prop.get("Units_Thickness", default_units)
                thickness = number(thickness_value) * factor(thickness_unit)
                if thickness <= 0: raise ValueError("Stackup thickness must be positive.")
                row = {"name": layer_name, "type": kind, "thickness": thickness, "thickness_mm": thickness,
                       "material": selected.get("MaterialName"), "odb_source": {"layer": dict(layer.attrib), "selection": dict(selected.attrib),
                       "material": dict(material.attrib), "thickness": dict(defaults.attrib), "property": dict(prop.attrib) if prop is not None else {}}}
                if kind == "dielectric":
                    if prop is None: raise ValueError("Dielectric has no electrical properties.")
                    row["epsilon_r"] = number(prop.get("DielectricConstant_Dk"))
                    row["loss_tangent"] = number(prop.get("LossTangent_Df"))
                    if row["epsilon_r"] < 1 or row["loss_tangent"] < 0: raise ValueError("Invalid dielectric properties.")
                if prop is not None and prop.get("Conductivity_mho_cm"):
                    row["conductivity_s_per_m"] = number(prop.get("Conductivity_mho_cm")) * 100
                    if row["conductivity_s_per_m"] <= 0: raise ValueError("Conductivity must be positive.")
                result.append(row)
            except (ValueError, KeyError, TypeError) as exc:
                issue("ODB_STACKUP_UNRESOLVED", f"Layer {layer_name}: {exc}", layer_name, severity="warning")
    return result
