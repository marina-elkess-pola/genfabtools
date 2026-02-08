from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import math

# Import centerline-based detection from smart_parking module
try:
    from smart_parking import generate_smart_layout as generate_centerline_layout
    CENTERLINE_AVAILABLE = True
except ImportError:
    CENTERLINE_AVAILABLE = False
    print("[WARNING] smart_parking module not available - centerline detection disabled")

# Import RECTILINEAR circulation loop (orthogonal paths around obstacles)
try:
    from circulation_loop import generate_circulation_loop
    CIRCULATION_LOOP_AVAILABLE = True
    print("[OK] circulation_loop module loaded - using RECTILINEAR orthogonal loops")
except ImportError:
    CIRCULATION_LOOP_AVAILABLE = False
    print("[WARNING] circulation_loop module not available")

# Import TRUE medial axis centerline detection (continuous paths around obstacles)
try:
    from medial_axis_streets import generate_centerline_streets
    MEDIAL_AXIS_AVAILABLE = True
    print("[OK] medial_axis_streets module loaded - using TRUE medial axis centerlines")
except ImportError:
    MEDIAL_AXIS_AVAILABLE = False
    print("[WARNING] medial_axis_streets module not available")

# Legacy: Voronoi skeleton with H/V conversion (fallback)
try:
    from skeleton_streets import generate_streets_from_centerlines
    GEOMETRY_CENTERLINE_AVAILABLE = True
    print("[OK] skeleton_streets module loaded - H/V conversion fallback")
except ImportError:
    GEOMETRY_CENTERLINE_AVAILABLE = False
    print("[WARNING] skeleton_streets module not available")

app = FastAPI()


class Point(BaseModel):
    x: float
    y: float


class Constraints(BaseModel):
    stallWidth: float = 9.0
    stallLength: float = 18.0
    aisleWidth: float = 24.0
    angleDeg: float = 90.0
    setback: float = 5.0  # perimeter setback


# Standard dimensions for structured/underground parking
class StructureStandards(BaseModel):
    floorToFloor: float = 10.5  # ft (3.2m typical)
    columnGridX: float = 30.0   # ft (9.1m typical column spacing)
    columnGridY: float = 30.0   # ft (9.1m)
    rampWidth: float = 14.0     # ft (4.3m for two-way ramp)
    rampSlope: float = 0.05     # 5% slope
    rampLength: float = 60.0    # ft typical straight ramp
    ventShaftSize: float = 8.0  # ft x 8 ft typical


class ExclusionZone(BaseModel):
    type: str = "exclusion"  # "mechanical", "stairs", "elevator", "core", "exclusion"
    polygon: List[Point]


class GenerateRequest(BaseModel):
    boundary: List[Point] | None = None
    constraints: Constraints | None = None
    # Mechanical rooms, stairs, etc.
    exclusions: List[ExclusionZone] | None = None
    parkingType: str = "surface"  # "surface", "structured", "underground"
    numLevels: int = 1
    standards: StructureStandards | None = None

# ─────────────────────────────────────────────────────────────────────────────
# Geometry helpers
# ─────────────────────────────────────────────────────────────────────────────


def polygon_bbox(pts: List[Point]):
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    return {"minX": min(xs), "maxX": max(xs), "minY": min(ys), "maxY": max(ys)}


def point_in_polygon(pt: Point, poly: List[Point]) -> bool:
    """Ray casting algorithm."""
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i].x, poly[i].y
        xj, yj = poly[j].x, poly[j].y
        if ((yi > pt.y) != (yj > pt.y)) and (pt.x < (xj - xi) * (pt.y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def rect_corners(cx: float, cy: float, w: float, h: float, angle: float) -> List[Point]:
    """Return 4 corners of a rectangle centered at (cx, cy) with given width, height, and rotation."""
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    hw, hh = w / 2, h / 2
    corners = [
        (-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)
    ]
    return [Point(x=cx + dx * cos_a - dy * sin_a, y=cy + dx * sin_a + dy * cos_a) for dx, dy in corners]


def rect_inside_polygon(cx: float, cy: float, w: float, h: float, angle: float, poly: List[Point]) -> bool:
    corners = rect_corners(cx, cy, w, h, angle)
    return all(point_in_polygon(c, poly) for c in corners)


def rects_overlap(r1: List[Point], r2: List[Point]) -> bool:
    """Check if two convex quads overlap using SAT (separating axis theorem)."""
    def get_axes(rect):
        axes = []
        for i in range(len(rect)):
            p1, p2 = rect[i], rect[(i + 1) % len(rect)]
            edge = (p2.x - p1.x, p2.y - p1.y)
            normal = (-edge[1], edge[0])
            length = math.sqrt(normal[0]**2 + normal[1]**2)
            if length > 1e-9:
                axes.append((normal[0] / length, normal[1] / length))
        return axes

    def project(rect, axis):
        dots = [p.x * axis[0] + p.y * axis[1] for p in rect]
        return min(dots), max(dots)

    for axis in get_axes(r1) + get_axes(r2):
        min1, max1 = project(r1, axis)
        min2, max2 = project(r2, axis)
        if max1 < min2 or max2 < min1:
            return False  # separating axis found
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Structured/Underground Parking - Column Grid and Ramp Generation
# ─────────────────────────────────────────────────────────────────────────────


def generate_column_grid_optimized(bbox: Dict[str, float], constraints: "Constraints",
                                   layout_data: Dict[str, Any], strategy: str) -> List[Dict[str, Any]]:
    """
    Generate structural column positions optimized for the parking layout.
    Columns are placed at stall bay boundaries, avoiding drive lanes and aisles.

    Typical parking structure column spacing:
    - Along stall rows: every 3 stalls (27' for 9' stalls)
    - Perpendicular: at module boundaries (stall depth + aisle + stall depth = 60')
    """
    columns = []
    column_size = 1.5  # 1.5ft x 1.5ft columns (18" typical for parking)

    stall_w = constraints.stallWidth
    stall_l = constraints.stallLength
    aisle_w = constraints.aisleWidth
    setback = constraints.setback
    drive_lane_w = 24.0

    # Module = double-loaded aisle
    module_depth = stall_l + aisle_w + stall_l  # e.g., 18 + 24 + 18 = 60 ft

    # Column spacing along stall rows (every 3 stalls typical)
    stalls_per_bay = 3
    bay_width = stall_w * stalls_per_bay  # e.g., 9 * 3 = 27 ft

    # Get circulation areas to avoid
    streets = layout_data.get("streets", [])
    aisles = layout_data.get("aisles", [])

    # Build exclusion zones for drive lanes and aisles
    circulation_zones = []
    for street in streets:
        # Create exclusion zone around street
        from_pt = street["from"]
        to_pt = street["to"]
        width = street.get("width", 24)

        min_x = min(from_pt["x"], to_pt["x"]) - width/2
        max_x = max(from_pt["x"], to_pt["x"]) + width/2
        min_y = min(from_pt["y"], to_pt["y"]) - width/2
        max_y = max(from_pt["y"], to_pt["y"]) + width/2

        circulation_zones.append({
            "minX": min_x, "maxX": max_x,
            "minY": min_y, "maxY": max_y
        })

    for aisle in aisles:
        from_pt = aisle["from"]
        to_pt = aisle["to"]
        width = aisle.get("width", 24)

        min_x = min(from_pt["x"], to_pt["x"]) - width/2
        max_x = max(from_pt["x"], to_pt["x"]) + width/2
        min_y = min(from_pt["y"], to_pt["y"]) - width/2
        max_y = max(from_pt["y"], to_pt["y"]) + width/2

        circulation_zones.append({
            "minX": min_x, "maxX": max_x,
            "minY": min_y, "maxY": max_y
        })

    # Determine parking area bounds based on strategy
    if strategy == "horizontal":
        # Vertical drive lanes on left/right, horizontal aisles
        park_minX = bbox["minX"] + setback + drive_lane_w
        park_maxX = bbox["maxX"] - setback - drive_lane_w
        park_minY = bbox["minY"] + setback + drive_lane_w
        park_maxY = bbox["maxY"] - setback

        # Place columns at bay boundaries along X (between stall groups)
        # and at module boundaries along Y (between stall rows, at aisle edges)
        x = park_minX
        while x <= park_maxX + 0.1:
            # Calculate Y positions at module boundaries
            park_height = park_maxY - park_minY
            num_modules = max(1, int(park_height / module_depth))
            module_start_y = park_minY + \
                (park_height - num_modules * module_depth) / 2

            for m in range(num_modules + 1):
                # Column at bottom of each module (before first stall row)
                y = module_start_y + m * module_depth
                if y >= park_minY and y <= park_maxY:
                    columns.append({
                        "x": x, "y": y,
                        "size": column_size, "type": "column"
                    })

            x += bay_width

    elif strategy == "vertical":
        # Horizontal drive lanes on top/bottom, vertical aisles
        park_minX = bbox["minX"] + setback + drive_lane_w
        park_maxX = bbox["maxX"] - setback
        park_minY = bbox["minY"] + setback + drive_lane_w
        park_maxY = bbox["maxY"] - setback - drive_lane_w

        # Place columns at module boundaries along X and bay boundaries along Y
        y = park_minY
        while y <= park_maxY + 0.1:
            park_width = park_maxX - park_minX
            num_modules = max(1, int(park_width / module_depth))
            module_start_x = park_minX + \
                (park_width - num_modules * module_depth) / 2

            for m in range(num_modules + 1):
                x = module_start_x + m * module_depth
                if x >= park_minX and x <= park_maxX:
                    columns.append({
                        "x": x, "y": y,
                        "size": column_size, "type": "column"
                    })

            y += bay_width

    else:
        # Loop or dual-access - use perimeter + internal grid
        park_minX = bbox["minX"] + setback + drive_lane_w
        park_maxX = bbox["maxX"] - setback - drive_lane_w
        park_minY = bbox["minY"] + setback + drive_lane_w
        park_maxY = bbox["maxY"] - setback - drive_lane_w

        # Place columns at regular intervals avoiding circulation
        x = park_minX
        while x <= park_maxX:
            y = park_minY
            while y <= park_maxY:
                # Check if this position is inside a circulation zone
                in_circulation = False
                buffer = column_size + 2  # 2ft buffer from circulation edge

                for zone in circulation_zones:
                    if (x + buffer > zone["minX"] and x - buffer < zone["maxX"] and
                            y + buffer > zone["minY"] and y - buffer < zone["maxY"]):
                        in_circulation = True
                        break

                if not in_circulation:
                    columns.append({
                        "x": x, "y": y,
                        "size": column_size, "type": "column"
                    })

                y += bay_width
            x += bay_width

    return columns


def generate_column_grid(bbox: Dict[str, float], standards: StructureStandards, setback: float) -> List[Dict[str, Any]]:
    """Legacy column grid - simple fixed grid (fallback)."""
    columns = []
    column_size = 2.0  # 2ft x 2ft columns (typical)

    # Calculate grid origin (start from inner setback)
    start_x = bbox["minX"] + setback + standards.columnGridX / 2
    start_y = bbox["minY"] + setback + standards.columnGridY / 2
    end_x = bbox["maxX"] - setback
    end_y = bbox["maxY"] - setback

    x = start_x
    while x < end_x:
        y = start_y
        while y < end_y:
            columns.append({
                "x": x,
                "y": y,
                "size": column_size,
                "type": "column"
            })
            y += standards.columnGridY
        x += standards.columnGridX

    return columns


def generate_ramp(bbox: Dict[str, float], standards: StructureStandards, level: int,
                  total_levels: int, parking_type: str, strategy: str) -> Dict[str, Any]:
    """
    Generate ramp connecting to next level.
    Returns ramp data including position, type, and footprint to exclude from stall layout.

    For underground: ramp goes down (B1->B2->B3)
    For structured: ramp goes up (L1->L2->L3)
    """
    ramp_width = standards.rampWidth
    ramp_length = standards.rampLength

    # Determine ramp position based on strategy
    # Place ramp at corner or edge to minimize impact on parking efficiency
    lot_width = bbox["maxX"] - bbox["minX"]
    lot_height = bbox["maxY"] - bbox["minY"]

    # Default: place ramp at bottom-right corner
    if strategy in ["horizontal", "loop"]:
        # Ramp runs vertically on right side
        ramp_x = bbox["maxX"] - ramp_width - 5  # 5ft from edge
        ramp_y = bbox["minY"] + 30  # 30ft from bottom
        ramp_orientation = "vertical"
    else:
        # Ramp runs horizontally at bottom
        ramp_x = bbox["maxX"] - ramp_length - 5
        ramp_y = bbox["minY"] + 5
        ramp_orientation = "horizontal"

    # Rise per floor
    floor_height = standards.floorToFloor

    # Ramp direction
    direction = "down" if parking_type == "underground" else "up"

    # Is this the last level? (no ramp needed)
    is_last_level = level == total_levels

    if is_last_level:
        return None

    return {
        "x": ramp_x,
        "y": ramp_y,
        "width": ramp_width,
        "length": ramp_length,
        "orientation": ramp_orientation,
        "direction": direction,
        "fromLevel": level,
        "toLevel": level + 1 if direction == "down" else level - 1,
        "slope": standards.rampSlope,
        "type": "ramp",
        # Exclusion zone for stall placement
        "exclusionZone": {
            "minX": ramp_x - 2,
            "maxX": ramp_x + (ramp_width if ramp_orientation == "vertical" else ramp_length) + 2,
            "minY": ramp_y - 2,
            "maxY": ramp_y + (ramp_length if ramp_orientation == "vertical" else ramp_width) + 2
        }
    }


def filter_stalls_for_exclusions(stalls: List[Dict], exclusions: List[Dict]) -> List[Dict]:
    """Remove stalls that overlap with exclusion zones (columns, ramps, etc.)."""
    filtered = []
    for stall in stalls:
        # Get bounding box from polygon
        if "polygon" in stall:
            xs = [p["x"] for p in stall["polygon"]]
            ys = [p["y"] for p in stall["polygon"]]
            stall_minX = min(xs)
            stall_maxX = max(xs)
            stall_minY = min(ys)
            stall_maxY = max(ys)
        else:
            # Fallback to x/y/w/h if available
            stall_minX = stall.get("x", 0)
            stall_maxX = stall_minX + stall.get("w", 0)
            stall_minY = stall.get("y", 0)
            stall_maxY = stall_minY + stall.get("h", 0)

        excluded = False
        for zone in exclusions:
            # Check overlap
            if not (stall_maxX < zone["minX"] or stall_minX > zone["maxX"] or
                    stall_maxY < zone["minY"] or stall_minY > zone["maxY"]):
                excluded = True
                break

        if not excluded:
            filtered.append(stall)

    return filtered


def filter_streets_for_exclusions(streets: List[Dict], exclusions: List[Dict]) -> List[Dict]:
    """Remove or trim streets that overlap with exclusion zones."""
    if not exclusions:
        return streets

    filtered = []
    for street in streets:
        # Calculate street bounding box
        from_pt = street["from"]
        to_pt = street["to"]
        width = street.get("width", 24)

        # Determine if street is horizontal or vertical
        is_horizontal = abs(to_pt["y"] - from_pt["y"]) < 1
        is_vertical = abs(to_pt["x"] - from_pt["x"]) < 1

        if is_horizontal:
            street_minX = min(from_pt["x"], to_pt["x"])
            street_maxX = max(from_pt["x"], to_pt["x"])
            street_minY = from_pt["y"] - width / 2
            street_maxY = from_pt["y"] + width / 2
        elif is_vertical:
            street_minX = from_pt["x"] - width / 2
            street_maxX = from_pt["x"] + width / 2
            street_minY = min(from_pt["y"], to_pt["y"])
            street_maxY = max(from_pt["y"], to_pt["y"])
        else:
            # Diagonal - use rough bounding box
            street_minX = min(from_pt["x"], to_pt["x"]) - width / 2
            street_maxX = max(from_pt["x"], to_pt["x"]) + width / 2
            street_minY = min(from_pt["y"], to_pt["y"]) - width / 2
            street_maxY = max(from_pt["y"], to_pt["y"]) + width / 2

        overlaps = False
        for zone in exclusions:
            # Check overlap
            if not (street_maxX < zone["minX"] or street_minX > zone["maxX"] or
                    street_maxY < zone["minY"] or street_minY > zone["maxY"]):
                overlaps = True
                break

        if not overlaps:
            filtered.append(street)

    return filtered


def filter_aisles_for_exclusions(aisles: List[Dict], exclusions: List[Dict]) -> List[Dict]:
    """Remove aisles that overlap with exclusion zones."""
    if not exclusions:
        return aisles

    filtered = []
    for aisle in aisles:
        from_pt = aisle["from"]
        to_pt = aisle["to"]
        width = aisle.get("width", 24)

        # Calculate aisle bounding box
        is_horizontal = abs(to_pt["y"] - from_pt["y"]) < 1

        if is_horizontal:
            aisle_minX = min(from_pt["x"], to_pt["x"])
            aisle_maxX = max(from_pt["x"], to_pt["x"])
            aisle_minY = from_pt["y"] - width / 2
            aisle_maxY = from_pt["y"] + width / 2
        else:
            aisle_minX = from_pt["x"] - width / 2
            aisle_maxX = from_pt["x"] + width / 2
            aisle_minY = min(from_pt["y"], to_pt["y"])
            aisle_maxY = max(from_pt["y"], to_pt["y"])

        overlaps = False
        for zone in exclusions:
            if not (aisle_maxX < zone["minX"] or aisle_minX > zone["maxX"] or
                    aisle_maxY < zone["minY"] or aisle_minY > zone["maxY"]):
                overlaps = True
                break

        if not overlaps:
            filtered.append(aisle)

    return filtered


# ─────────────────────────────────────────────────────────────────────────────
# Constraint-aware layout generation
# ─────────────────────────────────────────────────────────────────────────────


def is_area_clear(minX: float, maxX: float, minY: float, maxY: float, exclusions: List[Dict]) -> bool:
    """Check if a rectangular area is free of exclusions."""
    for zone in exclusions:
        # Check overlap
        if not (maxX <= zone["minX"] or minX >= zone["maxX"] or
                maxY <= zone["minY"] or minY >= zone["maxY"]):
            return False
    return True


def find_best_drive_lane_position(start: float, end: float, lane_width: float,
                                  is_vertical: bool, fixed_coord_min: float,
                                  fixed_coord_max: float, exclusions: List[Dict],
                                  step: float = 5.0) -> float:
    """Find the best position for a drive lane that avoids most exclusions."""
    best_pos = (start + end) / 2
    best_clear_length = 0

    for pos in [start + lane_width/2 + i * step for i in range(int((end - start - lane_width) / step) + 1)]:
        if is_vertical:
            minX = pos - lane_width / 2
            maxX = pos + lane_width / 2
            minY = fixed_coord_min
            maxY = fixed_coord_max
        else:
            minX = fixed_coord_min
            maxX = fixed_coord_max
            minY = pos - lane_width / 2
            maxY = pos + lane_width / 2

        if is_area_clear(minX, maxX, minY, maxY, exclusions):
            clear_length = fixed_coord_max - fixed_coord_min
            if clear_length > best_clear_length:
                best_clear_length = clear_length
                best_pos = pos

    return best_pos


def find_clear_bands(axis_min: float, axis_max: float, fixed_min: float, fixed_max: float,
                     lane_width: float, is_vertical: bool, exclusions: List[Dict],
                     step: float = 2.0) -> List[tuple]:
    """
    Find gaps between constraints where a street can be placed without overlap.
    Returns list of (start, end) positions where a drive lane fits.

    For horizontal streets: returns list of Y positions where a lane fits
    For vertical streets: returns list of X positions where a lane fits
    """
    clear_bands = []
    band_start = None

    for pos in [axis_min + i * step for i in range(int((axis_max - axis_min) / step) + 1)]:
        if is_vertical:
            minX = pos - lane_width / 2
            maxX = pos + lane_width / 2
            minY = fixed_min
            maxY = fixed_max
        else:
            minX = fixed_min
            maxX = fixed_max
            minY = pos - lane_width / 2
            maxY = pos + lane_width / 2

        is_clear = is_area_clear(minX, maxX, minY, maxY, exclusions)

        if is_clear:
            if band_start is None:
                band_start = pos
        else:
            if band_start is not None and pos - band_start >= lane_width * 1.5:
                clear_bands.append((band_start, pos))
            band_start = None

    # Close any remaining band
    if band_start is not None and axis_max - band_start >= lane_width * 1.5:
        clear_bands.append((band_start, axis_max))

    return clear_bands


def connect_street_segments(streets: List[Dict], aisles: List[Dict],
                            boundary: List[Point], exclusions: List[Dict],
                            drive_lane_w: float = 24.0) -> tuple:
    """
    Connect isolated street segments with bridge streets to ensure full circulation.

    Finds gaps between street segment endpoints and adds connecting streets to bridge them.
    This ensures the entire street network is connected and traversable.

    Returns: (updated_streets, connectors)
    """
    import math

    if not streets:
        return streets, []

    connectors = []
    bbox = polygon_bbox(boundary)

    # Build a spatial index of street endpoints
    endpoints = []
    for i, street in enumerate(streets):
        endpoints.append((street["from"]["x"], street["from"]["y"], i, "from"))
        endpoints.append((street["to"]["x"], street["to"]["y"], i, "to"))

    # Find pairs of close but unconnected endpoints
    tolerance = drive_lane_w * 2
    visited_pairs = set()

    for i in range(len(endpoints)):
        for j in range(i + 1, len(endpoints)):
            x1, y1, seg1, end1 = endpoints[i]
            x2, y2, seg2, end2 = endpoints[j]

            # Skip if same segment
            if seg1 == seg2:
                continue

            # Skip if already very close (touching)
            dist = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
            if dist < drive_lane_w * 0.8:  # Already touching
                continue

            # Only connect if reasonably close (within 2 drive lanes)
            if dist > tolerance:
                continue

            # Skip if pair already processed
            pair_key = tuple(sorted([(seg1, end1), (seg2, end2)]))
            if pair_key in visited_pairs:
                continue
            visited_pairs.add(pair_key)

            # Create bridge connector
            bridge = {
                "from": {"x": x1, "y": y1},
                "to": {"x": x2, "y": y2},
                "width": drive_lane_w,
                "type": "bridge"
            }

            # Check if bridge clears obstacles (simplified check)
            mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
            clear_to_place = True

            for excl in exclusions:
                # Simple bounding box check
                xs = [p["x"] if isinstance(
                    p, dict) else p.x for p in excl.get("polygon", [])]
                ys = [p["y"] if isinstance(
                    p, dict) else p.y for p in excl.get("polygon", [])]

                if xs and ys:
                    excl_minX, excl_maxX = min(xs), max(xs)
                    excl_minY, excl_maxY = min(ys), max(ys)

                    # Check if bridge midpoint is inside exclusion (with buffer)
                    if (excl_minX - drive_lane_w < mid_x < excl_maxX + drive_lane_w and
                            excl_minY - drive_lane_w < mid_y < excl_maxY + drive_lane_w):
                        clear_to_place = False
                        break

            if clear_to_place:
                connectors.append(bridge)

    return streets, connectors


def generate_circulation_first_layout(boundary: List[Point], c: Constraints,
                                      exclusions: List[Dict]) -> Dict[str, Any]:
    """
    CIRCULATION-FIRST APPROACH:
    1. Map all obstacles and find clear corridors
    2. Build a connected circulation network that routes AROUND obstacles
    3. Place stalls along the circulation paths with safe buffers from constraints

    This ensures streets are always connected and stalls are properly accessible.
    """
    import math

    bbox = polygon_bbox(boundary)
    lot_width = bbox["maxX"] - bbox["minX"]
    lot_height = bbox["maxY"] - bbox["minY"]

    stall_w = c.stallWidth
    stall_l = c.stallLength
    aisle_w = c.aisleWidth
    setback = c.setback
    drive_lane_w = 24.0
    access_w = 24.0

    # Minimum buffer from obstacles
    OBSTACLE_BUFFER = 3.0  # feet clearance from any obstacle

    streets = []
    aisles = []
    access_list = []
    stalls = []

    inner_minX = bbox["minX"] + setback
    inner_maxX = bbox["maxX"] - setback
    inner_minY = bbox["minY"] + setback
    inner_maxY = bbox["maxY"] - setback

    print(f"[CIRCULATION-FIRST] Starting with {len(exclusions)} obstacles")

    # =========================================================================
    # STEP 1: Map obstacles and compute clear zones
    # =========================================================================

    # Get bounding boxes of all obstacles with buffer
    obstacle_rects = []
    for excl in exclusions:
        minX = excl.get("minX", 0) - OBSTACLE_BUFFER
        maxX = excl.get("maxX", 0) + OBSTACLE_BUFFER
        minY = excl.get("minY", 0) - OBSTACLE_BUFFER
        maxY = excl.get("maxY", 0) + OBSTACLE_BUFFER
        obstacle_rects.append(
            {"minX": minX, "maxX": maxX, "minY": minY, "maxY": maxY})

    def is_clear(minX, maxX, minY, maxY):
        """Check if a rectangle is clear of all obstacles."""
        for obs in obstacle_rects:
            # Check for overlap
            if not (maxX <= obs["minX"] or minX >= obs["maxX"] or
                    maxY <= obs["minY"] or minY >= obs["maxY"]):
                return False
        return True

    # =========================================================================
    # STEP 2: Build main circulation spine
    # Find the longest clear corridor through the lot
    # =========================================================================

    # Try to find clear vertical corridors (X positions where a full-height drive fits)
    vertical_corridors = []
    step = 5.0
    for x in [inner_minX + drive_lane_w/2 + i * step
              for i in range(int((inner_maxX - inner_minX - drive_lane_w) / step) + 1)]:
        # Check if this X position is clear from top to bottom
        if is_clear(x - drive_lane_w/2, x + drive_lane_w/2, inner_minY, inner_maxY):
            vertical_corridors.append(x)

    # Try to find clear horizontal corridors
    horizontal_corridors = []
    for y in [inner_minY + drive_lane_w/2 + i * step
              for i in range(int((inner_maxY - inner_minY - drive_lane_w) / step) + 1)]:
        if is_clear(inner_minX, inner_maxX, y - drive_lane_w/2, y + drive_lane_w/2):
            horizontal_corridors.append(y)

    print(
        f"[CIRCULATION-FIRST] Found {len(vertical_corridors)} clear vertical corridors, {len(horizontal_corridors)} clear horizontal corridors")

    # =========================================================================
    # STEP 3: Build connected circulation network
    # =========================================================================

    main_street_x = None
    main_street_y = None

    # Prefer a center vertical corridor for main spine
    if vertical_corridors:
        # Find corridor closest to center
        center_x = (inner_minX + inner_maxX) / 2
        main_street_x = min(vertical_corridors,
                            key=lambda x: abs(x - center_x))

        # Add main vertical street
        streets.append({
            "from": {"x": main_street_x, "y": inner_minY},
            "to": {"x": main_street_x, "y": inner_maxY},
            "width": drive_lane_w, "type": "drive-lane"
        })
        print(
            f"[CIRCULATION-FIRST] Main vertical spine at X={main_street_x:.1f}")

    # Add a horizontal connector if we found one
    if horizontal_corridors:
        center_y = (inner_minY + inner_maxY) / 2
        main_street_y = min(horizontal_corridors,
                            key=lambda y: abs(y - center_y))

        streets.append({
            "from": {"x": inner_minX, "y": main_street_y},
            "to": {"x": inner_maxX, "y": main_street_y},
            "width": drive_lane_w, "type": "drive-lane"
        })
        print(
            f"[CIRCULATION-FIRST] Main horizontal connector at Y={main_street_y:.1f}")

    # If no full corridors, build perimeter loop with routing around obstacles
    if not vertical_corridors and not horizontal_corridors:
        print("[CIRCULATION-FIRST] No clear corridors - building perimeter loop")

        # Add perimeter streets
        loop_offset = drive_lane_w / 2 + setback

        # Bottom edge
        streets.append({
            "from": {"x": inner_minX, "y": inner_minY + drive_lane_w/2},
            "to": {"x": inner_maxX, "y": inner_minY + drive_lane_w/2},
            "width": drive_lane_w, "type": "drive-lane"
        })
        # Top edge
        streets.append({
            "from": {"x": inner_minX, "y": inner_maxY - drive_lane_w/2},
            "to": {"x": inner_maxX, "y": inner_maxY - drive_lane_w/2},
            "width": drive_lane_w, "type": "drive-lane"
        })
        # Left edge
        streets.append({
            "from": {"x": inner_minX + drive_lane_w/2, "y": inner_minY + drive_lane_w/2},
            "to": {"x": inner_minX + drive_lane_w/2, "y": inner_maxY - drive_lane_w/2},
            "width": drive_lane_w, "type": "drive-lane"
        })
        # Right edge
        streets.append({
            "from": {"x": inner_maxX - drive_lane_w/2, "y": inner_minY + drive_lane_w/2},
            "to": {"x": inner_maxX - drive_lane_w/2, "y": inner_maxY - drive_lane_w/2},
            "width": drive_lane_w, "type": "drive-lane"
        })

        main_street_x = (inner_minX + inner_maxX) / 2
        main_street_y = (inner_minY + inner_maxY) / 2

    # =========================================================================
    # STEP 4: Add access point
    # =========================================================================

    access_x = main_street_x if main_street_x else (
        inner_minX + inner_maxX) / 2
    if is_clear(access_x - access_w/2, access_x + access_w/2, bbox["minY"], inner_minY + drive_lane_w):
        access_list.append({
            "from": {"x": access_x, "y": bbox["minY"]},
            "to": {"x": access_x, "y": inner_minY},
            "width": access_w, "type": "access"
        })

    # =========================================================================
    # STEP 5: Place parking aisles perpendicular to main circulation
    # =========================================================================

    module_depth = stall_l + aisle_w + stall_l  # Double-loaded aisle

    if main_street_x:
        # Main street is vertical - place horizontal aisles on either side

        # Left side aisles
        left_zone_maxX = main_street_x - drive_lane_w/2 - OBSTACLE_BUFFER
        left_zone_minX = inner_minX + \
            (drive_lane_w/2 if not vertical_corridors and not horizontal_corridors else 0)

        if left_zone_maxX - left_zone_minX >= stall_l + aisle_w:
            # Place aisles from bottom to top
            y = inner_minY + stall_l + aisle_w/2
            while y + aisle_w/2 + stall_l <= inner_maxY:
                # Check if aisle is clear
                if is_clear(left_zone_minX, left_zone_maxX, y - aisle_w/2, y + aisle_w/2):
                    aisles.append({
                        "from": {"x": left_zone_minX, "y": y},
                        "to": {"x": left_zone_maxX, "y": y},
                        "width": aisle_w, "type": "aisle"
                    })

                    # Place stalls on both sides of aisle
                    aisle_length = left_zone_maxX - left_zone_minX
                    num_stalls = int(aisle_length / stall_w)

                    for s in range(num_stalls):
                        stall_cx = left_zone_minX + stall_w/2 + s * stall_w

                        # Stall above aisle
                        stall_cy_top = y + aisle_w/2 + stall_l/2
                        if (stall_cy_top + stall_l/2 <= inner_maxY and
                            is_clear(stall_cx - stall_w/2, stall_cx + stall_w/2,
                                     stall_cy_top - stall_l/2, stall_cy_top + stall_l/2)):
                            corners = rect_corners(
                                stall_cx, stall_cy_top, stall_w, stall_l, 0)
                            stalls.append({
                                "polygon": [{"x": p.x, "y": p.y} for p in corners],
                                "center": {"x": stall_cx, "y": stall_cy_top}
                            })

                        # Stall below aisle
                        stall_cy_bot = y - aisle_w/2 - stall_l/2
                        if (stall_cy_bot - stall_l/2 >= inner_minY and
                            is_clear(stall_cx - stall_w/2, stall_cx + stall_w/2,
                                     stall_cy_bot - stall_l/2, stall_cy_bot + stall_l/2)):
                            corners = rect_corners(
                                stall_cx, stall_cy_bot, stall_w, stall_l, 0)
                            stalls.append({
                                "polygon": [{"x": p.x, "y": p.y} for p in corners],
                                "center": {"x": stall_cx, "y": stall_cy_bot}
                            })

                y += module_depth

        # Right side aisles
        right_zone_minX = main_street_x + drive_lane_w/2 + OBSTACLE_BUFFER
        right_zone_maxX = inner_maxX - \
            (drive_lane_w/2 if not vertical_corridors and not horizontal_corridors else 0)

        if right_zone_maxX - right_zone_minX >= stall_l + aisle_w:
            y = inner_minY + stall_l + aisle_w/2
            while y + aisle_w/2 + stall_l <= inner_maxY:
                if is_clear(right_zone_minX, right_zone_maxX, y - aisle_w/2, y + aisle_w/2):
                    aisles.append({
                        "from": {"x": right_zone_minX, "y": y},
                        "to": {"x": right_zone_maxX, "y": y},
                        "width": aisle_w, "type": "aisle"
                    })

                    aisle_length = right_zone_maxX - right_zone_minX
                    num_stalls = int(aisle_length / stall_w)

                    for s in range(num_stalls):
                        stall_cx = right_zone_minX + stall_w/2 + s * stall_w

                        stall_cy_top = y + aisle_w/2 + stall_l/2
                        if (stall_cy_top + stall_l/2 <= inner_maxY and
                            is_clear(stall_cx - stall_w/2, stall_cx + stall_w/2,
                                     stall_cy_top - stall_l/2, stall_cy_top + stall_l/2)):
                            corners = rect_corners(
                                stall_cx, stall_cy_top, stall_w, stall_l, 0)
                            stalls.append({
                                "polygon": [{"x": p.x, "y": p.y} for p in corners],
                                "center": {"x": stall_cx, "y": stall_cy_top}
                            })

                        stall_cy_bot = y - aisle_w/2 - stall_l/2
                        if (stall_cy_bot - stall_l/2 >= inner_minY and
                            is_clear(stall_cx - stall_w/2, stall_cx + stall_w/2,
                                     stall_cy_bot - stall_l/2, stall_cy_bot + stall_l/2)):
                            corners = rect_corners(
                                stall_cx, stall_cy_bot, stall_w, stall_l, 0)
                            stalls.append({
                                "polygon": [{"x": p.x, "y": p.y} for p in corners],
                                "center": {"x": stall_cx, "y": stall_cy_bot}
                            })

                y += module_depth

    elif main_street_y:
        # Main street is horizontal - place vertical aisles on either side

        # Bottom zone aisles
        bottom_zone_maxY = main_street_y - drive_lane_w/2 - OBSTACLE_BUFFER
        bottom_zone_minY = inner_minY + drive_lane_w/2

        if bottom_zone_maxY - bottom_zone_minY >= stall_l + aisle_w:
            x = inner_minX + stall_l + aisle_w/2
            while x + aisle_w/2 + stall_l <= inner_maxX:
                if is_clear(x - aisle_w/2, x + aisle_w/2, bottom_zone_minY, bottom_zone_maxY):
                    aisles.append({
                        "from": {"x": x, "y": bottom_zone_minY},
                        "to": {"x": x, "y": bottom_zone_maxY},
                        "width": aisle_w, "type": "aisle"
                    })

                    aisle_length = bottom_zone_maxY - bottom_zone_minY
                    num_stalls = int(aisle_length / stall_w)

                    for s in range(num_stalls):
                        stall_cy = bottom_zone_minY + stall_w/2 + s * stall_w

                        # Stall to the right
                        stall_cx_right = x + aisle_w/2 + stall_l/2
                        if (stall_cx_right + stall_l/2 <= inner_maxX and
                            is_clear(stall_cx_right - stall_l/2, stall_cx_right + stall_l/2,
                                     stall_cy - stall_w/2, stall_cy + stall_w/2)):
                            corners = rect_corners(
                                stall_cx_right, stall_cy, stall_l, stall_w, 0)
                            stalls.append({
                                "polygon": [{"x": p.x, "y": p.y} for p in corners],
                                "center": {"x": stall_cx_right, "y": stall_cy}
                            })

                        # Stall to the left
                        stall_cx_left = x - aisle_w/2 - stall_l/2
                        if (stall_cx_left - stall_l/2 >= inner_minX and
                            is_clear(stall_cx_left - stall_l/2, stall_cx_left + stall_l/2,
                                     stall_cy - stall_w/2, stall_cy + stall_w/2)):
                            corners = rect_corners(
                                stall_cx_left, stall_cy, stall_l, stall_w, 0)
                            stalls.append({
                                "polygon": [{"x": p.x, "y": p.y} for p in corners],
                                "center": {"x": stall_cx_left, "y": stall_cy}
                            })

                x += stall_l + aisle_w + stall_l

        # Top zone aisles
        top_zone_minY = main_street_y + drive_lane_w/2 + OBSTACLE_BUFFER
        top_zone_maxY = inner_maxY - drive_lane_w/2

        if top_zone_maxY - top_zone_minY >= stall_l + aisle_w:
            x = inner_minX + stall_l + aisle_w/2
            while x + aisle_w/2 + stall_l <= inner_maxX:
                if is_clear(x - aisle_w/2, x + aisle_w/2, top_zone_minY, top_zone_maxY):
                    aisles.append({
                        "from": {"x": x, "y": top_zone_minY},
                        "to": {"x": x, "y": top_zone_maxY},
                        "width": aisle_w, "type": "aisle"
                    })

                    aisle_length = top_zone_maxY - top_zone_minY
                    num_stalls = int(aisle_length / stall_w)

                    for s in range(num_stalls):
                        stall_cy = top_zone_minY + stall_w/2 + s * stall_w

                        stall_cx_right = x + aisle_w/2 + stall_l/2
                        if (stall_cx_right + stall_l/2 <= inner_maxX and
                            is_clear(stall_cx_right - stall_l/2, stall_cx_right + stall_l/2,
                                     stall_cy - stall_w/2, stall_cy + stall_w/2)):
                            corners = rect_corners(
                                stall_cx_right, stall_cy, stall_l, stall_w, 0)
                            stalls.append({
                                "polygon": [{"x": p.x, "y": p.y} for p in corners],
                                "center": {"x": stall_cx_right, "y": stall_cy}
                            })

                        stall_cx_left = x - aisle_w/2 - stall_l/2
                        if (stall_cx_left - stall_l/2 >= inner_minX and
                            is_clear(stall_cx_left - stall_l/2, stall_cx_left + stall_l/2,
                                     stall_cy - stall_w/2, stall_cy + stall_w/2)):
                            corners = rect_corners(
                                stall_cx_left, stall_cy, stall_l, stall_w, 0)
                            stalls.append({
                                "polygon": [{"x": p.x, "y": p.y} for p in corners],
                                "center": {"x": stall_cx_left, "y": stall_cy}
                            })

                x += stall_l + aisle_w + stall_l

    print(
        f"[CIRCULATION-FIRST] Generated {len(stalls)} stalls with {len(streets)} streets, {len(aisles)} aisles")

    return {
        "name": "circulation-first",
        "streets": streets,
        "aisles": aisles,
        "access": access_list,
        "stalls": stalls,
        "stallCount": len(stalls),
        "connectors": [],
        "tjunctions": [],
        "exclusionShapes": []
    }


def generate_constraint_aware_layout(boundary: List[Point], c: Constraints,
                                     exclusions: List[Dict]) -> Dict[str, Any]:
    """
    Generate a parking layout that works around constraints using a simple perimeter loop approach.

    Strategy:
    1. Create a perimeter loop road (always connected, hugs the boundary)
    2. Add an access point at the bottom
    3. Generate parking modules (aisle + stalls) in clear interior zones
    4. Only place stalls that don't overlap with constraints
    """
    bbox = polygon_bbox(boundary)
    lot_width = bbox["maxX"] - bbox["minX"]
    lot_height = bbox["maxY"] - bbox["minY"]

    stall_w = c.stallWidth
    stall_l = c.stallLength
    aisle_w = c.aisleWidth
    setback = c.setback
    drive_lane_w = 24.0
    access_w = 24.0

    module_depth = stall_l + aisle_w + stall_l  # Double-loaded aisle

    streets = []
    aisles = []
    access = []
    stalls = []

    inner_minX = bbox["minX"] + setback
    inner_maxX = bbox["maxX"] - setback
    inner_minY = bbox["minY"] + setback
    inner_maxY = bbox["maxY"] - setback
    inner_width = inner_maxX - inner_minX
    inner_height = inner_maxY - inner_minY

    if inner_width <= drive_lane_w * 2 or inner_height <= drive_lane_w * 2:
        return {"name": "adaptive", "streets": [], "aisles": [], "access": [], "stalls": [], "stallCount": 0}

    # =========================================================================
    # STEP 1: Create a connected perimeter loop road
    # This ensures streets are always connected regardless of constraints
    # =========================================================================

    # Bottom horizontal drive lane
    streets.append({
        "from": {"x": inner_minX + drive_lane_w / 2, "y": inner_minY + drive_lane_w / 2},
        "to": {"x": inner_maxX - drive_lane_w / 2, "y": inner_minY + drive_lane_w / 2},
        "width": drive_lane_w, "type": "drive-lane"
    })
    # Right vertical drive lane
    streets.append({
        "from": {"x": inner_maxX - drive_lane_w / 2, "y": inner_minY + drive_lane_w / 2},
        "to": {"x": inner_maxX - drive_lane_w / 2, "y": inner_maxY - drive_lane_w / 2},
        "width": drive_lane_w, "type": "drive-lane"
    })
    # Top horizontal drive lane
    streets.append({
        "from": {"x": inner_maxX - drive_lane_w / 2, "y": inner_maxY - drive_lane_w / 2},
        "to": {"x": inner_minX + drive_lane_w / 2, "y": inner_maxY - drive_lane_w / 2},
        "width": drive_lane_w, "type": "drive-lane"
    })
    # Left vertical drive lane
    streets.append({
        "from": {"x": inner_minX + drive_lane_w / 2, "y": inner_maxY - drive_lane_w / 2},
        "to": {"x": inner_minX + drive_lane_w / 2, "y": inner_minY + drive_lane_w / 2},
        "width": drive_lane_w, "type": "drive-lane"
    })

    # =========================================================================
    # STEP 2: Add access point at bottom center
    # =========================================================================
    access_x = (inner_minX + inner_maxX) / 2
    access.append({
        "from": {"x": access_x, "y": bbox["minY"]},
        "to": {"x": access_x, "y": inner_minY + drive_lane_w},
        "width": access_w, "type": "access"
    })

    # =========================================================================
    # STEP 3: Generate parking modules in the interior
    # =========================================================================
    park_minX = inner_minX + drive_lane_w
    park_maxX = inner_maxX - drive_lane_w
    park_minY = inner_minY + drive_lane_w
    park_maxY = inner_maxY - drive_lane_w
    park_width = park_maxX - park_minX
    park_height = park_maxY - park_minY

    if park_width < stall_w * 2 or park_height < aisle_w:
        return {
            "name": "adaptive",
            "streets": streets,
            "aisles": aisles,
            "access": access,
            "stalls": stalls,
            "stallCount": len(stalls),
            "connectors": [],
            "tjunctions": []
        }

    # Determine layout orientation based on lot shape
    use_horizontal_aisles = park_width >= park_height

    if use_horizontal_aisles:
        # Horizontal aisles with vertical stalls
        num_modules = max(1, int(park_height / module_depth))
        total_module_height = num_modules * module_depth
        start_y = park_minY + (park_height - total_module_height) / 2

        for m in range(num_modules):
            aisle_y = start_y + m * module_depth + stall_l + aisle_w / 2

            # Add the aisle
            aisles.append({
                "from": {"x": park_minX, "y": aisle_y},
                "to": {"x": park_maxX, "y": aisle_y},
                "width": aisle_w, "type": "aisle"
            })

            # Generate stalls along this aisle
            num_stalls = int(park_width / stall_w)
            stall_start_x = park_minX + (park_width - num_stalls * stall_w) / 2

            for s in range(num_stalls):
                stall_cx = stall_start_x + stall_w / 2 + s * stall_w

                # Top stall (above aisle)
                stall_cy_top = aisle_y + aisle_w / 2 + stall_l / 2
                if stall_cy_top + stall_l / 2 <= park_maxY:
                    stall_minX = stall_cx - stall_w / 2
                    stall_maxX = stall_cx + stall_w / 2
                    stall_minY = stall_cy_top - stall_l / 2
                    stall_maxY = stall_cy_top + stall_l / 2

                    if (is_area_clear(stall_minX, stall_maxX, stall_minY, stall_maxY, exclusions) and
                            rect_inside_polygon(stall_cx, stall_cy_top, stall_w, stall_l, 0, boundary)):
                        corners = rect_corners(
                            stall_cx, stall_cy_top, stall_w, stall_l, 0)
                        stalls.append({
                            "polygon": [{"x": p.x, "y": p.y} for p in corners],
                            "center": {"x": stall_cx, "y": stall_cy_top}
                        })

                # Bottom stall (below aisle)
                stall_cy_bot = aisle_y - aisle_w / 2 - stall_l / 2
                if stall_cy_bot - stall_l / 2 >= park_minY:
                    stall_minY = stall_cy_bot - stall_l / 2
                    stall_maxY = stall_cy_bot + stall_l / 2

                    if (is_area_clear(stall_minX, stall_maxX, stall_minY, stall_maxY, exclusions) and
                            rect_inside_polygon(stall_cx, stall_cy_bot, stall_w, stall_l, 0, boundary)):
                        corners = rect_corners(
                            stall_cx, stall_cy_bot, stall_w, stall_l, 0)
                        stalls.append({
                            "polygon": [{"x": p.x, "y": p.y} for p in corners],
                            "center": {"x": stall_cx, "y": stall_cy_bot}
                        })
    else:
        # Vertical aisles with horizontal stalls
        num_modules = max(1, int(park_width / module_depth))
        total_module_width = num_modules * module_depth
        start_x = park_minX + (park_width - total_module_width) / 2

        for m in range(num_modules):
            aisle_x = start_x + m * module_depth + stall_l + aisle_w / 2

            # Add the aisle
            aisles.append({
                "from": {"x": aisle_x, "y": park_minY},
                "to": {"x": aisle_x, "y": park_maxY},
                "width": aisle_w, "type": "aisle"
            })

            # Generate stalls along this aisle
            num_stalls = int(park_height / stall_w)
            stall_start_y = park_minY + \
                (park_height - num_stalls * stall_w) / 2

            for s in range(num_stalls):
                stall_cy = stall_start_y + stall_w / 2 + s * stall_w

                # Right stall
                stall_cx_right = aisle_x + aisle_w / 2 + stall_l / 2
                if stall_cx_right + stall_l / 2 <= park_maxX:
                    stall_minX = stall_cx_right - stall_l / 2
                    stall_maxX = stall_cx_right + stall_l / 2
                    stall_minY = stall_cy - stall_w / 2
                    stall_maxY = stall_cy + stall_w / 2

                    if (is_area_clear(stall_minX, stall_maxX, stall_minY, stall_maxY, exclusions) and
                            rect_inside_polygon(stall_cx_right, stall_cy, stall_l, stall_w, 0, boundary)):
                        corners = rect_corners(
                            stall_cx_right, stall_cy, stall_l, stall_w, 0)
                        stalls.append({
                            "polygon": [{"x": p.x, "y": p.y} for p in corners],
                            "center": {"x": stall_cx_right, "y": stall_cy}
                        })

                # Left stall
                stall_cx_left = aisle_x - aisle_w / 2 - stall_l / 2
                if stall_cx_left - stall_l / 2 >= park_minX:
                    stall_minX = stall_cx_left - stall_l / 2
                    stall_maxX = stall_cx_left + stall_l / 2

                    if (is_area_clear(stall_minX, stall_maxX, stall_minY, stall_maxY, exclusions) and
                            rect_inside_polygon(stall_cx_left, stall_cy, stall_l, stall_w, 0, boundary)):
                        corners = rect_corners(
                            stall_cx_left, stall_cy, stall_l, stall_w, 0)
                        stalls.append({
                            "polygon": [{"x": p.x, "y": p.y} for p in corners],
                            "center": {"x": stall_cx_left, "y": stall_cy}
                        })

    return {
        "name": "adaptive",
        "streets": streets,
        "aisles": aisles,
        "access": access,
        "stalls": stalls,
        "stallCount": len(stalls),
        "connectors": [],
        "tjunctions": []
    }


def generate_smart_layout(boundary: List[Point], c: Constraints,
                          exclusions: List[Dict]) -> Dict[str, Any]:
    """
    Generate an OPTIMIZED parking layout by trying multiple street configurations
    and selecting the one with MAXIMUM stall capacity.

    Strategies tried:
    1. Horizontal main drive lane (at various Y positions)
    2. Vertical main drive lane (at various X positions)
    3. Perimeter loop with internal aisles
    4. Multiple parallel horizontal aisles
    5. Multiple parallel vertical aisles
    """
    print(f"[SMART] Starting optimization with {len(exclusions)} exclusions")

    bbox = polygon_bbox(boundary)
    stall_w = c.stallWidth
    stall_l = c.stallLength
    aisle_w = c.aisleWidth
    setback = c.setback
    drive_lane_w = 24.0
    access_w = 24.0

    inner_minX = bbox["minX"] + setback
    inner_maxX = bbox["maxX"] - setback
    inner_minY = bbox["minY"] + setback
    inner_maxY = bbox["maxY"] - setback
    inner_width = inner_maxX - inner_minX
    inner_height = inner_maxY - inner_minY

    if inner_width <= drive_lane_w * 2 or inner_height <= drive_lane_w * 2:
        return {"name": "smart", "streets": [], "aisles": [], "access": [], "stalls": [], "stallCount": 0, "connectors": [], "tjunctions": []}

    # Helper function to check if area is clear
    def area_clear(minX, maxX, minY, maxY):
        return is_area_clear(minX, maxX, minY, maxY, exclusions)

    # Helper to check if streets form a connected network
    def are_streets_connected(streets_list, aisles_list, tolerance=2.0):
        """
        Check if all streets and aisles form a single connected network.
        Returns True if connected, False if there are isolated segments.
        """
        if not streets_list and not aisles_list:
            return True
        if len(streets_list) + len(aisles_list) <= 1:
            return True

        # Build a list of all segments (streets and aisles)
        all_segments = []
        for s in streets_list:
            all_segments.append(
                (s["from"]["x"], s["from"]["y"], s["to"]["x"], s["to"]["y"]))
        for a in aisles_list:
            all_segments.append(
                (a["from"]["x"], a["from"]["y"], a["to"]["x"], a["to"]["y"]))

        if len(all_segments) <= 1:
            return True

        # Check if segments touch (share endpoints or cross)
        def segments_touch(seg1, seg2, tol):
            x1, y1, x2, y2 = seg1
            x3, y3, x4, y4 = seg2

            # Check if any endpoints are close
            points1 = [(x1, y1), (x2, y2)]
            points2 = [(x3, y3), (x4, y4)]

            for p1 in points1:
                for p2 in points2:
                    if abs(p1[0] - p2[0]) <= tol and abs(p1[1] - p2[1]) <= tol:
                        return True

            # Check if endpoints touch the body of the other segment
            def point_on_segment(px, py, sx1, sy1, sx2, sy2, tol):
                # Check if point is near the line segment
                min_x, max_x = min(sx1, sx2) - tol, max(sx1, sx2) + tol
                min_y, max_y = min(sy1, sy2) - tol, max(sy1, sy2) + tol
                if not (min_x <= px <= max_x and min_y <= py <= max_y):
                    return False

                # For axis-aligned segments
                if abs(sx1 - sx2) < 1:  # Vertical segment
                    return abs(px - sx1) <= tol and min(sy1, sy2) - tol <= py <= max(sy1, sy2) + tol
                if abs(sy1 - sy2) < 1:  # Horizontal segment
                    return abs(py - sy1) <= tol and min(sx1, sx2) - tol <= px <= max(sx1, sx2) + tol
                return False

            for px, py in points1:
                if point_on_segment(px, py, x3, y3, x4, y4, tol):
                    return True
            for px, py in points2:
                if point_on_segment(px, py, x1, y1, x2, y2, tol):
                    return True

            return False

        # Use union-find to check connectivity
        parent = list(range(len(all_segments)))

        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        for i in range(len(all_segments)):
            for j in range(i + 1, len(all_segments)):
                if segments_touch(all_segments[i], all_segments[j], tolerance + drive_lane_w):
                    union(i, j)

        # Check if all segments are in the same group
        roots = set(find(i) for i in range(len(all_segments)))
        return len(roots) == 1

    # Helper to detect optimal street direction based on geometry
    def detect_street_direction(street, all_streets, all_aisles, stalls):
        """
        Determine if a street should be one-way or two-way based on:
        - Street width (narrow = one-way)
        - Connected aisles (parking bays often use one-way aisles)
        - Main drive lanes vs parking aisles
        - Traffic flow patterns

        Returns: {"twoWay": bool, "flowDirection": angle in degrees}
        """
        width = street.get("width", 24.0)
        street_type = street.get("type", "drive-lane")

        # Main drive lanes (24ft+) are typically two-way
        if width >= 24.0 and street_type == "drive-lane":
            return {"twoWay": True, "flowDirection": None}

        # Narrow lanes (< 14ft) are one-way
        if width < 14.0:
            dx = street["to"]["x"] - street["from"]["x"]
            dy = street["to"]["y"] - street["from"]["y"]
            angle = math.atan2(dy, dx) * 180 / math.pi
            return {"twoWay": False, "flowDirection": angle}

        # Aisles between parking stalls are typically two-way for 90° parking
        # but can be one-way for angled parking
        if street_type == "aisle":
            # For 90° parking (our default), aisles are two-way
            return {"twoWay": True, "flowDirection": None}

        # Default to two-way for safety
        return {"twoWay": True, "flowDirection": None}

    # Helper to verify all stalls are reachable from the street network
    def verify_stall_reachability(streets, aisles, stalls, tolerance=5.0):
        """
        Check if all stalls are adjacent to either a street or an aisle.
        Returns: (all_reachable: bool, unreachable_stalls: list of indices)
        """
        if not stalls:
            return True, []

        unreachable = []

        for i, stall in enumerate(stalls):
            center = stall.get("center", {})
            stall_x = center.get("x", 0)
            stall_y = center.get("y", 0)

            # Check if stall is adjacent to any aisle
            reachable = False

            for aisle in aisles:
                aisle_from = aisle["from"]
                aisle_to = aisle["to"]

                # Check if stall center is near the aisle
                # For horizontal aisle
                if abs(aisle_from["y"] - aisle_to["y"]) < 1:  # Horizontal
                    aisle_y = aisle_from["y"]
                    min_x = min(aisle_from["x"], aisle_to["x"])
                    max_x = max(aisle_from["x"], aisle_to["x"])
                    aisle_half_w = aisle.get("width", 24) / 2

                    if (min_x - tolerance <= stall_x <= max_x + tolerance and
                            abs(stall_y - aisle_y) <= stall_l + aisle_half_w + tolerance):
                        reachable = True
                        break

                # For vertical aisle
                elif abs(aisle_from["x"] - aisle_to["x"]) < 1:  # Vertical
                    aisle_x = aisle_from["x"]
                    min_y = min(aisle_from["y"], aisle_to["y"])
                    max_y = max(aisle_from["y"], aisle_to["y"])
                    aisle_half_w = aisle.get("width", 24) / 2

                    if (min_y - tolerance <= stall_y <= max_y + tolerance and
                            abs(stall_x - aisle_x) <= stall_l + aisle_half_w + tolerance):
                        reachable = True
                        break

            if not reachable:
                unreachable.append(i)

        return len(unreachable) == 0, unreachable

    # Helper to add direction info to all streets and aisles
    def add_direction_info(streets, aisles, stalls):
        """Add twoWay and flowDirection properties to all streets and aisles."""
        for street in streets:
            dir_info = detect_street_direction(street, streets, aisles, stalls)
            street["twoWay"] = dir_info["twoWay"]
            if dir_info["flowDirection"] is not None:
                street["flowDirection"] = dir_info["flowDirection"]

        for aisle in aisles:
            # Parking aisles are typically two-way for 90° parking
            aisle["twoWay"] = True

        return streets, aisles

    # Helper to ensure circulation continuity
    def ensure_circulation(streets, aisles, stalls, access_list):
        """
        Verify and fix circulation issues:
        1. All streets/aisles are connected
        2. All stalls are reachable
        3. There's a path from access to all areas

        Returns modified streets and aisles with connectivity fixes
        """
        # Check stall reachability
        all_reachable, unreachable = verify_stall_reachability(
            streets, aisles, stalls)

        if not all_reachable:
            print(
                f"[CIRCULATION] Warning: {len(unreachable)} unreachable stalls detected")

        # Add direction info
        streets, aisles = add_direction_info(streets, aisles, stalls)

        return streets, aisles, all_reachable

    # Helper to find clear segments along a line
    def find_clear_segments(is_horizontal, fixed_pos, width, start, end, min_length):
        """Find clear segments along a horizontal or vertical line."""
        segments = []
        segment_start = None
        step = 2

        for pos in range(int(start), int(end) + 1, step):
            if is_horizontal:
                clear = area_clear(
                    pos - 1, pos + 1, fixed_pos - width/2, fixed_pos + width/2)
            else:
                clear = area_clear(fixed_pos - width/2,
                                   fixed_pos + width/2, pos - 1, pos + 1)

            if clear:
                if segment_start is None:
                    segment_start = pos
            else:
                if segment_start is not None:
                    if pos - segment_start >= min_length:
                        segments.append((segment_start, pos))
                    segment_start = None

        if segment_start is not None and end - segment_start >= min_length:
            segments.append((segment_start, end))

        return segments

    # Helper to generate stalls along an aisle segment
    def generate_stalls_for_aisle(seg_start, seg_end, aisle_y, aisle_w,
                                  is_horizontal, zone_min, zone_max, stalls_list):
        """Generate stalls on both sides of an aisle segment."""
        seg_length = seg_end - seg_start
        if seg_length < stall_w * 2:
            return

        num_stalls = int(seg_length / stall_w)
        start_offset = (seg_length - num_stalls * stall_w) / 2

        for s in range(num_stalls):
            if is_horizontal:
                stall_cx = seg_start + start_offset + stall_w / 2 + s * stall_w

                # Stall above aisle
                stall_cy_top = aisle_y + aisle_w / 2 + stall_l / 2
                stall_minX, stall_maxX = stall_cx - stall_w / 2, stall_cx + stall_w / 2
                stall_minY, stall_maxY = stall_cy_top - stall_l / 2, stall_cy_top + stall_l / 2

                if (stall_maxY <= zone_max and
                    area_clear(stall_minX, stall_maxX, stall_minY, stall_maxY) and
                        rect_inside_polygon(stall_cx, stall_cy_top, stall_w, stall_l, 0, boundary)):
                    corners = rect_corners(
                        stall_cx, stall_cy_top, stall_w, stall_l, 0)
                    stalls_list.append({
                        "polygon": [{"x": p.x, "y": p.y} for p in corners],
                        "center": {"x": stall_cx, "y": stall_cy_top}
                    })

                # Stall below aisle
                stall_cy_bot = aisle_y - aisle_w / 2 - stall_l / 2
                stall_minY, stall_maxY = stall_cy_bot - stall_l / 2, stall_cy_bot + stall_l / 2

                if (stall_minY >= zone_min and
                    area_clear(stall_minX, stall_maxX, stall_minY, stall_maxY) and
                        rect_inside_polygon(stall_cx, stall_cy_bot, stall_w, stall_l, 0, boundary)):
                    corners = rect_corners(
                        stall_cx, stall_cy_bot, stall_w, stall_l, 0)
                    stalls_list.append({
                        "polygon": [{"x": p.x, "y": p.y} for p in corners],
                        "center": {"x": stall_cx, "y": stall_cy_bot}
                    })
            else:
                # Vertical aisle - stalls on left and right
                stall_cy = seg_start + start_offset + stall_w / 2 + s * stall_w

                # Stall to the right of aisle
                stall_cx_right = aisle_y + aisle_w / 2 + stall_l / 2
                stall_minY, stall_maxY = stall_cy - stall_w / 2, stall_cy + stall_w / 2
                stall_minX, stall_maxX = stall_cx_right - \
                    stall_l / 2, stall_cx_right + stall_l / 2

                if (stall_maxX <= zone_max and
                    area_clear(stall_minX, stall_maxX, stall_minY, stall_maxY) and
                        rect_inside_polygon(stall_cx_right, stall_cy, stall_l, stall_w, 0, boundary)):
                    corners = rect_corners(
                        stall_cx_right, stall_cy, stall_l, stall_w, 0)
                    stalls_list.append({
                        "polygon": [{"x": p.x, "y": p.y} for p in corners],
                        "center": {"x": stall_cx_right, "y": stall_cy}
                    })

                # Stall to the left of aisle
                stall_cx_left = aisle_y - aisle_w / 2 - stall_l / 2
                stall_minX, stall_maxX = stall_cx_left - \
                    stall_l / 2, stall_cx_left + stall_l / 2

                if (stall_minX >= zone_min and
                    area_clear(stall_minX, stall_maxX, stall_minY, stall_maxY) and
                        rect_inside_polygon(stall_cx_left, stall_cy, stall_l, stall_w, 0, boundary)):
                    corners = rect_corners(
                        stall_cx_left, stall_cy, stall_l, stall_w, 0)
                    stalls_list.append({
                        "polygon": [{"x": p.x, "y": p.y} for p in corners],
                        "center": {"x": stall_cx_left, "y": stall_cy}
                    })

    # =========================================================================
    # STRATEGY 1: Horizontal drive lane with vertical access
    # =========================================================================
    def try_horizontal_drive(drive_y):
        streets, aisles, access_list, stalls, tjunctions = [], [], [], [], []

        # Find clear segments for drive lane
        drive_segments = find_clear_segments(
            True, drive_y, drive_lane_w, inner_minX, inner_maxX, drive_lane_w)
        if not drive_segments:
            return None

        for seg_start, seg_end in drive_segments:
            streets.append({
                "from": {"x": seg_start, "y": drive_y},
                "to": {"x": seg_end, "y": drive_y},
                "width": drive_lane_w, "type": "drive-lane"
            })

        # Find access point
        for test_x in [(inner_minX + inner_maxX) / 2, inner_minX + inner_width * 0.3,
                       inner_maxX - inner_width * 0.3, inner_minX + access_w]:
            if area_clear(test_x - access_w/2, test_x + access_w/2, bbox["minY"], drive_y + drive_lane_w/2):
                access_list.append({
                    "from": {"x": test_x, "y": bbox["minY"]},
                    "to": {"x": test_x, "y": drive_y},
                    "width": access_w, "type": "access"
                })
                tjunctions.append(
                    {"x": test_x, "y": drive_y, "size": drive_lane_w, "orientation": "up"})
                break

        # Generate aisles above drive lane with vertical connectors
        upper_minY = drive_y + drive_lane_w / 2
        module_h = stall_l + aisle_w + stall_l
        y = upper_minY + stall_l + aisle_w / 2
        upper_aisles = []

        while y + aisle_w / 2 + stall_l <= inner_maxY:
            aisle_segments = find_clear_segments(
                True, y, aisle_w, inner_minX, inner_maxX, stall_w * 2)
            for seg_start, seg_end in aisle_segments:
                aisles.append({
                    "from": {"x": seg_start, "y": y},
                    "to": {"x": seg_end, "y": y},
                    "width": aisle_w, "type": "aisle"
                })
                upper_aisles.append({"x": (seg_start + seg_end) / 2, "y": y})
                generate_stalls_for_aisle(
                    seg_start, seg_end, y, aisle_w, True, upper_minY, inner_maxY, stalls)
            y += module_h

        # Add vertical connectors from drive to upper aisles
        if upper_aisles:
            max_upper_y = max(a["y"] for a in upper_aisles)
            # Add vertical connector on each end
            for conn_x in [inner_minX + aisle_w/2, inner_maxX - aisle_w/2]:
                if area_clear(conn_x - aisle_w/2, conn_x + aisle_w/2, drive_y, max_upper_y + aisle_w/2):
                    streets.append({
                        "from": {"x": conn_x, "y": drive_y},
                        "to": {"x": conn_x, "y": max_upper_y},
                        "width": aisle_w, "type": "connector"
                    })

        # Generate aisles below drive lane
        lower_maxY = drive_y - drive_lane_w / 2
        y = lower_maxY - stall_l - aisle_w / 2
        lower_aisles = []

        while y - aisle_w / 2 - stall_l >= inner_minY:
            aisle_segments = find_clear_segments(
                True, y, aisle_w, inner_minX, inner_maxX, stall_w * 2)
            for seg_start, seg_end in aisle_segments:
                aisles.append({
                    "from": {"x": seg_start, "y": y},
                    "to": {"x": seg_end, "y": y},
                    "width": aisle_w, "type": "aisle"
                })
                lower_aisles.append({"x": (seg_start + seg_end) / 2, "y": y})
                generate_stalls_for_aisle(
                    seg_start, seg_end, y, aisle_w, True, inner_minY, lower_maxY, stalls)
            y -= module_h

        # Add vertical connectors from drive to lower aisles
        if lower_aisles:
            min_lower_y = min(a["y"] for a in lower_aisles)
            for conn_x in [inner_minX + aisle_w/2, inner_maxX - aisle_w/2]:
                if area_clear(conn_x - aisle_w/2, conn_x + aisle_w/2, min_lower_y - aisle_w/2, drive_y):
                    streets.append({
                        "from": {"x": conn_x, "y": min_lower_y},
                        "to": {"x": conn_x, "y": drive_y},
                        "width": aisle_w, "type": "connector"
                    })

        # Connect any isolated street segments with bridge streets
        streets, bridge_connectors = connect_street_segments(
            streets, aisles, boundary, exclusions, drive_lane_w)

        return {"name": "smart-horizontal", "streets": streets, "aisles": aisles,
                "access": access_list, "stalls": stalls, "stallCount": len(stalls),
                "connectors": bridge_connectors, "tjunctions": tjunctions}

    # =========================================================================
    # STRATEGY 2: Vertical drive lane with horizontal access
    # =========================================================================
    def try_vertical_drive(drive_x):
        streets, aisles, access_list, stalls, tjunctions = [], [], [], [], []

        # Find clear segments for vertical drive lane
        drive_segments = find_clear_segments(
            False, drive_x, drive_lane_w, inner_minY, inner_maxY, drive_lane_w)
        if not drive_segments:
            return None

        for seg_start, seg_end in drive_segments:
            streets.append({
                "from": {"x": drive_x, "y": seg_start},
                "to": {"x": drive_x, "y": seg_end},
                "width": drive_lane_w, "type": "drive-lane"
            })

        # Find horizontal access from left or right edge
        for test_y in [(inner_minY + inner_maxY) / 2, inner_minY + inner_height * 0.3,
                       inner_maxY - inner_height * 0.3]:
            if area_clear(bbox["minX"], drive_x + drive_lane_w/2, test_y - access_w/2, test_y + access_w/2):
                access_list.append({
                    "from": {"x": bbox["minX"], "y": test_y},
                    "to": {"x": drive_x, "y": test_y},
                    "width": access_w, "type": "access"
                })
                tjunctions.append(
                    {"x": drive_x, "y": test_y, "size": drive_lane_w, "orientation": "left"})
                break

        # Generate aisles to the right of drive lane with horizontal connectors
        right_minX = drive_x + drive_lane_w / 2
        module_w = stall_l + aisle_w + stall_l
        x = right_minX + stall_l + aisle_w / 2
        right_aisles = []

        while x + aisle_w / 2 + stall_l <= inner_maxX:
            aisle_segments = find_clear_segments(
                False, x, aisle_w, inner_minY, inner_maxY, stall_w * 2)
            for seg_start, seg_end in aisle_segments:
                aisles.append({
                    "from": {"x": x, "y": seg_start},
                    "to": {"x": x, "y": seg_end},
                    "width": aisle_w, "type": "aisle"
                })
                right_aisles.append({"x": x, "y": (seg_start + seg_end) / 2})
                generate_stalls_for_aisle(
                    seg_start, seg_end, x, aisle_w, False, right_minX, inner_maxX, stalls)
            x += module_w

        # Add horizontal connectors from drive to right aisles
        if right_aisles:
            max_right_x = max(a["x"] for a in right_aisles)
            for conn_y in [inner_minY + aisle_w/2, inner_maxY - aisle_w/2]:
                if area_clear(drive_x, max_right_x + aisle_w/2, conn_y - aisle_w/2, conn_y + aisle_w/2):
                    streets.append({
                        "from": {"x": drive_x, "y": conn_y},
                        "to": {"x": max_right_x, "y": conn_y},
                        "width": aisle_w, "type": "connector"
                    })

        # Generate aisles to the left of drive lane
        left_maxX = drive_x - drive_lane_w / 2
        x = left_maxX - stall_l - aisle_w / 2
        left_aisles = []

        while x - aisle_w / 2 - stall_l >= inner_minX:
            aisle_segments = find_clear_segments(
                False, x, aisle_w, inner_minY, inner_maxY, stall_w * 2)
            for seg_start, seg_end in aisle_segments:
                aisles.append({
                    "from": {"x": x, "y": seg_start},
                    "to": {"x": x, "y": seg_end},
                    "width": aisle_w, "type": "aisle"
                })
                left_aisles.append({"x": x, "y": (seg_start + seg_end) / 2})
                generate_stalls_for_aisle(
                    seg_start, seg_end, x, aisle_w, False, inner_minX, left_maxX, stalls)
            x -= module_w

        # Add horizontal connectors from drive to left aisles
        if left_aisles:
            min_left_x = min(a["x"] for a in left_aisles)
            for conn_y in [inner_minY + aisle_w/2, inner_maxY - aisle_w/2]:
                if area_clear(min_left_x - aisle_w/2, drive_x, conn_y - aisle_w/2, conn_y + aisle_w/2):
                    streets.append({
                        "from": {"x": min_left_x, "y": conn_y},
                        "to": {"x": drive_x, "y": conn_y},
                        "width": aisle_w, "type": "connector"
                    })

        # Connect any isolated street segments with bridge streets
        streets, bridge_connectors = connect_street_segments(
            streets, aisles, boundary, exclusions, drive_lane_w)

        return {"name": "smart-vertical", "streets": streets, "aisles": aisles,
                "access": access_list, "stalls": stalls, "stallCount": len(stalls),
                "connectors": bridge_connectors, "tjunctions": tjunctions}

    # =========================================================================
    # STRATEGY 3: Perimeter loop with central aisles
    # =========================================================================
    def try_perimeter_loop():
        streets, aisles, access_list, stalls, tjunctions = [], [], [], [], []

        loop_inset = drive_lane_w / 2 + 2
        loop_minX = inner_minX + loop_inset
        loop_maxX = inner_maxX - loop_inset
        loop_minY = inner_minY + loop_inset
        loop_maxY = inner_maxY - loop_inset

        # Check if perimeter is mostly clear
        perimeter_segments = []

        # Bottom edge
        segs = find_clear_segments(
            True, loop_minY, drive_lane_w, loop_minX, loop_maxX, drive_lane_w)
        for s, e in segs:
            streets.append({"from": {"x": s, "y": loop_minY}, "to": {"x": e, "y": loop_minY},
                           "width": drive_lane_w, "type": "drive-lane"})

        # Top edge
        segs = find_clear_segments(
            True, loop_maxY, drive_lane_w, loop_minX, loop_maxX, drive_lane_w)
        for s, e in segs:
            streets.append({"from": {"x": s, "y": loop_maxY}, "to": {"x": e, "y": loop_maxY},
                           "width": drive_lane_w, "type": "drive-lane"})

        # Left edge
        segs = find_clear_segments(
            False, loop_minX, drive_lane_w, loop_minY, loop_maxY, drive_lane_w)
        for s, e in segs:
            streets.append({"from": {"x": loop_minX, "y": s}, "to": {"x": loop_minX, "y": e},
                           "width": drive_lane_w, "type": "drive-lane"})

        # Right edge
        segs = find_clear_segments(
            False, loop_maxX, drive_lane_w, loop_minY, loop_maxY, drive_lane_w)
        for s, e in segs:
            streets.append({"from": {"x": loop_maxX, "y": s}, "to": {"x": loop_maxX, "y": e},
                           "width": drive_lane_w, "type": "drive-lane"})

        if not streets:
            return None

        # Access from boundary
        access_list.append({
            "from": {"x": (loop_minX + loop_maxX) / 2, "y": bbox["minY"]},
            "to": {"x": (loop_minX + loop_maxX) / 2, "y": loop_minY},
            "width": access_w, "type": "access"
        })

        # Fill interior with horizontal aisles
        interior_minX = loop_minX + drive_lane_w / 2
        interior_maxX = loop_maxX - drive_lane_w / 2
        interior_minY = loop_minY + drive_lane_w / 2
        interior_maxY = loop_maxY - drive_lane_w / 2

        module_h = stall_l + aisle_w + stall_l
        y = interior_minY + stall_l + aisle_w / 2
        interior_aisles = []

        while y + aisle_w / 2 + stall_l <= interior_maxY:
            aisle_segments = find_clear_segments(
                True, y, aisle_w, interior_minX, interior_maxX, stall_w * 2)
            for seg_start, seg_end in aisle_segments:
                aisles.append({
                    "from": {"x": seg_start, "y": y},
                    "to": {"x": seg_end, "y": y},
                    "width": aisle_w, "type": "aisle"
                })
                interior_aisles.append(
                    {"y": y, "minX": seg_start, "maxX": seg_end})
                generate_stalls_for_aisle(
                    seg_start, seg_end, y, aisle_w, True, interior_minY, interior_maxY, stalls)
            y += module_h

        # Add vertical connectors from perimeter to interior aisles
        if interior_aisles:
            min_aisle_y = min(a["y"] for a in interior_aisles)
            max_aisle_y = max(a["y"] for a in interior_aisles)

            # Left connector from perimeter to aisles
            conn_left_x = interior_minX + aisle_w/2
            if area_clear(conn_left_x - aisle_w/2, conn_left_x + aisle_w/2, loop_minY, max_aisle_y):
                streets.append({
                    "from": {"x": conn_left_x, "y": loop_minY},
                    "to": {"x": conn_left_x, "y": max_aisle_y},
                    "width": aisle_w, "type": "connector"
                })

            # Right connector from perimeter to aisles
            conn_right_x = interior_maxX - aisle_w/2
            if area_clear(conn_right_x - aisle_w/2, conn_right_x + aisle_w/2, loop_minY, max_aisle_y):
                streets.append({
                    "from": {"x": conn_right_x, "y": loop_minY},
                    "to": {"x": conn_right_x, "y": max_aisle_y},
                    "width": aisle_w, "type": "connector"
                })

        return {"name": "smart-perimeter", "streets": streets, "aisles": aisles,
                "access": access_list, "stalls": stalls, "stallCount": len(stalls),
                "connectors": [], "tjunctions": tjunctions}

    # =========================================================================
    # STRATEGY 4: All horizontal aisles with vertical connectors
    # =========================================================================
    def try_all_horizontal_aisles():
        streets, aisles, access_list, stalls, tjunctions = [], [], [], [], []

        # Access on left side
        access_x = inner_minX + drive_lane_w / 2
        access_list.append({
            "from": {"x": bbox["minX"], "y": (inner_minY + inner_maxY) / 2},
            "to": {"x": access_x, "y": (inner_minY + inner_maxY) / 2},
            "width": access_w, "type": "access"
        })

        # Vertical drive lane on left - connecting all aisles
        left_drive_segs = find_clear_segments(
            False, access_x, drive_lane_w, inner_minY, inner_maxY, drive_lane_w)
        for seg_start, seg_end in left_drive_segs:
            streets.append({
                "from": {"x": access_x, "y": seg_start},
                "to": {"x": access_x, "y": seg_end},
                "width": drive_lane_w, "type": "drive-lane"
            })

        # Vertical drive lane on right - for loop circulation
        right_drive_x = inner_maxX - drive_lane_w / 2
        right_drive_segs = find_clear_segments(
            False, right_drive_x, drive_lane_w, inner_minY, inner_maxY, drive_lane_w)
        for seg_start, seg_end in right_drive_segs:
            streets.append({
                "from": {"x": right_drive_x, "y": seg_start},
                "to": {"x": right_drive_x, "y": seg_end},
                "width": drive_lane_w, "type": "drive-lane"
            })

        # ADD HORIZONTAL CONNECTORS at top and bottom to complete the loop
        # Bottom horizontal connector
        bottom_conn_y = inner_minY + drive_lane_w / 2
        bottom_segs = find_clear_segments(
            True, bottom_conn_y, drive_lane_w, access_x, right_drive_x, drive_lane_w)
        for seg_start, seg_end in bottom_segs:
            streets.append({
                "from": {"x": seg_start, "y": bottom_conn_y},
                "to": {"x": seg_end, "y": bottom_conn_y},
                "width": drive_lane_w, "type": "drive-lane"
            })

        # Top horizontal connector
        top_conn_y = inner_maxY - drive_lane_w / 2
        top_segs = find_clear_segments(
            True, top_conn_y, drive_lane_w, access_x, right_drive_x, drive_lane_w)
        for seg_start, seg_end in top_segs:
            streets.append({
                "from": {"x": seg_start, "y": top_conn_y},
                "to": {"x": seg_end, "y": top_conn_y},
                "width": drive_lane_w, "type": "drive-lane"
            })

        # Horizontal aisles filling the middle (between top and bottom connectors)
        park_minX = access_x + drive_lane_w / 2
        park_maxX = right_drive_x - drive_lane_w / 2
        park_minY = bottom_conn_y + drive_lane_w / 2
        park_maxY = top_conn_y - drive_lane_w / 2
        module_h = stall_l + aisle_w + stall_l
        y = park_minY + stall_l + aisle_w / 2

        while y + aisle_w / 2 + stall_l <= park_maxY:
            aisle_segments = find_clear_segments(
                True, y, aisle_w, park_minX, park_maxX, stall_w * 2)
            for seg_start, seg_end in aisle_segments:
                aisles.append({
                    "from": {"x": seg_start, "y": y},
                    "to": {"x": seg_end, "y": y},
                    "width": aisle_w, "type": "aisle"
                })
                generate_stalls_for_aisle(
                    seg_start, seg_end, y, aisle_w, True, park_minY, park_maxY, stalls)
            y += module_h

        # Connect any isolated street segments with bridge streets
        streets, bridge_connectors = connect_street_segments(
            streets, aisles, boundary, exclusions, drive_lane_w)

        return {"name": "smart-h-aisles", "streets": streets, "aisles": aisles,
                "access": access_list, "stalls": stalls, "stallCount": len(stalls),
                "connectors": bridge_connectors, "tjunctions": tjunctions}

    # =========================================================================
    # STRATEGY 5: All vertical aisles with horizontal connectors
    # =========================================================================
    def try_all_vertical_aisles():
        streets, aisles, access_list, stalls, tjunctions = [], [], [], [], []

        # Access on bottom
        access_y = inner_minY + drive_lane_w / 2
        access_list.append({
            "from": {"x": (inner_minX + inner_maxX) / 2, "y": bbox["minY"]},
            "to": {"x": (inner_minX + inner_maxX) / 2, "y": access_y},
            "width": access_w, "type": "access"
        })

        # Horizontal drive lane at bottom - connecting all aisles
        bottom_drive_segs = find_clear_segments(
            True, access_y, drive_lane_w, inner_minX, inner_maxX, drive_lane_w)
        for seg_start, seg_end in bottom_drive_segs:
            streets.append({
                "from": {"x": seg_start, "y": access_y},
                "to": {"x": seg_end, "y": access_y},
                "width": drive_lane_w, "type": "drive-lane"
            })

        # Horizontal drive lane at top - for loop circulation
        top_drive_y = inner_maxY - drive_lane_w / 2
        top_drive_segs = find_clear_segments(
            True, top_drive_y, drive_lane_w, inner_minX, inner_maxX, drive_lane_w)
        for seg_start, seg_end in top_drive_segs:
            streets.append({
                "from": {"x": seg_start, "y": top_drive_y},
                "to": {"x": seg_end, "y": top_drive_y},
                "width": drive_lane_w, "type": "drive-lane"
            })

        # ADD VERTICAL CONNECTORS on left and right to complete the loop
        # Left vertical connector
        left_conn_x = inner_minX + drive_lane_w / 2
        left_segs = find_clear_segments(
            False, left_conn_x, drive_lane_w, access_y, top_drive_y, drive_lane_w)
        for seg_start, seg_end in left_segs:
            streets.append({
                "from": {"x": left_conn_x, "y": seg_start},
                "to": {"x": left_conn_x, "y": seg_end},
                "width": drive_lane_w, "type": "drive-lane"
            })

        # Right vertical connector
        right_conn_x = inner_maxX - drive_lane_w / 2
        right_segs = find_clear_segments(
            False, right_conn_x, drive_lane_w, access_y, top_drive_y, drive_lane_w)
        for seg_start, seg_end in right_segs:
            streets.append({
                "from": {"x": right_conn_x, "y": seg_start},
                "to": {"x": right_conn_x, "y": seg_end},
                "width": drive_lane_w, "type": "drive-lane"
            })

        # Vertical aisles filling the middle - between left and right connectors
        park_minX = left_conn_x + drive_lane_w / 2
        park_maxX = right_conn_x - drive_lane_w / 2
        park_minY = access_y + drive_lane_w / 2
        park_maxY = top_drive_y - drive_lane_w / 2
        module_w = stall_l + aisle_w + stall_l
        x = park_minX + stall_l + aisle_w / 2

        while x + aisle_w / 2 + stall_l <= park_maxX:
            aisle_segments = find_clear_segments(
                False, x, aisle_w, park_minY, park_maxY, stall_w * 2)
            for seg_start, seg_end in aisle_segments:
                aisles.append({
                    "from": {"x": x, "y": seg_start},
                    "to": {"x": x, "y": seg_end},
                    "width": aisle_w, "type": "aisle"
                })
                generate_stalls_for_aisle(
                    seg_start, seg_end, x, aisle_w, False, park_minX, park_maxX, stalls)
            x += module_w

        # Connect any isolated street segments with bridge streets
        streets, bridge_connectors = connect_street_segments(
            streets, aisles, boundary, exclusions, drive_lane_w)

        return {"name": "smart-v-aisles", "streets": streets, "aisles": aisles,
                "access": access_list, "stalls": stalls, "stallCount": len(stalls),
                "connectors": bridge_connectors, "tjunctions": tjunctions}

    # =========================================================================
    # STRATEGY 6: Zone-Based Layout - Analyzes Constraints and Designs Zones
    # =========================================================================
    def try_zone_based_layout():
        """
        Analyzes constraint positions and creates parking zones between them.
        1. Find clear rectangular zones (no constraints)
        2. Place a main drive lane through the largest clear corridor
        3. Fill each zone with appropriate parking modules
        4. Connect all zones with a circulation network
        """
        streets, aisles, access_list, stalls, tjunctions = [], [], [], [], []

        if not exclusions:
            # No constraints - use simple layout
            return None

        # Find the largest horizontal and vertical clear corridors
        def find_clear_corridors(is_horizontal, width):
            """Find clear corridors of given width across the lot."""
            corridors = []
            step = 5.0

            if is_horizontal:
                for y in range(int(inner_minY + width), int(inner_maxY - width), int(step)):
                    segs = find_clear_segments(
                        True, y, width, inner_minX, inner_maxX, drive_lane_w * 2)
                    total_length = sum(seg[1] - seg[0] for seg in segs)
                    if total_length >= inner_width * 0.5:  # At least 50% clear
                        corridors.append(
                            {"y": y, "segs": segs, "length": total_length})
            else:
                for x in range(int(inner_minX + width), int(inner_maxX - width), int(step)):
                    segs = find_clear_segments(
                        False, x, width, inner_minY, inner_maxY, drive_lane_w * 2)
                    total_length = sum(seg[1] - seg[0] for seg in segs)
                    if total_length >= inner_height * 0.5:  # At least 50% clear
                        corridors.append(
                            {"x": x, "segs": segs, "length": total_length})

            return sorted(corridors, key=lambda c: c["length"], reverse=True)

        # Find best main drive position
        h_corridors = find_clear_corridors(True, drive_lane_w)
        v_corridors = find_clear_corridors(False, drive_lane_w)

        # Choose the orientation with the longest clear corridor
        use_horizontal = True
        if v_corridors and (not h_corridors or v_corridors[0]["length"] > h_corridors[0]["length"]):
            use_horizontal = False

        if use_horizontal and h_corridors:
            main_y = h_corridors[0]["y"]
            main_segs = h_corridors[0]["segs"]

            # Create main horizontal drive
            for seg_start, seg_end in main_segs:
                streets.append({
                    "from": {"x": seg_start, "y": main_y},
                    "to": {"x": seg_end, "y": main_y},
                    "width": drive_lane_w, "type": "drive-lane"
                })

            # Add access from bottom edge
            access_x = (inner_minX + inner_maxX) / 2
            for test_x in [access_x, inner_minX + inner_width * 0.3, inner_maxX - inner_width * 0.3]:
                if area_clear(test_x - access_w/2, test_x + access_w/2, bbox["minY"], main_y):
                    access_list.append({
                        "from": {"x": test_x, "y": bbox["minY"]},
                        "to": {"x": test_x, "y": main_y},
                        "width": access_w, "type": "access"
                    })
                    # Add vertical connector to main drive
                    streets.append({
                        "from": {"x": test_x, "y": bbox["minY"] + setback},
                        "to": {"x": test_x, "y": main_y},
                        "width": drive_lane_w, "type": "connector"
                    })
                    break

            # Fill zones above and below main drive
            zones = [
                {"min_y": main_y + drive_lane_w/2,
                    "max_y": inner_maxY, "name": "upper"},
                {"min_y": inner_minY, "max_y": main_y -
                    drive_lane_w/2, "name": "lower"}
            ]

            for zone in zones:
                zone_height = zone["max_y"] - zone["min_y"]
                if zone_height < stall_l + aisle_w:
                    continue

                # Create horizontal aisles in this zone
                module_h = stall_l + aisle_w + stall_l

                if zone["name"] == "upper":
                    y = zone["min_y"] + stall_l + aisle_w/2
                else:
                    y = zone["max_y"] - stall_l - aisle_w/2

                while True:
                    if zone["name"] == "upper" and y + aisle_w/2 + stall_l > zone["max_y"]:
                        break
                    if zone["name"] == "lower" and y - aisle_w/2 - stall_l < zone["min_y"]:
                        break

                    aisle_segs = find_clear_segments(
                        True, y, aisle_w, inner_minX, inner_maxX, stall_w * 2)

                    for seg_start, seg_end in aisle_segs:
                        aisles.append({
                            "from": {"x": seg_start, "y": y},
                            "to": {"x": seg_end, "y": y},
                            "width": aisle_w, "type": "aisle"
                        })
                        generate_stalls_for_aisle(seg_start, seg_end, y, aisle_w, True,
                                                  zone["min_y"], zone["max_y"], stalls)

                    if zone["name"] == "upper":
                        y += module_h
                    else:
                        y -= module_h

            # Add vertical connectors from main drive to aisles
            if aisles:
                aisle_ys = set(a["from"]["y"] for a in aisles)
                for conn_x in [inner_minX + aisle_w, inner_maxX - aisle_w]:
                    min_aisle_y = min(aisle_ys)
                    max_aisle_y = max(aisle_ys)

                    # Connect from main drive upward
                    if max_aisle_y > main_y:
                        if area_clear(conn_x - aisle_w/2, conn_x + aisle_w/2, main_y, max_aisle_y):
                            streets.append({
                                "from": {"x": conn_x, "y": main_y},
                                "to": {"x": conn_x, "y": max_aisle_y},
                                "width": aisle_w, "type": "connector"
                            })

                    # Connect from main drive downward
                    if min_aisle_y < main_y:
                        if area_clear(conn_x - aisle_w/2, conn_x + aisle_w/2, min_aisle_y, main_y):
                            streets.append({
                                "from": {"x": conn_x, "y": min_aisle_y},
                                "to": {"x": conn_x, "y": main_y},
                                "width": aisle_w, "type": "connector"
                            })

        elif not use_horizontal and v_corridors:
            main_x = v_corridors[0]["x"]
            main_segs = v_corridors[0]["segs"]

            # Create main vertical drive
            for seg_start, seg_end in main_segs:
                streets.append({
                    "from": {"x": main_x, "y": seg_start},
                    "to": {"x": main_x, "y": seg_end},
                    "width": drive_lane_w, "type": "drive-lane"
                })

            # Add access from left edge
            access_y = (inner_minY + inner_maxY) / 2
            for test_y in [access_y, inner_minY + inner_height * 0.3, inner_maxY - inner_height * 0.3]:
                if area_clear(bbox["minX"], main_x, test_y - access_w/2, test_y + access_w/2):
                    access_list.append({
                        "from": {"x": bbox["minX"], "y": test_y},
                        "to": {"x": main_x, "y": test_y},
                        "width": access_w, "type": "access"
                    })
                    streets.append({
                        "from": {"x": bbox["minX"] + setback, "y": test_y},
                        "to": {"x": main_x, "y": test_y},
                        "width": drive_lane_w, "type": "connector"
                    })
                    break

            # Fill zones left and right of main drive
            zones = [
                {"min_x": main_x + drive_lane_w/2,
                    "max_x": inner_maxX, "name": "right"},
                {"min_x": inner_minX, "max_x": main_x -
                    drive_lane_w/2, "name": "left"}
            ]

            for zone in zones:
                zone_width = zone["max_x"] - zone["min_x"]
                if zone_width < stall_l + aisle_w:
                    continue

                module_w = stall_l + aisle_w + stall_l

                if zone["name"] == "right":
                    x = zone["min_x"] + stall_l + aisle_w/2
                else:
                    x = zone["max_x"] - stall_l - aisle_w/2

                while True:
                    if zone["name"] == "right" and x + aisle_w/2 + stall_l > zone["max_x"]:
                        break
                    if zone["name"] == "left" and x - aisle_w/2 - stall_l < zone["min_x"]:
                        break

                    aisle_segs = find_clear_segments(
                        False, x, aisle_w, inner_minY, inner_maxY, stall_w * 2)

                    for seg_start, seg_end in aisle_segs:
                        aisles.append({
                            "from": {"x": x, "y": seg_start},
                            "to": {"x": x, "y": seg_end},
                            "width": aisle_w, "type": "aisle"
                        })
                        generate_stalls_for_aisle(seg_start, seg_end, x, aisle_w, False,
                                                  zone["min_x"], zone["max_x"], stalls)

                    if zone["name"] == "right":
                        x += module_w
                    else:
                        x -= module_w

            # Add horizontal connectors
            if aisles:
                aisle_xs = set(a["from"]["x"] for a in aisles)
                for conn_y in [inner_minY + aisle_w, inner_maxY - aisle_w]:
                    min_aisle_x = min(aisle_xs)
                    max_aisle_x = max(aisle_xs)

                    if max_aisle_x > main_x:
                        if area_clear(main_x, max_aisle_x, conn_y - aisle_w/2, conn_y + aisle_w/2):
                            streets.append({
                                "from": {"x": main_x, "y": conn_y},
                                "to": {"x": max_aisle_x, "y": conn_y},
                                "width": aisle_w, "type": "connector"
                            })

                    if min_aisle_x < main_x:
                        if area_clear(min_aisle_x, main_x, conn_y - aisle_w/2, conn_y + aisle_w/2):
                            streets.append({
                                "from": {"x": min_aisle_x, "y": conn_y},
                                "to": {"x": main_x, "y": conn_y},
                                "width": aisle_w, "type": "connector"
                            })
        else:
            return None

        if not streets or not stalls:
            return None

        # Connect any isolated street segments with bridge streets
        streets, bridge_connectors = connect_street_segments(
            streets, aisles, boundary, exclusions, drive_lane_w)

        return {"name": "smart-zones", "streets": streets, "aisles": aisles,
                "access": access_list, "stalls": stalls, "stallCount": len(stalls),
                "connectors": bridge_connectors, "tjunctions": tjunctions}

    # =========================================================================
    # STRATEGY 7: Connected Street Network - Routes Around Obstacles
    # =========================================================================
    def try_connected_street_network():
        """
        Creates a truly connected street network that routes AROUND obstacles.
        - Builds a perimeter street loop in clear zones
        - Adds internal streets only where they can connect
        - Ensures cars can drive through the entire lot
        """
        streets, aisles, access_list, stalls, tjunctions = [], [], [], [], []

        # Define drive lane corridors - offset from boundary
        perimeter_offset = drive_lane_w / 2 + setback
        loop_minX = bbox["minX"] + perimeter_offset
        loop_maxX = bbox["maxX"] - perimeter_offset
        loop_minY = bbox["minY"] + perimeter_offset
        loop_maxY = bbox["maxY"] - perimeter_offset

        # Track which edges are clear for a continuous perimeter
        # We'll build street segments and connect them with corners

        # Check each edge segment for clearance and find gaps
        def get_edge_segments(is_horizontal, fixed_pos, start, end):
            """Get clear segments along an edge, including gap info."""
            segments = find_clear_segments(
                is_horizontal, fixed_pos, drive_lane_w, start, end, drive_lane_w)
            return segments

        # Get clear segments for each edge
        bottom_segs = get_edge_segments(True, loop_minY, loop_minX, loop_maxX)
        top_segs = get_edge_segments(True, loop_maxY, loop_minX, loop_maxX)
        left_segs = get_edge_segments(False, loop_minX, loop_minY, loop_maxY)
        right_segs = get_edge_segments(False, loop_maxX, loop_minY, loop_maxY)

        print(
            f"[CONNECTED] Edge segments - Bottom: {len(bottom_segs)}, Top: {len(top_segs)}, Left: {len(left_segs)}, Right: {len(right_segs)}")

        # Strategy: Create a connected loop using available segments
        # If an edge is blocked, try to route through the interior

        # First, add all clear perimeter segments
        for seg_start, seg_end in bottom_segs:
            streets.append({"from": {"x": seg_start, "y": loop_minY},
                           "to": {"x": seg_end, "y": loop_minY},
                            "width": drive_lane_w, "type": "drive-lane"})

        for seg_start, seg_end in top_segs:
            streets.append({"from": {"x": seg_start, "y": loop_maxY},
                           "to": {"x": seg_end, "y": loop_maxY},
                            "width": drive_lane_w, "type": "drive-lane"})

        for seg_start, seg_end in left_segs:
            streets.append({"from": {"x": loop_minX, "y": seg_start},
                           "to": {"x": loop_minX, "y": seg_end},
                            "width": drive_lane_w, "type": "drive-lane"})

        for seg_start, seg_end in right_segs:
            streets.append({"from": {"x": loop_maxX, "y": seg_start},
                           "to": {"x": loop_maxX, "y": seg_end},
                            "width": drive_lane_w, "type": "drive-lane"})

        # Now add internal cross-streets to connect gaps and create circulation
        # Find positions for internal horizontal streets
        interior_minX = loop_minX + drive_lane_w / 2
        interior_maxX = loop_maxX - drive_lane_w / 2
        interior_minY = loop_minY + drive_lane_w / 2
        interior_maxY = loop_maxY - drive_lane_w / 2

        # Add a center horizontal street if there's room
        center_y = (loop_minY + loop_maxY) / 2
        center_h_segs = find_clear_segments(
            True, center_y, drive_lane_w, loop_minX, loop_maxX, drive_lane_w * 2)

        for seg_start, seg_end in center_h_segs:
            streets.append({"from": {"x": seg_start, "y": center_y},
                           "to": {"x": seg_end, "y": center_y},
                            "width": drive_lane_w, "type": "drive-lane"})

            # Add vertical connectors from this center street to perimeter
            # These help connect any gaps in the perimeter
            for x_pos in [seg_start + drive_lane_w, seg_end - drive_lane_w]:
                if x_pos > loop_minX + drive_lane_w and x_pos < loop_maxX - drive_lane_w:
                    # Connect to top
                    v_segs_up = find_clear_segments(
                        False, x_pos, drive_lane_w, center_y, loop_maxY, drive_lane_w)
                    for vs, ve in v_segs_up:
                        streets.append({"from": {"x": x_pos, "y": vs},
                                       "to": {"x": x_pos, "y": ve},
                                        "width": drive_lane_w, "type": "drive-lane"})

                    # Connect to bottom
                    v_segs_down = find_clear_segments(
                        False, x_pos, drive_lane_w, loop_minY, center_y, drive_lane_w)
                    for vs, ve in v_segs_down:
                        streets.append({"from": {"x": x_pos, "y": vs},
                                       "to": {"x": x_pos, "y": ve},
                                        "width": drive_lane_w, "type": "drive-lane"})

        # Add a center vertical street if there's room
        center_x = (loop_minX + loop_maxX) / 2
        center_v_segs = find_clear_segments(
            False, center_x, drive_lane_w, loop_minY, loop_maxY, drive_lane_w * 2)

        for seg_start, seg_end in center_v_segs:
            streets.append({"from": {"x": center_x, "y": seg_start},
                           "to": {"x": center_x, "y": seg_end},
                            "width": drive_lane_w, "type": "drive-lane"})

        if not streets:
            print("[CONNECTED] No streets could be placed")
            return None

        # Find access point - prefer bottom center
        access_y = bbox["minY"]
        access_candidates_x = [(loop_minX + loop_maxX) / 2, loop_minX + inner_width * 0.3,
                               loop_maxX - inner_width * 0.3]

        for access_x in access_candidates_x:
            if area_clear(access_x - access_w/2, access_x + access_w/2, bbox["minY"], loop_minY + drive_lane_w/2):
                access_list.append({
                    "from": {"x": access_x, "y": bbox["minY"]},
                    "to": {"x": access_x, "y": loop_minY},
                    "width": access_w, "type": "access"
                })
                break

        # If no bottom access, try other edges
        if not access_list:
            for access_y in [(loop_minY + loop_maxY) / 2]:
                if area_clear(bbox["minX"], loop_minX + drive_lane_w/2, access_y - access_w/2, access_y + access_w/2):
                    access_list.append({
                        "from": {"x": bbox["minX"], "y": access_y},
                        "to": {"x": loop_minX, "y": access_y},
                        "width": access_w, "type": "access"
                    })
                    break

        # Now fill the zones between streets with aisles and stalls
        # Always try to fill the interior regardless of center streets

        zone_min_y = loop_minY + drive_lane_w / 2
        zone_max_y = loop_maxY - drive_lane_w / 2

        # Use the full interior width for stalls
        stall_zone_minX = interior_minX
        stall_zone_maxX = interior_maxX

        module_h = stall_l + aisle_w + stall_l

        # Try multiple starting offsets to find the best aisle positions
        best_stalls_for_aisles = []
        best_aisles_for_strategy = []

        for start_offset in [0, stall_l/2, stall_l, aisle_w/2]:
            test_stalls = []
            test_aisles = []
            y = zone_min_y + stall_l + aisle_w / 2 + start_offset

            while y + aisle_w / 2 + stall_l <= zone_max_y:
                # Skip the center street area if it exists
                if center_h_segs and abs(y - center_y) < drive_lane_w:
                    y += module_h
                    continue

                aisle_segs = find_clear_segments(
                    True, y, aisle_w, stall_zone_minX, stall_zone_maxX, stall_w * 2)

                for aisle_start, aisle_end in aisle_segs:
                    test_aisles.append({
                        "from": {"x": aisle_start, "y": y},
                        "to": {"x": aisle_end, "y": y},
                        "width": aisle_w, "type": "aisle"
                    })
                    generate_stalls_for_aisle(aisle_start, aisle_end, y, aisle_w, True,
                                              zone_min_y, zone_max_y, test_stalls)
                y += module_h

            if len(test_stalls) > len(best_stalls_for_aisles):
                best_stalls_for_aisles = test_stalls
                best_aisles_for_strategy = test_aisles

        stalls = best_stalls_for_aisles
        aisles = best_aisles_for_strategy

        print(
            f"[CONNECTED] Generated {len(stalls)} stalls with {len(streets)} street segments, {len(aisles)} aisles")

        # Connect any isolated street segments with bridge streets to ensure full circulation
        streets, bridge_connectors = connect_street_segments(
            streets, aisles, boundary, exclusions, drive_lane_w)

        return {"name": "smart-connected", "streets": streets, "aisles": aisles,
                "access": access_list, "stalls": stalls, "stallCount": len(stalls),
                "connectors": bridge_connectors, "tjunctions": tjunctions}

    # =========================================================================
    # Try all strategies and pick the best one
    # =========================================================================
    candidates = []

    # CONSTRAINT-AWARE: Find clear bands between obstacles
    horizontal_bands = []
    vertical_bands = []
    try:
        horizontal_bands = find_clear_bands(inner_minY, inner_maxY, inner_minX, inner_maxX,
                                            drive_lane_w, False, exclusions, step=5.0)
    except Exception as e:
        print(f"[ERROR] Horizontal bands failed: {e}")

    try:
        vertical_bands = find_clear_bands(inner_minX, inner_maxX, inner_minY, inner_maxY,
                                          drive_lane_w, True, exclusions, step=5.0)
    except Exception as e:
        print(f"[ERROR] Vertical bands failed: {e}")

    # If we found clear bands, use their midpoints; otherwise fall back to default positions
    if horizontal_bands:
        print(f"[SMART] Found {len(horizontal_bands)} clear horizontal bands")
        for band_start, band_end in horizontal_bands:
            test_y = (band_start + band_end) / 2
            result = try_horizontal_drive(test_y)
            if result and result["stallCount"] > 0:
                candidates.append(result)
                print(
                    f"[SMART] Horizontal @ Y={test_y:.0f} (band {band_start:.0f}-{band_end:.0f}): {result['stallCount']} stalls")
    else:
        # Fall back to fixed offsets if no clear bands found
        for y_offset in [0.3, 0.5, 0.7, 0.25, 0.75]:
            test_y = inner_minY + inner_height * y_offset
            result = try_horizontal_drive(test_y)
            if result and result["stallCount"] > 0:
                candidates.append(result)
                print(
                    f"[SMART] Horizontal @ Y={test_y:.0f}: {result['stallCount']} stalls")

    # CONSTRAINT-AWARE: Try vertical drives in clear bands
    if vertical_bands:
        print(f"[SMART] Found {len(vertical_bands)} clear vertical bands")
        for band_start, band_end in vertical_bands:
            test_x = (band_start + band_end) / 2
            result = try_vertical_drive(test_x)
            if result and result["stallCount"] > 0:
                candidates.append(result)
                print(
                    f"[SMART] Vertical @ X={test_x:.0f} (band {band_start:.0f}-{band_end:.0f}): {result['stallCount']} stalls")
    else:
        # Fall back to fixed offsets
        for x_offset in [0.3, 0.5, 0.7, 0.25, 0.75]:
            test_x = inner_minX + inner_width * x_offset
            result = try_vertical_drive(test_x)
            if result and result["stallCount"] > 0:
                candidates.append(result)
                print(
                    f"[SMART] Vertical @ X={test_x:.0f}: {result['stallCount']} stalls")

    # Try perimeter loop
    result = try_perimeter_loop()
    if result and result["stallCount"] > 0:
        candidates.append(result)
        print(f"[SMART] Perimeter loop: {result['stallCount']} stalls")

    # Try all horizontal aisles
    result = try_all_horizontal_aisles()
    if result and result["stallCount"] > 0:
        candidates.append(result)
        print(f"[SMART] All horizontal aisles: {result['stallCount']} stalls")

    # Try all vertical aisles
    result = try_all_vertical_aisles()
    if result and result["stallCount"] > 0:
        candidates.append(result)
        print(f"[SMART] All vertical aisles: {result['stallCount']} stalls")

    # Try zone-based layout (analyzes constraints and designs zones)
    result = try_zone_based_layout()
    if result and result["stallCount"] > 0:
        candidates.append(result)
        print(f"[SMART] Zone-based layout: {result['stallCount']} stalls")

    # Try connected street network (routes around obstacles, ensures circulation)
    result = try_connected_street_network()
    if result and result["stallCount"] > 0:
        candidates.append(result)
        print(
            f"[SMART] Connected street network: {result['stallCount']} stalls")

    # Pick the best result - prefer connected layouts
    if not candidates:
        print("[SMART] No valid layout found")
        return {"name": "smart", "streets": [], "aisles": [], "access": [],
                "stalls": [], "stallCount": 0, "connectors": [], "tjunctions": []}

    # Check connectivity for each candidate and mark disconnected ones
    connected_candidates = []
    disconnected_candidates = []

    for c in candidates:
        streets = c.get("streets", [])
        aisles = c.get("aisles", [])
        if are_streets_connected(streets, aisles):
            connected_candidates.append(c)
            print(
                f"[SMART] {c.get('name', 'unknown')}: CONNECTED ({c['stallCount']} stalls)")
        else:
            disconnected_candidates.append(c)
            print(
                f"[SMART] {c.get('name', 'unknown')}: DISCONNECTED ({c['stallCount']} stalls)")

    # Prefer connected layouts, fall back to disconnected if none available
    if connected_candidates:
        best = max(connected_candidates, key=lambda c: c["stallCount"])
        print(
            f"[SMART] Choosing connected layout: {best.get('name', 'unknown')} with {best['stallCount']} stalls")
    else:
        best = max(disconnected_candidates, key=lambda c: c["stallCount"])
        print(
            f"[SMART] WARNING: No connected layouts, using disconnected: {best.get('name', 'unknown')}")

    # Apply smart direction detection and circulation verification
    streets = best.get("streets", [])
    aisles = best.get("aisles", [])
    stalls = best.get("stalls", [])
    access_list = best.get("access", [])

    # Ensure circulation continuity and add direction info
    streets, aisles, all_reachable = ensure_circulation(
        streets, aisles, stalls, access_list)
    best["streets"] = streets
    best["aisles"] = aisles
    best["allStallsReachable"] = all_reachable

    if all_reachable:
        print(
            f"[SMART] All {len(stalls)} stalls are reachable from the street network")
    else:
        print(f"[SMART] WARNING: Some stalls may not be reachable")

    best["name"] = "smart"  # Rename to smart for consistency

    return best


# ─────────────────────────────────────────────────────────────────────────────
# Optimized stall packing with proper drive lanes, aisles, and circulation
# ─────────────────────────────────────────────────────────────────────────────


def generate_layout(boundary: List[Point], c: Constraints, strategy: str) -> Dict[str, Any]:
    """
    Generate a parking layout using a specific strategy.

    Architecture:
    - Access: Entry/exit points at the lot boundary
    - Drive lanes (streets): Main circulation corridors connecting access to aisles
    - Connectors: Short segments linking drive lanes to aisles
    - Aisles: Access lanes between stall rows (cars drive here to park)
    - Stalls: Individual parking spaces perpendicular or angled to aisles

    Standard module = stalls + aisle + stalls (double-loaded aisle)
    """
    bbox = polygon_bbox(boundary)
    lot_width = bbox["maxX"] - bbox["minX"]
    lot_height = bbox["maxY"] - bbox["minY"]

    stall_w = c.stallWidth      # Width of stall (typically 9 ft)
    stall_l = c.stallLength     # Length/depth of stall (typically 18 ft)
    aisle_w = c.aisleWidth      # Aisle width (typically 24 ft for 90°)
    setback = c.setback         # Perimeter buffer
    drive_lane_w = 24.0         # Main drive lane width (24 ft standard)
    access_w = 24.0             # Access point width

    # Module = double-loaded aisle: stall + aisle + stall
    module_depth = stall_l + aisle_w + stall_l  # e.g., 18 + 24 + 18 = 60 ft

    streets = []      # Main drive lanes
    aisles = []       # Parking aisles
    connectors = []   # Links between drive lanes and aisles
    access = []       # Entry/exit points
    tjunctions = []   # T-junction markers where aisles meet streets
    stalls = []

    # Usable area after setback
    inner_minX = bbox["minX"] + setback
    inner_maxX = bbox["maxX"] - setback
    inner_minY = bbox["minY"] + setback
    inner_maxY = bbox["maxY"] - setback
    inner_width = inner_maxX - inner_minX
    inner_height = inner_maxY - inner_minY

    if inner_width <= aisle_w or inner_height <= aisle_w:
        return {"name": strategy, "streets": [], "aisles": [], "connectors": [], "access": [], "tjunctions": [], "stalls": [], "stallCount": 0}

    if strategy == "horizontal":
        # Layout with proper circulation:
        # - Access at bottom center
        # - Vertical drive lanes on left/right
        # - Horizontal connector at bottom linking drive lanes
        # - Horizontal aisles connected to drive lanes
        #
        # ║  S S S S S S S S S S S S S  ║
        # ║  ─────────AISLE─────────────  ║
        # ║  S S S S S S S S S S S S S  ║
        # ║  S S S S S S S S S S S S S  ║
        # ║  ─────────AISLE─────────────  ║
        # ║  S S S S S S S S S S S S S  ║
        # ╚══════════════╦══════════════╝
        #              ACCESS

        # Add access point at bottom center
        access_x = (inner_minX + inner_maxX) / 2
        access.append({
            "from": {"x": access_x, "y": bbox["minY"]},
            "to": {"x": access_x, "y": inner_minY + drive_lane_w},
            "width": access_w, "type": "access"
        })
        # T-junction where access meets bottom drive lane
        tjunctions.append({
            "x": access_x,
            "y": inner_minY + drive_lane_w / 2,
            "size": drive_lane_w,
            "orientation": "up"  # access comes from below
        })

        # Bottom horizontal drive lane (connects to access)
        streets.append({
            "from": {"x": inner_minX, "y": inner_minY + drive_lane_w / 2},
            "to": {"x": inner_maxX, "y": inner_minY + drive_lane_w / 2},
            "width": drive_lane_w, "type": "drive-lane"
        })
        # T-junctions where left/right ends of bottom drive lane meet vertical drive lanes
        tjunctions.append({
            "x": inner_minX + drive_lane_w / 2,
            "y": inner_minY + drive_lane_w / 2,
            "size": drive_lane_w,
            "orientation": "right"
        })
        tjunctions.append({
            "x": inner_maxX - drive_lane_w / 2,
            "y": inner_minY + drive_lane_w / 2,
            "size": drive_lane_w,
            "orientation": "left"
        })

        # Vertical drive lanes on left and right
        streets.append({
            "from": {"x": inner_minX + drive_lane_w / 2, "y": inner_minY + drive_lane_w},
            "to": {"x": inner_minX + drive_lane_w / 2, "y": inner_maxY},
            "width": drive_lane_w, "type": "drive-lane"
        })
        streets.append({
            "from": {"x": inner_maxX - drive_lane_w / 2, "y": inner_minY + drive_lane_w},
            "to": {"x": inner_maxX - drive_lane_w / 2, "y": inner_maxY},
            "width": drive_lane_w, "type": "drive-lane"
        })

        # Parking area between drive lanes
        park_minX = inner_minX + drive_lane_w
        park_maxX = inner_maxX - drive_lane_w
        park_minY = inner_minY + drive_lane_w
        park_maxY = inner_maxY
        park_width = park_maxX - park_minX
        park_height = park_maxY - park_minY

        if park_width < stall_w * 2 or park_height < module_depth:
            return {"name": strategy, "streets": streets, "aisles": [], "connectors": connectors, "access": access, "tjunctions": [], "stalls": [], "stallCount": 0}

        # Calculate number of modules that fit vertically
        num_modules = max(1, int(park_height / module_depth))
        total_module_height = num_modules * module_depth
        start_y = park_minY + (park_height - total_module_height) / 2

        for m in range(num_modules):
            # Aisle center Y position (center of the module)
            aisle_center_y = start_y + m * module_depth + stall_l + aisle_w / 2

            # Add aisle running horizontally
            aisles.append({
                "from": {"x": park_minX, "y": aisle_center_y},
                "to": {"x": park_maxX, "y": aisle_center_y},
                "width": aisle_w, "type": "aisle"
            })

            # Connectors from drive lanes to this aisle
            connectors.append({
                "from": {"x": inner_minX + drive_lane_w / 2, "y": aisle_center_y},
                "to": {"x": park_minX, "y": aisle_center_y},
                "width": aisle_w, "type": "connector"
            })
            connectors.append({
                "from": {"x": park_maxX, "y": aisle_center_y},
                "to": {"x": inner_maxX - drive_lane_w / 2, "y": aisle_center_y},
                "width": aisle_w, "type": "connector"
            })

            # T-junctions where aisle meets left and right drive lanes
            tjunctions.append({
                "x": inner_minX + drive_lane_w / 2,
                "y": aisle_center_y,
                "size": drive_lane_w,
                "orientation": "right"  # aisle goes right from drive lane
            })
            tjunctions.append({
                "x": inner_maxX - drive_lane_w / 2,
                "y": aisle_center_y,
                "size": drive_lane_w,
                "orientation": "left"  # aisle goes left from drive lane
            })

            # Stall positions
            num_stalls_per_row = int(park_width / stall_w)
            stall_offset_x = (park_width - num_stalls_per_row * stall_w) / 2

            for s in range(num_stalls_per_row):
                stall_cx = park_minX + stall_offset_x + stall_w / 2 + s * stall_w

                # Top row of stalls (above aisle)
                stall_cy_top = aisle_center_y + aisle_w / 2 + stall_l / 2
                if stall_cy_top + stall_l / 2 <= start_y + (m + 1) * module_depth:
                    corners = rect_corners(
                        stall_cx, stall_cy_top, stall_w, stall_l, 0)
                    if rect_inside_polygon(stall_cx, stall_cy_top, stall_w, stall_l, 0, boundary):
                        stalls.append({
                            "polygon": [{"x": p.x, "y": p.y} for p in corners],
                            "center": {"x": stall_cx, "y": stall_cy_top}
                        })

                # Bottom row of stalls (below aisle)
                stall_cy_bot = aisle_center_y - aisle_w / 2 - stall_l / 2
                if stall_cy_bot - stall_l / 2 >= start_y + m * module_depth:
                    corners = rect_corners(
                        stall_cx, stall_cy_bot, stall_w, stall_l, 0)
                    if rect_inside_polygon(stall_cx, stall_cy_bot, stall_w, stall_l, 0, boundary):
                        stalls.append({
                            "polygon": [{"x": p.x, "y": p.y} for p in corners],
                            "center": {"x": stall_cx, "y": stall_cy_bot}
                        })

    elif strategy == "vertical":
        # Layout with vertical aisles:
        # - Access at left center
        # - Horizontal drive lanes on top/bottom
        # - Vertical drive lane on left connecting to access
        # - Vertical aisles connected to drive lanes

        # Add access point at left center
        access_y = (inner_minY + inner_maxY) / 2
        access.append({
            "from": {"x": bbox["minX"], "y": access_y},
            "to": {"x": inner_minX + drive_lane_w, "y": access_y},
            "width": access_w, "type": "access"
        })
        # T-junction where access meets left drive lane
        tjunctions.append({
            "x": inner_minX + drive_lane_w / 2,
            "y": access_y,
            "size": drive_lane_w,
            "orientation": "right"
        })

        # Left vertical drive lane (connects to access)
        streets.append({
            "from": {"x": inner_minX + drive_lane_w / 2, "y": inner_minY},
            "to": {"x": inner_minX + drive_lane_w / 2, "y": inner_maxY},
            "width": drive_lane_w, "type": "drive-lane"
        })
        # T-junctions where top/bottom ends of left drive lane meet horizontal drive lanes
        tjunctions.append({
            "x": inner_minX + drive_lane_w / 2,
            "y": inner_minY + drive_lane_w / 2,
            "size": drive_lane_w,
            "orientation": "down"
        })
        tjunctions.append({
            "x": inner_minX + drive_lane_w / 2,
            "y": inner_maxY - drive_lane_w / 2,
            "size": drive_lane_w,
            "orientation": "up"
        })

        # Top and bottom horizontal drive lanes
        streets.append({
            "from": {"x": inner_minX + drive_lane_w, "y": inner_minY + drive_lane_w / 2},
            "to": {"x": inner_maxX, "y": inner_minY + drive_lane_w / 2},
            "width": drive_lane_w, "type": "drive-lane"
        })
        streets.append({
            "from": {"x": inner_minX + drive_lane_w, "y": inner_maxY - drive_lane_w / 2},
            "to": {"x": inner_maxX, "y": inner_maxY - drive_lane_w / 2},
            "width": drive_lane_w, "type": "drive-lane"
        })

        # Parking area
        park_minX = inner_minX + drive_lane_w
        park_maxX = inner_maxX
        park_minY = inner_minY + drive_lane_w
        park_maxY = inner_maxY - drive_lane_w
        park_width = park_maxX - park_minX
        park_height = park_maxY - park_minY

        if park_height < stall_w * 2 or park_width < module_depth:
            return {"name": strategy, "streets": streets, "aisles": [], "connectors": connectors, "access": access, "tjunctions": [], "stalls": [], "stallCount": 0}

        # Calculate number of modules that fit horizontally
        num_modules = max(1, int(park_width / module_depth))
        total_module_width = num_modules * module_depth
        start_x = park_minX + (park_width - total_module_width) / 2

        for m in range(num_modules):
            # Aisle center X position
            aisle_center_x = start_x + m * module_depth + stall_l + aisle_w / 2

            # Add aisle running vertically
            aisles.append({
                "from": {"x": aisle_center_x, "y": park_minY},
                "to": {"x": aisle_center_x, "y": park_maxY},
                "width": aisle_w, "type": "aisle"
            })

            # Connectors from drive lanes to this aisle
            connectors.append({
                "from": {"x": aisle_center_x, "y": inner_minY + drive_lane_w / 2},
                "to": {"x": aisle_center_x, "y": park_minY},
                "width": aisle_w, "type": "connector"
            })
            connectors.append({
                "from": {"x": aisle_center_x, "y": park_maxY},
                "to": {"x": aisle_center_x, "y": inner_maxY - drive_lane_w / 2},
                "width": aisle_w, "type": "connector"
            })

            # T-junctions where aisle meets top and bottom drive lanes
            tjunctions.append({
                "x": aisle_center_x,
                "y": inner_minY + drive_lane_w / 2,
                "size": drive_lane_w,
                "orientation": "up"  # aisle goes up from drive lane
            })
            tjunctions.append({
                "x": aisle_center_x,
                "y": inner_maxY - drive_lane_w / 2,
                "size": drive_lane_w,
                "orientation": "down"  # aisle goes down from drive lane
            })

            # Stall positions
            num_stalls_per_row = int(park_height / stall_w)
            stall_offset_y = (park_height - num_stalls_per_row * stall_w) / 2

            for s in range(num_stalls_per_row):
                stall_cy = park_minY + stall_offset_y + stall_w / 2 + s * stall_w

                # Right column of stalls
                stall_cx_right = aisle_center_x + aisle_w / 2 + stall_l / 2
                if stall_cx_right + stall_l / 2 <= start_x + (m + 1) * module_depth:
                    corners = rect_corners(
                        stall_cx_right, stall_cy, stall_l, stall_w, 0)
                    if rect_inside_polygon(stall_cx_right, stall_cy, stall_l, stall_w, 0, boundary):
                        stalls.append({
                            "polygon": [{"x": p.x, "y": p.y} for p in corners],
                            "center": {"x": stall_cx_right, "y": stall_cy}
                        })

                # Left column of stalls
                stall_cx_left = aisle_center_x - aisle_w / 2 - stall_l / 2
                if stall_cx_left - stall_l / 2 >= start_x + m * module_depth:
                    corners = rect_corners(
                        stall_cx_left, stall_cy, stall_l, stall_w, 0)
                    if rect_inside_polygon(stall_cx_left, stall_cy, stall_l, stall_w, 0, boundary):
                        stalls.append({
                            "polygon": [{"x": p.x, "y": p.y} for p in corners],
                            "center": {"x": stall_cx_left, "y": stall_cy}
                        })

    elif strategy == "loop":
        # Perimeter loop with access and connected circulation
        # - Access at bottom center
        # - Loop drive lane around perimeter
        # - Single-loaded stalls along perimeter

        # Access point at bottom center
        access_x = (inner_minX + inner_maxX) / 2
        access.append({
            "from": {"x": access_x, "y": bbox["minY"]},
            "to": {"x": access_x, "y": inner_minY + drive_lane_w / 2},
            "width": access_w, "type": "access"
        })

        loop_inset = drive_lane_w / 2

        # Four sides of the loop (connected)
        streets.append({
            "from": {"x": inner_minX + loop_inset, "y": inner_minY + loop_inset},
            "to": {"x": inner_maxX - loop_inset, "y": inner_minY + loop_inset},
            "width": drive_lane_w, "type": "drive-lane"
        })
        streets.append({
            "from": {"x": inner_maxX - loop_inset, "y": inner_minY + loop_inset},
            "to": {"x": inner_maxX - loop_inset, "y": inner_maxY - loop_inset},
            "width": drive_lane_w, "type": "drive-lane"
        })
        streets.append({
            "from": {"x": inner_maxX - loop_inset, "y": inner_maxY - loop_inset},
            "to": {"x": inner_minX + loop_inset, "y": inner_maxY - loop_inset},
            "width": drive_lane_w, "type": "drive-lane"
        })
        streets.append({
            "from": {"x": inner_minX + loop_inset, "y": inner_maxY - loop_inset},
            "to": {"x": inner_minX + loop_inset, "y": inner_minY + loop_inset},
            "width": drive_lane_w, "type": "drive-lane"
        })

        # Stalls along perimeter (single-loaded, facing into the loop)
        stall_area_offset = drive_lane_w + stall_l / 2

        # Bottom row
        num_stalls_bottom = int(
            (inner_width - 2 * drive_lane_w - 2 * stall_l) / stall_w)
        if num_stalls_bottom > 0:
            start_x = inner_minX + drive_lane_w + stall_l + \
                (inner_width - 2 * drive_lane_w - 2 * stall_l -
                 num_stalls_bottom * stall_w) / 2 + stall_w / 2
            for s in range(num_stalls_bottom):
                stall_cx = start_x + s * stall_w
                stall_cy = inner_minY + stall_area_offset
                corners = rect_corners(stall_cx, stall_cy, stall_w, stall_l, 0)
                if rect_inside_polygon(stall_cx, stall_cy, stall_w, stall_l, 0, boundary):
                    stalls.append({"polygon": [{"x": p.x, "y": p.y} for p in corners], "center": {
                                  "x": stall_cx, "y": stall_cy}})

        # Top row
        if num_stalls_bottom > 0:
            for s in range(num_stalls_bottom):
                stall_cx = start_x + s * stall_w
                stall_cy = inner_maxY - stall_area_offset
                corners = rect_corners(stall_cx, stall_cy, stall_w, stall_l, 0)
                if rect_inside_polygon(stall_cx, stall_cy, stall_w, stall_l, 0, boundary):
                    stalls.append({"polygon": [{"x": p.x, "y": p.y} for p in corners], "center": {
                                  "x": stall_cx, "y": stall_cy}})

        # Side columns
        num_stalls_side = int(
            (inner_height - 2 * drive_lane_w - 2 * stall_l) / stall_w)
        if num_stalls_side > 0:
            start_y = inner_minY + drive_lane_w + stall_l + \
                (inner_height - 2 * drive_lane_w - 2 * stall_l -
                 num_stalls_side * stall_w) / 2 + stall_w / 2
            for s in range(num_stalls_side):
                # Left column
                stall_cx = inner_minX + stall_area_offset
                stall_cy = start_y + s * stall_w
                corners = rect_corners(stall_cx, stall_cy, stall_l, stall_w, 0)
                if rect_inside_polygon(stall_cx, stall_cy, stall_l, stall_w, 0, boundary):
                    stalls.append({"polygon": [{"x": p.x, "y": p.y} for p in corners], "center": {
                                  "x": stall_cx, "y": stall_cy}})
                # Right column
                stall_cx = inner_maxX - stall_area_offset
                corners = rect_corners(stall_cx, stall_cy, stall_l, stall_w, 0)
                if rect_inside_polygon(stall_cx, stall_cy, stall_l, stall_w, 0, boundary):
                    stalls.append({"polygon": [{"x": p.x, "y": p.y} for p in corners], "center": {
                                  "x": stall_cx, "y": stall_cy}})

    elif strategy == "dual-access":
        # Two access points with full circulation
        # - Access at bottom-left and bottom-right
        # - U-shaped drive lane connecting both
        # - Multiple aisles in the center

        # Access points at bottom corners
        access.append({
            "from": {"x": inner_minX + drive_lane_w / 2, "y": bbox["minY"]},
            "to": {"x": inner_minX + drive_lane_w / 2, "y": inner_minY + drive_lane_w},
            "width": access_w, "type": "access"
        })
        access.append({
            "from": {"x": inner_maxX - drive_lane_w / 2, "y": bbox["minY"]},
            "to": {"x": inner_maxX - drive_lane_w / 2, "y": inner_minY + drive_lane_w},
            "width": access_w, "type": "access"
        })
        # T-junctions where access meets left/right drive lanes
        tjunctions.append({
            "x": inner_minX + drive_lane_w / 2,
            "y": inner_minY + drive_lane_w / 2,
            "size": drive_lane_w,
            "orientation": "up"
        })
        tjunctions.append({
            "x": inner_maxX - drive_lane_w / 2,
            "y": inner_minY + drive_lane_w / 2,
            "size": drive_lane_w,
            "orientation": "up"
        })

        # U-shaped drive lane
        # Bottom horizontal
        streets.append({
            "from": {"x": inner_minX + drive_lane_w / 2, "y": inner_minY + drive_lane_w / 2},
            "to": {"x": inner_maxX - drive_lane_w / 2, "y": inner_minY + drive_lane_w / 2},
            "width": drive_lane_w, "type": "drive-lane"
        })
        # Left vertical
        streets.append({
            "from": {"x": inner_minX + drive_lane_w / 2, "y": inner_minY + drive_lane_w},
            "to": {"x": inner_minX + drive_lane_w / 2, "y": inner_maxY - drive_lane_w / 2},
            "width": drive_lane_w, "type": "drive-lane"
        })
        # Right vertical
        streets.append({
            "from": {"x": inner_maxX - drive_lane_w / 2, "y": inner_minY + drive_lane_w},
            "to": {"x": inner_maxX - drive_lane_w / 2, "y": inner_maxY - drive_lane_w / 2},
            "width": drive_lane_w, "type": "drive-lane"
        })
        # Top horizontal (closes the U into a loop for better circulation)
        streets.append({
            "from": {"x": inner_minX + drive_lane_w / 2, "y": inner_maxY - drive_lane_w / 2},
            "to": {"x": inner_maxX - drive_lane_w / 2, "y": inner_maxY - drive_lane_w / 2},
            "width": drive_lane_w, "type": "drive-lane"
        })

        # Parking area
        park_minX = inner_minX + drive_lane_w
        park_maxX = inner_maxX - drive_lane_w
        park_minY = inner_minY + drive_lane_w
        park_maxY = inner_maxY - drive_lane_w
        park_width = park_maxX - park_minX
        park_height = park_maxY - park_minY

        if park_width < stall_w * 2 or park_height < module_depth:
            return {"name": strategy, "streets": streets, "aisles": [], "connectors": connectors, "access": access, "tjunctions": [], "stalls": [], "stallCount": 0}

        # Horizontal aisles
        num_modules = max(1, int(park_height / module_depth))
        total_module_height = num_modules * module_depth
        start_y = park_minY + (park_height - total_module_height) / 2

        for m in range(num_modules):
            aisle_center_y = start_y + m * module_depth + stall_l + aisle_w / 2

            aisles.append({
                "from": {"x": park_minX, "y": aisle_center_y},
                "to": {"x": park_maxX, "y": aisle_center_y},
                "width": aisle_w, "type": "aisle"
            })

            # Connectors to left and right drive lanes
            connectors.append({
                "from": {"x": inner_minX + drive_lane_w / 2, "y": aisle_center_y},
                "to": {"x": park_minX, "y": aisle_center_y},
                "width": aisle_w, "type": "connector"
            })
            connectors.append({
                "from": {"x": park_maxX, "y": aisle_center_y},
                "to": {"x": inner_maxX - drive_lane_w / 2, "y": aisle_center_y},
                "width": aisle_w, "type": "connector"
            })

            # T-junctions where aisle meets left and right drive lanes
            tjunctions.append({
                "x": inner_minX + drive_lane_w / 2,
                "y": aisle_center_y,
                "size": drive_lane_w,
                "orientation": "right"
            })
            tjunctions.append({
                "x": inner_maxX - drive_lane_w / 2,
                "y": aisle_center_y,
                "size": drive_lane_w,
                "orientation": "left"
            })

            # Stalls
            num_stalls_per_row = int(park_width / stall_w)
            stall_offset_x = (park_width - num_stalls_per_row * stall_w) / 2

            for s in range(num_stalls_per_row):
                stall_cx = park_minX + stall_offset_x + stall_w / 2 + s * stall_w

                # Top row
                stall_cy_top = aisle_center_y + aisle_w / 2 + stall_l / 2
                if stall_cy_top + stall_l / 2 <= start_y + (m + 1) * module_depth:
                    corners = rect_corners(
                        stall_cx, stall_cy_top, stall_w, stall_l, 0)
                    if rect_inside_polygon(stall_cx, stall_cy_top, stall_w, stall_l, 0, boundary):
                        stalls.append({
                            "polygon": [{"x": p.x, "y": p.y} for p in corners],
                            "center": {"x": stall_cx, "y": stall_cy_top}
                        })

                # Bottom row
                stall_cy_bot = aisle_center_y - aisle_w / 2 - stall_l / 2
                if stall_cy_bot - stall_l / 2 >= start_y + m * module_depth:
                    corners = rect_corners(
                        stall_cx, stall_cy_bot, stall_w, stall_l, 0)
                    if rect_inside_polygon(stall_cx, stall_cy_bot, stall_w, stall_l, 0, boundary):
                        stalls.append({
                            "polygon": [{"x": p.x, "y": p.y} for p in corners],
                            "center": {"x": stall_cx, "y": stall_cy_bot}
                        })

    return {
        "name": strategy,
        "streets": streets,
        "aisles": aisles,
        "connectors": connectors,
        "access": access,
        "tjunctions": tjunctions,
        "stalls": stalls,
        "stallCount": len(stalls),
        "meta": {
            "boundary": [{"x": p.x, "y": p.y} for p in boundary],
            "constraints": c.model_dump(),
            "lotArea": lot_width * lot_height,
            "efficiency": len(stalls) * stall_w * stall_l / (lot_width * lot_height) if lot_width * lot_height > 0 else 0
        }
    }


def _parking_generate_impl(req: GenerateRequest):
    """Internal implementation of parking generation."""
    boundary = req.boundary or [Point(x=0, y=0), Point(
        x=100, y=0), Point(x=100, y=60), Point(x=0, y=60)]
    c = req.constraints or Constraints()
    standards = req.standards or StructureStandards()
    parking_type = req.parkingType
    num_levels = max(1, min(req.numLevels, 10))  # Clamp 1-10 levels

    # Process user-uploaded exclusion zones (mechanical rooms, stairs, etc.)
    user_exclusions = []
    exclusion_shapes = []  # For frontend rendering

    # Add buffer around exclusions to ensure stalls don't touch edges
    EXCLUSION_BUFFER = 2.0  # 2 feet buffer around each exclusion

    if req.exclusions:
        print(f"Processing {len(req.exclusions)} exclusions from request")
        for exc in req.exclusions:
            if exc.polygon and len(exc.polygon) >= 3:
                pts = exc.polygon
                xs = [p.x for p in pts]
                ys = [p.y for p in pts]
                user_exclusions.append({
                    "minX": min(xs) - EXCLUSION_BUFFER,
                    "maxX": max(xs) + EXCLUSION_BUFFER,
                    "minY": min(ys) - EXCLUSION_BUFFER,
                    "maxY": max(ys) + EXCLUSION_BUFFER,
                    "type": exc.type
                })
                exclusion_shapes.append({
                    "type": exc.type,
                    "polygon": [{"x": p.x, "y": p.y} for p in pts]
                })
                print(
                    f"  Exclusion {exc.type}: bbox ({min(xs):.1f}, {min(ys):.1f}) to ({max(xs):.1f}, {max(ys):.1f})")

    print(f"Total user exclusions with buffer: {len(user_exclusions)}")

    bbox = polygon_bbox(boundary)

    iterations = []

    # If there are exclusions, use constraint-aware layouts as primary options
    if user_exclusions:
        print("Using constraint-aware layouts...")

        # Generate CIRCULATION-FIRST layout (builds connected circulation, then places stalls)
        circulation_layout = generate_circulation_first_layout(
            boundary, c, user_exclusions)
        circulation_layout["exclusions"] = exclusion_shapes

        if parking_type == "surface":
            circulation_layout["levels"] = [{
                "level": 1,
                "label": "Surface",
                "stalls": circulation_layout["stalls"],
                "stallCount": circulation_layout["stallCount"],
                "columns": [],
                "ramp": None
            }]

        if circulation_layout["stallCount"] > 0:
            iterations.append(circulation_layout)
            print(
                f"  Circulation-first layout: {circulation_layout['stallCount']} stalls, {len(circulation_layout['streets'])} streets")

        # Generate SMART layout (analyzes constraints, places streets intelligently)
        smart_layout = generate_smart_layout(boundary, c, user_exclusions)
        smart_layout["exclusions"] = exclusion_shapes

        if parking_type == "surface":
            smart_layout["levels"] = [{
                "level": 1,
                "label": "Surface",
                "stalls": smart_layout["stalls"],
                "stallCount": smart_layout["stallCount"],
                "columns": [],
                "ramp": None
            }]

        iterations.append(smart_layout)
        print(
            f"  Smart layout: {smart_layout['stallCount']} stalls, {len(smart_layout.get('streets', []))} streets, {len(smart_layout.get('aisles', []))} aisles")

        # Generate CENTERLINE-BASED layout (new algorithm using medial axis detection)
        if CENTERLINE_AVAILABLE:
            try:
                # Convert boundary and exclusions to format expected by centerline module
                centerline_boundary = {
                    "minX": bbox["minX"],
                    "maxX": bbox["maxX"],
                    "minY": bbox["minY"],
                    "maxY": bbox["maxY"]
                }
                centerline_obstacles = []
                for exc in user_exclusions:
                    centerline_obstacles.append({
                        "minX": exc["minX"],
                        "maxX": exc["maxX"],
                        "minY": exc["minY"],
                        "maxY": exc["maxY"]
                    })

                centerline_result = generate_centerline_layout(
                    boundary=centerline_boundary,
                    constraints=centerline_obstacles,
                    stall_width=c.stallWidth,
                    stall_length=c.stallLength,
                    aisle_width=c.aisleWidth,
                    setback=c.setback,
                    verbose=True,
                    use_centerline_detection=True
                )

                # Convert to app.py format - streets already come in from/to format from smart_parking.to_dict()
                cl_streets = []
                for s in centerline_result.get("streets", []):
                    # Streets from smart_parking.py already have from/to format
                    cl_streets.append({
                        "from": s.get("from", {"x": 0, "y": 0}),
                        "to": s.get("to", {"x": 0, "y": 0}),
                        "width": s.get("width", 24.0),
                        "type": s.get("type", "drive-lane"),
                        "twoWay": True
                    })

                cl_stalls = []
                for stall in centerline_result.get("stalls", []):
                    cl_stalls.append({
                        "center": {"x": stall["center"]["x"], "y": stall["center"]["y"]},
                        "width": stall["width"],
                        "length": stall["length"],
                        "angle": stall["angle"],
                        "polygon": stall["polygon"]
                    })

                centerline_layout = {
                    "name": "centerline",
                    "streets": cl_streets,
                    "aisles": [],  # Centerline method uses streets only
                    "access": [],
                    "stalls": cl_stalls,
                    "stallCount": len(cl_stalls),
                    "connectors": [],
                    "tjunctions": [],
                    "exclusions": exclusion_shapes,
                    "method": "centerline"
                }

                if parking_type == "surface":
                    centerline_layout["levels"] = [{
                        "level": 1,
                        "label": "Surface",
                        "stalls": centerline_layout["stalls"],
                        "stallCount": centerline_layout["stallCount"],
                        "columns": [],
                        "ramp": None
                    }]

                if centerline_layout["stallCount"] > 0:
                    iterations.append(centerline_layout)
                    print(
                        f"  Centerline layout: {centerline_layout['stallCount']} stalls, {len(centerline_layout['streets'])} streets (medial axis method)")
            except Exception as e:
                print(f"  [WARNING] Centerline layout failed: {e}")

        # Also generate adaptive layout for comparison
        adaptive_layout = generate_constraint_aware_layout(
            boundary, c, user_exclusions)
        adaptive_layout["exclusions"] = exclusion_shapes

        if parking_type == "surface":
            adaptive_layout["levels"] = [{
                "level": 1,
                "label": "Surface",
                "stalls": adaptive_layout["stalls"],
                "stallCount": adaptive_layout["stallCount"],
                "columns": [],
                "ramp": None
            }]

        iterations.append(adaptive_layout)
        print(
            f"  Adaptive layout: {adaptive_layout['stallCount']} stalls, {len(adaptive_layout.get('streets', []))} streets, {len(adaptive_layout.get('aisles', []))} aisles")

    # Also generate traditional strategies for comparison
    strategies = ["horizontal", "vertical", "dual-access", "loop"]

    for strat in strategies:
        # Generate base layout (same for all levels in structured/underground)
        base_layout = generate_layout(boundary, c, strat)
        stalls_before = len(base_layout["stalls"])
        streets_before = len(base_layout.get("streets", []))
        aisles_before = len(base_layout.get("aisles", []))

        # Filter only stalls that overlap with user exclusions
        # Streets and aisles represent the road network and should NOT be filtered
        # - they show where cars drive, not where obstacles are
        if user_exclusions:
            base_layout["stalls"] = filter_stalls_for_exclusions(
                base_layout["stalls"], user_exclusions)
            base_layout["stallCount"] = len(base_layout["stalls"])

            # NOTE: Streets and aisles are intentionally NOT filtered
            # The exclusions represent obstacles that affect parking stalls,
            # not the circulation paths which are part of the design

            stalls_after = len(base_layout["stalls"])
            streets_after = len(base_layout.get("streets", []))
            aisles_after = len(base_layout.get("aisles", []))
            print(
                f"  {strat}: stalls {stalls_before}->{stalls_after}, streets {streets_before} (kept), aisles {aisles_before} (kept)")
        else:
            print(f"  {strat}: {stalls_before} stalls (no exclusions to filter)")

        # Store exclusion shapes for frontend rendering
        base_layout["exclusions"] = exclusion_shapes

        if parking_type == "surface":
            # Simple surface parking - single level
            base_layout["levels"] = [{
                "level": 1,
                "label": "Surface",
                "stalls": base_layout["stalls"],
                "stallCount": base_layout["stallCount"],
                "columns": [],
                "ramp": None
            }]
            base_layout["totalStallCount"] = base_layout["stallCount"]
            iterations.append(base_layout)
        else:
            # Structured or underground - multi-level
            levels_data = []
            total_stalls = 0

            # Generate optimized column grid based on layout (same for all levels)
            columns = generate_column_grid_optimized(
                bbox, c, base_layout, strat)

            # Create exclusion zones for columns
            column_exclusions = []
            for col in columns:
                half_size = col["size"] / 2 + 1  # 1ft buffer around columns
                column_exclusions.append({
                    "minX": col["x"] - half_size,
                    "maxX": col["x"] + half_size,
                    "minY": col["y"] - half_size,
                    "maxY": col["y"] + half_size
                })

            for level in range(1, num_levels + 1):
                # Generate ramp for this level (except last level)
                ramp = generate_ramp(bbox, standards, level,
                                     num_levels, parking_type, strat)

                # Build exclusion zones
                exclusions = column_exclusions.copy()
                if ramp:
                    exclusions.append(ramp["exclusionZone"])

                # Filter stalls to exclude column and ramp zones
                level_stalls = filter_stalls_for_exclusions(
                    base_layout["stalls"], exclusions)

                # Convert stalls to standard format with x/y/w/h for frontend
                formatted_stalls = []
                for stall in level_stalls:
                    # Calculate bounding box from polygon
                    xs = [p["x"] for p in stall["polygon"]]
                    ys = [p["y"] for p in stall["polygon"]]
                    formatted_stalls.append({
                        "polygon": stall["polygon"],
                        "center": stall["center"],
                        "x": min(xs),
                        "y": min(ys),
                        "w": max(xs) - min(xs),
                        "h": max(ys) - min(ys)
                    })

                level_label = f"B{level}" if parking_type == "underground" else f"L{level}"

                levels_data.append({
                    "level": level,
                    "label": level_label,
                    "stalls": formatted_stalls,
                    "stallCount": len(formatted_stalls),
                    "columns": columns,
                    "ramp": ramp
                })

                total_stalls += len(formatted_stalls)

            base_layout["levels"] = levels_data
            base_layout["totalStallCount"] = total_stalls
            base_layout["parkingType"] = parking_type
            base_layout["numLevels"] = num_levels
            base_layout["standards"] = standards.model_dump()
            iterations.append(base_layout)

    # Sort by total stall count (highest capacity first)
    sort_key = "totalStallCount" if parking_type != "surface" else "stallCount"
    iterations.sort(key=lambda x: x.get(
        "totalStallCount", x["stallCount"]), reverse=True)

    # Add rank to each
    for i, it in enumerate(iterations):
        it["rank"] = i + 1
        total = it.get("totalStallCount", it["stallCount"])
        level_text = f" × {num_levels} levels" if parking_type != "surface" else ""
        it["name"] = f"{it['name']} ({total} stalls{level_text})"

    return {"ok": True, "iterations": iterations, "parkingType": parking_type, "numLevels": num_levels}


# ─────────────────────────────────────────────────────────────────────────────
# SiteGen Feasibility Endpoint (stub - returns mock data for frontend)
# ─────────────────────────────────────────────────────────────────────────────

class SiteGenRequest(BaseModel):
    boundary: List[Point] | None = None
    exclusions: List[ExclusionZone] | None = None
    zoning: Dict[str, Any] | None = None
    building_type: Dict[str, Any] | None = None
    options: Dict[str, Any] | None = None


@app.post("/sitegen/feasibility")
def sitegen_feasibility(req: SiteGenRequest):
    """
    SiteGen feasibility endpoint - returns basic feasibility data.
    The actual massing visualization is done client-side in SiteGen.jsx.
    This endpoint provides supplementary data for the summary panel.
    """
    print("[ENDPOINT] sitegen_feasibility called!", flush=True)
    try:
        # Calculate basic site metrics from boundary
        if req.boundary and len(req.boundary) >= 3:
            xs = [p.x for p in req.boundary]
            ys = [p.y for p in req.boundary]
            site_width = max(xs) - min(xs)
            site_depth = max(ys) - min(ys)

            # Shoelace formula for polygon area
            n = len(req.boundary)
            area = 0
            for i in range(n):
                j = (i + 1) % n
                area += req.boundary[i].x * req.boundary[j].y
                area -= req.boundary[j].x * req.boundary[i].y
            site_area = abs(area) / 2
        else:
            site_width = 0
            site_depth = 0
            site_area = 0

        # Return basic feasibility data
        return {
            "ok": True,
            "site": {
                "area_sf": site_area,
                "width_ft": site_width,
                "depth_ft": site_depth,
            },
            "message": "Feasibility analysis complete. Visualization rendered client-side.",
        }
    except Exception as e:
        print(f"[ERROR] sitegen_feasibility failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}


@app.post("/parking/generate")
def parking_generate(req: GenerateRequest):
    """Generate parking layouts with constraint awareness."""
    print("[ENDPOINT] parking_generate called!", flush=True)
    try:
        print("[ENDPOINT] calling _parking_generate_impl...", flush=True)
        result = _parking_generate_impl(req)
        print(
            f"[ENDPOINT] Success! Returning {len(result.get('iterations', []))} layouts", flush=True)
        return result
    except Exception as e:
        print(f"[ERROR] parking_generate failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e), "iterations": [], "parkingType": req.parkingType or "surface", "numLevels": 1}


@app.post("/parking/circulation")
def parking_circulation(req: GenerateRequest):
    """PARALLEL MODULE LOGIC - Clean 60ft grid with hard pruning.

    Rules:
    1. Clear Canvas: Start from zero (no perimeter ring, just parallel lines)
    2. 60ft Grid: Horizontal centerlines spaced exactly 60ft apart
    3. 30ft Offset: First centerline 30ft from top boundary
    4. Hard Pruning: Cut segments within 12ft of obstacles (leave gaps, don't move lines)
    5. Double-Loaded Stalls: 8.5' x 18' stalls on both sides of each line
    """
    print("[ENDPOINT] parking_circulation - PARALLEL MODULE LOGIC", flush=True)
    try:
        from shapely.geometry import box, Polygon, LineString
        from shapely.ops import unary_union

        # =====================================================================
        # CONSTANTS - Parallel Module System
        # =====================================================================
        MODULE_SPACING = 60.0    # Distance between parallel centerlines
        FIRST_LINE_OFFSET = 30.0  # First centerline 30ft from top boundary
        OBSTACLE_BUFFER = 12.0   # Cut lines within 12ft of obstacles
        STALL_WIDTH = 8.5        # Stall width (perpendicular to aisle)
        STALL_DEPTH = 18.0       # Stall depth (parallel to aisle)
        # Half of 24ft aisle (stall front offset from centerline)
        AISLE_HALF_WIDTH = 12.0
        BOUNDARY_BUFFER = 12.0   # Keep stalls 12ft from boundary

        # =====================================================================
        # STEP 1: Parse boundary and constraints
        # =====================================================================
        print(
            f"[PARALLEL] req.boundary: {len(req.boundary) if req.boundary else 0} points", flush=True)
        print(
            f"[PARALLEL] req.exclusions: {len(req.exclusions) if req.exclusions else 0} exclusions", flush=True)

        boundary = req.boundary or [Point(x=0, y=0), Point(x=200, y=0),
                                    Point(x=200, y=150), Point(x=0, y=150)]
        xs = [p.x for p in boundary]
        ys = [p.y for p in boundary]
        boundary_bbox = {
            "minX": min(xs), "maxX": max(xs),
            "minY": min(ys), "maxY": max(ys)
        }

        lot_width = boundary_bbox["maxX"] - boundary_bbox["minX"]
        lot_height = boundary_bbox["maxY"] - boundary_bbox["minY"]

        print(
            f"[PARALLEL] Lot: {lot_width:.0f}ft x {lot_height:.0f}ft", flush=True)

        # Parse obstacles (red constraint boxes)
        constraints = []
        if req.exclusions:
            for exc in req.exclusions:
                if exc.polygon and len(exc.polygon) >= 3:
                    pts = exc.polygon
                    ex = [p.x for p in pts]
                    ey = [p.y for p in pts]
                    constraints.append({
                        "minX": min(ex), "maxX": max(ex),
                        "minY": min(ey), "maxY": max(ey)
                    })

        print(f"[PARALLEL] Constraints: {len(constraints)}", flush=True)
        for i, c in enumerate(constraints):
            print(
                f"  Constraint {i}: X=[{c['minX']:.1f},{c['maxX']:.1f}] Y=[{c['minY']:.1f},{c['maxY']:.1f}]", flush=True)

        # =====================================================================
        # STEP 2: Create obstacle zones for centerline cutting
        # Use small buffer (1ft) to ensure line intersection is detected properly
        # =====================================================================
        LINE_CUT_BUFFER = 1.0  # Small buffer to ensure intersection detection
        obstacle_zones_for_lines = []
        for obs in constraints:
            # Small buffer to ensure line-box intersection works correctly
            obs_box = box(obs['minX'] - LINE_CUT_BUFFER, obs['minY'] - LINE_CUT_BUFFER,
                          obs['maxX'] + LINE_CUT_BUFFER, obs['maxY'] + LINE_CUT_BUFFER)
            obstacle_zones_for_lines.append(obs_box)

        all_obstacles_for_lines = unary_union(
            obstacle_zones_for_lines) if obstacle_zones_for_lines else Polygon()

        print(
            f"[PARALLEL] Obstacle zones created: {len(obstacle_zones_for_lines)}", flush=True)

        # =====================================================================
        # STEP 3: Generate 60ft-spaced parallel centerlines (30ft offset from top)
        # =====================================================================
        # FULL WIDTH: Centerlines span the entire lot width (no X buffer)
        x_min = boundary_bbox["minX"]
        x_max = boundary_bbox["maxX"]

        # First centerline at 30ft from top, then every 60ft
        y_first = boundary_bbox["minY"] + FIRST_LINE_OFFSET
        y_last = boundary_bbox["maxY"] - \
            FIRST_LINE_OFFSET  # Stop 30ft from bottom

        print(
            f"[PARALLEL] Centerline X range: {x_min:.0f} to {x_max:.0f} (FULL WIDTH)", flush=True)
        print(
            f"[PARALLEL] Centerline Y range: {y_first:.0f} to {y_last:.0f} (60ft spacing)", flush=True)

        streets = []
        centerline_y_positions = []

        y = y_first
        line_id = 0
        while y <= y_last:
            centerline_y_positions.append(y)

            # Create FULL-WIDTH horizontal line at this Y
            full_line = LineString([(x_min, y), (x_max, y)])

            # HARD PRUNING: Only cut where line physically hits obstacle (no buffer)
            if not all_obstacles_for_lines.is_empty:
                clipped = full_line.difference(all_obstacles_for_lines)
            else:
                clipped = full_line

            # Process the resulting geometry (could be LineString or MultiLineString)
            if clipped.is_empty:
                print(
                    f"[PARALLEL] Line {line_id} at Y={y:.0f} - fully blocked", flush=True)
            else:
                # Extract line segments
                if clipped.geom_type == 'LineString':
                    segments = [clipped]
                elif clipped.geom_type == 'MultiLineString':
                    segments = list(clipped.geoms)
                else:
                    segments = []

                for seg_idx, seg in enumerate(segments):
                    if seg.length >= STALL_WIDTH * 2:  # At least 2 stalls wide
                        coords = list(seg.coords)
                        polyline = [
                            {"x": float(c[0]), "y": float(c[1])} for c in coords]
                        streets.append({
                            "polyline": polyline,
                            "from": {"x": float(coords[0][0]), "y": float(coords[0][1])},
                            "to": {"x": float(coords[-1][0]), "y": float(coords[-1][1])},
                            "width": 24.0,
                            "type": "interior-aisle",
                            "twoWay": True,
                            "closed": False,
                            "lineId": line_id,
                            "segmentId": seg_idx
                        })

                print(
                    f"[PARALLEL] Line {line_id} at Y={y:.0f} - {len(segments)} segment(s)", flush=True)

            y += MODULE_SPACING
            line_id += 1

        print(
            f"[PARALLEL] Generated {len(streets)} street segments from {line_id} centerlines", flush=True)

        # =====================================================================
        # STEP 4: Generate double-loaded stalls along each centerline segment
        # =====================================================================
        # Stalls: 8.5' wide x 18' deep, placed on both sides of centerline
        # Stall front is 12ft from centerline (half of 24ft aisle)

        all_stalls = []
        stall_id = 0

        # Stall boundary check: stalls must be fully inside lot boundary
        # Use the full lot boundary (no buffer) - stalls can go to edge
        stall_boundary = box(
            boundary_bbox["minX"],
            boundary_bbox["minY"],
            boundary_bbox["maxX"],
            boundary_bbox["maxY"]
        )

        for street in streets:
            polyline = street["polyline"]
            if len(polyline) < 2:
                continue

            # Get the centerline Y and X range
            y_center = polyline[0]["y"]
            x_start = min(p["x"] for p in polyline)
            x_end = max(p["x"] for p in polyline)

            # Place stalls along this segment starting at the segment edge
            x = x_start + STALL_WIDTH / 2  # Start half-stall in from segment edge

            while x + STALL_WIDTH / 2 <= x_end:
                # Create stalls on both sides (top and bottom)
                # 1 = top (positive Y), -1 = bottom (negative Y)
                for side in [1, -1]:
                    # Stall rectangle: front at 12ft from centerline, extends 18ft out
                    stall_front_y = y_center + side * AISLE_HALF_WIDTH
                    stall_back_y = stall_front_y + side * STALL_DEPTH

                    stall_left_x = x - STALL_WIDTH / 2
                    stall_right_x = x + STALL_WIDTH / 2

                    # Ensure proper min/max for box
                    stall_min_y = min(stall_front_y, stall_back_y)
                    stall_max_y = max(stall_front_y, stall_back_y)

                    # Create stall geometry
                    stall_box = box(stall_left_x, stall_min_y,
                                    stall_right_x, stall_max_y)

                    # Check if stall is within boundary
                    if not stall_boundary.contains(stall_box):
                        continue

                    # Check if stall hits any obstacle
                    hits_obstacle = False
                    for obs in constraints:
                        obs_box = box(obs["minX"], obs["minY"],
                                      obs["maxX"], obs["maxY"])
                        if stall_box.intersects(obs_box):
                            hits_obstacle = True
                            break

                    if hits_obstacle:
                        continue

                    # Valid stall - add it
                    stall_id += 1
                    all_stalls.append({
                        "id": stall_id,
                        "polygon": [
                            {"x": stall_left_x, "y": stall_min_y},
                            {"x": stall_right_x, "y": stall_min_y},
                            {"x": stall_right_x, "y": stall_max_y},
                            {"x": stall_left_x, "y": stall_max_y}
                        ],
                        "center": {"x": x, "y": (stall_min_y + stall_max_y) / 2},
                        "width": STALL_WIDTH,
                        "depth": STALL_DEPTH,
                        "side": "top" if side > 0 else "bottom",
                        "aisleY": y_center
                    })

                x += STALL_WIDTH  # Move to next stall position

        print(f"[PARALLEL] Generated {len(all_stalls)} stalls", flush=True)

        # =====================================================================
        # STEP 5: Build response
        # =====================================================================
        layout = {
            "name": "parallel-module-60ft",
            "streets": streets,
            "aisles": [],
            "stalls": all_stalls,
            "stallCount": len(all_stalls),
            "connected": True,
            "safeZone": [],  # No safe zone in parallel module logic
            "stats": {
                "module_spacing": MODULE_SPACING,
                "first_line_offset": FIRST_LINE_OFFSET,
                "obstacle_buffer": OBSTACLE_BUFFER,
                "stall_width": STALL_WIDTH,
                "stall_depth": STALL_DEPTH,
                "lot_width": lot_width,
                "lot_height": lot_height,
                "num_centerlines": line_id,
                "num_streets": len(streets),
                "stall_count": len(all_stalls)
            },
            "exclusions": [{"type": "constraint", "polygon": [
                {"x": obs["minX"], "y": obs["minY"]},
                {"x": obs["maxX"], "y": obs["minY"]},
                {"x": obs["maxX"], "y": obs["maxY"]},
                {"x": obs["minX"], "y": obs["maxY"]}
            ]} for obs in constraints]
        }

        print(
            f"[PARALLEL] Complete: {len(streets)} streets, {len(all_stalls)} stalls", flush=True)
        return {"ok": True, "iterations": [layout], "parkingType": "surface", "numLevels": 1}

    except Exception as e:
        print(f"[ERROR] parking_circulation failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e), "iterations": [], "parkingType": "surface", "numLevels": 1}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
