"""
Geometry Normalizer
===================

Unit conversion, coordinate alignment, and 2D flattening for imported geometry.

All parking engine geometry uses feet as the unit of measurement.
This module converts imported geometry from various source units to feet.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple

from ..geometry import Polygon, Point
from .models import ImportedConstraint, ConstraintSet


# =============================================================================
# UNIT SYSTEMS
# =============================================================================

class UnitSystem(Enum):
    """
    Supported unit systems for CAD/BIM files.
    """
    FEET = "feet"
    INCHES = "inches"
    METERS = "meters"
    CENTIMETERS = "centimeters"
    MILLIMETERS = "millimeters"

    @classmethod
    def from_string(cls, value: str) -> UnitSystem:
        """Parse unit system from string."""
        mapping = {
            "feet": cls.FEET,
            "ft": cls.FEET,
            "foot": cls.FEET,
            "'": cls.FEET,
            "inches": cls.INCHES,
            "inch": cls.INCHES,
            "in": cls.INCHES,
            '"': cls.INCHES,
            "meters": cls.METERS,
            "meter": cls.METERS,
            "m": cls.METERS,
            "centimeters": cls.CENTIMETERS,
            "centimeter": cls.CENTIMETERS,
            "cm": cls.CENTIMETERS,
            "millimeters": cls.MILLIMETERS,
            "millimeter": cls.MILLIMETERS,
            "mm": cls.MILLIMETERS,
        }
        normalized = value.lower().strip()
        if normalized not in mapping:
            raise ValueError(f"Unknown unit system: {value}")
        return mapping[normalized]


# Conversion factors to feet
_TO_FEET: Dict[UnitSystem, float] = {
    UnitSystem.FEET: 1.0,
    UnitSystem.INCHES: 1.0 / 12.0,
    UnitSystem.METERS: 3.28084,
    UnitSystem.CENTIMETERS: 0.0328084,
    UnitSystem.MILLIMETERS: 0.00328084,
}


def get_conversion_factor(from_unit: UnitSystem) -> float:
    """Get conversion factor from source unit to feet."""
    return _TO_FEET[from_unit]


# =============================================================================
# NORMALIZATION CONFIG
# =============================================================================

@dataclass
class NormalizationConfig:
    """
    Configuration for geometry normalization.

    Attributes:
        source_units: Unit system of source geometry
        site_origin: Origin point for coordinate alignment (in feet)
        site_rotation: Rotation angle in degrees (counter-clockwise)
        flatten_z: Whether to flatten 3D geometry to 2D
        scale_factor: Additional scale factor (after unit conversion)
        min_area_threshold: Minimum area in SF to keep (0 = keep all)
        max_area_threshold: Maximum area in SF to keep (0 = no limit)
    """
    source_units: UnitSystem = UnitSystem.FEET
    site_origin: Optional[Point] = None
    site_rotation: float = 0.0
    flatten_z: bool = True
    scale_factor: float = 1.0
    min_area_threshold: float = 0.0
    max_area_threshold: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_units": self.source_units.value,
            "site_origin": {"x": self.site_origin.x, "y": self.site_origin.y} if self.site_origin else None,
            "site_rotation": self.site_rotation,
            "flatten_z": self.flatten_z,
            "scale_factor": self.scale_factor,
            "min_area_threshold": self.min_area_threshold,
            "max_area_threshold": self.max_area_threshold,
        }


# =============================================================================
# NORMALIZATION FUNCTIONS
# =============================================================================

def normalize_point(
    point: Point,
    config: NormalizationConfig,
) -> Point:
    """
    Normalize a single point.

    Applies unit conversion, origin translation, and rotation.
    """
    import math

    # Unit conversion
    factor = get_conversion_factor(config.source_units) * config.scale_factor
    x = point.x * factor
    y = point.y * factor

    # Origin translation
    if config.site_origin:
        x -= config.site_origin.x
        y -= config.site_origin.y

    # Rotation
    if config.site_rotation != 0.0:
        angle_rad = math.radians(config.site_rotation)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        new_x = x * cos_a - y * sin_a
        new_y = x * sin_a + y * cos_a
        x, y = new_x, new_y

    return Point(x, y)


def normalize_polygon(
    polygon: Polygon,
    config: NormalizationConfig,
) -> Polygon:
    """
    Normalize a polygon.

    Applies unit conversion, origin translation, and rotation to all vertices.
    """
    normalized_vertices = [normalize_point(
        v, config) for v in polygon.vertices]
    return Polygon(normalized_vertices)


def normalize_geometry(
    geometry: Polygon,
    source_units: UnitSystem = UnitSystem.FEET,
    site_origin: Optional[Point] = None,
    site_rotation: float = 0.0,
    scale_factor: float = 1.0,
) -> Polygon:
    """
    Normalize geometry with specified parameters.

    Convenience function for simple normalization cases.

    Args:
        geometry: Polygon to normalize
        source_units: Unit system of source geometry
        site_origin: Origin point for coordinate alignment
        site_rotation: Rotation angle in degrees
        scale_factor: Additional scale factor

    Returns:
        Normalized polygon in feet
    """
    config = NormalizationConfig(
        source_units=source_units,
        site_origin=site_origin,
        site_rotation=site_rotation,
        scale_factor=scale_factor,
    )
    return normalize_polygon(geometry, config)


def normalize_constraint(
    constraint: ImportedConstraint,
    config: NormalizationConfig,
) -> Optional[ImportedConstraint]:
    """
    Normalize a single constraint.

    Returns None if constraint fails area thresholds.
    """
    normalized_geom = normalize_polygon(constraint.geometry, config)

    # Check area thresholds
    area = normalized_geom.area
    if config.min_area_threshold > 0 and area < config.min_area_threshold:
        return None
    if config.max_area_threshold > 0 and area > config.max_area_threshold:
        return None

    # Create new constraint with normalized geometry
    return ImportedConstraint(
        geometry=normalized_geom,
        constraint_type=constraint.constraint_type,
        source_format=constraint.source_format,
        source_layer_or_category=constraint.source_layer_or_category,
        source_id=constraint.source_id,
        confidence=constraint.confidence,
        metadata={
            **constraint.metadata,
            "normalized": True,
            "source_units": config.source_units.value,
        },
    )


def normalize_constraint_set(
    constraint_set: ConstraintSet,
    config: NormalizationConfig,
) -> Tuple[ConstraintSet, List[str]]:
    """
    Normalize all constraints in a set.

    Returns:
        Tuple of (normalized ConstraintSet, list of notes/warnings)
    """
    normalized_constraints = []
    notes = []
    rejected = 0

    for constraint in constraint_set.constraints:
        normalized = normalize_constraint(constraint, config)
        if normalized:
            normalized_constraints.append(normalized)
        else:
            rejected += 1
            notes.append(
                f"Constraint {constraint.source_id} rejected: "
                f"area {constraint.geometry.area:.1f} outside thresholds"
            )

    return ConstraintSet(
        constraints=normalized_constraints,
        source_file=constraint_set.source_file,
        source_format=constraint_set.source_format,
        import_notes=constraint_set.import_notes + notes,
        rejected_count=constraint_set.rejected_count + rejected,
    ), notes


# =============================================================================
# 2D FLATTENING
# =============================================================================

def flatten_3d_point(x: float, y: float, z: float = 0.0) -> Point:
    """
    Flatten a 3D point to 2D by dropping Z coordinate.

    This is the simplest flattening approach, suitable for
    plan views and horizontal elements.
    """
    return Point(x, y)


def flatten_3d_vertices(
    vertices: List[Tuple[float, float, float]],
) -> List[Point]:
    """
    Flatten a list of 3D vertices to 2D.
    """
    return [flatten_3d_point(x, y, z) for x, y, z in vertices]


# =============================================================================
# SCALE VALIDATION
# =============================================================================

def estimate_source_units(
    geometry: Polygon,
    expected_min_dimension: float = 1.0,  # feet
    expected_max_dimension: float = 1000.0,  # feet
) -> Optional[UnitSystem]:
    """
    Attempt to estimate source units based on geometry dimensions.

    This is a heuristic approach that may not always be accurate.
    Returns None if unable to determine units.

    Args:
        geometry: Source polygon
        expected_min_dimension: Expected minimum dimension in feet
        expected_max_dimension: Expected maximum dimension in feet

    Returns:
        Estimated UnitSystem or None
    """
    width = geometry.width
    height = geometry.height
    max_dim = max(width, height)

    if max_dim < 0.01:
        return None  # Too small to estimate

    # Check if already in feet (typical parking structure: 50-500 ft)
    if expected_min_dimension <= max_dim <= expected_max_dimension:
        return UnitSystem.FEET

    # Check if in inches (12x larger)
    if expected_min_dimension <= max_dim / 12 <= expected_max_dimension:
        return UnitSystem.INCHES

    # Check if in meters (~3.28x smaller when converted)
    if expected_min_dimension <= max_dim * 3.28084 <= expected_max_dimension:
        return UnitSystem.METERS

    # Check if in millimeters (1000x larger than meters)
    if expected_min_dimension <= max_dim * 0.00328084 <= expected_max_dimension:
        return UnitSystem.MILLIMETERS

    return None


def validate_scale(
    geometry: Polygon,
    source_units: UnitSystem,
    min_area_sf: float = 0.1,
    max_area_sf: float = 1_000_000.0,
) -> Tuple[bool, Optional[str]]:
    """
    Validate that geometry is within reasonable scale bounds.

    Returns:
        Tuple of (is_valid, error_message or None)
    """
    factor = get_conversion_factor(source_units)
    area_sf = geometry.area * (factor ** 2)

    if area_sf < min_area_sf:
        return False, f"Area {area_sf:.2f} SF is below minimum {min_area_sf} SF"

    if area_sf > max_area_sf:
        return False, f"Area {area_sf:.2f} SF exceeds maximum {max_area_sf} SF"

    return True, None
