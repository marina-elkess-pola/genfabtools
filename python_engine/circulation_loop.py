"""
Circulation Loop Generator v5 - Efficiency Optimization

SWEEP LINE ALGORITHM:
Test the layout at two primary orientations: 0° and 90°.
For each, 'sweep' the area with parallel lines spaced exactly 60 feet apart.
Calculate the total stall count for both and choose the orientation 
that yields the highest number.

PARKING MODULE GEOMETRY:
A standard parking module is 60 feet wide: 18' stall + 24' aisle + 18' stall

EFFICIENCY OPTIMIZATION ("Genius" Cost Function):
Optimize for the Stall-to-Aisle Ratio:
    Total Number of Stalls / Total Linear Feet of Centerline
If adding a new street segment decreases this ratio, the segment must be removed.

KEY PRINCIPLE: Maximize Efficiency
- Test both horizontal (0°) and vertical (90°) sweep directions
- Count potential double-loaded stalls for each orientation
- Choose the orientation with maximum stall yield
- Apply cost function to prune inefficient segments
"""

import math
from typing import List, Dict, Tuple, Any, Optional, Set
from shapely.geometry import Polygon, LineString, Point, box, MultiPolygon, GeometryCollection, MultiLineString
from shapely.ops import unary_union, linemerge
from shapely.validation import make_valid
import networkx as nx

# Constants - Parking Module Geometry
STALL_DEPTH = 18.0           # feet - parking stall depth
STALL_WIDTH = 9.0            # feet - parking stall width (for counting)
AISLE_WIDTH = 24.0           # feet - drive aisle width
HALF_AISLE = 12.0            # feet - half of drive aisle (centerline to stall)
MODULE_WIDTH = 60.0          # feet - 18' + 24' + 18' = full module
HALF_MODULE = 30.0           # feet - centerline to edge of module (18' + 12')

# Erosion/Buffer Constants
EROSION_BUFFER = 12.0        # feet - min distance from walls/obstacles
DOUBLE_LOAD_ZONE = 30.0      # feet - need 30ft on each side for double-loaded

# Spacing Constants
MIN_CENTERLINE_SPACING = 55.0  # feet - prune if closer than this
GRID_SNAP = 1.0              # feet - snap grid resolution
MIN_SEGMENT_LENGTH = 20.0    # feet - minimum segment length to keep
# feet - streets shorter than this are deleted (spur pruning)
MIN_STREET_LENGTH = 40.0


def create_eroded_legal_zone(boundary: Dict[str, float],
                             obstacles: List[Dict[str, float]],
                             erosion: float = EROSION_BUFFER,
                             verbose: bool = False) -> Polygon:
    """
    Create the LEGAL ZONE for centerlines using the correct method:

    Step 1: INSET the boundary by 12ft (shrink using negative buffer)
    Step 2: INFLATE each obstacle by 12ft (expand using positive buffer)
    Step 3: SUBTRACT inflated obstacles from inset boundary

    Any centerline placed inside this legal zone is GUARANTEED
    to be at least 12ft from any wall or obstacle.
    """
    # Step 1: Create boundary polygon and INSET by 12ft
    bnd = box(boundary["minX"], boundary["minY"],
              boundary["maxX"], boundary["maxY"])
    inset_boundary = bnd.buffer(-erosion, join_style=2)  # Shrink boundary

    if verbose:
        print(f"  [ZONE] Original boundary area: {bnd.area:.0f} sq ft")
        print(
            f"  [ZONE] After {erosion}ft inset: {inset_boundary.area:.0f} sq ft")

    # Step 2: INFLATE each obstacle by 12ft
    if obstacles:
        inflated_obs = []
        for obs in obstacles:
            obs_box = box(obs["minX"], obs["minY"], obs["maxX"], obs["maxY"])
            inflated = obs_box.buffer(erosion, join_style=2)  # Expand obstacle
            inflated_obs.append(inflated)
            if verbose:
                print(
                    f"  [ZONE] Obstacle inflated: {obs_box.area:.0f} -> {inflated.area:.0f} sq ft")

        # Union all inflated obstacles
        all_inflated = unary_union(inflated_obs)
        if not all_inflated.is_valid:
            all_inflated = make_valid(all_inflated)

        if verbose:
            print(
                f"  [ZONE] Total inflated obstacle area: {all_inflated.area:.0f} sq ft")

        # Step 3: SUBTRACT inflated obstacles from inset boundary
        legal_zone = inset_boundary.difference(all_inflated)
    else:
        legal_zone = inset_boundary

    if not legal_zone.is_valid:
        legal_zone = make_valid(legal_zone)

    # Handle MultiPolygon - return list of all pieces for complete coverage
    # We need to process ALL polygon pieces, not just the largest one
    if isinstance(legal_zone, MultiPolygon):
        # Return the MultiPolygon itself - callers will handle it
        if verbose:
            print(f"  [ZONE] MultiPolygon with {len(legal_zone.geoms)} pieces")
            total_area = sum(g.area for g in legal_zone.geoms)
            print(f"  [ZONE] LEGAL ZONE total area: {total_area:.0f} sq ft")
            print(f"  [ZONE] Bounds: {legal_zone.bounds}")
        return legal_zone
    elif isinstance(legal_zone, GeometryCollection):
        polys = [g for g in legal_zone.geoms if isinstance(g, Polygon)]
        if len(polys) > 1:
            legal_zone = MultiPolygon(polys)
            if verbose:
                print(
                    f"  [ZONE] GeometryCollection -> MultiPolygon with {len(polys)} pieces")
        elif polys:
            legal_zone = polys[0]
        else:
            legal_zone = Polygon()
    elif not isinstance(legal_zone, Polygon):
        legal_zone = Polygon()

    if verbose:
        if not legal_zone.is_empty:
            print(f"  [ZONE] LEGAL ZONE area: {legal_zone.area:.0f} sq ft")
            print(f"  [ZONE] Bounds: {legal_zone.bounds}")
        else:
            print(f"  [ZONE] WARNING: Legal zone is empty!")

    return legal_zone

    return legal_zone


def sweep_line_stall_count(legal_zone: Polygon,
                           orientation: str,
                           verbose: bool = False) -> Tuple[int, List[Tuple], float]:
    """
    Sweep the legal zone with parallel lines at 60ft spacing and count stalls.

    Args:
        legal_zone: The eroded polygon where centerlines can go
        orientation: 'horizontal' (0°) or 'vertical' (90°)
        verbose: Print debug info

    Returns:
        (stall_count, centerlines, total_length)

    Each centerline segment can have double-loaded parking (stalls on both sides).
    Stall count = (segment_length / STALL_WIDTH) * 2 for double-loaded
    """
    if legal_zone.is_empty:
        return 0, [], 0.0

    minX, minY, maxX, maxY = legal_zone.bounds

    centerlines = []
    total_stalls = 0
    total_length = 0.0

    if orientation == 'horizontal':
        # Sweep horizontally (lines at constant Y)
        # Start 30ft from bottom edge, then every 60ft
        y = minY + HALF_MODULE
        while y <= maxY - HALF_MODULE:
            line = LineString([(minX, y), (maxX, y)])
            clipped = line.intersection(legal_zone)

            if not clipped.is_empty:
                segments = []
                if isinstance(clipped, MultiLineString):
                    segments = list(clipped.geoms)
                elif isinstance(clipped, LineString):
                    segments = [clipped]
                elif isinstance(clipped, GeometryCollection):
                    segments = [
                        g for g in clipped.geoms if isinstance(g, LineString)]

                for seg in segments:
                    if seg.length >= MIN_SEGMENT_LENGTH:
                        coords = list(seg.coords)
                        p1 = (round(coords[0][0] / GRID_SNAP) * GRID_SNAP,
                              round(coords[0][1] / GRID_SNAP) * GRID_SNAP)
                        p2 = (round(coords[-1][0] / GRID_SNAP) * GRID_SNAP,
                              round(coords[-1][1] / GRID_SNAP) * GRID_SNAP)

                        seg_length = seg.length

                        # Check if double-loaded is possible (30ft clearance each side)
                        mid_x = (p1[0] + p2[0]) / 2
                        pt_above = Point(mid_x, y + HALF_MODULE - 1)
                        pt_below = Point(mid_x, y - HALF_MODULE + 1)

                        if legal_zone.contains(pt_above) and legal_zone.contains(pt_below):
                            # Double-loaded: stalls on both sides
                            stalls = int(seg_length / STALL_WIDTH) * 2
                        else:
                            # Single-loaded: stalls on one side only
                            stalls = int(seg_length / STALL_WIDTH)

                        centerlines.append((p1, p2, 'horizontal'))
                        total_stalls += stalls
                        total_length += seg_length

            y += MODULE_WIDTH

    else:  # vertical
        # Sweep vertically (lines at constant X)
        x = minX + HALF_MODULE
        while x <= maxX - HALF_MODULE:
            line = LineString([(x, minY), (x, maxY)])
            clipped = line.intersection(legal_zone)

            if not clipped.is_empty:
                segments = []
                if isinstance(clipped, MultiLineString):
                    segments = list(clipped.geoms)
                elif isinstance(clipped, LineString):
                    segments = [clipped]
                elif isinstance(clipped, GeometryCollection):
                    segments = [
                        g for g in clipped.geoms if isinstance(g, LineString)]

                for seg in segments:
                    if seg.length >= MIN_SEGMENT_LENGTH:
                        coords = list(seg.coords)
                        p1 = (round(coords[0][0] / GRID_SNAP) * GRID_SNAP,
                              round(coords[0][1] / GRID_SNAP) * GRID_SNAP)
                        p2 = (round(coords[-1][0] / GRID_SNAP) * GRID_SNAP,
                              round(coords[-1][1] / GRID_SNAP) * GRID_SNAP)

                        seg_length = seg.length

                        # Check if double-loaded is possible
                        mid_y = (p1[1] + p2[1]) / 2
                        pt_left = Point(x - HALF_MODULE + 1, mid_y)
                        pt_right = Point(x + HALF_MODULE - 1, mid_y)

                        if legal_zone.contains(pt_left) and legal_zone.contains(pt_right):
                            stalls = int(seg_length / STALL_WIDTH) * 2
                        else:
                            stalls = int(seg_length / STALL_WIDTH)

                        centerlines.append((p1, p2, 'vertical'))
                        total_stalls += stalls
                        total_length += seg_length

            x += MODULE_WIDTH

    if verbose:
        print(
            f"    [{orientation.upper()}] {len(centerlines)} lines, {total_stalls} stalls, {total_length:.0f}ft")

    return total_stalls, centerlines, total_length


def optimize_sweep_orientation(legal_zone: Polygon,
                               verbose: bool = False) -> Tuple[str, List[Tuple], List[Tuple], int]:
    """
    Test both 0° and 90° orientations and choose the one with maximum stalls.

    Returns:
        (best_orientation, primary_lines, cross_lines, stall_count)
    """
    if verbose:
        print("  [SWEEP] Testing orientations...")

    # Test horizontal sweep (0°)
    h_stalls, h_lines, h_length = sweep_line_stall_count(
        legal_zone, 'horizontal', verbose)

    # Test vertical sweep (90°)
    v_stalls, v_lines, v_length = sweep_line_stall_count(
        legal_zone, 'vertical', verbose)

    if verbose:
        print(f"  [SWEEP] Horizontal: {h_stalls} stalls in {h_length:.0f}ft")
        print(f"  [SWEEP] Vertical: {v_stalls} stalls in {v_length:.0f}ft")

    # Choose orientation with more stalls
    # If equal, choose the one with less centerline length (more efficient)
    if h_stalls > v_stalls:
        best = 'horizontal'
        primary = h_lines
        # Add vertical cross-aisles for connectivity
        _, cross, _ = sweep_line_stall_count(legal_zone, 'vertical', False)
    elif v_stalls > h_stalls:
        best = 'vertical'
        primary = v_lines
        _, cross, _ = sweep_line_stall_count(legal_zone, 'horizontal', False)
    else:
        # Equal stalls - choose shorter total length
        if h_length <= v_length:
            best = 'horizontal'
            primary = h_lines
            _, cross, _ = sweep_line_stall_count(legal_zone, 'vertical', False)
        else:
            best = 'vertical'
            primary = v_lines
            _, cross, _ = sweep_line_stall_count(
                legal_zone, 'horizontal', False)

    if verbose:
        print(
            f"  [SWEEP] WINNER: {best.upper()} with {max(h_stalls, v_stalls)} stalls")

    return best, primary, cross, max(h_stalls, v_stalls)


def create_perimeter_ring(legal_zone,
                          verbose: bool = False) -> List[Tuple]:
    """
    Create the perimeter ring road from the legal zone exterior AND interior holes.

    This is the PRIMARY circulation - orthogonal loops that:
    1. Trace around the outer boundary (exterior ring)
    2. Trace around each obstacle's buffer zone (interior holes)
    3. Handle MultiPolygon by processing ALL polygon pieces

    All segments are converted to strictly orthogonal (H or V only).
    """
    # Handle empty or None
    if legal_zone is None or legal_zone.is_empty:
        return []

    ring_edges = []

    def process_ring_coords(coords: list, check_polygon: Polygon = None) -> List[Tuple]:
        """Process a ring (exterior or interior) into orthogonal edges."""
        edges = []
        for i in range(len(coords) - 1):
            p1 = coords[i]
            p2 = coords[i + 1]

            dx = abs(p2[0] - p1[0])
            dy = abs(p2[1] - p1[1])

            # Snap to grid
            p1 = (round(p1[0] / GRID_SNAP) * GRID_SNAP,
                  round(p1[1] / GRID_SNAP) * GRID_SNAP)
            p2 = (round(p2[0] / GRID_SNAP) * GRID_SNAP,
                  round(p2[1] / GRID_SNAP) * GRID_SNAP)

            if dx < 0.5:
                # Vertical segment
                if abs(p2[1] - p1[1]) >= MIN_SEGMENT_LENGTH:
                    edges.append((p1, p2, 'vertical'))
            elif dy < 0.5:
                # Horizontal segment
                if abs(p2[0] - p1[0]) >= MIN_SEGMENT_LENGTH:
                    edges.append((p1, p2, 'horizontal'))
            else:
                # Diagonal - convert to Manhattan (H then V)
                corner = (p2[0], p1[1])
                corner = (round(corner[0] / GRID_SNAP) * GRID_SNAP,
                          round(corner[1] / GRID_SNAP) * GRID_SNAP)

                # Check if corner is inside or on the polygon
                corner_pt = Point(corner)
                poly_to_check = check_polygon if check_polygon else (
                    legal_zone if isinstance(legal_zone, Polygon) else legal_zone.geoms[0])
                if poly_to_check.contains(corner_pt) or poly_to_check.exterior.distance(corner_pt) < 1:
                    # H then V
                    if abs(corner[0] - p1[0]) >= MIN_SEGMENT_LENGTH:
                        edges.append((p1, corner, 'horizontal'))
                    if abs(p2[1] - corner[1]) >= MIN_SEGMENT_LENGTH:
                        edges.append((corner, p2, 'vertical'))
                else:
                    # V then H
                    corner = (p1[0], p2[1])
                    corner = (round(corner[0] / GRID_SNAP) * GRID_SNAP,
                              round(corner[1] / GRID_SNAP) * GRID_SNAP)
                    if abs(corner[1] - p1[1]) >= MIN_SEGMENT_LENGTH:
                        edges.append((p1, corner, 'vertical'))
                    if abs(p2[0] - corner[0]) >= MIN_SEGMENT_LENGTH:
                        edges.append((corner, p2, 'horizontal'))
        return edges

    def process_single_polygon(poly: Polygon, poly_idx: int = 0) -> List[Tuple]:
        """Process a single polygon's exterior and interior rings."""
        poly_edges = []

        # 1. Process EXTERIOR ring
        exterior = poly.exterior
        exterior_coords = list(exterior.coords)
        ext_edges = process_ring_coords(exterior_coords, poly)
        poly_edges.extend(ext_edges)

        if verbose:
            print(
                f"  [RING] Polygon {poly_idx+1}: {len(ext_edges)} exterior edges")

        # 2. Process INTERIOR rings (obstacle buffer zones)
        interior_count = 0
        for interior in poly.interiors:
            interior_coords = list(interior.coords)
            interior_edges = process_ring_coords(interior_coords, poly)
            poly_edges.extend(interior_edges)
            interior_count += 1
            if verbose:
                print(
                    f"  [RING] Polygon {poly_idx+1} interior #{interior_count}: {len(interior_edges)} edges")

        return poly_edges

    # Handle MultiPolygon vs Polygon
    if isinstance(legal_zone, MultiPolygon):
        for idx, poly in enumerate(legal_zone.geoms):
            if isinstance(poly, Polygon) and not poly.is_empty:
                ring_edges.extend(process_single_polygon(poly, idx))
    elif isinstance(legal_zone, Polygon):
        ring_edges.extend(process_single_polygon(legal_zone, 0))

    if verbose:
        print(f"  [RING] TOTAL: {len(ring_edges)} perimeter edges")

    return ring_edges


def find_double_loaded_corridors(legal_zone: Polygon,
                                 boundary: Dict[str, float],
                                 obstacles: List[Dict[str, float]],
                                 verbose: bool = False) -> Tuple[List, List]:
    """
    Find corridors where DOUBLE-LOADED aisles are possible.

    A double-loaded aisle needs 30ft clearance on EACH side of the centerline:
    - 18ft for parking stall
    - 12ft for half the drive aisle

    Returns lists of (y_position, x_start, x_end) for horizontal corridors
    and (x_position, y_start, y_end) for vertical corridors.
    """
    if legal_zone.is_empty:
        return [], []

    minX, minY, maxX, maxY = legal_zone.bounds
    width = maxX - minX
    height = maxY - minY

    # Create obstacle union for clearance checks
    obs_polys = []
    for obs in obstacles:
        obs_polys.append(
            box(obs["minX"], obs["minY"], obs["maxX"], obs["maxY"]))
    obs_union = unary_union(obs_polys) if obs_polys else Polygon()

    # Boundary box
    bnd = box(boundary["minX"], boundary["minY"],
              boundary["maxX"], boundary["maxY"])

    h_corridors = []  # (y, x_start, x_end, is_double_loaded)
    v_corridors = []  # (x, y_start, y_end, is_double_loaded)

    # For each potential horizontal centerline position
    # Check if there's 30ft clearance above AND below
    y = minY + HALF_MODULE
    while y <= maxY - HALF_MODULE:
        # Create test line
        line = LineString([(minX, y), (maxX, y)])
        clipped = line.intersection(legal_zone)

        if not clipped.is_empty:
            segments = []
            if isinstance(clipped, MultiLineString):
                segments = list(clipped.geoms)
            elif isinstance(clipped, LineString):
                segments = [clipped]

            for seg in segments:
                if seg.length >= MIN_SEGMENT_LENGTH:
                    coords = list(seg.coords)
                    x1, x2 = coords[0][0], coords[-1][0]

                    # Check if this segment has 30ft clearance on both sides
                    # by checking points along the segment
                    is_double = True
                    check_pts = [x1, (x1+x2)/2, x2]

                    for check_x in check_pts:
                        pt_above = Point(check_x, y + HALF_MODULE - 1)
                        pt_below = Point(check_x, y - HALF_MODULE + 1)

                        # Must be inside legal zone (12ft from obstacles already)
                        # AND not too close to boundary or obstacles
                        if not legal_zone.contains(pt_above) or not legal_zone.contains(pt_below):
                            is_double = False
                            break

                    if is_double and seg.length >= MODULE_WIDTH:
                        h_corridors.append((y, x1, x2, True))

        y += MODULE_WIDTH

    # Same for vertical corridors
    x = minX + HALF_MODULE
    while x <= maxX - HALF_MODULE:
        line = LineString([(x, minY), (x, maxY)])
        clipped = line.intersection(legal_zone)

        if not clipped.is_empty:
            segments = []
            if isinstance(clipped, MultiLineString):
                segments = list(clipped.geoms)
            elif isinstance(clipped, LineString):
                segments = [clipped]

            for seg in segments:
                if seg.length >= MIN_SEGMENT_LENGTH:
                    coords = list(seg.coords)
                    y1, y2 = coords[0][1], coords[-1][1]

                    is_double = True
                    check_pts = [y1, (y1+y2)/2, y2]

                    for check_y in check_pts:
                        pt_left = Point(x - HALF_MODULE + 1, check_y)
                        pt_right = Point(x + HALF_MODULE - 1, check_y)

                        if not legal_zone.contains(pt_left) or not legal_zone.contains(pt_right):
                            is_double = False
                            break

                    if is_double and seg.length >= MODULE_WIDTH:
                        v_corridors.append((x, y1, y2, True))

        x += MODULE_WIDTH

    if verbose:
        print(
            f"  [CORRIDORS] {len(h_corridors)} horizontal, {len(v_corridors)} vertical double-loaded")

    return h_corridors, v_corridors


def generate_optimized_centerlines(legal_zone: Polygon,
                                   boundary: Dict[str, float],
                                   obstacles: List[Dict[str, float]],
                                   verbose: bool = False) -> Tuple[List, List]:
    """
    Generate centerlines that MAXIMIZE double-loaded aisles.

    Priority:
    1. Place centerlines in the CENTER of 60ft-wide corridors
    2. Only add cross-aisles where needed for connectivity
    3. Minimize total centerline length
    """
    if legal_zone.is_empty:
        return [], []

    minX, minY, maxX, maxY = legal_zone.bounds
    width = maxX - minX
    height = maxY - minY

    h_lines = []
    v_lines = []

    # Determine primary direction (maximize double-loaded along longest dimension)
    if width >= height:
        primary = 'horizontal'
        primary_extent = width
        secondary_extent = height
    else:
        primary = 'vertical'
        primary_extent = height
        secondary_extent = width

    # Calculate optimal number of aisles
    # Each double-loaded aisle covers 60ft of width
    num_primary_aisles = max(1, int(secondary_extent / MODULE_WIDTH))

    if verbose:
        print(f"  [OPTIMIZE] Primary direction: {primary}")
        print(
            f"  [OPTIMIZE] Space for {num_primary_aisles} double-loaded aisles")

    if primary == 'horizontal':
        # Place horizontal centerlines for double-loaded aisles
        # Start 30ft from edge, then every 60ft
        spacing = secondary_extent / (num_primary_aisles + 1)
        if spacing < MODULE_WIDTH:
            spacing = MODULE_WIDTH

        y = minY + HALF_MODULE
        while y <= maxY - HALF_MODULE:
            line = LineString([(minX, y), (maxX, y)])
            clipped = line.intersection(legal_zone)

            if not clipped.is_empty:
                segments = []
                if isinstance(clipped, MultiLineString):
                    segments = list(clipped.geoms)
                elif isinstance(clipped, LineString):
                    segments = [clipped]
                elif isinstance(clipped, GeometryCollection):
                    segments = [
                        g for g in clipped.geoms if isinstance(g, LineString)]

                for seg in segments:
                    if seg.length >= MIN_SEGMENT_LENGTH:
                        coords = list(seg.coords)
                        p1 = (round(coords[0][0] / GRID_SNAP) * GRID_SNAP,
                              round(coords[0][1] / GRID_SNAP) * GRID_SNAP)
                        p2 = (round(coords[-1][0] / GRID_SNAP) * GRID_SNAP,
                              round(coords[-1][1] / GRID_SNAP) * GRID_SNAP)
                        h_lines.append((p1, p2, 'horizontal'))

            y += MODULE_WIDTH

        # Add vertical cross-aisles at module intervals
        x = minX + HALF_MODULE
        while x <= maxX - HALF_MODULE:
            line = LineString([(x, minY), (x, maxY)])
            clipped = line.intersection(legal_zone)

            if not clipped.is_empty:
                segments = []
                if isinstance(clipped, MultiLineString):
                    segments = list(clipped.geoms)
                elif isinstance(clipped, LineString):
                    segments = [clipped]
                elif isinstance(clipped, GeometryCollection):
                    segments = [
                        g for g in clipped.geoms if isinstance(g, LineString)]

                for seg in segments:
                    if seg.length >= MIN_SEGMENT_LENGTH:
                        coords = list(seg.coords)
                        p1 = (round(coords[0][0] / GRID_SNAP) * GRID_SNAP,
                              round(coords[0][1] / GRID_SNAP) * GRID_SNAP)
                        p2 = (round(coords[-1][0] / GRID_SNAP) * GRID_SNAP,
                              round(coords[-1][1] / GRID_SNAP) * GRID_SNAP)
                        v_lines.append((p1, p2, 'vertical'))

            x += MODULE_WIDTH

    else:  # primary == 'vertical'
        # Place vertical centerlines for double-loaded aisles
        x = minX + HALF_MODULE
        while x <= maxX - HALF_MODULE:
            line = LineString([(x, minY), (x, maxY)])
            clipped = line.intersection(legal_zone)

            if not clipped.is_empty:
                segments = []
                if isinstance(clipped, MultiLineString):
                    segments = list(clipped.geoms)
                elif isinstance(clipped, LineString):
                    segments = [clipped]
                elif isinstance(clipped, GeometryCollection):
                    segments = [
                        g for g in clipped.geoms if isinstance(g, LineString)]

                for seg in segments:
                    if seg.length >= MIN_SEGMENT_LENGTH:
                        coords = list(seg.coords)
                        p1 = (round(coords[0][0] / GRID_SNAP) * GRID_SNAP,
                              round(coords[0][1] / GRID_SNAP) * GRID_SNAP)
                        p2 = (round(coords[-1][0] / GRID_SNAP) * GRID_SNAP,
                              round(coords[-1][1] / GRID_SNAP) * GRID_SNAP)
                        v_lines.append((p1, p2, 'vertical'))

            x += MODULE_WIDTH

        # Add horizontal cross-aisles
        y = minY + HALF_MODULE
        while y <= maxY - HALF_MODULE:
            line = LineString([(minX, y), (maxX, y)])
            clipped = line.intersection(legal_zone)

            if not clipped.is_empty:
                segments = []
                if isinstance(clipped, MultiLineString):
                    segments = list(clipped.geoms)
                elif isinstance(clipped, LineString):
                    segments = [clipped]
                elif isinstance(clipped, GeometryCollection):
                    segments = [
                        g for g in clipped.geoms if isinstance(g, LineString)]

                for seg in segments:
                    if seg.length >= MIN_SEGMENT_LENGTH:
                        coords = list(seg.coords)
                        p1 = (round(coords[0][0] / GRID_SNAP) * GRID_SNAP,
                              round(coords[0][1] / GRID_SNAP) * GRID_SNAP)
                        p2 = (round(coords[-1][0] / GRID_SNAP) * GRID_SNAP,
                              round(coords[-1][1] / GRID_SNAP) * GRID_SNAP)
                        h_lines.append((p1, p2, 'horizontal'))

            y += MODULE_WIDTH

    if verbose:
        print(
            f"  [GRID] {len(h_lines)} H + {len(v_lines)} V centerlines (60ft module spacing)")

    return h_lines, v_lines


def generate_internal_grid(legal_zone: Polygon,
                           spacing: float = MODULE_WIDTH,
                           verbose: bool = False) -> Tuple[List, List]:
    """
    Generate internal cross-streets at 60ft spacing.

    Lines are clipped to the legal zone using intersection().
    This guarantees all segments are within the eroded polygon.
    """
    if legal_zone.is_empty:
        return [], []

    minX, minY, maxX, maxY = legal_zone.bounds

    h_lines = []  # Horizontal lines
    v_lines = []  # Vertical lines

    # Start from snapped positions
    start_y = math.ceil(minY / spacing) * spacing
    start_x = math.ceil(minX / spacing) * spacing

    # Generate horizontal lines at 60ft intervals
    y = start_y
    while y <= maxY:
        line = LineString([(minX, y), (maxX, y)])
        clipped = line.intersection(legal_zone)

        if not clipped.is_empty:
            segments = []
            if isinstance(clipped, MultiLineString):
                segments = list(clipped.geoms)
            elif isinstance(clipped, LineString):
                segments = [clipped]
            elif isinstance(clipped, GeometryCollection):
                segments = [
                    g for g in clipped.geoms if isinstance(g, LineString)]

            for seg in segments:
                if seg.length >= MIN_SEGMENT_LENGTH:
                    coords = list(seg.coords)
                    p1 = (round(coords[0][0] / GRID_SNAP) * GRID_SNAP,
                          round(coords[0][1] / GRID_SNAP) * GRID_SNAP)
                    p2 = (round(coords[-1][0] / GRID_SNAP) * GRID_SNAP,
                          round(coords[-1][1] / GRID_SNAP) * GRID_SNAP)
                    h_lines.append((p1, p2, 'horizontal'))

        y += spacing

    # Generate vertical lines at 60ft intervals
    x = start_x
    while x <= maxX:
        line = LineString([(x, minY), (x, maxY)])
        clipped = line.intersection(legal_zone)

        if not clipped.is_empty:
            segments = []
            if isinstance(clipped, MultiLineString):
                segments = list(clipped.geoms)
            elif isinstance(clipped, LineString):
                segments = [clipped]
            elif isinstance(clipped, GeometryCollection):
                segments = [
                    g for g in clipped.geoms if isinstance(g, LineString)]

            for seg in segments:
                if seg.length >= MIN_SEGMENT_LENGTH:
                    coords = list(seg.coords)
                    p1 = (round(coords[0][0] / GRID_SNAP) * GRID_SNAP,
                          round(coords[0][1] / GRID_SNAP) * GRID_SNAP)
                    p2 = (round(coords[-1][0] / GRID_SNAP) * GRID_SNAP,
                          round(coords[-1][1] / GRID_SNAP) * GRID_SNAP)
                    v_lines.append((p1, p2, 'vertical'))

        x += spacing

    if verbose:
        print(
            f"  [GRID] {len(h_lines)} horizontal + {len(v_lines)} vertical lines at {spacing}ft")

    return h_lines, v_lines


def prune_close_parallel_lines(h_lines: List[Tuple],
                               v_lines: List[Tuple],
                               min_spacing: float = MIN_CENTERLINE_SPACING,
                               verbose: bool = False) -> Tuple[List, List]:
    """
    Orthogonal pruning: if two parallel centerlines are closer than 40ft,
    delete the shorter one.
    """
    pruned_h = 0
    pruned_v = 0

    # Prune horizontal lines (same Y, check distance)
    h_by_y = {}
    for p1, p2, orient in h_lines:
        y = p1[1]
        length = abs(p2[0] - p1[0])
        if y not in h_by_y:
            h_by_y[y] = []
        h_by_y[y].append((p1, p2, orient, length))

    # For each Y, keep only one line (the longest)
    final_h = []
    y_values = sorted(h_by_y.keys())
    kept_ys = []

    for y in y_values:
        # Check if too close to any kept Y
        too_close = False
        for kept_y in kept_ys:
            if abs(y - kept_y) < min_spacing:
                too_close = True
                # Keep the longer one
                current_best = max(h_by_y[y], key=lambda x: x[3])
                kept_best = [line for line in final_h if line[0][1] == kept_y]
                if kept_best:
                    kept_length = kept_best[0][3] if len(kept_best[0]) > 3 else abs(
                        kept_best[0][1][0] - kept_best[0][0][0])
                    if current_best[3] > kept_length:
                        # Remove the kept one, add current
                        final_h = [
                            line for line in final_h if line[0][1] != kept_y]
                        kept_ys.remove(kept_y)
                        final_h.append(current_best[:3])
                        kept_ys.append(y)
                        pruned_h += 1
                    else:
                        pruned_h += 1
                break

        if not too_close:
            best = max(h_by_y[y], key=lambda x: x[3])
            final_h.append(best[:3])
            kept_ys.append(y)

    # Same for vertical lines
    v_by_x = {}
    for p1, p2, orient in v_lines:
        x = p1[0]
        length = abs(p2[1] - p1[1])
        if x not in v_by_x:
            v_by_x[x] = []
        v_by_x[x].append((p1, p2, orient, length))

    final_v = []
    x_values = sorted(v_by_x.keys())
    kept_xs = []

    for x in x_values:
        too_close = False
        for kept_x in kept_xs:
            if abs(x - kept_x) < min_spacing:
                too_close = True
                current_best = max(v_by_x[x], key=lambda x: x[3])
                kept_best = [line for line in final_v if line[0][0] == kept_x]
                if kept_best:
                    kept_length = kept_best[0][3] if len(kept_best[0]) > 3 else abs(
                        kept_best[0][1][1] - kept_best[0][0][1])
                    if current_best[3] > kept_length:
                        final_v = [
                            line for line in final_v if line[0][0] != kept_x]
                        kept_xs.remove(kept_x)
                        final_v.append(current_best[:3])
                        kept_xs.append(x)
                        pruned_v += 1
                    else:
                        pruned_v += 1
                break

        if not too_close:
            best = max(v_by_x[x], key=lambda x: x[3])
            final_v.append(best[:3])
            kept_xs.append(x)

    if verbose and (pruned_h > 0 or pruned_v > 0):
        print(
            f"  [PRUNE] Removed {pruned_h} H + {pruned_v} V lines (too close)")

    return final_h, final_v


def build_graph(ring_edges: List[Tuple],
                h_lines: List[Tuple],
                v_lines: List[Tuple],
                verbose: bool = False) -> nx.Graph:
    """
    Build NetworkX graph from ring road and grid lines.
    Find intersections and create edges.

    Ring edges are marked as 'perimeter' type to protect from pruning.
    """
    G = nx.Graph()

    # Collect all edges by orientation, tracking source
    all_h = []  # (p1, p2, is_perimeter)
    all_v = []

    # Ring edges are perimeter - protected from pruning
    for p1, p2, orient in ring_edges:
        if orient == 'horizontal':
            all_h.append((p1, p2, True))  # True = is_perimeter
        else:
            all_v.append((p1, p2, True))

    # Grid lines are internal - can be pruned
    for p1, p2, orient in h_lines:
        all_h.append((p1, p2, False))  # False = not perimeter

    for p1, p2, orient in v_lines:
        all_v.append((p1, p2, False))

    # Find all intersection points
    nodes = set()

    # Add all endpoints
    for p1, p2, _ in all_h + all_v:
        nodes.add(p1)
        nodes.add(p2)

    # Find H-V intersections
    for h_p1, h_p2, _ in all_h:
        y = h_p1[1]
        h_minX = min(h_p1[0], h_p2[0])
        h_maxX = max(h_p1[0], h_p2[0])

        for v_p1, v_p2, _ in all_v:
            x = v_p1[0]
            v_minY = min(v_p1[1], v_p2[1])
            v_maxY = max(v_p1[1], v_p2[1])

            if h_minX <= x <= h_maxX and v_minY <= y <= v_maxY:
                nodes.add((x, y))

    # Split lines at intersection points and add edges
    def split_and_add(p1, p2, is_horizontal, is_perimeter):
        pts = [p1, p2]

        for node in nodes:
            if is_horizontal:
                if abs(node[1] - p1[1]) < 0.5:
                    x_min = min(p1[0], p2[0])
                    x_max = max(p1[0], p2[0])
                    if x_min < node[0] < x_max:
                        pts.append(node)
            else:
                if abs(node[0] - p1[0]) < 0.5:
                    y_min = min(p1[1], p2[1])
                    y_max = max(p1[1], p2[1])
                    if y_min < node[1] < y_max:
                        pts.append(node)

        # Sort by coordinate
        if is_horizontal:
            pts.sort(key=lambda p: p[0])
        else:
            pts.sort(key=lambda p: p[1])

        # Add edges - mark perimeter edges as protected
        for i in range(len(pts) - 1):
            n1, n2 = pts[i], pts[i + 1]
            length = math.sqrt((n2[0] - n1[0])**2 + (n2[1] - n1[1])**2)
            if length > 1:
                G.add_node(n1, x=n1[0], y=n1[1])
                G.add_node(n2, x=n2[0], y=n2[1])
                orient = 'H' if is_horizontal else 'V'
                # Perimeter edges are protected from pruning
                G.add_edge(n1, n2, length=length, orientation=orient,
                           perimeter=is_perimeter)

    for p1, p2, is_perim in all_h:
        split_and_add(p1, p2, True, is_perim)

    for p1, p2, is_perim in all_v:
        split_and_add(p1, p2, False, is_perim)

    if verbose:
        print(
            f"  [GRAPH] {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    return G


def calculate_efficiency_ratio(G: nx.Graph, legal_zone: Polygon = None) -> Tuple[float, int, float]:
    """
    Calculate the "Genius" Cost Function: Stall-to-Aisle Ratio.

    Efficiency = Total Stalls / Total Linear Feet of Centerline

    Higher is better - more stalls per foot of aisle means more efficient use of space.

    Returns: (efficiency_ratio, total_stalls, total_centerline_feet)
    """
    total_centerline_ft = 0.0
    total_stalls = 0

    for n1, n2, data in G.edges(data=True):
        length = data.get('length', 0)
        total_centerline_ft += length

        # Calculate stalls this segment can support
        # Double-loaded aisle: stalls on both sides = length / STALL_WIDTH * 2
        # For simplicity, assume all internal aisles are double-loaded
        stalls_this_segment = int(length / STALL_WIDTH) * 2
        total_stalls += stalls_this_segment

    if total_centerline_ft > 0:
        efficiency = total_stalls / total_centerline_ft
    else:
        efficiency = 0.0

    return efficiency, total_stalls, total_centerline_ft


def optimize_efficiency(G: nx.Graph, min_length: float = MIN_STREET_LENGTH,
                        verbose: bool = False) -> nx.Graph:
    """
    EFFICIENCY OPTIMIZATION using the "Genius" Cost Function.

    Stall-to-Aisle Ratio = Total Stalls / Total Linear Feet of Centerline

    Algorithm:
    1. Calculate baseline efficiency ratio
    2. For each edge (prioritizing short dead-ends):
       - Temporarily remove the edge
       - Calculate new efficiency ratio
       - If new ratio >= old ratio, keep the removal (edge was inefficient)
       - Otherwise, restore the edge
    3. Repeat until no more improvements

    This ensures every remaining segment contributes positively to efficiency.
    """
    removed_count = 0
    iteration = 0
    max_iterations = 50  # Safety limit

    # Calculate baseline efficiency
    baseline_eff, baseline_stalls, baseline_ft = calculate_efficiency_ratio(G)

    if verbose:
        print(
            f"  [EFFICIENCY] Baseline: {baseline_stalls} stalls / {baseline_ft:.0f}ft = {baseline_eff:.4f} stalls/ft")

    while iteration < max_iterations:
        iteration += 1
        improved = False

        # Get all edges sorted by length (shortest first - most likely inefficient)
        edges = [(n1, n2, data.get('length', 0))
                 for n1, n2, data in G.edges(data=True)]
        edges.sort(key=lambda e: e[2])  # Sort by length ascending

        for n1, n2, length in edges:
            if not G.has_edge(n1, n2):
                continue

            # Only consider edges that are short OR dead-ends
            deg1 = G.degree(n1)
            deg2 = G.degree(n2)

            # Skip if this is the only edge (would disconnect graph)
            if deg1 == 1 and deg2 == 1:
                continue

            # Skip long edges that aren't dead-ends (structural)
            if length >= min_length and deg1 > 1 and deg2 > 1:
                continue

            # Temporarily remove edge
            edge_data = G.edges[n1, n2].copy()
            G.remove_edge(n1, n2)

            # Check if graph is still connected
            if G.degree(n1) == 0 or G.degree(n2) == 0 or not nx.is_connected(G):
                # Restore edge - removal would break connectivity
                G.add_edge(n1, n2, **edge_data)
                continue

            # Calculate new efficiency
            new_eff, new_stalls, new_ft = calculate_efficiency_ratio(G)

            # Keep removal if efficiency improved or stayed same
            if new_eff >= baseline_eff:
                removed_count += 1
                improved = True
                baseline_eff = new_eff
                baseline_stalls = new_stalls
                baseline_ft = new_ft
                if verbose:
                    print(
                        f"    [OPTIMIZE] Removed {length:.1f}ft segment: {new_stalls} stalls / {new_ft:.0f}ft = {new_eff:.4f} stalls/ft")
            else:
                # Restore edge - it was contributing to efficiency
                G.add_edge(n1, n2, **edge_data)

        if not improved:
            break

    # Clean up isolated nodes
    isolated = [n for n in G.nodes() if G.degree(n) == 0]
    for node in isolated:
        G.remove_node(node)

    if verbose:
        final_eff, final_stalls, final_ft = calculate_efficiency_ratio(G)
        print(
            f"  [EFFICIENCY] Final: {final_stalls} stalls / {final_ft:.0f}ft = {final_eff:.4f} stalls/ft")
        print(f"  [EFFICIENCY] Removed {removed_count} inefficient segments")

    return G


def prune_short_streets(G: nx.Graph, min_length: float = MIN_STREET_LENGTH,
                        verbose: bool = False) -> nx.Graph:
    """
    STREET PRUNING: Remove short spur streets (dead-ends < min_length).

    Short "spur" streets are stall-killers - they consume 24ft of width
    without adding enough stalls to justify their space.

    A dead-end parking row is more efficient than a short connecting street.

    IMPORTANT: 
    - Only remove edges where one endpoint is a dead-end (degree 1)
    - NEVER remove perimeter edges (they define the legal driving zone boundary)
    This preserves the main connectivity network.
    """
    removed_count = 0
    skipped_perimeter = 0
    iteration = 0
    max_iterations = 20  # Safety limit

    # Iteratively remove short dead-end spurs
    while iteration < max_iterations:
        iteration += 1
        edges_to_remove = []

        for n1, n2, data in G.edges(data=True):
            # NEVER prune perimeter edges - they define the legal zone boundary
            if data.get('perimeter', False):
                continue

            length = data.get('length', 0)
            if length < min_length:
                deg1 = G.degree(n1)
                deg2 = G.degree(n2)

                # ONLY remove if it's a dead-end spur (one end has degree 1)
                # This preserves structural connectivity
                if deg1 == 1 or deg2 == 1:
                    edges_to_remove.append((n1, n2, length))

        if not edges_to_remove:
            break  # No more short spurs to remove

        # Remove short dead-end edges
        for n1, n2, length in edges_to_remove:
            if G.has_edge(n1, n2):
                G.remove_edge(n1, n2)
                removed_count += 1
                if verbose:
                    print(
                        f"    [PRUNE] Removed short spur: {length:.1f}ft < {min_length}ft")

        # Clean up isolated nodes (degree 0)
        isolated = [n for n in G.nodes() if G.degree(n) == 0]
        for node in isolated:
            G.remove_node(node)

    if verbose:
        print(
            f"  [STREET PRUNE] Removed {removed_count} short spur streets (< {min_length}ft)")

    return G


def prune_dead_ends(G: nx.Graph, verbose: bool = False) -> nx.Graph:
    """
    Remove degree-1 nodes iteratively.

    IMPORTANT: Do NOT remove nodes that are endpoints of perimeter edges.
    Perimeter edges define the legal driving zone boundary.
    """
    removed = 0

    while True:
        dead_ends = []
        for n in G.nodes():
            if G.degree(n) == 1:
                # Check if this node's only edge is a perimeter edge
                edges = list(G.edges(n, data=True))
                if edges:
                    edge_data = edges[0][2]
                    if edge_data.get('perimeter', False):
                        # Don't remove - this is a perimeter edge endpoint
                        continue
                dead_ends.append(n)

        if not dead_ends:
            break
        for node in dead_ends:
            G.remove_node(node)
            removed += 1

    if verbose and removed > 0:
        print(f"  [PRUNE] Removed {removed} dead-end nodes")

    return G


def extract_largest_component(G: nx.Graph, verbose: bool = False) -> nx.Graph:
    """Get the largest connected component."""
    if G.number_of_nodes() == 0:
        return G

    if nx.number_connected_components(G) > 1:
        largest_cc = max(nx.connected_components(G), key=len)
        G = G.subgraph(largest_cc).copy()

    if verbose:
        print(
            f"  [COMPONENT] {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    return G


def trace_path(G: nx.Graph, boundary: Dict[str, float]) -> List[Tuple[float, float]]:
    """
    Trace edges in the LARGEST connected component only.

    Returns a continuous path through one component.
    Multiple components are handled by returning multiple streets.
    """
    if G.number_of_nodes() == 0:
        return []

    # Get largest connected component
    if nx.number_connected_components(G) > 1:
        largest_cc = max(nx.connected_components(G), key=len)
        G = G.subgraph(largest_cc).copy()

    visited_edges = set()

    def edge_key(n1, n2):
        return tuple(sorted([n1, n2]))

    def dfs(current, path):
        path.append(current)
        for neighbor in sorted(G.neighbors(current), key=lambda n: (n[0], n[1])):
            ek = edge_key(current, neighbor)
            if ek not in visited_edges:
                visited_edges.add(ek)
                dfs(neighbor, path)
                path.append(current)

    # Start from corner-most node
    start = min(G.nodes(), key=lambda n: n[0] + n[1])

    path = []
    dfs(start, path)

    # Remove consecutive duplicates
    if not path:
        return []

    cleaned = [path[0]]
    for p in path[1:]:
        if p != cleaned[-1]:
            cleaned.append(p)

    return cleaned


def trace_all_components(G: nx.Graph) -> List[List[Tuple[float, float]]]:
    """
    Trace edges in ALL connected components, returning separate paths.

    Returns a list of paths (one per component).
    """
    if G.number_of_nodes() == 0:
        return []

    all_paths = []

    for component in nx.connected_components(G):
        subgraph = G.subgraph(component).copy()
        if subgraph.number_of_nodes() == 0:
            continue

        visited_edges = set()

        def edge_key(n1, n2):
            return tuple(sorted([n1, n2]))

        def dfs(current, path):
            path.append(current)
            for neighbor in sorted(subgraph.neighbors(current), key=lambda n: (n[0], n[1])):
                ek = edge_key(current, neighbor)
                if ek not in visited_edges:
                    visited_edges.add(ek)
                    dfs(neighbor, path)
                    path.append(current)

        # Start from corner-most node in this component
        start = min(subgraph.nodes(), key=lambda n: n[0] + n[1])

        component_path = []
        dfs(start, component_path)

        if component_path:
            # Remove consecutive duplicates
            cleaned = [component_path[0]]
            for p in component_path[1:]:
                if p != cleaned[-1]:
                    cleaned.append(p)
            if len(cleaned) >= 2:
                all_paths.append(cleaned)

    return all_paths


def generate_circulation_loop(boundary: Dict[str, float],
                              obstacles: List[Dict[str, float]],
                              street_width: float = AISLE_WIDTH,
                              verbose: bool = False) -> Dict[str, Any]:
    """
    Generate orthogonal circulation using SWEEP LINE OPTIMIZATION.

    Algorithm:
    1. Erode boundary by 12ft to create legal zone
    2. Test BOTH 0° and 90° orientations with 60ft-spaced sweep lines
    3. Calculate stall count for each orientation
    4. Choose the orientation with MAXIMUM stalls
    5. Add cross-aisles for connectivity
    6. Build connected graph and trace path

    Module: 18' stall + 24' aisle + 18' stall = 60ft
    """
    log = print if verbose else lambda x: None

    log("=" * 60)
    log("SWEEP LINE OPTIMIZER")
    log("=" * 60)
    log(f"Boundary: {boundary['maxX']-boundary['minX']:.0f} x {boundary['maxY']-boundary['minY']:.0f} ft")
    log(f"Obstacles: {len(obstacles)}")
    log(f"Module width: {MODULE_WIDTH} ft (18' + 24' + 18')")
    log(f"Stall width: {STALL_WIDTH} ft")
    log(f"Erosion buffer: {EROSION_BUFFER} ft")

    # Step 1: Create eroded legal zone (12ft from all walls/obstacles)
    log("\n[STEP 1] Creating eroded legal zone (12ft from walls)...")
    legal_zone = create_eroded_legal_zone(
        boundary, obstacles, EROSION_BUFFER, verbose)

    if legal_zone.is_empty:
        log("ERROR: No legal zone created!")
        return {"streets": [], "connected": False}

    # Step 2: Create perimeter ring ONLY (no internal grid)
    # This ensures all centerlines stay on the Safe Zone boundary
    log("\n[STEP 2] Creating PERIMETER-ONLY circulation (Safe Zone boundary)...")
    ring_edges = create_perimeter_ring(legal_zone, verbose)

    # NO internal grid lines - only perimeter
    h_lines = []
    v_lines = []
    best_orientation = 'perimeter'

    # Step 3: Build graph from perimeter ONLY
    log("\n[STEP 3] Building graph from perimeter edges...")
    G = build_graph(ring_edges, h_lines, v_lines, verbose)

    if G.number_of_nodes() == 0:
        log("ERROR: No graph nodes!")
        return {"streets": [], "connected": False}

    # Step 4: Prune dead ends
    log("\n[STEP 4] Pruning dead ends...")
    G = prune_dead_ends(G, verbose)

    # Step 5: Check connected components
    log("\n[STEP 5] Checking connected components...")
    num_components = nx.number_connected_components(G)
    log(f"  [COMPONENTS] {num_components} connected component(s), {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # Step 6: Trace ALL components as separate paths
    log("\n[STEP 6] Tracing perimeter paths for all components...")
    all_paths = trace_all_components(G)

    # Use the longest path as the main result
    if all_paths:
        path = max(all_paths, key=len)
    else:
        path = []

    log(f"  [PATHS] {len(all_paths)} separate paths traced")

    # Calculate final efficiency
    final_eff, final_stalls, final_ft = calculate_efficiency_ratio(G)

    total_points = sum(len(p) for p in all_paths)
    log(f"\n[RESULT] {total_points} total points across {len(all_paths)} paths")
    log(f"[RESULT] Optimal orientation: {best_orientation}")
    log(f"[RESULT] Final stalls: {final_stalls}")
    log(f"[RESULT] Total centerline: {final_ft:.0f}ft")
    log(f"[RESULT] Efficiency: {final_eff:.4f} stalls/ft")

    # Verify orthogonality across all paths
    diagonals = 0
    for p in all_paths:
        for i in range(len(p) - 1):
            dx = abs(p[i+1][0] - p[i][0])
            dy = abs(p[i+1][1] - p[i][1])
            if dx > 0.5 and dy > 0.5:
                diagonals += 1
    log(f"[VERIFY] Diagonal segments: {diagonals} (should be 0)")

    # Package result - create separate street for each path
    streets = []
    for idx, p in enumerate(all_paths):
        if len(p) >= 2:
            streets.append({
                "id": f"circulation-{idx}",
                "polyline": p,
                "width": street_width,
                "type": "circulation",
                "twoWay": True
            })

    return {
        "streets": streets,
        "loop": path,  # Main path for backwards compatibility
        "connected": len(path) > 2,
        "num_edges": G.number_of_edges(),
        "num_paths": len(all_paths),
        "topology": "ring-road",
        "orthogonal": diagonals == 0,
        "orientation": best_orientation,
        "stall_count": final_stalls,
        "centerline_feet": final_ft,
        "efficiency_ratio": final_eff
    }


# For backwards compatibility with app.py
def generate_circulation_from_bbox(boundary, obstacles, street_width=24, verbose=False):
    """Wrapper for API compatibility."""
    return generate_circulation_loop(boundary, obstacles, street_width, verbose)


# =============================================================================
# TEST
# =============================================================================
if __name__ == "__main__":
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches

    print("Testing Polygon Erosion Circulation Generator\n")

    boundary = {"minX": 0, "maxX": 200, "minY": 0, "maxY": 150}
    obstacles = [
        {"minX": 20, "maxX": 50, "minY": 20, "maxY": 50},
        {"minX": 150, "maxX": 180, "minY": 20, "maxY": 50},
        {"minX": 85, "maxX": 115, "minY": 60, "maxY": 90},
        {"minX": 20, "maxX": 50, "minY": 100, "maxY": 130},
        {"minX": 150, "maxX": 180, "minY": 100, "maxY": 130},
    ]

    result = generate_circulation_loop(boundary, obstacles, verbose=True)

    # Visualization
    fig, ax = plt.subplots(figsize=(14, 10))

    # Boundary
    ax.add_patch(patches.Rectangle(
        (0, 0), 200, 150, fill=False, edgecolor='navy', linewidth=3
    ))

    # Legal zone (eroded polygon)
    legal_zone = create_eroded_legal_zone(boundary, obstacles, EROSION_BUFFER)
    if not legal_zone.is_empty:
        x, y = legal_zone.exterior.xy
        ax.fill(x, y, alpha=0.2, color='lightgreen',
                label='Legal Zone (12ft eroded)')
        ax.plot(x, y, 'g--', linewidth=1)

    # Obstacles
    for obs in obstacles:
        # Actual obstacle
        ax.add_patch(patches.Rectangle(
            (obs["minX"], obs["minY"]),
            obs["maxX"] - obs["minX"],
            obs["maxY"] - obs["minY"],
            fill=True, facecolor='salmon', edgecolor='red', linewidth=2
        ))

    # Circulation path
    if result.get("loop"):
        loop = result["loop"]
        xs = [p[0] for p in loop]
        ys = [p[1] for p in loop]
        ax.plot(xs, ys, 'orange', linewidth=4,
                label=f'Circulation ({len(loop)} pts)')
        ax.plot(xs[0], ys[0], 'go', markersize=12, label='Start')

    ax.set_xlim(-20, 220)
    ax.set_ylim(-20, 170)
    ax.set_aspect('equal')
    ax.set_title(
        'Polygon Erosion: Centerlines 12ft from all walls/obstacles', fontsize=14)
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('circulation_erosion.png', dpi=150)
    print("\nSaved: circulation_erosion.png")
    plt.show()
