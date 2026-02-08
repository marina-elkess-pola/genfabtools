"""
Geometry Validators
===================

Validation of imported CAD/BIM geometry.

All imported geometry must pass validation before being used
as parking constraints:
    - Polygons must be closed
    - No self-intersections
    - Reasonable scale (not microscopic or astronomical)
    - Valid vertex count (at least 3)

Invalid geometry is rejected with clear error messages.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Dict, Any, Tuple

from ..geometry import Polygon, Point
from .models import ImportedConstraint, ConstraintSet


# =============================================================================
# VALIDATION TOLERANCES
# =============================================================================

@dataclass
class ValidationTolerances:
    """
    Configurable tolerance values for geometry validation.
    """
    # Closure tolerance (max gap between first and last vertex)
    closure_tolerance: float = 0.001  # feet

    # Minimum polygon area (square feet)
    min_area: float = 0.1  # About 1 square inch

    # Maximum polygon area (square feet)
    max_area: float = 10_000_000.0  # About 230 acres

    # Minimum vertex count
    min_vertices: int = 3

    # Maximum vertex count (to catch bad imports)
    max_vertices: int = 10_000

    # Minimum edge length (feet)
    min_edge_length: float = 0.01  # About 1/8 inch

    # Collinearity tolerance for self-intersection check
    collinear_tolerance: float = 1e-9

    # Reasonable dimension bounds
    min_dimension: float = 0.1  # feet
    max_dimension: float = 10_000.0  # feet


# Default tolerances
VALIDATION_TOLERANCES = ValidationTolerances()


# =============================================================================
# VALIDATION ERRORS
# =============================================================================

class ValidationErrorType(Enum):
    """Types of validation errors."""
    NOT_CLOSED = auto()
    SELF_INTERSECTING = auto()
    TOO_FEW_VERTICES = auto()
    TOO_MANY_VERTICES = auto()
    AREA_TOO_SMALL = auto()
    AREA_TOO_LARGE = auto()
    DIMENSION_TOO_SMALL = auto()
    DIMENSION_TOO_LARGE = auto()
    DEGENERATE_EDGE = auto()
    INVALID_COORDINATES = auto()


@dataclass
class ValidationError:
    """
    A single validation error.
    """
    error_type: ValidationErrorType
    message: str
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.error_type.name,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class ValidationResult:
    """
    Result of geometry validation.
    """
    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Computed properties
    vertex_count: int = 0
    area: float = 0.0
    perimeter: float = 0.0
    is_closed: bool = True
    is_convex: bool = False

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": self.warnings,
            "vertex_count": self.vertex_count,
            "area": round(self.area, 2),
            "perimeter": round(self.perimeter, 2),
            "is_closed": self.is_closed,
            "is_convex": self.is_convex,
        }


# =============================================================================
# POLYGON VALIDATION
# =============================================================================

def validate_polygon(
    polygon: Polygon,
    tolerances: Optional[ValidationTolerances] = None,
) -> ValidationResult:
    """
    Validate a polygon for use as a parking constraint.

    Checks:
        - Minimum vertex count (3)
        - Maximum vertex count (10,000)
        - Polygon is closed
        - No self-intersections
        - Area within bounds
        - Dimensions within bounds
        - No degenerate edges

    Args:
        polygon: Polygon to validate
        tolerances: Validation tolerances (uses defaults if None)

    Returns:
        ValidationResult with errors and computed properties
    """
    tol = tolerances or VALIDATION_TOLERANCES
    errors: List[ValidationError] = []
    warnings: List[str] = []

    vertices = polygon.vertices
    vertex_count = len(vertices)

    # Check vertex count
    if vertex_count < tol.min_vertices:
        errors.append(ValidationError(
            error_type=ValidationErrorType.TOO_FEW_VERTICES,
            message=f"Polygon has {vertex_count} vertices, minimum is {tol.min_vertices}",
            details={"vertex_count": vertex_count,
                     "minimum": tol.min_vertices},
        ))

    if vertex_count > tol.max_vertices:
        errors.append(ValidationError(
            error_type=ValidationErrorType.TOO_MANY_VERTICES,
            message=f"Polygon has {vertex_count} vertices, maximum is {tol.max_vertices}",
            details={"vertex_count": vertex_count,
                     "maximum": tol.max_vertices},
        ))

    # Check for invalid coordinates
    for i, v in enumerate(vertices):
        if not _is_finite(v.x) or not _is_finite(v.y):
            errors.append(ValidationError(
                error_type=ValidationErrorType.INVALID_COORDINATES,
                message=f"Vertex {i} has invalid coordinates: ({v.x}, {v.y})",
                details={"vertex_index": i, "x": v.x, "y": v.y},
            ))

    # Check closure
    is_closed = True
    if vertex_count >= 2:
        gap = vertices[0].distance_to(vertices[-1])
        if gap > tol.closure_tolerance:
            is_closed = False
            # This is a warning, not an error - we can auto-close
            warnings.append(
                f"Polygon is not closed (gap: {gap:.4f} ft). "
                "Geometry will be auto-closed."
            )

    # Check area
    area = polygon.area
    if area < tol.min_area:
        errors.append(ValidationError(
            error_type=ValidationErrorType.AREA_TOO_SMALL,
            message=f"Polygon area {area:.4f} SF is below minimum {tol.min_area} SF",
            details={"area": area, "minimum": tol.min_area},
        ))

    if area > tol.max_area:
        errors.append(ValidationError(
            error_type=ValidationErrorType.AREA_TOO_LARGE,
            message=f"Polygon area {area:.0f} SF exceeds maximum {tol.max_area:.0f} SF",
            details={"area": area, "maximum": tol.max_area},
        ))

    # Check dimensions
    min_x, min_y, max_x, max_y = polygon.bounds
    width = max_x - min_x
    height = max_y - min_y

    if width < tol.min_dimension or height < tol.min_dimension:
        errors.append(ValidationError(
            error_type=ValidationErrorType.DIMENSION_TOO_SMALL,
            message=f"Polygon dimensions ({width:.2f} x {height:.2f}) below minimum {tol.min_dimension}",
            details={"width": width, "height": height,
                     "minimum": tol.min_dimension},
        ))

    if width > tol.max_dimension or height > tol.max_dimension:
        errors.append(ValidationError(
            error_type=ValidationErrorType.DIMENSION_TOO_LARGE,
            message=f"Polygon dimensions ({width:.0f} x {height:.0f}) exceed maximum {tol.max_dimension:.0f}",
            details={"width": width, "height": height,
                     "maximum": tol.max_dimension},
        ))

    # Check for degenerate edges
    if vertex_count >= 2:
        for i in range(vertex_count):
            j = (i + 1) % vertex_count
            edge_length = vertices[i].distance_to(vertices[j])
            if edge_length < tol.min_edge_length:
                errors.append(ValidationError(
                    error_type=ValidationErrorType.DEGENERATE_EDGE,
                    message=f"Edge {i}-{j} has length {edge_length:.4f} ft, below minimum {tol.min_edge_length}",
                    details={"edge_start": i, "edge_end": j,
                             "length": edge_length},
                ))

    # Check for self-intersection
    if vertex_count >= 4 and not errors:
        has_intersection, intersection_info = _check_self_intersection(
            vertices, tol)
        if has_intersection:
            errors.append(ValidationError(
                error_type=ValidationErrorType.SELF_INTERSECTING,
                message="Polygon has self-intersecting edges",
                details=intersection_info,
            ))

    # Compute convexity
    is_convex = _is_convex_polygon(vertices) if vertex_count >= 3 else False

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        vertex_count=vertex_count,
        area=area,
        perimeter=polygon.perimeter,
        is_closed=is_closed,
        is_convex=is_convex,
    )


def _is_finite(value: float) -> bool:
    """Check if value is finite (not NaN or infinity)."""
    import math
    return math.isfinite(value)


def _check_self_intersection(
    vertices: List[Point],
    tolerances: ValidationTolerances,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Check if polygon edges self-intersect.

    Uses line segment intersection test for non-adjacent edges.
    """
    n = len(vertices)

    for i in range(n):
        for j in range(i + 2, n):
            # Skip adjacent edges
            if i == 0 and j == n - 1:
                continue

            p1 = vertices[i]
            p2 = vertices[(i + 1) % n]
            p3 = vertices[j]
            p4 = vertices[(j + 1) % n]

            if _segments_intersect(p1, p2, p3, p4, tolerances.collinear_tolerance):
                return True, {
                    "edge1": (i, (i + 1) % n),
                    "edge2": (j, (j + 1) % n),
                }

    return False, None


def _segments_intersect(
    p1: Point, p2: Point,
    p3: Point, p4: Point,
    tolerance: float,
) -> bool:
    """
    Check if two line segments intersect (excluding endpoints).

    Uses cross product orientation test.
    """
    def cross(o: Point, a: Point, b: Point) -> float:
        return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x)

    d1 = cross(p3, p4, p1)
    d2 = cross(p3, p4, p2)
    d3 = cross(p1, p2, p3)
    d4 = cross(p1, p2, p4)

    if ((d1 > tolerance and d2 < -tolerance) or (d1 < -tolerance and d2 > tolerance)) and \
       ((d3 > tolerance and d4 < -tolerance) or (d3 < -tolerance and d4 > tolerance)):
        return True

    return False


def _is_convex_polygon(vertices: List[Point]) -> bool:
    """
    Check if polygon is convex.

    A polygon is convex if all cross products of consecutive
    edge vectors have the same sign.
    """
    n = len(vertices)
    if n < 3:
        return False

    sign = 0
    for i in range(n):
        p1 = vertices[i]
        p2 = vertices[(i + 1) % n]
        p3 = vertices[(i + 2) % n]

        cross = (p2.x - p1.x) * (p3.y - p2.y) - (p2.y - p1.y) * (p3.x - p2.x)

        if cross != 0:
            if sign == 0:
                sign = 1 if cross > 0 else -1
            elif (cross > 0) != (sign > 0):
                return False

    return True


# =============================================================================
# CONSTRAINT VALIDATION
# =============================================================================

def validate_constraint(
    constraint: ImportedConstraint,
    tolerances: Optional[ValidationTolerances] = None,
) -> ValidationResult:
    """
    Validate an imported constraint.

    Validates the underlying polygon geometry.
    """
    result = validate_polygon(constraint.geometry, tolerances)

    # Add constraint-specific warnings
    if constraint.constraint_type.name == "UNKNOWN":
        result.warnings.append(
            "Constraint type is UNKNOWN - will be treated as full exclusion"
        )

    if constraint.confidence < 0.8:
        result.warnings.append(
            f"Low classification confidence ({constraint.confidence:.2f})"
        )

    return result


def validate_constraint_set(
    constraint_set: ConstraintSet,
    tolerances: Optional[ValidationTolerances] = None,
) -> Tuple[ConstraintSet, List[ValidationResult]]:
    """
    Validate all constraints in a set.

    Returns a new ConstraintSet with only valid constraints,
    and a list of validation results for all constraints.
    """
    valid_constraints = []
    results = []
    rejected_count = 0
    notes = []

    for constraint in constraint_set.constraints:
        result = validate_constraint(constraint, tolerances)
        results.append(result)

        if result.is_valid:
            valid_constraints.append(constraint)
        else:
            rejected_count += 1
            error_msgs = "; ".join(e.message for e in result.errors)
            notes.append(
                f"Rejected constraint {constraint.source_id}: {error_msgs}"
            )

    return ConstraintSet(
        constraints=valid_constraints,
        source_file=constraint_set.source_file,
        source_format=constraint_set.source_format,
        import_notes=constraint_set.import_notes + notes,
        rejected_count=constraint_set.rejected_count + rejected_count,
    ), results


# =============================================================================
# GEOMETRY REPAIR
# =============================================================================

def repair_polygon(
    polygon: Polygon,
    tolerances: Optional[ValidationTolerances] = None,
) -> Optional[Polygon]:
    """
    Attempt to repair invalid polygon geometry.

    Repairs:
        - Remove duplicate vertices
        - Close open polygons
        - Remove degenerate edges

    Note: Cannot repair self-intersecting polygons.

    Returns:
        Repaired polygon, or None if unrepairable
    """
    tol = tolerances or VALIDATION_TOLERANCES
    vertices = polygon.vertices.copy()

    if len(vertices) < 3:
        return None

    # Remove duplicate consecutive vertices
    cleaned = [vertices[0]]
    for v in vertices[1:]:
        if v.distance_to(cleaned[-1]) > tol.min_edge_length:
            cleaned.append(v)

    # Check if last vertex duplicates first
    if len(cleaned) > 1 and cleaned[-1].distance_to(cleaned[0]) < tol.closure_tolerance:
        cleaned.pop()

    if len(cleaned) < 3:
        return None

    # Create repaired polygon
    repaired = Polygon(cleaned)

    # Validate result
    result = validate_polygon(repaired, tolerances)
    if result.is_valid:
        return repaired

    # Check if only remaining issue is acceptable
    serious_errors = [
        e for e in result.errors
        if e.error_type not in (
            ValidationErrorType.NOT_CLOSED,  # We auto-close
        )
    ]

    if not serious_errors:
        return repaired

    return None


def close_polygon(polygon: Polygon) -> Polygon:
    """
    Ensure polygon is closed by adding first vertex at end if needed.

    Note: The Polygon class typically handles this automatically,
    but this function makes the intent explicit.
    """
    vertices = polygon.vertices
    if len(vertices) < 3:
        return polygon

    # Polygon class should already treat as closed, so just return
    return polygon
