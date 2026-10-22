"""PyWorld's rule tables (视频："建筑规则表"、散布规则): settlement kinds, streets, building types and biomes."""

KIND_RADII = (("Town", 20000.0), ("Village", 12000.0), ("Hamlet", 0.0))   # a location's kind by its radius (cm)


def kind_of(radius_cm):
    for kind, r in KIND_RADII:
        if radius_cm >= r:
            return kind
    return "Hamlet"
