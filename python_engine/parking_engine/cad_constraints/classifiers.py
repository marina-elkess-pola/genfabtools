"""
Constraint Classifiers
======================

Layer-name and category-based classification of imported geometry
into semantic constraint types.

Classification Hierarchy:
    1. Explicit type specification (highest priority)
    2. Layer/category name pattern matching
    3. Block name matching (DXF/DWG)
    4. Geometry-based heuristics (lowest priority)
    5. Default to UNKNOWN
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Callable, Pattern
import re

from .models import ConstraintType


# =============================================================================
# CLASSIFICATION RULES
# =============================================================================

@dataclass
class ClassificationRule:
    """
    A single classification rule.

    Rules are matched against layer names, category names, or other
    source metadata to determine constraint type.
    """
    pattern: str  # Regex pattern or literal string
    constraint_type: ConstraintType
    is_regex: bool = True
    case_sensitive: bool = False
    priority: int = 0  # Higher = matched first
    description: Optional[str] = None

    def __post_init__(self):
        """Compile regex pattern."""
        if self.is_regex:
            flags = 0 if self.case_sensitive else re.IGNORECASE
            self._compiled = re.compile(self.pattern, flags)
        else:
            self._pattern_lower = self.pattern.lower(
            ) if not self.case_sensitive else self.pattern

    def matches(self, value: str) -> bool:
        """Check if rule matches the given value."""
        if self.is_regex:
            return bool(self._compiled.search(value))
        else:
            if self.case_sensitive:
                return self.pattern in value
            return self._pattern_lower in value.lower()


# =============================================================================
# DEFAULT LAYER RULES (DXF/DWG)
# =============================================================================

DEFAULT_LAYER_RULES: List[ClassificationRule] = [
    # Columns (highest priority for structural elements)
    ClassificationRule(
        pattern=r"\b(structural[_\-\s]?)?column[s]?\b",
        constraint_type=ConstraintType.COLUMN,
        priority=100,
        description="Structural columns",
    ),
    ClassificationRule(
        pattern=r"\bS[_\-]?COLS?\b",
        constraint_type=ConstraintType.COLUMN,
        priority=100,
        description="Standard column layer naming",
    ),
    ClassificationRule(
        pattern=r"\bA[_\-]?COLS?\b",
        constraint_type=ConstraintType.COLUMN,
        priority=100,
        description="Architectural column layer",
    ),
    ClassificationRule(
        pattern=r"col",
        constraint_type=ConstraintType.COLUMN,
        is_regex=False,
        priority=50,
        description="Generic column pattern",
    ),

    # Cores (stairs, elevators)
    ClassificationRule(
        pattern=r"stair",
        constraint_type=ConstraintType.CORE,
        is_regex=False,
        priority=90,
        description="Stair cores",
    ),
    ClassificationRule(
        pattern=r"\b(elevator|lift)[s]?\b",
        constraint_type=ConstraintType.CORE,
        priority=90,
        description="Elevator cores",
    ),
    ClassificationRule(
        pattern=r"\bcore[s]?\b",
        constraint_type=ConstraintType.CORE,
        priority=85,
        description="Generic core designation",
    ),
    ClassificationRule(
        pattern=r"\bA[_\-]?CORE\b",
        constraint_type=ConstraintType.CORE,
        priority=85,
        description="Architectural core layer",
    ),

    # Walls
    ClassificationRule(
        pattern=r"\bwall[s]?\b",
        constraint_type=ConstraintType.WALL,
        priority=80,
        description="Walls",
    ),
    ClassificationRule(
        pattern=r"\bA[_\-]?WALL\b",
        constraint_type=ConstraintType.WALL,
        priority=80,
        description="Architectural wall layer",
    ),
    ClassificationRule(
        pattern=r"\bS[_\-]?WALL\b",
        constraint_type=ConstraintType.WALL,
        priority=80,
        description="Structural wall layer",
    ),

    # MEP Rooms
    ClassificationRule(
        pattern=r"\b(mechanical|mech|hvac)\b",
        constraint_type=ConstraintType.MEP_ROOM,
        priority=75,
        description="Mechanical rooms/equipment",
    ),
    ClassificationRule(
        pattern=r"\b(electrical|elec|elect)\b",
        constraint_type=ConstraintType.MEP_ROOM,
        priority=75,
        description="Electrical rooms/equipment",
    ),
    ClassificationRule(
        pattern=r"\b(plumbing|plumb)\b",
        constraint_type=ConstraintType.MEP_ROOM,
        priority=75,
        description="Plumbing equipment",
    ),
    ClassificationRule(
        pattern=r"\bM[_\-]?EQUIP\b",
        constraint_type=ConstraintType.MEP_ROOM,
        priority=75,
        description="Mechanical equipment layer",
    ),
    ClassificationRule(
        pattern=r"\bE[_\-]?EQUIP\b",
        constraint_type=ConstraintType.MEP_ROOM,
        priority=75,
        description="Electrical equipment layer",
    ),
    ClassificationRule(
        pattern=r"\bP[_\-]?EQUIP\b",
        constraint_type=ConstraintType.MEP_ROOM,
        priority=75,
        description="Plumbing equipment layer",
    ),

    # Shafts
    ClassificationRule(
        pattern=r"\bshaft[s]?\b",
        constraint_type=ConstraintType.SHAFT,
        priority=70,
        description="Vertical shafts",
    ),
    ClassificationRule(
        pattern=r"\b(duct|pipe)[_\-\s]?shaft\b",
        constraint_type=ConstraintType.SHAFT,
        priority=70,
        description="Duct or pipe shafts",
    ),

    # Voids/Openings
    ClassificationRule(
        pattern=r"\b(void|opening|skylight)\b",
        constraint_type=ConstraintType.VOID,
        priority=65,
        description="Floor openings and voids",
    ),
    ClassificationRule(
        pattern=r"\bA[_\-]?OPEN\b",
        constraint_type=ConstraintType.VOID,
        priority=65,
        description="Architectural opening layer",
    ),
]


# =============================================================================
# DEFAULT CATEGORY RULES (RVT)
# =============================================================================

DEFAULT_CATEGORY_RULES: List[ClassificationRule] = [
    # Revit built-in categories
    ClassificationRule(
        pattern=r"^OST_StructuralColumns$",
        constraint_type=ConstraintType.COLUMN,
        priority=100,
        description="Revit structural columns category",
    ),
    ClassificationRule(
        pattern=r"^OST_Columns$",
        constraint_type=ConstraintType.COLUMN,
        priority=100,
        description="Revit columns category",
    ),
    ClassificationRule(
        pattern=r"^OST_Walls$",
        constraint_type=ConstraintType.WALL,
        priority=90,
        description="Revit walls category",
    ),
    ClassificationRule(
        pattern=r"^OST_Shafts$",
        constraint_type=ConstraintType.SHAFT,
        priority=85,
        description="Revit shafts category",
    ),
    ClassificationRule(
        pattern=r"^OST_ShaftOpening$",
        constraint_type=ConstraintType.SHAFT,
        priority=85,
        description="Revit shaft opening category",
    ),
    ClassificationRule(
        pattern=r"^OST_FloorOpening$",
        constraint_type=ConstraintType.VOID,
        priority=80,
        description="Revit floor opening category",
    ),
    ClassificationRule(
        pattern=r"^OST_Rooms$",
        constraint_type=ConstraintType.UNKNOWN,  # Requires room name analysis
        priority=50,
        description="Revit rooms category - needs name classification",
    ),

    # Category name patterns
    ClassificationRule(
        pattern=r"\bcolumn\b",
        constraint_type=ConstraintType.COLUMN,
        priority=40,
        description="Generic column category",
    ),
    ClassificationRule(
        pattern=r"\bwall\b",
        constraint_type=ConstraintType.WALL,
        priority=40,
        description="Generic wall category",
    ),
    ClassificationRule(
        pattern=r"\bshaft\b",
        constraint_type=ConstraintType.SHAFT,
        priority=40,
        description="Generic shaft category",
    ),
]


# =============================================================================
# LAYER CLASSIFIER
# =============================================================================

@dataclass
class LayerClassifier:
    """
    Classifier for DXF/DWG layer-based classification.
    """
    rules: List[ClassificationRule] = field(
        default_factory=lambda: DEFAULT_LAYER_RULES.copy())
    default_type: ConstraintType = ConstraintType.UNKNOWN

    def classify(self, layer_name: str) -> ConstraintType:
        """
        Classify a layer name to constraint type.

        Rules are evaluated in priority order (highest first).
        First matching rule wins.
        """
        # Sort by priority descending
        sorted_rules = sorted(
            self.rules, key=lambda r: r.priority, reverse=True)

        for rule in sorted_rules:
            if rule.matches(layer_name):
                return rule.constraint_type

        return self.default_type

    def add_rule(self, rule: ClassificationRule) -> None:
        """Add a custom classification rule."""
        self.rules.append(rule)

    def remove_rules_for_type(self, constraint_type: ConstraintType) -> None:
        """Remove all rules for a specific constraint type."""
        self.rules = [
            r for r in self.rules if r.constraint_type != constraint_type]


@dataclass
class CategoryClassifier:
    """
    Classifier for RVT category-based classification.
    """
    rules: List[ClassificationRule] = field(
        default_factory=lambda: DEFAULT_CATEGORY_RULES.copy())
    default_type: ConstraintType = ConstraintType.UNKNOWN

    def classify(self, category_name: str) -> ConstraintType:
        """
        Classify a Revit category to constraint type.
        """
        sorted_rules = sorted(
            self.rules, key=lambda r: r.priority, reverse=True)

        for rule in sorted_rules:
            if rule.matches(category_name):
                return rule.constraint_type

        return self.default_type

    def add_rule(self, rule: ClassificationRule) -> None:
        """Add a custom classification rule."""
        self.rules.append(rule)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

# Module-level classifiers
_layer_classifier = LayerClassifier()
_category_classifier = CategoryClassifier()


def classify_by_layer(layer_name: str) -> ConstraintType:
    """
    Classify a layer name to constraint type using default rules.

    Args:
        layer_name: DXF/DWG layer name

    Returns:
        ConstraintType classification
    """
    return _layer_classifier.classify(layer_name)


def classify_by_category(category_name: str) -> ConstraintType:
    """
    Classify a Revit category to constraint type using default rules.

    Args:
        category_name: Revit category name (e.g., "OST_Walls")

    Returns:
        ConstraintType classification
    """
    return _category_classifier.classify(category_name)


def classify_by_room_name(room_name: str) -> ConstraintType:
    """
    Classify a Revit room by its name.

    Used for MEP room detection and core identification.

    Args:
        room_name: Room name from Revit

    Returns:
        ConstraintType classification
    """
    name_lower = room_name.lower()

    # MEP keywords
    mep_keywords = [
        "mechanical", "mech", "hvac", "ahu", "air handler",
        "electrical", "elec", "transformer", "switchgear",
        "plumbing", "plumb", "water heater", "boiler",
        "utility", "service", "meter", "panel",
        "telecom", "data", "server", "it room",
        "fire pump", "sprinkler",
    ]
    if any(kw in name_lower for kw in mep_keywords):
        return ConstraintType.MEP_ROOM

    # Core keywords
    core_keywords = [
        "stair", "stairwell", "stairway", "exit stair",
        "elevator", "lift", "escalator",
        "egress", "exit",
        "lobby", "vestibule",  # May be core-related
    ]
    if any(kw in name_lower for kw in core_keywords):
        return ConstraintType.CORE

    # Shaft keywords
    shaft_keywords = ["shaft", "chase", "duct", "pipe chase"]
    if any(kw in name_lower for kw in shaft_keywords):
        return ConstraintType.SHAFT

    return ConstraintType.UNKNOWN


def classify_by_block_name(block_name: str) -> ConstraintType:
    """
    Classify a DXF/DWG block by its name.

    Common block naming conventions for structural elements.

    Args:
        block_name: Block definition name

    Returns:
        ConstraintType classification
    """
    name_lower = block_name.lower()

    # Column blocks
    column_patterns = ["col", "column", "pillar", "pier"]
    if any(p in name_lower for p in column_patterns):
        return ConstraintType.COLUMN

    # Stair/elevator blocks
    core_patterns = ["stair", "elev", "lift", "core"]
    if any(p in name_lower for p in core_patterns):
        return ConstraintType.CORE

    return ConstraintType.UNKNOWN


# =============================================================================
# CONFIDENCE SCORING
# =============================================================================

def compute_classification_confidence(
    constraint_type: ConstraintType,
    layer_name: str,
    source_format: str,
    block_name: Optional[str] = None,
) -> float:
    """
    Compute confidence score for a classification.

    Factors:
        - Explicit match (layer name exactly matches type): 1.0
        - Pattern match with multiple signals: 0.9
        - Single pattern match: 0.8
        - Block name only: 0.7
        - Unknown classification: 0.5

    Returns:
        Confidence score between 0.0 and 1.0
    """
    if constraint_type == ConstraintType.UNKNOWN:
        return 0.5

    signals = 0

    # Check layer name
    layer_type = classify_by_layer(layer_name)
    if layer_type == constraint_type:
        signals += 1

    # Check block name if provided
    if block_name:
        block_type = classify_by_block_name(block_name)
        if block_type == constraint_type:
            signals += 1

    # Multiple signals = high confidence
    if signals >= 2:
        return 0.95
    elif signals == 1:
        return 0.85
    else:
        # Classification came from somewhere else (e.g., category)
        return 0.75
