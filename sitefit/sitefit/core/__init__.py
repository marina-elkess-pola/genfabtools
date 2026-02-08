"""
SiteFit Core - Geometry Foundation

All other modules depend on these geometry primitives and operations.
"""

from .geometry import Point, Line, Polygon, Rectangle, distance, angle_between, bounding_box
from .operations import (
    # Boolean operations
    union, intersection, difference, subtract_all, symmetric_difference,
    # Buffer operations
    buffer, inset, offset, inset_square, buffer_with_square_corners,
    # Line clipping
    clip_line_to_polygon, clip_lines_to_polygon, extend_line_to_polygon,
    # Parallel lines
    generate_parallel_lines, generate_grid_lines,
    # Spatial relationships
    polygons_intersect, polygon_contains, polygon_touches,
    point_in_polygon, line_intersects_polygon,
    # Area calculations
    total_area, intersection_area, coverage_ratio,
    # Utilities
    make_polygon_valid, simplify, convex_hull,
    minimum_bounding_rectangle, split_polygon_with_line,
)

__all__ = [
    # Geometry primitives
    "Point", "Line", "Polygon", "Rectangle",
    "distance", "angle_between", "bounding_box",
    # Boolean operations
    "union", "intersection", "difference", "subtract_all", "symmetric_difference",
    # Buffer operations
    "buffer", "inset", "offset", "inset_square", "buffer_with_square_corners",
    # Line clipping
    "clip_line_to_polygon", "clip_lines_to_polygon", "extend_line_to_polygon",
    # Parallel lines
    "generate_parallel_lines", "generate_grid_lines",
    # Spatial relationships
    "polygons_intersect", "polygon_contains", "polygon_touches",
    "point_in_polygon", "line_intersects_polygon",
    # Area calculations
    "total_area", "intersection_area", "coverage_ratio",
    # Utilities
    "make_polygon_valid", "simplify", "convex_hull",
    "minimum_bounding_rectangle", "split_polygon_with_line",
]
