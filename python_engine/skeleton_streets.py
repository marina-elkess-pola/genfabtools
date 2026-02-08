#!/usr/bin/env python3
"""
Centerline-Based Street Detection using Medial Axis (Voronoi Skeleton)

CORRECT APPROACH:
1. Create FREE SPACE polygon = boundary - all obstacles
2. Compute the MEDIAL AXIS (skeleton) of the free space
   - The medial axis is the set of points equidistant from two or more edges
   - This naturally creates ONE CONTINUOUS centerline flowing around obstacles
3. For each point on the skeleton, the distance to the nearest edge IS the clearance
4. Keep only skeleton segments where clearance >= half_street_width
5. Build a connected network graph from valid segments

Uses:
- Shapely: Polygon operations
- NetworkX: Graph connectivity and path analysis
- SciPy.spatial: Voronoi diagrams for medial axis computation
"""

from typing import List, Dict, Any, Tuple, Optional, Set
import math
import numpy as np

from shapely.geometry import (
    Polygon, MultiPolygon, LineString, MultiLineString,
    Point, box, GeometryCollection, MultiPoint
)
from shapely.ops import unary_union, linemerge, polygonize
from shapely.validation import make_valid
from scipy.spatial import Voronoi
import networkx as nx


def sample_polygon_boundary(polygon: Polygon,
                            resolution: float = 2.0) -> np.ndarray:
    """
    Sample points along the boundary of a polygon at regular intervals.

    Args:
        polygon: Shapely polygon
        resolution: Distance between sample points

    Returns:
        Numpy array of (x, y) points
    """
    points = []

    # Sample exterior
    exterior = polygon.exterior
    length = exterior.length
    num_points = max(int(length / resolution), 4)

    for i in range(num_points):
        d = (i / num_points) * length
        p = exterior.interpolate(d)
        points.append([p.x, p.y])

    # Sample interiors (holes = obstacles)
    for interior in polygon.interiors:
        length = interior.length
        num_points = max(int(length / resolution), 4)
        for i in range(num_points):
            d = (i / num_points) * length
            p = interior.interpolate(d)
            points.append([p.x, p.y])

    return np.array(points)


def compute_voronoi_skeleton(free_space: Polygon,
                             resolution: float = 2.0) -> List[Tuple[Tuple[float, float],
                                                                    Tuple[float,
                                                                          float],
                                                                    float]]:
    """
    Compute the Voronoi-based skeleton (medial axis) of the free space.

    The Voronoi diagram of boundary points gives us the medial axis.
    Each Voronoi edge inside the polygon is part of the skeleton.
    The distance from skeleton point to boundary IS the clearance.

    Args:
        free_space: The free space polygon
        resolution: Sampling resolution for boundary

    Returns:
        List of (point1, point2, min_clearance) tuples for skeleton edges
    """
    if free_space.is_empty:
        return []

    # Handle MultiPolygon
    if isinstance(free_space, MultiPolygon):
        all_edges = []
        for poly in free_space.geoms:
            all_edges.extend(compute_voronoi_skeleton(poly, resolution))
        return all_edges

    # Sample boundary points
    boundary_points = sample_polygon_boundary(free_space, resolution)

    if len(boundary_points) < 4:
        return []

    print(f"  [VORONOI] Sampled {len(boundary_points)} boundary points")

    # Compute Voronoi diagram
    try:
        vor = Voronoi(boundary_points)
    except Exception as e:
        print(f"  [VORONOI] Failed: {e}")
        return []

    print(
        f"  [VORONOI] Generated {len(vor.vertices)} vertices, {len(vor.ridge_vertices)} ridges")

    # Extract skeleton edges that are inside the free space
    skeleton_edges = []

    for ridge_idx, ridge_vertices in enumerate(vor.ridge_vertices):
        # Skip ridges that go to infinity
        if -1 in ridge_vertices:
            continue

        v1_idx, v2_idx = ridge_vertices
        v1 = vor.vertices[v1_idx]
        v2 = vor.vertices[v2_idx]

        p1 = Point(v1)
        p2 = Point(v2)

        # Check if both endpoints are inside the free space
        if not (free_space.contains(p1) and free_space.contains(p2)):
            continue

        # Check if the edge itself is inside
        edge = LineString([v1, v2])
        if not free_space.contains(edge):
            continue

        # Compute clearance (distance to boundary) at both endpoints
        # For polygon with holes, we need to check both exterior and interiors
        clearance1 = free_space.boundary.distance(p1)
        clearance2 = free_space.boundary.distance(p2)

        min_clearance = min(clearance1, clearance2)

        skeleton_edges.append((
            (v1[0], v1[1]),
            (v2[0], v2[1]),
            min_clearance
        ))

    print(
        f"  [VORONOI] {len(skeleton_edges)} skeleton edges inside free space")

    return skeleton_edges


def build_skeleton_graph(skeleton_edges: List[Tuple],
                         min_clearance: float = 12.0) -> nx.Graph:
    """
    Build a NetworkX graph from skeleton edges.

    Only includes edges with sufficient clearance.

    Args:
        skeleton_edges: List of (point1, point2, clearance) tuples
        min_clearance: Minimum clearance for valid street

    Returns:
        NetworkX graph of the skeleton
    """
    G = nx.Graph()

    # Round coordinates to avoid floating point issues
    def round_point(p):
        return (round(p[0], 2), round(p[1], 2))

    valid_count = 0
    for p1, p2, clearance in skeleton_edges:
        if clearance >= min_clearance:
            valid_count += 1
            rp1 = round_point(p1)
            rp2 = round_point(p2)

            # Add nodes with position
            G.add_node(rp1, x=p1[0], y=p1[1], clearance=clearance)
            G.add_node(rp2, x=p2[0], y=p2[1], clearance=clearance)

            # Add edge with length
            length = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
            G.add_edge(rp1, rp2, length=length, clearance=clearance)

    print(f"  [GRAPH] {valid_count} edges with clearance >= {min_clearance}ft")

    return G


def extract_street_polylines(G: nx.Graph,
                             min_length: float = 30.0) -> List[Dict]:
    """
    Extract AXIS-ALIGNED street segments from the skeleton graph.

    The Voronoi skeleton produces diagonal paths, but the frontend
    expects horizontal and vertical streets. This function:
    1. Traces paths through the skeleton
    2. Converts diagonal segments into H/V segments
    3. Groups and merges collinear segments

    Args:
        G: NetworkX graph of skeleton
        min_length: Minimum street length

    Returns:
        List of street dictionaries (all horizontal or vertical)
    """
    if G.number_of_nodes() == 0:
        return []

    # Collect all skeleton points
    all_points = []
    for node in G.nodes():
        x = G.nodes[node].get('x', node[0])
        y = G.nodes[node].get('y', node[1])
        clearance = G.nodes[node].get('clearance', 12)
        all_points.append((x, y, clearance))

    if not all_points:
        return []

    # Find bounds
    xs = [p[0] for p in all_points]
    ys = [p[1] for p in all_points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # Create a set of valid skeleton points for quick lookup
    # Round to grid to avoid floating point issues
    grid_size = 5.0
    valid_zones = set()
    for x, y, _ in all_points:
        gx = round(x / grid_size) * grid_size
        gy = round(y / grid_size) * grid_size
        valid_zones.add((gx, gy))

    def is_valid_position(x, y):
        """Check if a position is near a valid skeleton point."""
        gx = round(x / grid_size) * grid_size
        gy = round(y / grid_size) * grid_size
        # Check nearby grid cells
        for dx in [-grid_size, 0, grid_size]:
            for dy in [-grid_size, 0, grid_size]:
                if (gx + dx, gy + dy) in valid_zones:
                    return True
        return False

    streets = []

    # Generate HORIZONTAL streets at various Y positions
    y_step = 20.0  # Scan every 20 feet
    y = min_y
    while y <= max_y:
        # Find all valid X ranges at this Y
        x = min_x
        segment_start = None

        while x <= max_x:
            if is_valid_position(x, y):
                if segment_start is None:
                    segment_start = x
            else:
                if segment_start is not None:
                    # End of segment
                    length = x - segment_start
                    if length >= min_length:
                        streets.append({
                            "x1": segment_start, "y1": y,
                            "x2": x - grid_size, "y2": y,
                            "is_horizontal": True,
                            "length": length,
                            "clearance": 12.0,
                            "polyline": [(segment_start, y), (x - grid_size, y)]
                        })
                    segment_start = None
            x += grid_size

        # Close any open segment
        if segment_start is not None:
            length = max_x - segment_start
            if length >= min_length:
                streets.append({
                    "x1": segment_start, "y1": y,
                    "x2": max_x, "y2": y,
                    "is_horizontal": True,
                    "length": length,
                    "clearance": 12.0,
                    "polyline": [(segment_start, y), (max_x, y)]
                })

        y += y_step

    # Generate VERTICAL streets at various X positions
    x_step = 20.0
    x = min_x
    while x <= max_x:
        # Find all valid Y ranges at this X
        y = min_y
        segment_start = None

        while y <= max_y:
            if is_valid_position(x, y):
                if segment_start is None:
                    segment_start = y
            else:
                if segment_start is not None:
                    length = y - segment_start
                    if length >= min_length:
                        streets.append({
                            "x1": x, "y1": segment_start,
                            "x2": x, "y2": y - grid_size,
                            "is_horizontal": False,
                            "length": length,
                            "clearance": 12.0,
                            "polyline": [(x, segment_start), (x, y - grid_size)]
                        })
                    segment_start = None
            y += grid_size

        # Close any open segment
        if segment_start is not None:
            length = max_y - segment_start
            if length >= min_length:
                streets.append({
                    "x1": x, "y1": segment_start,
                    "x2": x, "y2": max_y,
                    "is_horizontal": False,
                    "length": length,
                    "clearance": 12.0,
                    "polyline": [(x, segment_start), (x, max_y)]
                })

        x += x_step

    # Merge nearby parallel streets
    streets = merge_parallel_streets(streets)

    return streets


def merge_parallel_streets(streets: List[Dict], tolerance: float = 15.0) -> List[Dict]:
    """Merge streets that are close and parallel."""
    if len(streets) <= 1:
        return streets

    merged = []
    used = set()

    for i, s1 in enumerate(streets):
        if i in used:
            continue

        group = [s1]
        used.add(i)

        for j, s2 in enumerate(streets):
            if j in used or j <= i:
                continue

            # Same orientation
            if s1["is_horizontal"] == s2["is_horizontal"]:
                if s1["is_horizontal"]:
                    # Check if Y values are close
                    if abs(s1["y1"] - s2["y1"]) < tolerance:
                        group.append(s2)
                        used.add(j)
                else:
                    # Check if X values are close
                    if abs(s1["x1"] - s2["x1"]) < tolerance:
                        group.append(s2)
                        used.add(j)

        # Merge the group
        if s1["is_horizontal"]:
            x1 = min(s["x1"] for s in group)
            x2 = max(s["x2"] for s in group)
            y = sum(s["y1"] for s in group) / len(group)
            merged.append({
                "x1": x1, "y1": y, "x2": x2, "y2": y,
                "is_horizontal": True,
                "length": x2 - x1,
                "clearance": 12.0,
                "polyline": [(x1, y), (x2, y)]
            })
        else:
            y1 = min(s["y1"] for s in group)
            y2 = max(s["y2"] for s in group)
            x = sum(s["x1"] for s in group) / len(group)
            merged.append({
                "x1": x, "y1": y1, "x2": x, "y2": y2,
                "is_horizontal": False,
                "length": y2 - y1,
                "clearance": 12.0,
                "polyline": [(x, y1), (x, y2)]
            })

    return merged


def create_free_space_with_obstacles(boundary: Dict[str, float],
                                     obstacles: List[Dict[str, float]]) -> Polygon:
    """
    Create free space polygon with obstacles as holes.

    This is the key insight: by making obstacles into holes,
    the Voronoi skeleton naturally flows AROUND them.

    Args:
        boundary: {minX, maxX, minY, maxY}
        obstacles: List of obstacle bounding boxes

    Returns:
        Polygon with holes for obstacles
    """
    from shapely.geometry import GeometryCollection

    # Create exterior boundary
    minX, maxX = boundary["minX"], boundary["maxX"]
    minY, maxY = boundary["minY"], boundary["maxY"]

    exterior = [(minX, minY), (maxX, minY), (maxX, maxY), (minX, maxY)]

    # Create holes for obstacles
    holes = []
    for obs in obstacles:
        hole = [
            (obs["minX"], obs["minY"]),
            (obs["maxX"], obs["minY"]),
            (obs["maxX"], obs["maxY"]),
            (obs["minX"], obs["maxY"])
        ]
        holes.append(hole)

    # Create polygon with holes
    if holes:
        free_space = Polygon(exterior, holes)
    else:
        free_space = Polygon(exterior)

    if not free_space.is_valid:
        free_space = make_valid(free_space)

    # Handle case where make_valid returns GeometryCollection or MultiPolygon
    if isinstance(free_space, GeometryCollection):
        # Extract the largest polygon from the collection
        polygons = [g for g in free_space.geoms if isinstance(g, Polygon)]
        if polygons:
            free_space = max(polygons, key=lambda p: p.area)
        else:
            # Fallback: create simple polygon without holes
            free_space = Polygon(exterior)
    elif isinstance(free_space, MultiPolygon):
        # Take the largest polygon
        free_space = max(free_space.geoms, key=lambda p: p.area)

    return free_space


def generate_streets_from_centerlines(boundary: Dict[str, float],
                                      obstacles: List[Dict[str, float]],
                                      street_width: float = 24.0,
                                      stall_length: float = 18.0,
                                      setback: float = 5.0,
                                      verbose: bool = False) -> Dict[str, Any]:
    """
    Generate streets using the medial axis (Voronoi skeleton) approach.

    This creates ONE CONTINUOUS centerline network that naturally flows
    around obstacles, with clearance checked at every point.

    The key concept:
    - Obstacles become HOLES in the free space polygon
    - The Voronoi skeleton of a polygon with holes creates paths that
      flow around those holes
    - Each skeleton point is equidistant from the nearest boundaries
    - That distance IS the clearance on both sides

    Args:
        boundary: {minX, maxX, minY, maxY}
        obstacles: List of obstacle bounding boxes
        street_width: Required street width (typically 24ft)

    Returns:
        Dictionary with streets, connectivity info
    """
    def log(msg):
        if verbose:
            print(msg)

    half_width = street_width / 2

    log(f"[SKELETON] Starting medial axis street detection...")
    log(f"[SKELETON] Boundary: {boundary['maxX']-boundary['minX']:.0f}x{boundary['maxY']-boundary['minY']:.0f} ft")
    log(f"[SKELETON] Obstacles: {len(obstacles)}")
    log(f"[SKELETON] Required clearance: {half_width:.0f}ft on each side")

    # Step 1: Create free space with obstacles as holes
    log(f"[SKELETON] Step 1: Creating free space with obstacle holes...")
    free_space = create_free_space_with_obstacles(boundary, obstacles)

    if free_space.is_empty:
        log(f"[SKELETON] ERROR: No free space!")
        return {"streets": [], "connected": False, "error": "No free space"}

    log(f"[SKELETON] Free space area: {free_space.area:.0f} sq ft")
    num_holes = len(list(free_space.interiors)) if hasattr(
        free_space, 'interiors') else 0
    log(f"[SKELETON] Number of holes: {num_holes}")

    # Step 2: Compute Voronoi skeleton
    log(f"[SKELETON] Step 2: Computing Voronoi skeleton...")
    skeleton_edges = compute_voronoi_skeleton(free_space, resolution=3.0)
    log(f"[SKELETON] Raw skeleton edges: {len(skeleton_edges)}")

    if not skeleton_edges:
        log(f"[SKELETON] WARNING: No skeleton edges found!")
        return {"streets": [], "connected": False, "error": "No skeleton"}

    # Step 3: Build graph with clearance filtering
    log(f"[SKELETON] Step 3: Filtering by clearance >= {half_width:.0f}ft...")
    G = build_skeleton_graph(skeleton_edges, min_clearance=half_width)
    log(f"[SKELETON] Valid nodes: {G.number_of_nodes()}")
    log(f"[SKELETON] Valid edges: {G.number_of_edges()}")

    # Step 4: Extract street paths
    log(f"[SKELETON] Step 4: Extracting street paths...")
    streets = extract_street_polylines(G, min_length=30.0)
    log(f"[SKELETON] Streets: {len(streets)}")

    # Step 5: Check connectivity
    if G.number_of_nodes() > 0:
        connected = nx.is_connected(G)
        num_components = nx.number_connected_components(G)
    else:
        connected = False
        num_components = 0

    log(f"[SKELETON] Connected: {connected} ({num_components} components)")

    return {
        "streets": streets,
        "connected": connected,
        "num_components": num_components,
        "skeleton_edges": len(skeleton_edges),
        "valid_nodes": G.number_of_nodes(),
        "valid_edges": G.number_of_edges()
    }


# Test
if __name__ == "__main__":
    print("=" * 60)
    print("Testing Voronoi skeleton-based street detection")
    print("=" * 60)

    boundary = {"minX": 0, "maxX": 200, "minY": 0, "maxY": 150}
    obstacles = [
        {"minX": 10, "maxX": 40, "minY": 10, "maxY": 35},
        {"minX": 160, "maxX": 190, "minY": 10, "maxY": 40},
        {"minX": 160, "maxX": 190, "minY": 110, "maxY": 140},
        {"minX": 90, "maxX": 110, "minY": 65, "maxY": 85},
    ]

    result = generate_streets_from_centerlines(
        boundary, obstacles, verbose=True)

    print(f"\n{'=' * 60}")
    print(f"RESULTS:")
    print(f"  Streets: {len(result['streets'])}")
    print(f"  Connected: {result['connected']}")
    print(f"  Components: {result.get('num_components', 'N/A')}")

    for i, s in enumerate(result['streets']):
        polyline_len = len(s.get('polyline', []))
        print(f"  {i+1}. ({s['x1']:.0f},{s['y1']:.0f}) -> ({s['x2']:.0f},{s['y2']:.0f}) "
              f"len={s['length']:.0f}ft, {polyline_len} points")
