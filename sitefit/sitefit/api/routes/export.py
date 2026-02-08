"""
api/routes/export.py - Export API Routes

Endpoints for exporting site configurations in various formats.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, Response
from typing import Dict, Any, List
import json

from sitefit.api.schemas import (
    ExportRequest,
    ExportResponse,
    ExportFormatEnum,
    PolygonSchema,
    PointSchema
)
from sitefit.core.geometry import Point, Polygon

router = APIRouter()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def polygon_to_geojson_coords(polygon: Polygon) -> List[List[List[float]]]:
    """Convert Polygon to GeoJSON coordinates."""
    coords = [[v.x, v.y] for v in polygon.vertices]
    # Close the ring
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return [coords]


def create_geojson_feature(
    geometry_type: str,
    coordinates: Any,
    properties: Dict[str, Any]
) -> Dict[str, Any]:
    """Create a GeoJSON feature."""
    return {
        "type": "Feature",
        "geometry": {
            "type": geometry_type,
            "coordinates": coordinates
        },
        "properties": properties
    }


def create_dxf_polygon(points: List[Point], layer: str = "0") -> str:
    """Create DXF LWPOLYLINE entity."""
    lines = []
    lines.append("0")
    lines.append("LWPOLYLINE")
    lines.append("8")
    lines.append(layer)
    lines.append("90")
    lines.append(str(len(points)))
    lines.append("70")
    lines.append("1")  # Closed polyline

    for p in points:
        lines.append("10")
        lines.append(str(p.x))
        lines.append("20")
        lines.append(str(p.y))

    return "\n".join(lines)


def create_svg_polygon(points: List[Point], fill: str, stroke: str) -> str:
    """Create SVG polygon element."""
    point_str = " ".join(f"{p.x},{p.y}" for p in points)
    return f'<polygon points="{point_str}" fill="{fill}" stroke="{stroke}" stroke-width="1"/>'


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/json")
async def export_json(
    site_boundary: PolygonSchema,
    building_footprint: PolygonSchema = None,
    parking_areas: List[PolygonSchema] = None,
    metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Export configuration as JSON.

    Returns a structured JSON representation of the site configuration.
    """
    result = {
        "format": "json",
        "version": "1.0",
        "site": {
            "boundary": {
                "points": [{"x": p.x, "y": p.y} for p in site_boundary.points]
            }
        }
    }

    if building_footprint:
        result["building"] = {
            "footprint": {
                "points": [{"x": p.x, "y": p.y} for p in building_footprint.points]
            }
        }

    if parking_areas:
        result["parking"] = {
            "areas": [
                {"points": [{"x": p.x, "y": p.y} for p in area.points]}
                for area in parking_areas
            ]
        }

    if metadata:
        result["metadata"] = metadata

    return result


@router.post("/geojson")
async def export_geojson(
    site_boundary: PolygonSchema,
    building_footprint: PolygonSchema = None,
    parking_areas: List[PolygonSchema] = None
) -> Dict[str, Any]:
    """
    Export configuration as GeoJSON FeatureCollection.

    Compatible with GIS tools and mapping applications.
    """
    features = []

    # Site boundary
    boundary_points = [Point(p.x, p.y) for p in site_boundary.points]
    boundary_polygon = Polygon(boundary_points)

    site_coords = polygon_to_geojson_coords(boundary_polygon)
    features.append(create_geojson_feature(
        "Polygon",
        site_coords,
        {"type": "site_boundary", "layer": "site"}
    ))

    # Building footprint
    if building_footprint:
        building_points = [Point(p.x, p.y) for p in building_footprint.points]
        building_polygon = Polygon(building_points)
        building_coords = polygon_to_geojson_coords(building_polygon)
        features.append(create_geojson_feature(
            "Polygon",
            building_coords,
            {"type": "building_footprint", "layer": "building"}
        ))

    # Parking areas
    if parking_areas:
        for i, area in enumerate(parking_areas):
            area_points = [Point(p.x, p.y) for p in area.points]
            area_polygon = Polygon(area_points)
            area_coords = polygon_to_geojson_coords(area_polygon)
            features.append(create_geojson_feature(
                "Polygon",
                area_coords,
                {"type": "parking_area", "layer": "parking", "index": i}
            ))

    return {
        "type": "FeatureCollection",
        "features": features
    }


@router.post("/dxf", response_class=PlainTextResponse)
async def export_dxf(
    site_boundary: PolygonSchema,
    building_footprint: PolygonSchema = None,
    parking_areas: List[PolygonSchema] = None
) -> str:
    """
    Export configuration as DXF (AutoCAD format).

    Returns a DXF file string that can be imported into CAD software.
    """
    lines = []

    # Header
    lines.append("0")
    lines.append("SECTION")
    lines.append("2")
    lines.append("HEADER")
    lines.append("0")
    lines.append("ENDSEC")

    # Tables section (minimal)
    lines.append("0")
    lines.append("SECTION")
    lines.append("2")
    lines.append("TABLES")
    lines.append("0")
    lines.append("ENDSEC")

    # Entities section
    lines.append("0")
    lines.append("SECTION")
    lines.append("2")
    lines.append("ENTITIES")

    # Site boundary
    site_points = [Point(p.x, p.y) for p in site_boundary.points]
    lines.append(create_dxf_polygon(site_points, "SITE"))

    # Building footprint
    if building_footprint:
        building_points = [Point(p.x, p.y) for p in building_footprint.points]
        lines.append(create_dxf_polygon(building_points, "BUILDING"))

    # Parking areas
    if parking_areas:
        for area in parking_areas:
            area_points = [Point(p.x, p.y) for p in area.points]
            lines.append(create_dxf_polygon(area_points, "PARKING"))

    # End entities
    lines.append("0")
    lines.append("ENDSEC")

    # EOF
    lines.append("0")
    lines.append("EOF")

    return "\n".join(lines)


@router.post("/svg", response_class=Response)
async def export_svg(
    site_boundary: PolygonSchema,
    building_footprint: PolygonSchema = None,
    parking_areas: List[PolygonSchema] = None,
    width: int = 800,
    height: int = 600
) -> Response:
    """
    Export configuration as SVG.

    Returns an SVG image suitable for web display or print.
    """
    # Calculate bounding box
    all_x = [p.x for p in site_boundary.points]
    all_y = [p.y for p in site_boundary.points]

    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)

    # Add padding
    padding = 20
    view_width = max_x - min_x + 2 * padding
    view_height = max_y - min_y + 2 * padding

    # SVG header
    svg_parts = [
        f'<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="{min_x - padding} {min_y - padding} {view_width} {view_height}">',
        '<style>',
        '  .site { fill: #f0f0f0; stroke: #333; stroke-width: 2; }',
        '  .building { fill: #3b82f6; stroke: #1d4ed8; stroke-width: 1; opacity: 0.8; }',
        '  .parking { fill: #94a3b8; stroke: #64748b; stroke-width: 0.5; }',
        '</style>',
        '<g transform="scale(1,-1)" transform-origin="center">'  # Flip Y axis
    ]

    # Site boundary
    site_points = [Point(p.x, p.y) for p in site_boundary.points]
    point_str = " ".join(f"{p.x},{p.y}" for p in site_points)
    svg_parts.append(f'<polygon class="site" points="{point_str}"/>')

    # Parking areas (draw first so building is on top)
    if parking_areas:
        for area in parking_areas:
            area_points = [Point(p.x, p.y) for p in area.points]
            point_str = " ".join(f"{p.x},{p.y}" for p in area_points)
            svg_parts.append(
                f'<polygon class="parking" points="{point_str}"/>')

    # Building footprint
    if building_footprint:
        building_points = [Point(p.x, p.y) for p in building_footprint.points]
        point_str = " ".join(f"{p.x},{p.y}" for p in building_points)
        svg_parts.append(f'<polygon class="building" points="{point_str}"/>')

    # Close SVG
    svg_parts.append('</g>')
    svg_parts.append('</svg>')

    svg_content = "\n".join(svg_parts)

    return Response(
        content=svg_content,
        media_type="image/svg+xml",
        headers={"Content-Disposition": "attachment; filename=sitefit_export.svg"}
    )


@router.get("/formats")
async def get_export_formats() -> Dict[str, Any]:
    """Get available export formats and their descriptions."""
    return {
        "json": {
            "extension": ".json",
            "mime_type": "application/json",
            "description": "Standard JSON format with structured site data"
        },
        "geojson": {
            "extension": ".geojson",
            "mime_type": "application/geo+json",
            "description": "GeoJSON FeatureCollection for GIS applications"
        },
        "dxf": {
            "extension": ".dxf",
            "mime_type": "application/dxf",
            "description": "AutoCAD DXF format for CAD software"
        },
        "svg": {
            "extension": ".svg",
            "mime_type": "image/svg+xml",
            "description": "Scalable Vector Graphics for web and print"
        }
    }
