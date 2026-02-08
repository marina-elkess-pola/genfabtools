#!/usr/bin/env python3
"""
TRUE Medial Axis Street Detection

This module generates ONE CONTINUOUS CENTERLINE that flows around obstacles.
The centerline is the medial axis (Voronoi skeleton) of the free space.

Algorithm:
1. Create FREE SPACE polygon = boundary with obstacles as holes
2. Compute MEDIAL AXIS (Voronoi skeleton) of free space
3. Each skeleton point is equidistant from nearest boundaries
4. That distance IS the clearance - keep segments where clearance >= half_street_width
5. Build connected graph and trace continuous paths

The output is POLYLINES following the actual skeleton, NOT axis-aligned segments.

Libraries:
- Shapely: Polygon geometry operations
- NetworkX: Graph connectivity and path tracing
- SciPy.spatial: Voronoi diagrams for medial axis
"""

from typing import List, Dict, Any, Tuple, Optional, Set
import math
import numpy as np

from shapely.geometry import (
    Polygon, MultiPolygon, LineString, Point, GeometryCollection
)
from shapely.ops import linemerge
from shapely.validation import make_valid
from scipy.spatial import Voronoi
import networkx as nx


def sample_polygon_boundary(polygon: Polygon, resolution: float = 2.0) -> np.ndarray:
    """
    Sample points along polygon boundary at regular intervals.

    Args:
        polygon: Shapely polygon (may have holes for obstacles)
        resolution: Distance between sample points

    Returns:
        Numpy array of (x, y) boundary sample points
    """
    points = []

    # Sample exterior ring
    exterior = polygon.exterior
    length = exterior.length
    num_points = max(int(length / resolution), 4)
    for i in range(num_points):
        d = (i / num_points) * length
        p = exterior.interpolate(d)
        points.append([p.x, p.y])

    # Sample interior rings (holes = obstacles)
    for interior in polygon.interiors:
        length = interior.length
        num_points = max(int(length / resolution), 4)
        for i in range(num_points):
            d = (i / num_points) * length
            p = interior.interpolate(d)
            points.append([p.x, p.y])

    return np.array(points)


def compute_voronoi_skeleton(free_space: Polygon,
                             resolution: float = 2.0,
                             verbose: bool = False) -> List[Tuple]:
    """
    Compute the Voronoi-based medial axis (skeleton) of the free space.

    The Voronoi diagram of boundary sample points creates the medial axis.
    Each Voronoi ridge inside the polygon is a skeleton segment.
    The distance from any skeleton point to boundary IS the clearance.

    Args:
        free_space: Polygon with holes (obstacles)
        resolution: Boundary sampling resolution
        verbose: Print debug info

    Returns:
        List of (point1, point2, clearance) skeleton edges
    """
    if free_space.is_empty:
        return []

    # Handle MultiPolygon - process largest
    if isinstance(free_space, MultiPolygon):
        free_space = max(free_space.geoms, key=lambda p: p.area)

    if isinstance(free_space, GeometryCollection):
        polygons = [g for g in free_space.geoms if isinstance(g, Polygon)]
        if polygons:
            free_space = max(polygons, key=lambda p: p.area)
        else:
            return []

    # Sample boundary points
    boundary_points = sample_polygon_boundary(free_space, resolution)

    if len(boundary_points) < 4:
        return []

    if verbose:
        print(f"  [VORONOI] Sampled {len(boundary_points)} boundary points")

    # Compute Voronoi diagram
    try:
        vor = Voronoi(boundary_points)
    except Exception as e:
        if verbose:
            print(f"  [VORONOI] Failed: {e}")
        return []

    if verbose:
        print(
            f"  [VORONOI] Generated {len(vor.vertices)} vertices, {len(vor.ridge_vertices)} ridges")

    # Extract skeleton edges inside free space
    skeleton_edges = []

    for ridge_vertices in vor.ridge_vertices:
        # Skip ridges going to infinity
        if -1 in ridge_vertices:
            continue

        v1_idx, v2_idx = ridge_vertices
        v1 = vor.vertices[v1_idx]
        v2 = vor.vertices[v2_idx]

        p1 = Point(v1)
        p2 = Point(v2)

        # Both endpoints must be inside free space
        if not (free_space.contains(p1) and free_space.contains(p2)):
            continue

        # Edge must be inside free space
        edge = LineString([v1, v2])
        if not free_space.contains(edge):
            continue

        # Compute clearance (distance to nearest boundary) at endpoints
        clearance1 = free_space.boundary.distance(p1)
        clearance2 = free_space.boundary.distance(p2)
        min_clearance = min(clearance1, clearance2)

        skeleton_edges.append((
            (v1[0], v1[1]),
            (v2[0], v2[1]),
            min_clearance
        ))

    if verbose:
        print(
            f"  [VORONOI] {len(skeleton_edges)} skeleton edges inside free space")

    return skeleton_edges


def build_skeleton_graph(skeleton_edges: List[Tuple],
                         min_clearance: float = 12.0,
                         verbose: bool = False) -> nx.Graph:
    """
    Build NetworkX graph from skeleton edges with clearance filtering.

    Only includes edges where clearance >= min_clearance on BOTH sides.

    Args:
        skeleton_edges: List of (point1, point2, clearance)
        min_clearance: Minimum required clearance (half_street_width)
        verbose: Print debug info

    Returns:
        NetworkX graph of valid skeleton
    """
    G = nx.Graph()

    def round_point(p):
        return (round(p[0], 2), round(p[1], 2))

    valid_count = 0
    for p1, p2, clearance in skeleton_edges:
        # Only keep edges with sufficient clearance on both sides
        if clearance >= min_clearance:
            valid_count += 1
            rp1 = round_point(p1)
            rp2 = round_point(p2)

            G.add_node(rp1, x=p1[0], y=p1[1], clearance=clearance)
            G.add_node(rp2, x=p2[0], y=p2[1], clearance=clearance)

            length = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
            G.add_edge(rp1, rp2, length=length, clearance=clearance)

    if verbose:
        print(
            f"  [GRAPH] {valid_count} edges with clearance >= {min_clearance}ft")
        print(
            f"  [GRAPH] {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    return G


def trace_single_continuous_centerline(G: nx.Graph,
                                       verbose: bool = False) -> List[Tuple[float, float]]:
    """
    Trace ONE SINGLE CONTINUOUS centerline through the entire skeleton.

    Uses DFS traversal that backtracks to visit ALL edges, creating
    a single path that covers the entire skeleton network.

    Args:
        G: Skeleton graph
        verbose: Print debug info

    Returns:
        Single polyline that traverses entire skeleton (with backtracking)
    """
    if G.number_of_nodes() == 0:
        return []

    # Find best starting point (prefer endpoint with lowest degree)
    endpoints = [n for n in G.nodes() if G.degree(n) == 1]
    if endpoints:
        start = endpoints[0]
    else:
        start = list(G.nodes())[0]

    path = []
    visited_edges = set()

    def edge_key(n1, n2):
        return tuple(sorted([n1, n2]))

    def get_coords(node):
        x = G.nodes[node].get('x', node[0])
        y = G.nodes[node].get('y', node[1])
        return (x, y)

    def dfs_traverse(current, came_from=None):
        """DFS that visits ALL edges, backtracking as needed."""
        path.append(get_coords(current))

        # Get all neighbors with unvisited edges
        neighbors = list(G.neighbors(current))

        for neighbor in neighbors:
            ek = edge_key(current, neighbor)
            if ek not in visited_edges:
                visited_edges.add(ek)
                dfs_traverse(neighbor, current)
                # Backtrack - add current again to show we came back
                path.append(get_coords(current))

    dfs_traverse(start)

    # Remove duplicate final point if we ended where we started
    if len(path) > 1 and path[-1] == path[-2]:
        path = path[:-1]

    if verbose:
        total_length = sum(
            math.sqrt((path[i+1][0]-path[i][0])**2 +
                      (path[i+1][1]-path[i][1])**2)
            for i in range(len(path)-1)
        )
        print(
            f"  [CENTERLINE] Single continuous path: {len(path)} points, {total_length:.0f}ft total")

    return path


def trace_continuous_paths(G: nx.Graph,
                           min_length: float = 20.0,
                           verbose: bool = False) -> List[List[Tuple[float, float]]]:
    """
    Trace ONE SINGLE continuous centerline through entire skeleton.

    Returns as list with single path for API compatibility.
    """
    single_path = trace_single_continuous_centerline(G, verbose=verbose)

    if not single_path:
        return []

    return [single_path]  # Return as list with single element


def simplify_path(path: List[Tuple[float, float]],
                  tolerance: float = 2.0) -> List[Tuple[float, float]]:
    """
    Simplify a path using Douglas-Peucker algorithm.

    Args:
        path: List of (x, y) points
        tolerance: Simplification tolerance

    Returns:
        Simplified path
    """
    if len(path) < 3:
        return path

    line = LineString(path)
    simplified = line.simplify(tolerance, preserve_topology=True)
    return list(simplified.coords)


def create_free_space_polygon(boundary: Dict[str, float],
                              obstacles: List[Dict[str, float]],
                              verbose: bool = False) -> Polygon:
    """
    Create the free space polygon with obstacles as holes.

    This is the key insight: obstacles become HOLES in the polygon.
    The Voronoi skeleton naturally flows AROUND these holes.

    Args:
        boundary: {minX, maxX, minY, maxY}
        obstacles: List of obstacle bounding boxes
        verbose: Print debug info

    Returns:
        Polygon with holes for obstacles
    """
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

    # Create polygon
    if holes:
        free_space = Polygon(exterior, holes)
    else:
        free_space = Polygon(exterior)

    # Validate and fix if needed
    if not free_space.is_valid:
        free_space = make_valid(free_space)

    # Handle GeometryCollection result
    if isinstance(free_space, GeometryCollection):
        polygons = [g for g in free_space.geoms if isinstance(g, Polygon)]
        if polygons:
            free_space = max(polygons, key=lambda p: p.area)
        else:
            free_space = Polygon(exterior)
    elif isinstance(free_space, MultiPolygon):
        free_space = max(free_space.geoms, key=lambda p: p.area)

    if verbose:
        num_holes = len(list(free_space.interiors)) if hasattr(
            free_space, 'interiors') else 0
        print(
            f"  [FREESPACE] Area: {free_space.area:.0f} sq ft, Holes: {num_holes}")

    return free_space


def generate_centerline_streets(boundary: Dict[str, float],
                                obstacles: List[Dict[str, float]],
                                street_width: float = 24.0,
                                setback: float = 5.0,
                                verbose: bool = False) -> Dict[str, Any]:
    """
    Generate streets using TRUE medial axis centerline.

    Creates ONE CONTINUOUS CENTERLINE network that flows around obstacles.
    The centerline is the Voronoi skeleton of the free space.
    Streets are only drawn where clearance >= half_street_width on BOTH sides.

    Args:
        boundary: {minX, maxX, minY, maxY}
        obstacles: List of obstacle bounding boxes
        street_width: Required street width (24ft typical)
        setback: Distance from boundary to inset
        verbose: Print debug info

    Returns:
        Dictionary with streets (as polylines), connectivity info
    """
    def log(msg):
        if verbose:
            print(msg)

    half_width = street_width / 2

    log(f"[MEDIAL AXIS] Starting TRUE centerline detection...")
    log(f"[MEDIAL AXIS] Boundary: {boundary['maxX']-boundary['minX']:.0f}x{boundary['maxY']-boundary['minY']:.0f} ft")
    log(f"[MEDIAL AXIS] Obstacles: {len(obstacles)}")
    log(f"[MEDIAL AXIS] Required clearance: {half_width:.0f}ft on EACH side")

    # Step 1: Create free space with obstacles as holes
    log(f"[MEDIAL AXIS] Step 1: Creating free space polygon...")
    free_space = create_free_space_polygon(boundary, obstacles, verbose)

    if free_space.is_empty:
        log(f"[MEDIAL AXIS] ERROR: No free space!")
        return {"streets": [], "connected": False, "error": "No free space"}

    # Step 2: Compute Voronoi skeleton (medial axis)
    log(f"[MEDIAL AXIS] Step 2: Computing Voronoi skeleton...")
    skeleton_edges = compute_voronoi_skeleton(
        free_space, resolution=2.0, verbose=verbose)

    if not skeleton_edges:
        log(f"[MEDIAL AXIS] WARNING: No skeleton edges!")
        return {"streets": [], "connected": False, "error": "No skeleton"}

    # Step 3: Build graph with clearance filtering
    log(
        f"[MEDIAL AXIS] Step 3: Filtering by clearance >= {half_width:.0f}ft...")
    G = build_skeleton_graph(
        skeleton_edges, min_clearance=half_width, verbose=verbose)

    if G.number_of_nodes() == 0:
        log(f"[MEDIAL AXIS] WARNING: No valid skeleton nodes!")
        return {"streets": [], "connected": False, "error": "No clearance"}

    # Step 4: Trace continuous paths through skeleton
    log(f"[MEDIAL AXIS] Step 4: Tracing continuous centerline paths...")
    paths = trace_continuous_paths(G, min_length=20.0, verbose=verbose)

    # Step 5: Use paths directly (NO simplification - preserve all curve points)
    # Simplification was removing too many points, causing streets to appear straight
    log(f"[MEDIAL AXIS] Step 5: Using paths directly (no simplification)...")
    simplified_paths = paths  # Keep all intermediate points for proper curves

    # Step 6: Convert to street format
    streets = []
    for i, path in enumerate(simplified_paths):
        if len(path) < 2:
            continue

        # Calculate average clearance along path
        total_clearance = 0
        count = 0
        for x, y in path:
            p = Point(x, y)
            c = free_space.boundary.distance(p)
            total_clearance += c
            count += 1
        avg_clearance = total_clearance / count if count > 0 else half_width

        streets.append({
            "id": f"centerline-{i+1}",
            "polyline": path,
            "clearance": avg_clearance,
            "width": min(avg_clearance * 2, street_width),
            "type": "drive-lane",
            "twoWay": True
        })

    # Check connectivity
    if G.number_of_nodes() > 0:
        connected = nx.is_connected(G)
        num_components = nx.number_connected_components(G)
    else:
        connected = False
        num_components = 0

    log(f"[MEDIAL AXIS] Result: {len(streets)} centerline paths")
    log(f"[MEDIAL AXIS] Connected: {connected} ({num_components} components)")

    return {
        "streets": streets,
        "connected": connected,
        "num_components": num_components,
        "skeleton_edges": len(skeleton_edges),
        "valid_nodes": G.number_of_nodes(),
        "valid_edges": G.number_of_edges()
    }


# =============================================================================
# TESTING
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("TRUE MEDIAL AXIS CENTERLINE TEST")
    print("=" * 60)

    # Test with obstacles
    boundary = {"minX": 0, "maxX": 200, "minY": 0, "maxY": 150}
    obstacles = [
        {"minX": 10, "maxX": 40, "minY": 10, "maxY": 35},    # Top-left
        {"minX": 160, "maxX": 190, "minY": 10, "maxY": 40},  # Top-right
        {"minX": 90, "maxX": 110, "minY": 65, "maxY": 85},   # Center
        {"minX": 160, "maxX": 190, "minY": 110, "maxY": 140},  # Bottom-right
    ]

    result = generate_centerline_streets(
        boundary=boundary,
        obstacles=obstacles,
        street_width=24.0,
        verbose=True
    )

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Streets: {len(result['streets'])}")
    print(f"Connected: {result['connected']}")

    for st in result['streets']:
        path = st['polyline']
        total_len = sum(
            math.sqrt((path[i+1][0]-path[i][0])**2 +
                      (path[i+1][1]-path[i][1])**2)
            for i in range(len(path)-1)
        )
        print(
            f"  {st['id']}: {len(path)} points, {total_len:.0f}ft, clearance={st['clearance']:.1f}ft")
