"""
CAD/BIM Constraint Models
=========================

Core data models for imported CAD/BIM constraints.

All constraints are represented as 2D planar polygons with
semantic classification and source metadata.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Dict, Any

from ..geometry import Polygon


# =============================================================================
# CONSTRAINT TYPES
# =============================================================================

class ConstraintType(Enum):
    """
    Semantic classification of imported CAD/BIM constraints.

    All constraint types are treated as no-parking exclusion zones.
    UNKNOWN constraints default to full exclusion for safety.
    """
    COLUMN = auto()      # Structural columns
    CORE = auto()        # Stair/elevator cores
    WALL = auto()        # Walls (structural or partition)
    MEP_ROOM = auto()    # Mechanical/Electrical/Plumbing rooms
    SHAFT = auto()       # Vertical shafts (mechanical, duct, pipe)
    VOID = auto()        # Floor voids, openings, skylights
    UNKNOWN = auto()     # Unclassified - defaults to exclusion

    @classmethod
    def from_string(cls, value: str) -> ConstraintType:
        """Parse constraint type from string."""
        mapping = {
            "column": cls.COLUMN,
            "columns": cls.COLUMN,
            "structural_column": cls.COLUMN,
            "core": cls.CORE,
            "stair": cls.CORE,
            "elevator": cls.CORE,
            "stair_core": cls.CORE,
            "elevator_core": cls.CORE,
            "wall": cls.WALL,
            "walls": cls.WALL,
            "mep": cls.MEP_ROOM,
            "mep_room": cls.MEP_ROOM,
            "mechanical": cls.MEP_ROOM,
            "electrical": cls.MEP_ROOM,
            "plumbing": cls.MEP_ROOM,
            "shaft": cls.SHAFT,
            "shafts": cls.SHAFT,
            "duct_shaft": cls.SHAFT,
            "pipe_shaft": cls.SHAFT,
            "void": cls.VOID,
            "opening": cls.VOID,
            "skylight": cls.VOID,
            "floor_opening": cls.VOID,
        }
        normalized = value.lower().strip().replace(" ", "_").replace("-", "_")
        return mapping.get(normalized, cls.UNKNOWN)

    def to_string(self) -> str:
        """Convert to lowercase string."""
        return self.name.lower()


# =============================================================================
# IMPORTED CONSTRAINT
# =============================================================================

@dataclass
class ImportedConstraint:
    """
    A single imported CAD/BIM constraint.

    Represents a 2D polygon extracted from external CAD/BIM files,
    classified by type and tracked to its source.

    Attributes:
        geometry: 2D polygon in site coordinate system (feet)
        constraint_type: Semantic classification (COLUMN, CORE, etc.)
        source_format: Original file format (dxf, dwg, rvt)
        source_layer_or_category: Layer name (DXF/DWG) or category (RVT)
        source_id: Optional unique identifier from source file
        confidence: Classification confidence (0.0-1.0)
        metadata: Additional source-specific metadata
    """
    geometry: Polygon
    constraint_type: ConstraintType
    source_format: str
    source_layer_or_category: str
    source_id: Optional[str] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate constraint after initialization."""
        if self.confidence < 0.0 or self.confidence > 1.0:
            raise ValueError(
                f"Confidence must be between 0.0 and 1.0, got {self.confidence}")
        if self.source_format.lower() not in ("dxf", "dwg", "rvt"):
            raise ValueError(
                f"Unsupported source format: {self.source_format}")

    @property
    def area(self) -> float:
        """Area of constraint polygon in square feet."""
        return self.geometry.area

    @property
    def bounds(self):
        """Bounding box of constraint polygon."""
        return self.geometry.bounds

    @property
    def is_high_confidence(self) -> bool:
        """Check if classification confidence is high (>= 0.8)."""
        return self.confidence >= 0.8

    @property
    def is_unknown(self) -> bool:
        """Check if constraint type is UNKNOWN."""
        return self.constraint_type == ConstraintType.UNKNOWN

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "geometry": self.geometry.to_dict(),
            "constraint_type": self.constraint_type.to_string(),
            "source_format": self.source_format,
            "source_layer_or_category": self.source_layer_or_category,
            "source_id": self.source_id,
            "confidence": self.confidence,
            "area_sf": round(self.area, 2),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ImportedConstraint:
        """Deserialize from dictionary."""
        from geometry import Polygon, Point

        vertices = [Point(v["x"], v["y"])
                    for v in data["geometry"]["vertices"]]
        geometry = Polygon(vertices)

        return cls(
            geometry=geometry,
            constraint_type=ConstraintType.from_string(
                data["constraint_type"]),
            source_format=data["source_format"],
            source_layer_or_category=data["source_layer_or_category"],
            source_id=data.get("source_id"),
            confidence=data.get("confidence", 1.0),
            metadata=data.get("metadata", {}),
        )


# =============================================================================
# CONSTRAINT SET
# =============================================================================

@dataclass
class ConstraintSet:
    """
    Collection of imported constraints with aggregate metadata.

    Represents all constraints from a single import operation,
    with source file information and summary statistics.
    """
    constraints: List[ImportedConstraint] = field(default_factory=list)
    source_file: Optional[str] = None
    source_format: Optional[str] = None
    import_notes: List[str] = field(default_factory=list)
    rejected_count: int = 0

    @property
    def count(self) -> int:
        """Total number of constraints."""
        return len(self.constraints)

    @property
    def total_area(self) -> float:
        """Total area of all constraints in square feet."""
        return sum(c.area for c in self.constraints)

    @property
    def by_type(self) -> Dict[ConstraintType, List[ImportedConstraint]]:
        """Group constraints by type."""
        result: Dict[ConstraintType, List[ImportedConstraint]] = {}
        for c in self.constraints:
            if c.constraint_type not in result:
                result[c.constraint_type] = []
            result[c.constraint_type].append(c)
        return result

    @property
    def unknown_count(self) -> int:
        """Count of UNKNOWN constraints."""
        return sum(1 for c in self.constraints if c.is_unknown)

    @property
    def low_confidence_count(self) -> int:
        """Count of low-confidence constraints."""
        return sum(1 for c in self.constraints if not c.is_high_confidence)

    def get_polygons(self) -> List[Polygon]:
        """Get all constraint polygons."""
        return [c.geometry for c in self.constraints]

    def get_polygons_by_type(self, constraint_type: ConstraintType) -> List[Polygon]:
        """Get polygons for a specific constraint type."""
        return [c.geometry for c in self.constraints if c.constraint_type == constraint_type]

    def filter_by_type(self, *types: ConstraintType) -> ConstraintSet:
        """Create new ConstraintSet with only specified types."""
        filtered = [c for c in self.constraints if c.constraint_type in types]
        return ConstraintSet(
            constraints=filtered,
            source_file=self.source_file,
            source_format=self.source_format,
            import_notes=self.import_notes.copy(),
        )

    def filter_by_confidence(self, min_confidence: float = 0.8) -> ConstraintSet:
        """Create new ConstraintSet with only high-confidence constraints."""
        filtered = [
            c for c in self.constraints if c.confidence >= min_confidence]
        return ConstraintSet(
            constraints=filtered,
            source_file=self.source_file,
            source_format=self.source_format,
            import_notes=self.import_notes.copy(),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "constraints": [c.to_dict() for c in self.constraints],
            "source_file": self.source_file,
            "source_format": self.source_format,
            "import_notes": self.import_notes,
            "rejected_count": self.rejected_count,
            "summary": {
                "total_count": self.count,
                "total_area_sf": round(self.total_area, 2),
                "unknown_count": self.unknown_count,
                "low_confidence_count": self.low_confidence_count,
                "by_type": {
                    t.to_string(): len(constraints)
                    for t, constraints in self.by_type.items()
                },
            },
        }

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"ConstraintSet: {self.count} constraints, {self.total_area:.0f} SF total",
        ]
        if self.source_file:
            lines.append(f"  Source: {self.source_file}")
        for t, constraints in self.by_type.items():
            area = sum(c.area for c in constraints)
            lines.append(
                f"  {t.to_string()}: {len(constraints)} ({area:.0f} SF)")
        if self.rejected_count > 0:
            lines.append(f"  Rejected: {self.rejected_count} elements")
        return "\n".join(lines)


# =============================================================================
# CONSTRAINT IMPACT
# =============================================================================

@dataclass
class ConstraintImpact:
    """
    Impact of constraints on parking layout.

    Tracks stalls and area lost due to each constraint type,
    with efficiency comparison against unconstrained layout.
    """
    total_stalls_lost: int = 0
    total_area_lost: float = 0.0
    stalls_lost_by_type: Dict[str, int] = field(default_factory=dict)
    area_lost_by_type: Dict[str, float] = field(default_factory=dict)

    # Efficiency comparison
    unconstrained_stalls: int = 0
    constrained_stalls: int = 0
    efficiency_delta: float = 0.0  # Percentage loss

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "total_stalls_lost": self.total_stalls_lost,
            "total_area_lost_sf": round(self.total_area_lost, 2),
            "stalls_lost_by_type": self.stalls_lost_by_type,
            "area_lost_by_type": {k: round(v, 2) for k, v in self.area_lost_by_type.items()},
            "unconstrained_stalls": self.unconstrained_stalls,
            "constrained_stalls": self.constrained_stalls,
            "efficiency_delta_pct": round(self.efficiency_delta * 100, 1),
        }

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Constraint Impact: {self.total_stalls_lost} stalls lost, {self.total_area_lost:.0f} SF excluded",
            f"  Unconstrained: {self.unconstrained_stalls} stalls",
            f"  Constrained: {self.constrained_stalls} stalls",
            f"  Efficiency delta: {self.efficiency_delta * 100:.1f}% reduction",
        ]
        for ctype, stalls in self.stalls_lost_by_type.items():
            area = self.area_lost_by_type.get(ctype, 0)
            lines.append(f"  {ctype}: {stalls} stalls, {area:.0f} SF")
        return "\n".join(lines)


@dataclass
class LevelConstraintImpact:
    """
    Per-level constraint impact for structured parking.
    """
    level_index: int
    stalls_lost: int = 0
    area_lost: float = 0.0
    stalls_lost_by_type: Dict[str, int] = field(default_factory=dict)
    area_lost_by_type: Dict[str, float] = field(default_factory=dict)
    constraints_applied: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "level_index": self.level_index,
            "stalls_lost": self.stalls_lost,
            "area_lost_sf": round(self.area_lost, 2),
            "stalls_lost_by_type": self.stalls_lost_by_type,
            "area_lost_by_type": {k: round(v, 2) for k, v in self.area_lost_by_type.items()},
            "constraints_applied": self.constraints_applied,
        }
