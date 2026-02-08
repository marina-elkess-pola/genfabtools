"""
Surface Parking Layout Engine
=============================

Generates conceptual parking layouts for surface parking lots.
Supports 90-degree stalls, one-way and two-way aisles, double-loaded bays.

This module produces advisory layouts for feasibility analysis.
Outputs are NOT construction documents.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict
from enum import Enum
import math

from .geometry import (
    Polygon, Point, offset_polygon, offset_polygon_directional, partition_rectangle,
    compute_module_width, rectangles_overlap
)
from .rules import (
    ParkingRules, StallType, AisleDirection,
    calculate_ada_stall_requirement
)


@dataclass
class Stall:
    """
    Individual parking stall.

    For ADA stalls, the access_aisle field contains the geometry of the
    adjacent access aisle. The stall geometry is the parking space only
    (11' × 18'), and the access aisle is separate (5' × 18' for standard
    ADA, 8' × 18' for van-accessible).
    """
    id: str
    geometry: Polygon
    stall_type: StallType
    bay_id: str
    row: str  # "north" or "south" relative to aisle
    access_aisle: Optional[Polygon] = None  # Only for ADA/ADA_VAN stalls

    @property
    def centroid(self) -> Point:
        return self.geometry.centroid

    @property
    def total_width(self) -> float:
        """Total width including access aisle if present."""
        min_x, min_y, max_x, max_y = self.geometry.bounds
        stall_width = max_x - min_x
        if self.access_aisle:
            aisle_min_x, _, aisle_max_x, _ = self.access_aisle.bounds
            aisle_width = aisle_max_x - aisle_min_x
            return stall_width + aisle_width
        return stall_width

    def to_dict(self) -> Dict:
        # Determine layer based on stall type for CAD export
        if self.stall_type in (StallType.ADA, StallType.ADA_VAN):
            layer = "PARKING_STALL_ADA"
        else:
            layer = "PARKING_STALL_STANDARD"

        result = {
            "id": self.id,
            "geometry": self.geometry.to_dict(),
            "stallType": self.stall_type.value,
            "bayId": self.bay_id,
            "layer": layer,
        }
        if self.access_aisle:
            result["accessAisle"] = {
                **self.access_aisle.to_dict(),
                "layer": "PARKING_ACCESS_AISLE",
            }
        return result


@dataclass
class Aisle:
    """Drive aisle between stall rows."""
    id: str
    geometry: Polygon
    direction: AisleDirection
    bay_id: str

    @property
    def length(self) -> float:
        return self.geometry.width

    @property
    def width(self) -> float:
        return self.geometry.height

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "geometry": self.geometry.to_dict(),
            "direction": self.direction.value,
            "layer": "PARKING_AISLES",
        }


@dataclass
class ParkingBay:
    """
    A parking bay consisting of an aisle and stall rows on one or both sides.

    Double-loaded bay: stalls on both sides of aisle
    Single-loaded bay: stalls on one side only
    """
    id: str
    aisle: Aisle
    north_stalls: List[Stall] = field(default_factory=list)
    south_stalls: List[Stall] = field(default_factory=list)

    @property
    def is_double_loaded(self) -> bool:
        return len(self.north_stalls) > 0 and len(self.south_stalls) > 0

    @property
    def stall_count(self) -> int:
        return len(self.north_stalls) + len(self.south_stalls)

    def all_stalls(self) -> List[Stall]:
        return self.north_stalls + self.south_stalls

    def to_dict(self) -> Dict:
        # Combine north and south stalls into single array for frontend
        all_stalls = [s.to_dict() for s in self.all_stalls()]
        return {
            "id": self.id,
            "geometry": self.aisle.geometry.to_dict(),  # Use aisle geometry as bay geometry
            "aisle": self.aisle.to_dict(),
            "stalls": all_stalls,
            "isDoubleLoaded": self.is_double_loaded,
            "stallCount": self.stall_count,
        }


@dataclass
class SurfaceParkingLayout:
    """
    Complete surface parking layout result.

    Contains all generated bays, stalls, and circulation elements.
    """
    site_boundary: Polygon
    net_parking_area: Polygon
    bays: List[ParkingBay]
    drive_lanes: List[Polygon]
    rules: ParkingRules
    aisle_direction: AisleDirection
    orientation: str  # "horizontal" or "vertical"

    @property
    def all_stalls(self) -> List[Stall]:
        stalls = []
        for bay in self.bays:
            stalls.extend(bay.all_stalls())
        return stalls

    @property
    def total_stalls(self) -> int:
        return sum(bay.stall_count for bay in self.bays)

    @property
    def stalls_by_type(self) -> Dict[str, int]:
        counts = {}
        for stall in self.all_stalls:
            key = stall.stall_type.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def to_dict(self) -> Dict:
        return {
            "siteBoundary": {
                **self.site_boundary.to_dict(),
                "layer": "PARKING_SITE_BOUNDARY",
            },
            "netParkingArea": self.net_parking_area.to_dict(),
            "bays": [bay.to_dict() for bay in self.bays],
            "driveLanes": [
                {**dl.to_dict(), "layer": "PARKING_AISLES"}
                for dl in self.drive_lanes
            ],
            "aisleDirection": self.aisle_direction.value,
            "orientation": self.orientation,
            "totalStalls": self.total_stalls,
            "stallsByType": self.stalls_by_type,
        }


def generate_surface_layout(
    site_boundary: Polygon,
    rules: Optional[ParkingRules] = None,
    aisle_direction: AisleDirection = AisleDirection.TWO_WAY,
    setback: Optional[float] = None,
    setbacks: Optional[dict] = None,
    orientation: str = "auto",
    exclusion_zones: Optional[List[Polygon]] = None,
) -> SurfaceParkingLayout:
    """
    Generate a surface parking layout for a given site.

    Args:
        site_boundary: Site polygon (must be rectangular for MVP)
        rules: Parking dimension rules (uses defaults if None)
        aisle_direction: One-way or two-way aisles
        setback: Uniform site setback distance (uses rules default if None)
        setbacks: Per-edge setbacks dict with keys: north, south, east, west
                  If provided, overrides uniform setback
        orientation: "horizontal", "vertical", or "auto" (chooses best)
        exclusion_zones: Areas to exclude from parking (no-build zones)

    Returns:
        SurfaceParkingLayout with generated bays and stalls
    """
    if not site_boundary.is_rectangular:
        raise ValueError("MVP only supports rectangular site boundaries")

    rules = rules or ParkingRules()

    # Step 1: Apply setback(s) to get net parking area
    if setbacks is not None:
        # Per-edge setbacks
        net_parking_area = offset_polygon_directional(
            site_boundary,
            north=setbacks.get("north", 0.0),
            south=setbacks.get("south", 0.0),
            east=setbacks.get("east", 0.0),
            west=setbacks.get("west", 0.0),
        )
        if net_parking_area is None:
            raise ValueError("Setbacks exceed site dimensions")
    else:
        # Uniform setback (legacy behavior)
        setback = setback if setback is not None else rules.setback_default
        net_parking_area = offset_polygon(site_boundary, setback)
        if net_parking_area is None:
            raise ValueError(f"Setback of {setback}' exceeds site dimensions")

    # Step 2: Subtract exclusion zones if any
    if exclusion_zones:
        for zone in exclusion_zones:
            # For MVP, simple subtraction (reduces available area)
            # Complex boolean operations deferred to post-MVP
            pass

    # Step 3: Determine orientation
    if orientation == "auto":
        orientation = _select_orientation(
            net_parking_area, rules, aisle_direction)

    # Step 4: Generate parking bays
    bays = _generate_bays(net_parking_area, rules,
                          aisle_direction, orientation)

    # Step 5: Generate drive lanes (end-of-row circulation)
    drive_lanes = _generate_drive_lanes(
        net_parking_area, bays, rules, orientation)

    # Step 6: Assign ADA stalls
    _assign_ada_stalls(bays, rules)

    # Step 7: Center stall rows within bays to eliminate residual gaps
    _center_rows_in_bays(bays, orientation)

    return SurfaceParkingLayout(
        site_boundary=site_boundary,
        net_parking_area=net_parking_area,
        bays=bays,
        drive_lanes=drive_lanes,
        rules=rules,
        aisle_direction=aisle_direction,
        orientation=orientation,
    )


def _select_orientation(
    net_area: Polygon,
    rules: ParkingRules,
    direction: AisleDirection
) -> str:
    """
    Select optimal bay orientation based on site proportions.

    Aisles should run parallel to the longer dimension for efficiency.
    """
    width = net_area.width
    height = net_area.height

    module_width = rules.get_module_width(direction, double_loaded=True)

    # Check how many modules fit each way
    horizontal_modules = int(height // module_width)
    vertical_modules = int(width // module_width)

    # Prefer orientation that fits more complete modules
    # and has longer aisle runs
    horizontal_score = horizontal_modules * width
    vertical_score = vertical_modules * height

    return "horizontal" if horizontal_score >= vertical_score else "vertical"


def _generate_bays(
    net_area: Polygon,
    rules: ParkingRules,
    direction: AisleDirection,
    orientation: str
) -> List[ParkingBay]:
    """
    Generate parking bays to fill the net parking area.

    Creates double-loaded bays where possible.
    """
    min_x, min_y, max_x, max_y = net_area.bounds

    stall_width = rules.stall_standard.width
    stall_length = rules.stall_standard.length
    aisle_width = rules.get_aisle_width(direction)
    module_width = rules.get_module_width(direction, double_loaded=True)

    bays = []
    bay_index = 0

    if orientation == "horizontal":
        # Aisles run horizontally (left-right), stacked vertically
        available_height = max_y - min_y
        num_modules = int(available_height // module_width)

        # Calculate starting Y to center modules
        total_module_height = num_modules * module_width
        start_y = min_y + (available_height - total_module_height) / 2

        for i in range(num_modules):
            bay_id = f"bay_{bay_index}"
            bay_index += 1

            # Module Y positions
            module_base_y = start_y + i * module_width

            # South stall row
            south_row_min_y = module_base_y
            south_row_max_y = south_row_min_y + stall_length

            # Aisle
            aisle_min_y = south_row_max_y
            aisle_max_y = aisle_min_y + aisle_width

            # North stall row
            north_row_min_y = aisle_max_y
            north_row_max_y = north_row_min_y + stall_length

            # Create aisle geometry
            aisle_geom = Polygon.from_bounds(
                min_x, aisle_min_y, max_x, aisle_max_y)
            aisle = Aisle(
                id=f"aisle_{bay_index}",
                geometry=aisle_geom,
                direction=direction,
                bay_id=bay_id,
            )

            # Generate stalls along the aisle
            north_stalls = _generate_stall_row(
                row_min_x=min_x,
                row_max_x=max_x,
                row_min_y=north_row_min_y,
                row_max_y=north_row_max_y,
                stall_width=stall_width,
                bay_id=bay_id,
                row_name="north",
                orientation="horizontal",
            )

            south_stalls = _generate_stall_row(
                row_min_x=min_x,
                row_max_x=max_x,
                row_min_y=south_row_min_y,
                row_max_y=south_row_max_y,
                stall_width=stall_width,
                bay_id=bay_id,
                row_name="south",
                orientation="horizontal",
            )

            bay = ParkingBay(
                id=bay_id,
                aisle=aisle,
                north_stalls=north_stalls,
                south_stalls=south_stalls,
            )
            bays.append(bay)

    else:  # vertical orientation
        # Aisles run vertically (up-down), stacked horizontally
        available_width = max_x - min_x
        num_modules = int(available_width // module_width)

        # Calculate starting X to center modules
        total_module_width = num_modules * module_width
        start_x = min_x + (available_width - total_module_width) / 2

        for i in range(num_modules):
            bay_id = f"bay_{bay_index}"
            bay_index += 1

            # Module X positions
            module_base_x = start_x + i * module_width

            # West stall row (treated as "south" for naming consistency)
            west_row_min_x = module_base_x
            west_row_max_x = west_row_min_x + stall_length

            # Aisle
            aisle_min_x = west_row_max_x
            aisle_max_x = aisle_min_x + aisle_width

            # East stall row (treated as "north")
            east_row_min_x = aisle_max_x
            east_row_max_x = east_row_min_x + stall_length

            # Create aisle geometry
            aisle_geom = Polygon.from_bounds(
                aisle_min_x, min_y, aisle_max_x, max_y)
            aisle = Aisle(
                id=f"aisle_{bay_index}",
                geometry=aisle_geom,
                direction=direction,
                bay_id=bay_id,
            )

            # Generate stalls along the aisle (rotated 90 degrees)
            east_stalls = _generate_stall_row(
                row_min_x=east_row_min_x,
                row_max_x=east_row_max_x,
                row_min_y=min_y,
                row_max_y=max_y,
                stall_width=stall_width,
                bay_id=bay_id,
                row_name="north",
                orientation="vertical",
            )

            west_stalls = _generate_stall_row(
                row_min_x=west_row_min_x,
                row_max_x=west_row_max_x,
                row_min_y=min_y,
                row_max_y=max_y,
                stall_width=stall_width,
                bay_id=bay_id,
                row_name="south",
                orientation="vertical",
            )

            bay = ParkingBay(
                id=bay_id,
                aisle=aisle,
                north_stalls=east_stalls,
                south_stalls=west_stalls,
            )
            bays.append(bay)

    return bays


def _generate_stall_row(
    row_min_x: float,
    row_max_x: float,
    row_min_y: float,
    row_max_y: float,
    stall_width: float,
    bay_id: str,
    row_name: str,
    orientation: str,
) -> List[Stall]:
    """
    Generate stalls within a row envelope.

    For horizontal orientation: stalls are arranged left-to-right
    For vertical orientation: stalls are arranged bottom-to-top
    """
    stalls = []
    stall_index = 0

    if orientation == "horizontal":
        # Stalls arranged along X axis
        row_length = row_max_x - row_min_x
        num_stalls = int(row_length // stall_width)

        # Center stalls within row
        total_stalls_width = num_stalls * stall_width
        start_x = row_min_x + (row_length - total_stalls_width) / 2

        for i in range(num_stalls):
            stall_min_x = start_x + i * stall_width
            stall_max_x = stall_min_x + stall_width

            geometry = Polygon.from_bounds(
                stall_min_x, row_min_y,
                stall_max_x, row_max_y
            )

            stall = Stall(
                id=f"{bay_id}_{row_name}_{stall_index}",
                geometry=geometry,
                stall_type=StallType.STANDARD,
                bay_id=bay_id,
                row=row_name,
            )
            stalls.append(stall)
            stall_index += 1

    else:  # vertical
        # Stalls arranged along Y axis
        row_length = row_max_y - row_min_y
        num_stalls = int(row_length // stall_width)

        # Center stalls within row
        total_stalls_height = num_stalls * stall_width
        start_y = row_min_y + (row_length - total_stalls_height) / 2

        for i in range(num_stalls):
            stall_min_y = start_y + i * stall_width
            stall_max_y = stall_min_y + stall_width

            geometry = Polygon.from_bounds(
                row_min_x, stall_min_y,
                row_max_x, stall_max_y
            )

            stall = Stall(
                id=f"{bay_id}_{row_name}_{stall_index}",
                geometry=geometry,
                stall_type=StallType.STANDARD,
                bay_id=bay_id,
                row=row_name,
            )
            stalls.append(stall)
            stall_index += 1

    return stalls


def _generate_drive_lanes(
    net_area: Polygon,
    bays: List[ParkingBay],
    rules: ParkingRules,
    orientation: str
) -> List[Polygon]:
    """
    Generate end-of-row drive lanes for circulation.

    Creates drive lanes at the ends of parking bays to allow
    vehicles to circulate between aisles.
    """
    if not bays:
        return []

    min_x, min_y, max_x, max_y = net_area.bounds
    drive_lanes = []

    # For now, reserve space at ends but don't create explicit lane geometry
    # This is implicit in the stall row centering

    return drive_lanes


def _assign_ada_stalls(bays: List[ParkingBay], rules: ParkingRules) -> None:
    """
    Convert standard stalls to ADA stalls based on requirements.

    ADA stalls have two components:
    - Parking stall: 11 ft × 18 ft
    - Access aisle: 5 ft × 18 ft (8 ft for van-accessible)

    Key ADA compliance rules:
    - Access aisles CAN be shared between TWO adjacent ADA stalls
    - Pattern: [Stall A][Shared Aisle][Stall B] - one aisle serves both
    - Van-accessible stall needs 8' aisle

    Optimal packing with shared aisles:
    - Pair stalls to share aisles: [A][aisle][B][aisle][C]...
    - For N stalls: N × 11' + ceil(N/2) × aisle_width
    - Van stall first with 8' aisle, can be shared with next stall

    Example: 1 van + 2 ADA with sharing:
    [Van 11'][8' shared aisle][ADA 11'][5' shared aisle][ADA 11'] = 46'
    Without sharing: 11+8+11+5+11+5 = 51' (5' wasted)
    """
    total_stalls = sum(bay.stall_count for bay in bays)
    ada_req = calculate_ada_stall_requirement(total_stalls)

    total_ada = ada_req["total_ada"]
    van_accessible = ada_req["van_accessible"]

    if total_ada == 0:
        return

    # Get dimension info from rules
    standard_width = rules.stall_standard.width  # 9 ft
    ada_stall_width = rules.stall_ada.stall_width  # 11 ft
    ada_access_aisle = rules.stall_ada.access_aisle_width  # 5 ft
    ada_van_access_aisle = rules.stall_ada_van.access_aisle_width  # 8 ft

    ada_assigned = 0
    van_assigned = 0

    for bay in bays:
        if ada_assigned >= total_ada:
            break

        for row_stalls, row_name in [(bay.south_stalls, "south"), (bay.north_stalls, "north")]:
            if ada_assigned >= total_ada or len(row_stalls) < 2:
                continue

            remaining_ada = total_ada - ada_assigned
            remaining_van = van_accessible - van_assigned

            if len(row_stalls) == 0:
                continue

            # Get orientation info
            first_stall = row_stalls[0]
            min_x, min_y, max_x, max_y = first_stall.geometry.bounds
            stall_current_width = max_x - min_x
            stall_current_height = max_y - min_y
            horizontal_stalls = stall_current_width < stall_current_height

            last_stall = row_stalls[-1]
            last_bounds = last_stall.geometry.bounds

            if horizontal_stalls:
                row_start = min_x
                row_end = last_bounds[2]
                stall_depth = max_y - min_y
            else:
                row_start = min_y
                row_end = last_bounds[3]
                stall_depth = max_x - min_x

            ada_stalls_to_place = min(remaining_ada, len(row_stalls) - 1)
            if ada_stalls_to_place == 0:
                continue

            # Build ADA layout with SHARED aisles
            # Pattern: stalls are placed in pairs sharing an aisle
            # [Stall 0][Aisle 0-1][Stall 1][Aisle 1-2][Stall 2]...
            # Stall 0 and 1 share Aisle 0-1
            # If odd count, last stall gets its own trailing aisle

            elements = []
            current_pos = row_start
            ada_placed = 0
            van_placed = 0

            while ada_placed < ada_stalls_to_place:
                # Determine stall type
                if van_placed < remaining_van:
                    stall_type = StallType.ADA_VAN
                    aisle_width = ada_van_access_aisle  # 8'
                    van_placed += 1
                else:
                    stall_type = StallType.ADA
                    aisle_width = ada_access_aisle  # 5'

                is_last = (ada_placed == ada_stalls_to_place - 1)
                can_share_with_next = not is_last and (
                    ada_placed + 1 < ada_stalls_to_place)

                # Determine space needed and whether this stall shares previous aisle
                # Even-indexed stalls (0, 2, 4...) create a new aisle after them
                # Odd-indexed stalls (1, 3, 5...) share the previous stall's aisle

                is_odd_index = (ada_placed % 2 == 1)
                shares_previous_aisle = is_odd_index and ada_placed > 0

                if is_last:
                    # Last stall always needs a trailing aisle for access
                    if shares_previous_aisle:
                        # Odd-indexed last: shares prev aisle + needs trailing aisle
                        space_needed = ada_stall_width + aisle_width
                        needs_own_aisle = False  # Shares prev, but also gets trailing
                        needs_trailing_aisle = True
                    else:
                        # Even-indexed last: just stall + trailing aisle
                        space_needed = ada_stall_width + aisle_width
                        needs_own_aisle = True
                        needs_trailing_aisle = False  # The "own aisle" IS the trailing
                else:
                    # Not last stall
                    if shares_previous_aisle:
                        # Odd-indexed: just stall, shares previous aisle
                        space_needed = ada_stall_width
                        needs_own_aisle = False
                        needs_trailing_aisle = False
                    else:
                        # Even-indexed: stall + aisle (to be shared with next)
                        space_needed = ada_stall_width + aisle_width
                        needs_own_aisle = True
                        needs_trailing_aisle = False

                if current_pos + space_needed > row_end:
                    break

                # Create stall geometry
                if horizontal_stalls:
                    stall_geom = Polygon.from_bounds(
                        current_pos, min_y,
                        current_pos + ada_stall_width, min_y + stall_depth
                    )
                    if needs_own_aisle:
                        # Create new aisle after this stall
                        aisle_geom = Polygon.from_bounds(
                            current_pos + ada_stall_width, min_y,
                            current_pos + ada_stall_width + aisle_width, min_y + stall_depth
                        )
                    elif needs_trailing_aisle:
                        # Odd-indexed last stall: shares previous aisle but ALSO needs trailing aisle
                        # Create the trailing aisle AFTER this stall
                        # (The stall also uses prev aisle, but we store the trailing one as the primary)
                        aisle_geom = Polygon.from_bounds(
                            current_pos + ada_stall_width, min_y,
                            current_pos + ada_stall_width + aisle_width, min_y + stall_depth
                        )
                    else:
                        # Shared aisle is the PREVIOUS stall's aisle
                        if elements:
                            aisle_geom = elements[-1]['access_aisle']
                        else:
                            aisle_geom = Polygon.from_bounds(
                                current_pos + ada_stall_width, min_y,
                                current_pos + ada_stall_width + aisle_width, min_y + stall_depth
                            )
                else:
                    stall_geom = Polygon.from_bounds(
                        min_x, current_pos,
                        min_x + stall_depth, current_pos + ada_stall_width
                    )
                    if needs_own_aisle:
                        aisle_geom = Polygon.from_bounds(
                            min_x, current_pos + ada_stall_width,
                            min_x + stall_depth, current_pos + ada_stall_width + aisle_width
                        )
                    elif needs_trailing_aisle:
                        # Odd-indexed last stall: create trailing aisle AFTER this stall
                        aisle_geom = Polygon.from_bounds(
                            min_x, current_pos + ada_stall_width,
                            min_x + stall_depth, current_pos + ada_stall_width + aisle_width
                        )
                    else:
                        if elements:
                            aisle_geom = elements[-1]['access_aisle']
                        else:
                            aisle_geom = Polygon.from_bounds(
                                min_x, current_pos + ada_stall_width,
                                min_x + stall_depth, current_pos + ada_stall_width + aisle_width
                            )

                elements.append({
                    'type': stall_type,
                    'geometry': stall_geom,
                    'access_aisle': aisle_geom,
                })

                current_pos += space_needed
                ada_placed += 1

            if ada_placed == 0:
                continue

            # Calculate the actual end of the ADA cluster including the trailing aisle
            # This is the true "consumed width" that standard stalls cannot overlap
            ada_cluster_end = current_pos

            # Also verify by checking the last element's aisle geometry
            if elements:
                last_aisle = elements[-1]['access_aisle']
                if last_aisle:
                    aisle_bounds = last_aisle.bounds
                    # Get the end coordinate based on orientation
                    aisle_end = aisle_bounds[2] if horizontal_stalls else aisle_bounds[3]
                    ada_cluster_end = max(ada_cluster_end, aisle_end)

            # Remove original stalls that overlap with the ADA cluster
            # A stall overlaps if its START is before the ADA cluster end
            original_stalls_consumed = 0
            for stall in row_stalls:
                s_bounds = stall.geometry.bounds
                s_start = s_bounds[0] if horizontal_stalls else s_bounds[1]
                # Consume if stall START is before ADA cluster end
                # (meaning any part of the stall overlaps the ADA area)
                if s_start < ada_cluster_end - 0.01:
                    original_stalls_consumed += 1
                else:
                    break

            for _ in range(min(original_stalls_consumed, len(row_stalls))):
                row_stalls.pop(0)

            # Insert new ADA stalls
            new_stalls = []
            for idx, elem in enumerate(elements):
                new_stall = Stall(
                    id=f"{bay.id}_{row_name}_ada_{idx}",
                    geometry=elem['geometry'],
                    stall_type=elem['type'],
                    bay_id=bay.id,
                    row=row_name,
                    access_aisle=elem['access_aisle']
                )
                new_stalls.append(new_stall)

            for stall in reversed(new_stalls):
                row_stalls.insert(0, stall)

            # Update counters
            ada_assigned += ada_placed
            van_assigned += van_placed


def _center_rows_in_bays(bays: List[ParkingBay], orientation: str) -> None:
    """
    Center stall rows within their bays to eliminate residual gaps.

    After ADA stall placement, there may be gaps between the ADA cluster and
    standard stalls. This function:
    1. First packs standard stalls immediately after ADA stalls (eliminates internal gap)
    2. Then centers the compacted row within the bay bounds.

    Args:
        bays: List of parking bays to process
        orientation: "horizontal" or "vertical" - determines translation axis
    """
    # For vertical bay orientation, stalls run along Y axis (use y-coords)
    # For horizontal bay orientation, stalls run along X axis (use x-coords)
    stalls_along_y = (orientation == "vertical")

    for bay in bays:
        # Use the aisle geometry to determine the bay's length dimension
        aisle_bounds = bay.aisle.geometry.bounds
        if stalls_along_y:
            bay_start = aisle_bounds[1]  # min_y (stalls run along y-axis)
            bay_end = aisle_bounds[3]    # max_y
        else:
            bay_start = aisle_bounds[0]  # min_x (stalls run along x-axis)
            bay_end = aisle_bounds[2]    # max_x

        bay_length = bay_end - bay_start

        for row_name in ["south_stalls", "north_stalls"]:
            row_stalls = getattr(bay, row_name)
            if not row_stalls:
                continue

            # Step 1: Pack standard stalls immediately after ADA stalls
            # Find ADA cluster end and first standard stall position
            ada_cluster_end = None
            first_standard_start = None

            for stall in row_stalls:
                is_ada = 'ada' in stall.stall_type.value.lower()
                bounds = stall.geometry.bounds
                stall_end = bounds[3] if stalls_along_y else bounds[2]
                stall_start = bounds[1] if stalls_along_y else bounds[0]

                if is_ada:
                    # Include access aisle in ADA cluster end
                    if stall.access_aisle:
                        aisle_b = stall.access_aisle.bounds
                        aisle_end = aisle_b[3] if stalls_along_y else aisle_b[2]
                        stall_end = max(stall_end, aisle_end)
                    if ada_cluster_end is None or stall_end > ada_cluster_end:
                        ada_cluster_end = stall_end
                else:
                    if first_standard_start is None or stall_start < first_standard_start:
                        first_standard_start = stall_start

            # If there's a gap between ADA cluster and standard stalls, close it
            if ada_cluster_end is not None and first_standard_start is not None:
                gap = first_standard_start - ada_cluster_end
                if gap > 0.01:
                    # Shift all standard stalls backward by gap amount
                    for stall in row_stalls:
                        is_ada = 'ada' in stall.stall_type.value.lower()
                        if not is_ada:
                            stall.geometry = _translate_polygon(
                                stall.geometry,
                                dy=-gap if stalls_along_y else 0,
                                dx=-gap if not stalls_along_y else 0
                            )
                            if stall.access_aisle:
                                stall.access_aisle = _translate_polygon(
                                    stall.access_aisle,
                                    dy=-gap if stalls_along_y else 0,
                                    dx=-gap if not stalls_along_y else 0
                                )

            # Step 2: Now center the compacted row within the bay
            # Recompute the row's actual extent
            row_min = float('inf')
            row_max = float('-inf')

            for stall in row_stalls:
                bounds = stall.geometry.bounds
                if stalls_along_y:
                    row_min = min(row_min, bounds[1])  # min_y
                    row_max = max(row_max, bounds[3])  # max_y
                else:
                    row_min = min(row_min, bounds[0])  # min_x
                    row_max = max(row_max, bounds[2])  # max_x

                # Include access aisle in extent calculation
                if stall.access_aisle:
                    aisle_b = stall.access_aisle.bounds
                    if stalls_along_y:
                        row_min = min(row_min, aisle_b[1])
                        row_max = max(row_max, aisle_b[3])
                    else:
                        row_min = min(row_min, aisle_b[0])
                        row_max = max(row_max, aisle_b[2])
            row_length = row_max - row_min
            residual = bay_length - row_length

            # Only center if there's meaningful residual space
            if residual < 0.5:
                continue

            # Calculate offset to center the row
            current_offset = row_min - bay_start
            target_offset = residual / 2
            translation = target_offset - current_offset

            if abs(translation) < 0.01:
                continue

            # Translate all stall geometries
            for stall in row_stalls:
                stall.geometry = _translate_polygon(
                    stall.geometry,
                    dy=translation if stalls_along_y else 0,
                    dx=translation if not stalls_along_y else 0
                )
                if stall.access_aisle:
                    stall.access_aisle = _translate_polygon(
                        stall.access_aisle,
                        dy=translation if stalls_along_y else 0,
                        dx=translation if not stalls_along_y else 0
                    )


def _translate_polygon(poly: Polygon, dx: float = 0, dy: float = 0) -> Polygon:
    """
    Translate a polygon by (dx, dy).

    Args:
        poly: The polygon to translate
        dx: Translation in x direction
        dy: Translation in y direction

    Returns:
        New polygon with translated coordinates
    """
    new_vertices = [Point(v.x + dx, v.y + dy) for v in poly.vertices]
    return Polygon(new_vertices)


def evaluate_layout_options(
    site_boundary: Polygon,
    rules: Optional[ParkingRules] = None,
    setback: Optional[float] = None,
) -> List[Tuple[SurfaceParkingLayout, str]]:
    """
    Generate and compare multiple layout options.

    Creates layouts with different orientations and aisle configurations,
    returning them ranked by stall count.

    Args:
        site_boundary: Site polygon
        rules: Parking dimension rules
        setback: Site setback distance

    Returns:
        List of (layout, description) tuples, sorted by stall count descending
    """
    rules = rules or ParkingRules()
    options = []

    configurations = [
        (AisleDirection.TWO_WAY, "horizontal", "Two-way horizontal"),
        (AisleDirection.TWO_WAY, "vertical", "Two-way vertical"),
        (AisleDirection.ONE_WAY, "horizontal", "One-way horizontal"),
        (AisleDirection.ONE_WAY, "vertical", "One-way vertical"),
    ]

    for direction, orientation, description in configurations:
        try:
            layout = generate_surface_layout(
                site_boundary=site_boundary,
                rules=rules,
                aisle_direction=direction,
                setback=setback,
                orientation=orientation,
            )
            options.append((layout, description))
        except ValueError:
            # Configuration doesn't fit site
            continue

    # Sort by stall count (descending)
    options.sort(key=lambda x: x[0].total_stalls, reverse=True)

    return options


# =============================================================================
# IRREGULAR GEOMETRY SUPPORT
# =============================================================================

@dataclass
class IrregularLayoutResult:
    """
    Result of generating parking layout for an irregular site.

    Extends SurfaceParkingLayout with zone-level decomposition data.
    """
    layout: SurfaceParkingLayout
    zones: List["ParkingZone"]
    decomposition_metrics: dict
    zone_layouts: List[SurfaceParkingLayout]

    @property
    def total_stalls(self) -> int:
        return self.layout.total_stalls

    @property
    def usability_ratio(self) -> float:
        return self.decomposition_metrics.get("usability_ratio", 0.0)

    def to_dict(self) -> dict:
        result = self.layout.to_dict()
        result["decomposition"] = self.decomposition_metrics
        result["zone_count"] = len(self.zones)
        return result


def generate_surface_layout_irregular(
    site_boundary: Polygon,
    rules: Optional[ParkingRules] = None,
    aisle_direction: AisleDirection = AisleDirection.TWO_WAY,
    setback: Optional[float] = None,
    voids: Optional[List[Polygon]] = None,
    min_zone_width: float = 40.0,
    min_zone_area: float = 1000.0,
) -> IrregularLayoutResult:
    """
    Generate surface parking layout for irregular site geometries.

    Handles L-shaped sites, sites with internal voids, concave polygons,
    and other non-rectangular geometries through rectangular decomposition.

    Strategy:
    1. Decompose irregular site into rectangular zones
    2. Apply standard layout engine to each parkable zone
    3. Aggregate stalls, aisles, and bays into unified layout
    4. Validate no stalls extend outside original boundary

    Args:
        site_boundary: Site polygon (may be irregular)
        rules: Parking dimension rules
        aisle_direction: Aisle traffic direction
        setback: Setback from site edges (applied to decomposed zones)
        voids: Internal exclusion polygons (cut-outs)
        min_zone_width: Minimum width for parkable zone (feet)
        min_zone_area: Minimum area for parkable zone (square feet)

    Returns:
        IrregularLayoutResult with aggregated layout and decomposition metrics

    Note:
        For rectangular sites, this delegates to generate_surface_layout.
        All outputs are conceptual and advisory.
    """
    from .irregular import (
        extract_parking_zones,
        ZoneType,
        ParkingZone,
        validate_stalls_within_boundary,
        compute_geometry_loss,
    )

    rules = rules or ParkingRules()
    voids = voids or []

    # If site is rectangular, use standard layout
    if site_boundary.is_rectangular and not voids:
        standard_layout = generate_surface_layout(
            site_boundary=site_boundary,
            rules=rules,
            aisle_direction=aisle_direction,
            setback=setback,
        )

        from .irregular import ParkingZone, ZoneType
        zone = ParkingZone(
            id="zone_0",
            geometry=site_boundary,
            zone_type=ZoneType.RECTANGULAR,
        )

        return IrregularLayoutResult(
            layout=standard_layout,
            zones=[zone],
            decomposition_metrics={
                "original_area_sf": site_boundary.area,
                "parkable_area_sf": site_boundary.area,
                "unusable_area_sf": 0.0,
                "usability_ratio": 1.0,
                "zone_count": 1,
            },
            zone_layouts=[standard_layout],
        )

    # Decompose irregular site into rectangular zones
    decomposition = extract_parking_zones(
        polygon=site_boundary,
        voids=voids,
        min_zone_width=min_zone_width,
        min_zone_area=min_zone_area,
    )

    # Generate layout for each parkable zone
    zone_layouts: List[SurfaceParkingLayout] = []
    all_bays: List[ParkingBay] = []
    bay_counter = 0

    for zone in decomposition.zones:
        if not zone.is_parkable:
            continue

        try:
            # Generate layout for this zone
            zone_layout = generate_surface_layout(
                site_boundary=zone.geometry,
                rules=rules,
                aisle_direction=aisle_direction,
                setback=setback,
            )

            # Rename bays to avoid ID conflicts
            for bay in zone_layout.bays:
                # Update bay ID with zone prefix
                new_bay_id = f"zone{zone.id}_{bay.id}"
                bay.id = new_bay_id
                bay.aisle.bay_id = new_bay_id

                for stall in bay.north_stalls:
                    stall.bay_id = new_bay_id
                for stall in bay.south_stalls:
                    stall.bay_id = new_bay_id

                all_bays.append(bay)
                bay_counter += 1

            zone_layouts.append(zone_layout)

        except ValueError:
            # Zone too small for parking configuration
            continue

    # Validate stalls are within original boundary
    all_stalls = []
    for bay in all_bays:
        all_stalls.extend(bay.north_stalls)
        all_stalls.extend(bay.south_stalls)

    valid_stalls, invalid_stalls = validate_stalls_within_boundary(
        stalls=all_stalls,
        boundary=site_boundary,
    )

    # Remove invalid stalls from bays
    if invalid_stalls:
        invalid_ids = {s.id for s in invalid_stalls}
        for bay in all_bays:
            bay.north_stalls = [
                s for s in bay.north_stalls if s.id not in invalid_ids]
            bay.south_stalls = [
                s for s in bay.south_stalls if s.id not in invalid_ids]

    # Determine orientation from zone layouts
    orientation = "horizontal"
    if zone_layouts:
        orientation = zone_layouts[0].orientation

    # Collect drive lanes from all zone layouts
    all_drive_lanes = []
    for zl in zone_layouts:
        all_drive_lanes.extend(zl.drive_lanes)

    # Create aggregated layout
    aggregated_layout = SurfaceParkingLayout(
        site_boundary=site_boundary,
        net_parking_area=site_boundary,  # Use original boundary
        bays=all_bays,
        drive_lanes=all_drive_lanes,
        rules=rules,
        aisle_direction=aisle_direction,
        orientation=orientation,
    )

    # Compute decomposition metrics
    decomp_metrics = compute_geometry_loss(site_boundary, decomposition.zones)
    decomp_metrics["zone_count"] = len(decomposition.zones)
    decomp_metrics["parkable_zones"] = sum(
        1 for z in decomposition.zones if z.is_parkable)
    decomp_metrics["void_count"] = len(voids)
    decomp_metrics["stalls_removed"] = len(invalid_stalls)

    return IrregularLayoutResult(
        layout=aggregated_layout,
        zones=decomposition.zones,
        decomposition_metrics=decomp_metrics,
        zone_layouts=zone_layouts,
    )
