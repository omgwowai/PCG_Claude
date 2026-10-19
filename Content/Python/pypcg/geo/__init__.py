"""Plain values and pure geometry for the Python stages (spec 2.3). No unreal import.

`assets` (the Assign_Assets primitive's pure half) is exported as a submodule only: its `choose` is
a different function from this package's `choose` (the Filter_RandomChoice ratio pick), so the two
must never share a name. Call it as `geo.assets.choose`."""
from . import areas  # noqa: F401
from . import assets  # noqa: F401
from . import ground  # noqa: F401
from . import roads  # noqa: F401
from . import sections  # noqa: F401
from .plane import (at, bbox, ccw, clean_points, clip_path, convex_hull, drop_closing,  # noqa: F401
                    enclosing_polygon, extract_segments, frame_box, inside, longest, ngon, path_length, place,
                    quat_from_yaw, quat_rotate, rect, rotate, signed_area, split_frame, unit, xy)
from .sample import area_m2, choose, contains, keep_each, scatter  # noqa: F401
from .subdivide import SLIVER_CM2, auto_split, grid_lines, recursive_split  # noqa: F401
from .types import (MAX_RECORDED_POINTS, ParamSet, Points, Polygon, Spline, from_json, to_json,  # noqa: F401
                    values, with_tag)
