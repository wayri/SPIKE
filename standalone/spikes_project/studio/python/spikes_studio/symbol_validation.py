"""Geometry validation shared by the designer and library loader."""
import math


def validate_symbol(symbol):
    for field in ("id", "name", "family", "standard", "conformance", "grid", "body_keepout", "label_keepouts", "terminals", "primitives"):
        if field not in symbol: raise ValueError(f"Symbol missing {field}")
    def point(value):
        if not isinstance(value,list) or len(value)!=2 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in value): raise ValueError("Expected two finite coordinates")
    grid=symbol["grid"]
    if not isinstance(grid,(float,int)) or not math.isfinite(grid) or grid<=0:raise ValueError("Grid must be positive")
    low,high=symbol["body_keepout"]["min"],symbol["body_keepout"]["max"];point(low);point(high)
    if any(a>=b for a,b in zip(low,high)):raise ValueError("Empty or inverted body bounds")
    terminals=symbol["terminals"]
    if not terminals or len(terminals)>256:raise ValueError("Need 1..256 terminals")
    if len({p["id"] for p in terminals})!=len(terminals):raise ValueError("Duplicate terminal ID")
    for terminal in terminals:
        at,end=terminal["at"],terminal["leg_endpoint"];point(at);point(end)
        if at==end:raise ValueError("Terminal needs a nonzero leg")
        if any(abs(v/grid-round(v/grid))>1e-8 for v in at):raise ValueError("Terminal is off grid")
        if terminal.get("connection_indicator") is not True:raise ValueError("Terminal marker required")
        if low[0]<at[0]<high[0] and low[1]<at[1]<high[1]:raise ValueError("Connection anchor is inside the symbol body")
    if not isinstance(symbol["primitives"],list) or not symbol["primitives"]:raise ValueError("Symbol needs geometry")
    return symbol
