"""
DXF Import Module
=================

Imports site boundaries and constraints from DXF files.
Supports 2D closed polylines only (v1).

Unsupported entities are logged and skipped.
Invalid geometry causes clear error responses.

Units: Assumes feet (no automatic conversion in v1).
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple, Dict, Any
from io import BytesIO
import tempfile
import os

import ezdxf
from ezdxf.document import Drawing
from ezdxf.entities import LWPolyline, Polyline, Line, Circle, Arc, Spline


# =============================================================================
# Error Types
# =============================================================================

class DxfImportErrorCode(str, Enum):
    """Error codes for DXF import failures."""
    FILE_READ_ERROR = "FILE_READ_ERROR"
    INVALID_DXF = "INVALID_DXF"
    NO_GEOMETRY = "NO_GEOMETRY"
    NO_CLOSED_POLYLINES = "NO_CLOSED_POLYLINES"
    UNSUPPORTED_ENTITY = "UNSUPPORTED_ENTITY"
    INVALID_GEOMETRY = "INVALID_GEOMETRY"
    UNIT_ERROR = "UNIT_ERROR"
    EMPTY_FILE = "EMPTY_FILE"


class DxfImportError(Exception):
    """Exception raised when DXF import fails."""

    def __init__(
        self,
        code: DxfImportErrorCode,
        detail: str,
        entities_found: Optional[Dict[str, int]] = None,
    ):
        self.code = code
        self.detail = detail
        self.entities_found = entities_found or {}
        super().__init__(f"{code.value}: {detail}")


# =============================================================================
# Result Types
# =============================================================================

@dataclass
class ImportedPolygon:
    """A polygon extracted from DXF."""
    points: List[Tuple[float, float]]
    layer: str
    is_closed: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "points": [{"x": x, "y": y} for x, y in self.points],
            "layer": self.layer,
            "isClosed": self.is_closed,
        }


@dataclass
class DxfImportResult:
    """Result of DXF import operation."""
    success: bool
    polygons: List[ImportedPolygon]
    warnings: List[str]
    entities_found: Dict[str, int]
    entities_imported: int
    entities_skipped: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "polygons": [p.to_dict() for p in self.polygons],
            "warnings": self.warnings,
            "entitiesFound": self.entities_found,
            "entitiesImported": self.entities_imported,
            "entitiesSkipped": self.entities_skipped,
        }


# =============================================================================
# Entity Classification
# =============================================================================

# Entities we can import
SUPPORTED_ENTITIES = {"LWPOLYLINE", "POLYLINE", "LINE"}

# Entities we silently skip (non-geometric)
IGNORED_ENTITIES = {
    "TEXT", "MTEXT", "DIMENSION", "LEADER", "MULTILEADER",
    "INSERT", "BLOCK", "ATTRIB", "ATTDEF",
    "HATCH", "SOLID", "TRACE",
    "VIEWPORT", "LAYOUT",
    "IMAGE", "WIPEOUT",
    "POINT",
}

# Entities we reject (unsupported geometry)
REJECTED_ENTITIES = {
    "SPLINE", "ELLIPSE", "HELIX",
    "3DFACE", "3DSOLID", "MESH", "SURFACE",
    "REGION", "BODY",
}


def classify_entity(entity_type: str) -> str:
    """Classify entity as 'supported', 'ignored', or 'rejected'."""
    entity_type = entity_type.upper()
    if entity_type in SUPPORTED_ENTITIES:
        return "supported"
    elif entity_type in IGNORED_ENTITIES:
        return "ignored"
    elif entity_type in REJECTED_ENTITIES:
        return "rejected"
    else:
        return "unknown"


# =============================================================================
# Geometry Extraction
# =============================================================================

def extract_lwpolyline(entity: LWPolyline) -> Optional[ImportedPolygon]:
    """Extract polygon from LWPOLYLINE entity."""
    try:
        # Get vertices (x, y only, ignore bulge for v1)
        points = [(p[0], p[1]) for p in entity.get_points()]

        if len(points) < 3:
            return None

        is_closed = entity.closed
        layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else "0"

        return ImportedPolygon(
            points=points,
            layer=layer,
            is_closed=is_closed,
        )
    except Exception:
        return None


def extract_polyline(entity: Polyline) -> Optional[ImportedPolygon]:
    """Extract polygon from 2D POLYLINE entity."""
    try:
        # Check if it's 2D
        if hasattr(entity.dxf, 'flags') and entity.dxf.flags & 0x10:
            # 3D polyline - skip
            return None

        points = [(v.dxf.location.x, v.dxf.location.y)
                  for v in entity.vertices]

        if len(points) < 3:
            return None

        is_closed = entity.is_closed
        layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else "0"

        return ImportedPolygon(
            points=points,
            layer=layer,
            is_closed=is_closed,
        )
    except Exception:
        return None


def extract_line(entity: Line) -> Optional[ImportedPolygon]:
    """Extract line as 2-point polygon (for constraint boundaries)."""
    try:
        start = entity.dxf.start
        end = entity.dxf.end

        # Check if 2D (z should be 0 or very small)
        if abs(start.z) > 0.001 or abs(end.z) > 0.001:
            return None

        points = [(start.x, start.y), (end.x, end.y)]
        layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else "0"

        return ImportedPolygon(
            points=points,
            layer=layer,
            is_closed=False,
        )
    except Exception:
        return None


# =============================================================================
# Main Import Function
# =============================================================================

def import_dxf_from_bytes(
    data: bytes,
    require_closed: bool = True,
    layer_filter: Optional[List[str]] = None,
) -> DxfImportResult:
    """
    Import geometry from DXF file bytes.

    Args:
        data: Raw DXF file bytes
        require_closed: If True, only import closed polylines
        layer_filter: If provided, only import from these layers

    Returns:
        DxfImportResult with extracted polygons or error info

    Raises:
        DxfImportError: If import fails with specific error
    """
    warnings: List[str] = []
    entities_found: Dict[str, int] = {}
    polygons: List[ImportedPolygon] = []
    rejected_types: set = set()

    # Write to temp file (ezdxf needs file path or stream)
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.dxf', delete=False) as f:
        f.write(data)
        temp_path = f.name

    try:
        # Try to read the DXF file
        try:
            doc = ezdxf.readfile(temp_path)
        except ezdxf.DXFStructureError as e:
            raise DxfImportError(
                DxfImportErrorCode.INVALID_DXF,
                f"Invalid DXF structure: {str(e)}"
            )
        except Exception as e:
            raise DxfImportError(
                DxfImportErrorCode.FILE_READ_ERROR,
                f"Could not read DXF file: {str(e)}"
            )

        # Get modelspace
        msp = doc.modelspace()

        # Count and classify all entities
        for entity in msp:
            entity_type = entity.dxftype()
            entities_found[entity_type] = entities_found.get(
                entity_type, 0) + 1

            classification = classify_entity(entity_type)

            if classification == "rejected":
                rejected_types.add(entity_type)
                continue

            if classification == "ignored":
                continue

            # Extract geometry based on entity type
            polygon: Optional[ImportedPolygon] = None

            if entity_type == "LWPOLYLINE":
                polygon = extract_lwpolyline(entity)
            elif entity_type == "POLYLINE":
                polygon = extract_polyline(entity)
            elif entity_type == "LINE":
                polygon = extract_line(entity)

            if polygon is None:
                continue

            # Apply layer filter
            if layer_filter and polygon.layer not in layer_filter:
                continue

            # Apply closed filter
            if require_closed and not polygon.is_closed:
                continue

            polygons.append(polygon)

        # Check for rejected entity types
        if rejected_types:
            types_str = ", ".join(sorted(rejected_types))
            raise DxfImportError(
                DxfImportErrorCode.UNSUPPORTED_ENTITY,
                f"DXF contains unsupported entities: {types_str}. Only 2D closed polylines are supported.",
                entities_found=entities_found,
            )

        # Check if we found any geometry
        if not entities_found:
            raise DxfImportError(
                DxfImportErrorCode.EMPTY_FILE,
                "DXF file contains no entities",
            )

        # Check if we extracted any polygons
        if not polygons:
            if require_closed:
                raise DxfImportError(
                    DxfImportErrorCode.NO_CLOSED_POLYLINES,
                    "No closed polylines found. Site boundary must be a closed polyline.",
                    entities_found=entities_found,
                )
            else:
                raise DxfImportError(
                    DxfImportErrorCode.NO_GEOMETRY,
                    "No importable geometry found",
                    entities_found=entities_found,
                )

        # Generate warnings for skipped entities
        for entity_type, count in entities_found.items():
            if classify_entity(entity_type) == "ignored":
                warnings.append(f"Skipped {count} {entity_type} entities")

        entities_imported = len(polygons)
        entities_skipped = sum(entities_found.values()) - entities_imported

        return DxfImportResult(
            success=True,
            polygons=polygons,
            warnings=warnings,
            entities_found=entities_found,
            entities_imported=entities_imported,
            entities_skipped=entities_skipped,
        )

    finally:
        # Clean up temp file
        try:
            os.unlink(temp_path)
        except Exception:
            pass


def import_dxf_file(
    file_path: str,
    require_closed: bool = True,
    layer_filter: Optional[List[str]] = None,
) -> DxfImportResult:
    """
    Import geometry from DXF file path.

    Args:
        file_path: Path to DXF file
        require_closed: If True, only import closed polylines
        layer_filter: If provided, only import from these layers

    Returns:
        DxfImportResult with extracted polygons

    Raises:
        DxfImportError: If import fails
    """
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
    except FileNotFoundError:
        raise DxfImportError(
            DxfImportErrorCode.FILE_READ_ERROR,
            f"File not found: {file_path}"
        )
    except Exception as e:
        raise DxfImportError(
            DxfImportErrorCode.FILE_READ_ERROR,
            f"Could not read file: {str(e)}"
        )

    return import_dxf_from_bytes(data, require_closed, layer_filter)


# =============================================================================
# User-Friendly Error Messages
# =============================================================================

ERROR_MESSAGES = {
    DxfImportErrorCode.FILE_READ_ERROR: "Could not read the DXF file. The file may be corrupted or in an unsupported format.",
    DxfImportErrorCode.INVALID_DXF: "The file is not a valid DXF file or uses an unsupported DXF version.",
    DxfImportErrorCode.NO_GEOMETRY: "No geometry found in the DXF file.",
    DxfImportErrorCode.NO_CLOSED_POLYLINES: "No closed polylines found. Site boundaries must be drawn as closed polylines.",
    DxfImportErrorCode.UNSUPPORTED_ENTITY: "DXF contains unsupported entities (splines, 3D meshes, or blocks). Please use only 2D closed polylines.",
    DxfImportErrorCode.INVALID_GEOMETRY: "Geometry could not be processed. Ensure all shapes are planar and properly closed.",
    DxfImportErrorCode.UNIT_ERROR: "Could not determine file units. Please ensure the DXF uses feet or inches.",
    DxfImportErrorCode.EMPTY_FILE: "The DXF file is empty or contains no drawing entities.",
}


def get_user_message(error: DxfImportError) -> str:
    """Get user-friendly message for import error."""
    base_message = ERROR_MESSAGES.get(error.code, "Import failed")
    if error.detail and error.code == DxfImportErrorCode.UNSUPPORTED_ENTITY:
        return error.detail
    return base_message
