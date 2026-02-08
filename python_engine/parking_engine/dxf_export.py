"""
DXF Export Module
=================

Exports parking layouts to DXF format for CAD interoperability.

Uses ezdxf library to create AutoCAD-compatible DXF files
that open cleanly in Rhino, AutoCAD, and other CAD software.

COORDINATE SYSTEM
-----------------
- All geometry is exported in LOCAL PROJECT COORDINATES
- Origin (0,0) is placed at the lower-left corner of the site boundary
- All coordinates are positive (first quadrant only)
- NO survey alignment, shared coordinates, or project base points

UNITS
-----
- 1 drawing unit = 1 foot
- DXF $INSUNITS header is set to 2 (feet)
- All stall dimensions, setbacks, and aisles are in feet

ORIENTATION
-----------
- Screen-based orientation (NOT geographic north)
- North = top of the drawing (+Y direction)
- East = right of the drawing (+X direction)
- No rotation applied; geometry matches screen display

OUTPUT
------
- All geometry exported as closed LWPOLYLINEs on semantic layers
- A metadata note is placed on a non-print layer (PARKING_NOTES)
- Output is suitable for import into any CAD/BIM as a schematic block

This is CONCEPTUAL FEASIBILITY output only. Architects should
reposition and align as needed in their production environment.
"""

from __future__ import annotations
from typing import List, Optional, Union, BinaryIO, Tuple
from io import StringIO
import tempfile
import os

import ezdxf
from ezdxf import units
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace

from .geometry import Polygon, Point
from .layout import SurfaceParkingLayout, ParkingBay, Stall, Aisle
from .rules import StallType


# CAD Layer names - exact match for frontend/backend consistency
LAYER_SITE_BOUNDARY = "PARKING_SITE_BOUNDARY"
# Post-setback parkable boundary
LAYER_SETBACK_ENVELOPE = "PARKING_SETBACK_ENVELOPE"
LAYER_STALL_STANDARD = "PARKING_STALL_STANDARD"
LAYER_STALL_ADA = "PARKING_STALL_ADA"
LAYER_ACCESS_AISLE = "PARKING_ACCESS_AISLE"
LAYER_AISLES = "PARKING_AISLES"
LAYER_RAMPS = "PARKING_RAMPS"
LAYER_CORES = "PARKING_CORES"
LAYER_NOTES = "PARKING_NOTES"  # Non-print metadata layer

# Layer colors (AutoCAD Color Index)
# Using distinct colors for visual clarity in CAD
LAYER_COLORS = {
    LAYER_SITE_BOUNDARY: 7,    # White
    LAYER_SETBACK_ENVELOPE: 8,  # Gray (neutral, thin, dashed)
    LAYER_STALL_STANDARD: 3,   # Green
    LAYER_STALL_ADA: 5,        # Blue
    LAYER_ACCESS_AISLE: 4,     # Cyan
    LAYER_AISLES: 1,           # Red
    LAYER_RAMPS: 6,            # Magenta
    LAYER_CORES: 2,            # Yellow
    LAYER_NOTES: 8,            # Gray (non-print)
}

# Metadata note text - placed at origin on PARKING_NOTES layer
METADATA_NOTE = """DXF geometry is generated in local project coordinates.
Origin (0,0) = lower-left corner of site boundary.
Units: feet. Orientation is screen-based (North = +Y).
Conceptual feasibility output only.

PARKING_SETBACK_ENVELOPE shows the area available for parking after setbacks."""


def _compute_origin_offset(polygon: Polygon) -> Tuple[float, float]:
    """
    Compute the offset to translate geometry so that the
    lower-left corner of the site boundary is at (0,0).

    Returns:
        (dx, dy) - the offset to SUBTRACT from all coordinates
    """
    if not polygon.vertices:
        return (0.0, 0.0)

    min_x = min(v.x for v in polygon.vertices)
    min_y = min(v.y for v in polygon.vertices)

    return (min_x, min_y)


def _translate_polygon(polygon: Polygon, offset: Tuple[float, float]) -> Polygon:
    """
    Translate a polygon by subtracting the offset.
    Returns a new Polygon with all coordinates shifted.
    """
    dx, dy = offset
    new_vertices = [Point(v.x - dx, v.y - dy) for v in polygon.vertices]
    return Polygon(new_vertices)


def _create_layers(doc: Drawing) -> None:
    """
    Create all parking layers with assigned colors.

    The PARKING_NOTES and PARKING_SETBACK_ENVELOPE layers are set to non-plotting.
    The setback envelope uses a dashed linetype for visual distinction.
    """
    # Ensure DASHED linetype exists for setback envelope
    if "DASHED" not in doc.linetypes:
        # Standard DXF DASHED pattern: dash length 0.5, gap 0.25
        doc.linetypes.add("DASHED", pattern=[0.5, 0.25, -0.25])

    for layer_name, color in LAYER_COLORS.items():
        layer = doc.layers.add(layer_name, color=color)

        # Set notes layer to non-plotting (won't appear in prints)
        if layer_name == LAYER_NOTES:
            layer.dxf.plot = 0  # 0 = don't plot

        # Setback envelope: dashed, thin, non-print intent
        if layer_name == LAYER_SETBACK_ENVELOPE:
            layer.dxf.linetype = "DASHED"
            layer.dxf.plot = 0  # Non-print (verification only)
            layer.dxf.lineweight = 9  # Thin line (0.09mm)


def _add_metadata_note(msp: Modelspace) -> None:
    """
    Add metadata text note at origin on the non-print notes layer.

    This provides documentation about coordinate system, units,
    and orientation for anyone opening the DXF.
    """
    # Place text slightly offset from origin for visibility
    msp.add_mtext(
        METADATA_NOTE,
        dxfattribs={
            "layer": LAYER_NOTES,
            "insert": (0, -10),  # Below the origin
            "char_height": 2.0,  # 2 ft text height
        }
    )


def _polygon_to_points(polygon: Polygon) -> List[tuple]:
    """Convert Polygon to list of (x, y) tuples for DXF polyline."""
    return [(v.x, v.y) for v in polygon.vertices]


def _add_closed_polyline(msp: Modelspace, polygon: Polygon, layer: str) -> None:
    """Add a closed polyline to modelspace on the specified layer."""
    points = _polygon_to_points(polygon)
    msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})


def _export_stall(msp: Modelspace, stall: Stall) -> None:
    """Export a single stall (and its access aisle if present)."""
    # Determine layer based on stall type
    if stall.stall_type in (StallType.ADA, StallType.ADA_VAN):
        layer = LAYER_STALL_ADA
    else:
        layer = LAYER_STALL_STANDARD

    # Export stall geometry
    _add_closed_polyline(msp, stall.geometry, layer)

    # Export access aisle if present
    if stall.access_aisle:
        _add_closed_polyline(msp, stall.access_aisle, LAYER_ACCESS_AISLE)


def _export_bay(msp: Modelspace, bay: ParkingBay) -> None:
    """Export a parking bay (aisle + all stalls)."""
    # Export drive aisle
    _add_closed_polyline(msp, bay.aisle.geometry, LAYER_AISLES)

    # Export all stalls
    for stall in bay.all_stalls():
        _export_stall(msp, stall)


def export_surface_layout_to_dxf(
    layout: SurfaceParkingLayout,
    output: Optional[Union[str, BinaryIO]] = None,
) -> bytes:
    """
    Export a surface parking layout to DXF format.

    Args:
        layout: The SurfaceParkingLayout to export
        output: Optional file path or file-like object to write to.
                If None, returns bytes.

    Returns:
        DXF file contents as bytes (if output is None)

    COORDINATE SYSTEM:
        - Origin (0,0) = lower-left corner of site boundary
        - All coordinates are positive (geometry is translated)
        - 1 unit = 1 foot (DXF $INSUNITS = 2)
        - Orientation is screen-based (North = +Y)

    LAYERS:
        - PARKING_SITE_BOUNDARY: Site boundary polygon
        - PARKING_SETBACK_ENVELOPE: Post-setback parkable area (dashed, non-print)
        - PARKING_STALL_STANDARD: Standard parking stalls
        - PARKING_STALL_ADA: ADA accessible stalls
        - PARKING_ACCESS_AISLE: ADA access aisles (hatched area)
        - PARKING_AISLES: Drive aisles and lanes
        - PARKING_NOTES: Metadata text (non-printing)

    All geometry is exported as closed LWPOLYLINEs.
    """
    # Create new DXF document (R2010 for broad compatibility)
    doc = ezdxf.new("R2010")

    # Set units to feet (engineering/architectural)
    # $INSUNITS = 2 means feet
    doc.units = units.FT
    doc.header['$INSUNITS'] = 2  # Explicitly set insertion units to feet

    # Create semantic layers (including non-print notes layer)
    _create_layers(doc)

    # Get modelspace
    msp = doc.modelspace()

    # =========================================================================
    # COORDINATE NORMALIZATION
    # Translate all geometry so that the lower-left corner of the site
    # boundary is at origin (0,0). This ensures positive coordinates only
    # and makes the DXF easy to reposition in any CAD environment.
    # =========================================================================
    offset = _compute_origin_offset(layout.site_boundary)

    # Export site boundary (translated)
    translated_site = _translate_polygon(layout.site_boundary, offset)
    _add_closed_polyline(msp, translated_site, LAYER_SITE_BOUNDARY)

    # =========================================================================
    # SETBACK ENVELOPE
    # Export the post-setback parkable boundary (net_parking_area)
    # This is the exact polygon used for layout generation - no recomputation.
    # Displayed as dashed gray line for architect verification.
    # =========================================================================
    translated_setback_envelope = _translate_polygon(
        layout.net_parking_area, offset)
    _add_closed_polyline(msp, translated_setback_envelope,
                         LAYER_SETBACK_ENVELOPE)

    # Export all bays (aisles + stalls) - need to translate each geometry
    for bay in layout.bays:
        # Translate aisle
        translated_aisle = _translate_polygon(bay.aisle.geometry, offset)
        _add_closed_polyline(msp, translated_aisle, LAYER_AISLES)

        # Translate and export each stall
        for stall in bay.all_stalls():
            translated_stall_geom = _translate_polygon(stall.geometry, offset)

            # Determine layer based on stall type
            if stall.stall_type in (StallType.ADA, StallType.ADA_VAN):
                layer = LAYER_STALL_ADA
            else:
                layer = LAYER_STALL_STANDARD

            _add_closed_polyline(msp, translated_stall_geom, layer)

            # Export access aisle if present
            if stall.access_aisle:
                translated_access = _translate_polygon(
                    stall.access_aisle, offset)
                _add_closed_polyline(
                    msp, translated_access, LAYER_ACCESS_AISLE)

    # Export drive lanes (translated)
    for drive_lane in layout.drive_lanes:
        translated_lane = _translate_polygon(drive_lane, offset)
        _add_closed_polyline(msp, translated_lane, LAYER_AISLES)

    # Add metadata note (explains coordinate system, units, orientation)
    _add_metadata_note(msp)

    # Handle output
    if output is None:
        # Return as bytes using a temp file (ezdxf write() needs text stream)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dxf', delete=False) as f:
            temp_path = f.name
        try:
            doc.saveas(temp_path)
            with open(temp_path, 'rb') as f:
                return f.read()
        finally:
            os.unlink(temp_path)
    elif isinstance(output, str):
        # Write to file path
        doc.saveas(output)
        return b""
    else:
        # Write to file-like object (must be text mode)
        stream = StringIO()
        doc.write(stream)
        output.write(stream.getvalue().encode('utf-8'))
        return b""


def export_layout_dict_to_dxf(layout_dict: dict) -> bytes:
    """
    Export a layout from its dictionary representation to DXF.

    This is useful when working with JSON/API responses rather than
    the native SurfaceParkingLayout object.

    Args:
        layout_dict: The layout as returned by SurfaceParkingLayout.to_dict()

    Returns:
        DXF file contents as bytes

    COORDINATE SYSTEM:
        - Origin (0,0) = lower-left corner of site boundary
        - All coordinates are positive (geometry is translated)
        - 1 unit = 1 foot (DXF $INSUNITS = 2)
        - Orientation is screen-based (North = +Y)
    """
    from .geometry import Polygon, Point

    # Create new DXF document
    doc = ezdxf.new("R2010")
    doc.units = units.FT
    doc.header['$INSUNITS'] = 2  # Explicitly set insertion units to feet
    _create_layers(doc)
    msp = doc.modelspace()

    # =========================================================================
    # COORDINATE NORMALIZATION
    # Compute offset to place lower-left corner of site at origin (0,0)
    # =========================================================================
    offset_x, offset_y = 0.0, 0.0
    if "siteBoundary" in layout_dict:
        vertices = layout_dict["siteBoundary"].get("vertices", [])
        if vertices:
            offset_x = min(v["x"] for v in vertices)
            offset_y = min(v["y"] for v in vertices)

    # Helper to convert geometry dict to translated points
    def geom_to_points(geom: dict) -> List[tuple]:
        vertices = geom.get("vertices", [])
        # Translate all points by subtracting offset
        return [(v["x"] - offset_x, v["y"] - offset_y) for v in vertices]

    # Export site boundary (translated)
    if "siteBoundary" in layout_dict:
        points = geom_to_points(layout_dict["siteBoundary"])
        if points:
            msp.add_lwpolyline(points, close=True, dxfattribs={
                               "layer": LAYER_SITE_BOUNDARY})

    # Export setback envelope (net parking area) - translated
    # This is the exact polygon used for layout, no recomputation
    if "netParkingArea" in layout_dict:
        points = geom_to_points(layout_dict["netParkingArea"])
        if points:
            msp.add_lwpolyline(points, close=True, dxfattribs={
                               "layer": LAYER_SETBACK_ENVELOPE})

    # Export bays (translated)
    for bay in layout_dict.get("bays", []):
        # Export aisle
        if "aisle" in bay and "geometry" in bay["aisle"]:
            points = geom_to_points(bay["aisle"]["geometry"])
            if points:
                msp.add_lwpolyline(points, close=True, dxfattribs={
                                   "layer": LAYER_AISLES})

        # Export stalls
        for stall in bay.get("stalls", []):
            # Determine layer from stall type
            stall_type = stall.get("stallType", "standard")
            if "ada" in stall_type.lower():
                layer = LAYER_STALL_ADA
            else:
                layer = LAYER_STALL_STANDARD

            # Export stall geometry (translated)
            if "geometry" in stall:
                points = geom_to_points(stall["geometry"])
                if points:
                    msp.add_lwpolyline(points, close=True,
                                       dxfattribs={"layer": layer})

            # Export access aisle (translated)
            if "accessAisle" in stall:
                points = geom_to_points(stall["accessAisle"])
                if points:
                    msp.add_lwpolyline(points, close=True, dxfattribs={
                                       "layer": LAYER_ACCESS_AISLE})

    # Export drive lanes (translated)
    for drive_lane in layout_dict.get("driveLanes", []):
        points = geom_to_points(drive_lane)
        if points:
            msp.add_lwpolyline(points, close=True, dxfattribs={
                               "layer": LAYER_AISLES})

    # Add metadata note (explains coordinate system, units, orientation)
    _add_metadata_note(msp)

    # Return as bytes using a temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.dxf', delete=False) as f:
        temp_path = f.name
    try:
        doc.saveas(temp_path)
        with open(temp_path, 'rb') as f:
            return f.read()
    finally:
        os.unlink(temp_path)
