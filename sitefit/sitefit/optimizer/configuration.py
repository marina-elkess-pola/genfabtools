"""
optimizer/configuration.py - Site Configuration Module

Combines parking layout + building massing into a single testable configuration.
This represents one complete site design option that can be scored and compared.

Depends on:
- parking/* modules (layouts, stalls, circulation)
- building/* modules (floor plates, massing, unit mix)
- constraints/* modules (zoning, setbacks, parking ratios)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple, TYPE_CHECKING

from sitefit.core.geometry import Polygon, Rectangle, Point

if TYPE_CHECKING:
    from sitefit.parking.layout_generator import LayoutResult
    from sitefit.parking.circulation import CirculationNetwork
    from sitefit.building.massing import BuildingMass
    from sitefit.building.unit_mix import BuildingUnitMix
    from sitefit.constraints.zoning import ZoningDistrict
    from sitefit.constraints.parking_ratio import ParkingRequirement


class ElementType(Enum):
    """Types of elements on a site."""
    PARKING_SURFACE = "parking_surface"
    PARKING_STRUCTURE = "parking_structure"
    PARKING_UNDERGROUND = "parking_underground"
    BUILDING_RESIDENTIAL = "building_residential"
    BUILDING_COMMERCIAL = "building_commercial"
    BUILDING_MIXED_USE = "building_mixed_use"
    OPEN_SPACE = "open_space"
    AMENITY = "amenity"
    CIRCULATION = "circulation"


@dataclass
class SiteElement:
    """
    Base class for site elements.

    All elements on a site (buildings, parking, open space) share
    common properties like footprint, location, and metadata.
    """
    id: str
    element_type: ElementType
    footprint: Polygon
    name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def area(self) -> float:
        """Get footprint area in square feet."""
        return self.footprint.area

    @property
    def centroid(self) -> Point:
        """Get footprint centroid."""
        return self.footprint.centroid

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "element_type": self.element_type.value,
            "footprint_area": round(self.area, 2),
            "centroid": [round(self.centroid.x, 2), round(self.centroid.y, 2)],
            "name": self.name,
            "metadata": self.metadata,
        }


@dataclass
class ParkingElement(SiteElement):
    """
    Parking area on a site.

    Can be surface parking, structured parking, or underground.
    """
    stall_count: int = 0
    levels: int = 1
    total_spaces: int = 0
    layout_result: Optional[LayoutResult] = None
    circulation: Optional[CirculationNetwork] = None

    # Parking configuration
    stall_angle: float = 90.0  # Degrees
    stall_width: float = 9.0  # Feet
    stall_depth: float = 18.0  # Feet
    aisle_width: float = 24.0  # Feet

    # Efficiency metrics
    spaces_per_level: int = 0
    parking_efficiency: float = 0.0  # Spaces per 1000 SF

    def __post_init__(self):
        """Calculate derived values."""
        if self.total_spaces == 0 and self.stall_count > 0:
            self.total_spaces = self.stall_count * self.levels
        if self.spaces_per_level == 0 and self.stall_count > 0:
            self.spaces_per_level = self.stall_count
        if self.parking_efficiency == 0 and self.area > 0:
            self.parking_efficiency = (
                self.spaces_per_level / self.area) * 1000

    @classmethod
    def from_layout_result(
        cls,
        id: str,
        layout_result: LayoutResult,
        element_type: ElementType = ElementType.PARKING_SURFACE,
        levels: int = 1,
        name: Optional[str] = None
    ) -> ParkingElement:
        """
        Create parking element from layout result.

        Args:
            id: Unique identifier
            layout_result: Result from layout generator
            element_type: Type of parking
            levels: Number of levels
            name: Optional name

        Returns:
            ParkingElement instance
        """
        return cls(
            id=id,
            element_type=element_type,
            footprint=layout_result.boundary,
            name=name,
            stall_count=layout_result.total_stalls,
            levels=levels,
            layout_result=layout_result,
            stall_angle=layout_result.angle,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        base = super().to_dict()
        base.update({
            "stall_count": self.stall_count,
            "levels": self.levels,
            "total_spaces": self.total_spaces,
            "stall_angle": self.stall_angle,
            "spaces_per_level": self.spaces_per_level,
            "parking_efficiency": round(self.parking_efficiency, 2),
        })
        return base


@dataclass
class BuildingElement(SiteElement):
    """
    Building on a site.

    Contains massing information, unit mix, and area calculations.
    """
    floors: int = 1
    floor_height: float = 10.0  # Feet
    total_height: float = 0.0  # Feet
    gross_area: float = 0.0  # Total SF
    net_area: float = 0.0  # Usable SF
    building_mass: Optional[BuildingMass] = None
    unit_mix: Optional[BuildingUnitMix] = None

    # Unit counts
    total_units: int = 0
    studios: int = 0
    one_br: int = 0
    two_br: int = 0
    three_br: int = 0

    # Commercial areas
    retail_sf: float = 0.0
    office_sf: float = 0.0

    # Metrics
    far: float = 0.0  # Floor Area Ratio
    lot_coverage: float = 0.0  # Footprint / Site area

    def __post_init__(self):
        """Calculate derived values."""
        if self.total_height == 0 and self.floors > 0:
            self.total_height = self.floors * self.floor_height
        if self.gross_area == 0 and self.area > 0 and self.floors > 0:
            self.gross_area = self.area * self.floors

    @classmethod
    def from_massing(
        cls,
        id: str,
        building_mass: BuildingMass,
        element_type: ElementType = ElementType.BUILDING_RESIDENTIAL,
        name: Optional[str] = None,
        site_area: float = 0.0
    ) -> BuildingElement:
        """
        Create building element from building mass.

        Args:
            id: Unique identifier
            building_mass: Building massing
            element_type: Type of building
            name: Optional name
            site_area: Total site area for FAR calculation

        Returns:
            BuildingElement instance
        """
        # Calculate FAR
        far = 0.0
        lot_coverage = 0.0
        if site_area > 0:
            far = building_mass.total_gross_area / site_area
            lot_coverage = building_mass.footprint_area / site_area

        return cls(
            id=id,
            element_type=element_type,
            footprint=building_mass.footprint,
            name=name,
            floors=building_mass.floor_count,
            floor_height=building_mass.floor_height,
            total_height=building_mass.total_height,
            gross_area=building_mass.total_gross_area,
            net_area=building_mass.total_net_area,
            building_mass=building_mass,
            far=far,
            lot_coverage=lot_coverage,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        base = super().to_dict()
        base.update({
            "floors": self.floors,
            "floor_height": self.floor_height,
            "total_height": self.total_height,
            "gross_area": round(self.gross_area, 2),
            "net_area": round(self.net_area, 2),
            "total_units": self.total_units,
            "studios": self.studios,
            "one_br": self.one_br,
            "two_br": self.two_br,
            "three_br": self.three_br,
            "retail_sf": round(self.retail_sf, 2),
            "office_sf": round(self.office_sf, 2),
            "far": round(self.far, 3),
            "lot_coverage": round(self.lot_coverage, 3),
        })
        return base


@dataclass
class OpenSpaceElement(SiteElement):
    """
    Open space or amenity area on a site.
    """
    landscape_type: str = "lawn"  # lawn, plaza, courtyard, etc.
    is_public: bool = False
    amenities: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        base = super().to_dict()
        base.update({
            "landscape_type": self.landscape_type,
            "is_public": self.is_public,
            "amenities": self.amenities,
        })
        return base


@dataclass
class ConfigurationResult:
    """
    Results and metrics for a site configuration.

    Calculated from all elements in the configuration.
    """
    # Site metrics
    site_area: float = 0.0
    buildable_area: float = 0.0
    built_area: float = 0.0  # Sum of all footprints
    open_space_area: float = 0.0

    # Building metrics
    total_gross_area: float = 0.0
    total_net_area: float = 0.0
    total_units: int = 0
    total_floors: int = 0
    max_height: float = 0.0

    # Parking metrics
    total_parking_spaces: int = 0
    required_parking_spaces: int = 0
    parking_surplus: int = 0
    parking_ratio_actual: float = 0.0

    # Efficiency metrics
    site_coverage: float = 0.0  # Built area / Site area
    far: float = 0.0  # Total gross area / Site area
    open_space_ratio: float = 0.0  # Open space / Site area
    efficiency_score: float = 0.0  # Overall efficiency

    # Compliance
    zoning_compliant: bool = True
    parking_compliant: bool = True
    height_compliant: bool = True
    setback_compliant: bool = True
    compliance_issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "site_metrics": {
                "site_area": round(self.site_area, 2),
                "buildable_area": round(self.buildable_area, 2),
                "built_area": round(self.built_area, 2),
                "open_space_area": round(self.open_space_area, 2),
            },
            "building_metrics": {
                "total_gross_area": round(self.total_gross_area, 2),
                "total_net_area": round(self.total_net_area, 2),
                "total_units": self.total_units,
                "total_floors": self.total_floors,
                "max_height": round(self.max_height, 2),
            },
            "parking_metrics": {
                "total_parking_spaces": self.total_parking_spaces,
                "required_parking_spaces": self.required_parking_spaces,
                "parking_surplus": self.parking_surplus,
                "parking_ratio_actual": round(self.parking_ratio_actual, 2),
            },
            "efficiency_metrics": {
                "site_coverage": round(self.site_coverage, 3),
                "far": round(self.far, 3),
                "open_space_ratio": round(self.open_space_ratio, 3),
                "efficiency_score": round(self.efficiency_score, 2),
            },
            "compliance": {
                "zoning_compliant": self.zoning_compliant,
                "parking_compliant": self.parking_compliant,
                "height_compliant": self.height_compliant,
                "setback_compliant": self.setback_compliant,
                "issues": self.compliance_issues,
            },
        }


@dataclass
class SiteConfiguration:
    """
    Complete site configuration combining all elements.

    Represents one design option for a site, including:
    - One or more buildings
    - Parking (surface, structured, underground)
    - Open spaces and amenities
    - Circulation

    Can be scored, compared, and optimized.
    """
    id: str
    name: str
    site_boundary: Polygon
    buildable_boundary: Optional[Polygon] = None
    elements: List[SiteElement] = field(default_factory=list)
    zoning: Optional[ZoningDistrict] = None
    result: Optional[ConfigurationResult] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Configuration parameters (for regeneration)
    parking_angle: float = 90.0
    building_coverage: float = 0.5  # Target building coverage
    parking_location: str = "surface"  # surface, structure, underground, wrapped

    @property
    def site_area(self) -> float:
        """Get total site area."""
        return self.site_boundary.area

    @property
    def buildable_area(self) -> float:
        """Get buildable area after setbacks."""
        if self.buildable_boundary:
            return self.buildable_boundary.area
        return self.site_area

    @property
    def buildings(self) -> List[BuildingElement]:
        """Get all building elements."""
        return [e for e in self.elements if isinstance(e, BuildingElement)]

    @property
    def parking_areas(self) -> List[ParkingElement]:
        """Get all parking elements."""
        return [e for e in self.elements if isinstance(e, ParkingElement)]

    @property
    def open_spaces(self) -> List[OpenSpaceElement]:
        """Get all open space elements."""
        return [e for e in self.elements if isinstance(e, OpenSpaceElement)]

    def add_element(self, element: SiteElement) -> None:
        """Add an element to the configuration."""
        self.elements.append(element)

    def remove_element(self, element_id: str) -> bool:
        """Remove an element by ID."""
        for i, element in enumerate(self.elements):
            if element.id == element_id:
                self.elements.pop(i)
                return True
        return False

    def get_element(self, element_id: str) -> Optional[SiteElement]:
        """Get an element by ID."""
        for element in self.elements:
            if element.id == element_id:
                return element
        return None

    def calculate_results(self) -> ConfigurationResult:
        """
        Calculate configuration results and metrics.

        Returns:
            ConfigurationResult with all metrics
        """
        result = ConfigurationResult(
            site_area=self.site_area,
            buildable_area=self.buildable_area,
        )

        # Calculate built area
        for element in self.elements:
            result.built_area += element.area

        # Building metrics
        for building in self.buildings:
            result.total_gross_area += building.gross_area
            result.total_net_area += building.net_area
            result.total_units += building.total_units
            if building.floors > result.total_floors:
                result.total_floors = building.floors
            if building.total_height > result.max_height:
                result.max_height = building.total_height

        # Parking metrics
        for parking in self.parking_areas:
            result.total_parking_spaces += parking.total_spaces

        # Calculate parking requirement
        if result.total_units > 0:
            # Use default 1.5 ratio if no zoning specified
            ratio = 1.5
            if self.zoning and self.zoning.parking_ratio:
                ratio = self.zoning.parking_ratio
            result.required_parking_spaces = int(result.total_units * ratio)

        result.parking_surplus = result.total_parking_spaces - \
            result.required_parking_spaces
        if result.total_units > 0:
            result.parking_ratio_actual = result.total_parking_spaces / result.total_units

        # Open space
        for open_space in self.open_spaces:
            result.open_space_area += open_space.area

        # Efficiency metrics
        if self.site_area > 0:
            result.site_coverage = result.built_area / self.site_area
            result.far = result.total_gross_area / self.site_area
            result.open_space_ratio = result.open_space_area / self.site_area

        # Compliance checking
        if self.zoning:
            # Height compliance
            if self.zoning.max_height_ft and result.max_height > self.zoning.max_height_ft:
                result.height_compliant = False
                result.compliance_issues.append(
                    f"Height {result.max_height:.0f}' exceeds max {self.zoning.max_height_ft:.0f}'"
                )

            # FAR compliance
            if self.zoning.max_far and result.far > self.zoning.max_far:
                result.zoning_compliant = False
                result.compliance_issues.append(
                    f"FAR {result.far:.2f} exceeds max {self.zoning.max_far:.2f}"
                )

            # Lot coverage compliance
            if self.zoning.max_lot_coverage and result.site_coverage > self.zoning.max_lot_coverage:
                result.zoning_compliant = False
                result.compliance_issues.append(
                    f"Coverage {result.site_coverage:.1%} exceeds max {self.zoning.max_lot_coverage:.1%}"
                )

        # Parking compliance
        if result.parking_surplus < 0:
            result.parking_compliant = False
            result.compliance_issues.append(
                f"Parking deficit: {abs(result.parking_surplus)} spaces short"
            )

        # Overall efficiency score (0-100)
        # Based on unit density, parking efficiency, and compliance
        efficiency_factors = []

        # Unit density factor (more units = higher score)
        if self.buildable_area > 0:
            units_per_acre = result.total_units / (self.buildable_area / 43560)
            unit_density_score = min(
                100, units_per_acre * 2)  # 50 units/acre = 100
            efficiency_factors.append(unit_density_score)

        # Parking efficiency factor
        if result.required_parking_spaces > 0:
            parking_match = 1 - abs(result.parking_surplus) / \
                result.required_parking_spaces
            parking_score = max(0, min(100, parking_match * 100))
            efficiency_factors.append(parking_score)

        # Compliance factor
        if result.zoning_compliant and result.parking_compliant and result.height_compliant:
            efficiency_factors.append(100)
        else:
            efficiency_factors.append(50)

        if efficiency_factors:
            result.efficiency_score = sum(
                efficiency_factors) / len(efficiency_factors)

        self.result = result
        return result

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "site_area": round(self.site_area, 2),
            "buildable_area": round(self.buildable_area, 2),
            "elements": [e.to_dict() for e in self.elements],
            "parking_angle": self.parking_angle,
            "building_coverage": self.building_coverage,
            "parking_location": self.parking_location,
            "result": self.result.to_dict() if self.result else None,
            "metadata": self.metadata,
        }


# =============================================================================
# CONFIGURATION CREATION FUNCTIONS
# =============================================================================

def create_configuration(
    site_boundary: Polygon,
    name: str = "Configuration",
    id: Optional[str] = None,
    buildable_boundary: Optional[Polygon] = None,
    zoning: Optional[ZoningDistrict] = None,
    parking_angle: float = 90.0,
    building_coverage: float = 0.5,
    parking_location: str = "surface"
) -> SiteConfiguration:
    """
    Create a new site configuration.

    Args:
        site_boundary: Site boundary polygon
        name: Configuration name
        id: Optional unique identifier
        buildable_boundary: Boundary after setbacks
        zoning: Zoning district
        parking_angle: Parking stall angle
        building_coverage: Target building coverage
        parking_location: Parking type

    Returns:
        SiteConfiguration instance
    """
    import uuid
    if id is None:
        id = str(uuid.uuid4())[:8]

    return SiteConfiguration(
        id=id,
        name=name,
        site_boundary=site_boundary,
        buildable_boundary=buildable_boundary,
        zoning=zoning,
        parking_angle=parking_angle,
        building_coverage=building_coverage,
        parking_location=parking_location,
    )


def create_parking_element(
    footprint: Polygon,
    stall_count: int,
    id: Optional[str] = None,
    element_type: ElementType = ElementType.PARKING_SURFACE,
    levels: int = 1,
    name: Optional[str] = None,
    stall_angle: float = 90.0
) -> ParkingElement:
    """
    Create a parking element.

    Args:
        footprint: Parking area footprint
        stall_count: Number of stalls per level
        id: Optional unique identifier
        element_type: Type of parking
        levels: Number of levels
        name: Optional name
        stall_angle: Stall angle in degrees

    Returns:
        ParkingElement instance
    """
    import uuid
    if id is None:
        id = f"parking_{str(uuid.uuid4())[:6]}"

    return ParkingElement(
        id=id,
        element_type=element_type,
        footprint=footprint,
        name=name,
        stall_count=stall_count,
        levels=levels,
        stall_angle=stall_angle,
    )


def create_building_element(
    footprint: Polygon,
    floors: int,
    id: Optional[str] = None,
    element_type: ElementType = ElementType.BUILDING_RESIDENTIAL,
    name: Optional[str] = None,
    floor_height: float = 10.0,
    total_units: int = 0,
    site_area: float = 0.0
) -> BuildingElement:
    """
    Create a building element.

    Args:
        footprint: Building footprint
        floors: Number of floors
        id: Optional unique identifier
        element_type: Type of building
        name: Optional name
        floor_height: Floor height in feet
        total_units: Total unit count
        site_area: Site area for FAR calculation

    Returns:
        BuildingElement instance
    """
    import uuid
    if id is None:
        id = f"building_{str(uuid.uuid4())[:6]}"

    gross_area = footprint.area * floors
    far = gross_area / site_area if site_area > 0 else 0.0
    lot_coverage = footprint.area / site_area if site_area > 0 else 0.0

    return BuildingElement(
        id=id,
        element_type=element_type,
        footprint=footprint,
        name=name,
        floors=floors,
        floor_height=floor_height,
        total_height=floors * floor_height,
        gross_area=gross_area,
        total_units=total_units,
        far=far,
        lot_coverage=lot_coverage,
    )


def create_open_space_element(
    footprint: Polygon,
    id: Optional[str] = None,
    name: Optional[str] = None,
    landscape_type: str = "lawn",
    is_public: bool = False,
    amenities: Optional[List[str]] = None
) -> OpenSpaceElement:
    """
    Create an open space element.

    Args:
        footprint: Open space footprint
        id: Optional unique identifier
        name: Optional name
        landscape_type: Type of landscaping
        is_public: Whether publicly accessible
        amenities: List of amenities

    Returns:
        OpenSpaceElement instance
    """
    import uuid
    if id is None:
        id = f"openspace_{str(uuid.uuid4())[:6]}"

    return OpenSpaceElement(
        id=id,
        element_type=ElementType.OPEN_SPACE,
        footprint=footprint,
        name=name,
        landscape_type=landscape_type,
        is_public=is_public,
        amenities=amenities or [],
    )


# =============================================================================
# CONFIGURATION VALIDATION
# =============================================================================

def validate_configuration(config: SiteConfiguration) -> Tuple[bool, List[str]]:
    """
    Validate a site configuration.

    Args:
        config: Configuration to validate

    Returns:
        Tuple of (is_valid, list of issues)
    """
    issues = []

    # Check site boundary
    if config.site_boundary.area <= 0:
        issues.append("Site boundary has zero or negative area")

    # Check elements fit within site
    for element in config.elements:
        if not _element_within_site(element, config.site_boundary):
            issues.append(
                f"Element {element.id} extends outside site boundary")

    # Check for overlapping elements
    overlaps = _find_overlapping_elements(config.elements)
    for elem1_id, elem2_id in overlaps:
        issues.append(f"Elements {elem1_id} and {elem2_id} overlap")

    # Check building count
    if len(config.buildings) == 0:
        issues.append("Configuration has no buildings")

    # Calculate and check results
    config.calculate_results()

    # Add compliance issues
    if config.result:
        issues.extend(config.result.compliance_issues)

    return len(issues) == 0, issues


def _element_within_site(element: SiteElement, site_boundary: Polygon) -> bool:
    """Check if element is within site boundary."""
    try:
        from sitefit.core.operations import intersection

        intersect = intersection(element.footprint, site_boundary)
        if intersect is None:
            return False

        # Element should be 95%+ within site
        return intersect.area >= element.area * 0.95
    except Exception:
        return True  # Assume valid if can't check


def _find_overlapping_elements(elements: List[SiteElement]) -> List[Tuple[str, str]]:
    """Find overlapping element pairs."""
    overlaps = []

    try:
        from sitefit.core.operations import intersection

        for i, elem1 in enumerate(elements):
            for elem2 in elements[i + 1:]:
                # Skip certain overlaps (e.g., underground parking can overlap buildings)
                if _can_overlap(elem1, elem2):
                    continue

                intersect = intersection(elem1.footprint, elem2.footprint)
                if intersect and intersect.area > 1:  # More than 1 SF overlap
                    overlaps.append((elem1.id, elem2.id))
    except Exception:
        pass  # Assume no overlaps if can't check

    return overlaps


def _can_overlap(elem1: SiteElement, elem2: SiteElement) -> bool:
    """Check if two elements are allowed to overlap."""
    underground = {ElementType.PARKING_UNDERGROUND}

    # Underground parking can overlap with buildings
    if elem1.element_type in underground or elem2.element_type in underground:
        return True

    return False


# =============================================================================
# CONFIGURATION UTILITIES
# =============================================================================

def configuration_to_dict(config: SiteConfiguration) -> Dict[str, Any]:
    """
    Convert configuration to dictionary for serialization.

    Args:
        config: Configuration to convert

    Returns:
        Dictionary representation
    """
    return config.to_dict()


def configuration_from_dict(data: Dict[str, Any]) -> SiteConfiguration:
    """
    Create configuration from dictionary.

    Args:
        data: Dictionary data

    Returns:
        SiteConfiguration instance
    """
    # Parse site boundary
    boundary_data = data.get("site_boundary")
    if boundary_data:
        site_boundary = Polygon([Point(p[0], p[1]) for p in boundary_data])
    else:
        # Create from site_area if no boundary
        area = data.get("site_area", 10000)
        side = area ** 0.5
        site_boundary = Rectangle(0, 0, side, side).to_polygon()

    config = SiteConfiguration(
        id=data.get("id", "config"),
        name=data.get("name", "Configuration"),
        site_boundary=site_boundary,
        parking_angle=data.get("parking_angle", 90.0),
        building_coverage=data.get("building_coverage", 0.5),
        parking_location=data.get("parking_location", "surface"),
        metadata=data.get("metadata", {}),
    )

    return config


def get_configuration_summary(config: SiteConfiguration) -> Dict[str, Any]:
    """
    Get a summary of configuration metrics.

    Args:
        config: Configuration to summarize

    Returns:
        Summary dictionary
    """
    if not config.result:
        config.calculate_results()

    result = config.result

    return {
        "id": config.id,
        "name": config.name,
        "site_area_sf": round(config.site_area, 0),
        "site_area_acres": round(config.site_area / 43560, 2),
        "building_count": len(config.buildings),
        "total_units": result.total_units if result else 0,
        "total_parking": result.total_parking_spaces if result else 0,
        "far": round(result.far, 2) if result else 0,
        "is_compliant": (
            result.zoning_compliant and
            result.parking_compliant and
            result.height_compliant
        ) if result else True,
        "efficiency_score": round(result.efficiency_score, 1) if result else 0,
    }


def compare_configurations(
    configs: List[SiteConfiguration]
) -> Dict[str, Any]:
    """
    Compare multiple configurations.

    Args:
        configs: List of configurations to compare

    Returns:
        Comparison results
    """
    # Ensure all have results calculated
    for config in configs:
        if not config.result:
            config.calculate_results()

    summaries = [get_configuration_summary(c) for c in configs]

    # Find best by different metrics
    best_units = max(summaries, key=lambda s: s["total_units"])
    best_efficiency = max(summaries, key=lambda s: s["efficiency_score"])
    compliant = [s for s in summaries if s["is_compliant"]]

    return {
        "configurations": summaries,
        "best_by_units": best_units["id"],
        "best_by_efficiency": best_efficiency["id"],
        "compliant_count": len(compliant),
        "total_count": len(configs),
    }
