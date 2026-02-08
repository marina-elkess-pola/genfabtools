"""
CAD/BIM File Loaders
====================

File format loaders for DXF, DWG, and RVT files.

These loaders extract geometry from CAD/BIM files and convert them
to 2D constraint polygons. All geometry is flattened to 2D.

Supported Formats:
    - DXF: AutoCAD Drawing Exchange Format (2D plans)
    - DWG: AutoCAD Drawing Format (2D plans)
    - RVT: Revit Family/Project files (category-filtered extraction)

Note: These loaders work with geometry data only.
      For actual CAD/BIM file parsing, external libraries would be needed:
      - ezdxf for DXF files
      - ODA File Converter for DWG files
      - Revit API for RVT files
      
      This module provides the interface and mock implementations
      for testing and integration purposes.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum, auto

from ..geometry import Polygon, Point
from .models import ImportedConstraint, ConstraintType, ConstraintSet


# =============================================================================
# LOAD RESULT & ERRORS
# =============================================================================

class LoadErrorType(Enum):
    """Types of loading errors."""
    FILE_NOT_FOUND = auto()
    UNSUPPORTED_FORMAT = auto()
    PARSE_ERROR = auto()
    INVALID_GEOMETRY = auto()
    NO_VALID_ELEMENTS = auto()


@dataclass
class LoadError:
    """
    Error encountered during file loading.
    """
    error_type: LoadErrorType
    message: str
    source_element: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.error_type.name,
            "message": self.message,
            "source_element": self.source_element,
            "details": self.details,
        }


@dataclass
class LoadResult:
    """
    Result of loading a CAD/BIM file.

    Contains successfully loaded constraints, errors encountered,
    and metadata about the loading process.
    """
    success: bool
    constraint_set: Optional[ConstraintSet] = None
    errors: List[LoadError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Metadata
    file_path: Optional[str] = None
    file_format: Optional[str] = None
    elements_found: int = 0
    elements_loaded: int = 0
    elements_rejected: int = 0

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "constraint_set": self.constraint_set.to_dict() if self.constraint_set else None,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": self.warnings,
            "file_path": self.file_path,
            "file_format": self.file_format,
            "elements_found": self.elements_found,
            "elements_loaded": self.elements_loaded,
            "elements_rejected": self.elements_rejected,
        }

    def summary(self) -> str:
        lines = [
            f"LoadResult: {'SUCCESS' if self.success else 'FAILED'}",
            f"  File: {self.file_path}",
            f"  Format: {self.file_format}",
            f"  Elements: {self.elements_loaded}/{self.elements_found} loaded",
        ]
        if self.elements_rejected > 0:
            lines.append(f"  Rejected: {self.elements_rejected}")
        if self.errors:
            lines.append(f"  Errors: {len(self.errors)}")
        if self.warnings:
            lines.append(f"  Warnings: {len(self.warnings)}")
        return "\n".join(lines)


# =============================================================================
# ABSTRACT CAD LOADER
# =============================================================================

class CADLoader(ABC):
    """
    Abstract base class for CAD/BIM file loaders.

    Subclasses implement format-specific parsing logic.
    """

    @property
    @abstractmethod
    def supported_extensions(self) -> List[str]:
        """List of supported file extensions (lowercase, with dot)."""
        pass

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Human-readable format name."""
        pass

    def can_load(self, file_path: str) -> bool:
        """Check if this loader can handle the given file."""
        ext = Path(file_path).suffix.lower()
        return ext in self.supported_extensions

    @abstractmethod
    def load(self, file_path: str, **options) -> LoadResult:
        """
        Load constraints from a CAD/BIM file.

        Args:
            file_path: Path to the file to load
            **options: Format-specific loading options

        Returns:
            LoadResult containing constraints or errors
        """
        pass

    def _validate_file(self, file_path: str) -> Optional[LoadError]:
        """Validate file exists and has supported extension."""
        path = Path(file_path)

        if not path.exists():
            return LoadError(
                error_type=LoadErrorType.FILE_NOT_FOUND,
                message=f"File not found: {file_path}",
            )

        if not self.can_load(file_path):
            return LoadError(
                error_type=LoadErrorType.UNSUPPORTED_FORMAT,
                message=f"Unsupported file format: {path.suffix}",
                details={"supported": self.supported_extensions},
            )

        return None


# =============================================================================
# DXF LOADER
# =============================================================================

class DXFLoader(CADLoader):
    """
    Loader for DXF (Drawing Exchange Format) files.

    Extracts closed polylines from DXF files and classifies
    them based on layer names.

    Supported DXF Elements:
        - LWPOLYLINE (closed)
        - POLYLINE (closed)
        - CIRCLE (converted to polygon)
        - HATCH boundaries

    Layer-based Classification:
        - Layers containing "column" → COLUMN
        - Layers containing "core" or "stair" or "elevator" → CORE
        - Layers containing "wall" → WALL
        - Layers containing "mep" or "mechanical" → MEP_ROOM
        - Layers containing "shaft" → SHAFT
        - Layers containing "void" or "opening" → VOID
        - Other layers → UNKNOWN
    """

    @property
    def supported_extensions(self) -> List[str]:
        return [".dxf"]

    @property
    def format_name(self) -> str:
        return "DXF"

    def load(self, file_path: str, **options) -> LoadResult:
        """
        Load constraints from a DXF file.

        Options:
            layer_filter: List of layer names to include (None = all)
            min_area: Minimum polygon area in square feet
            flatten_z: Whether to flatten 3D to 2D (default: True)
        """
        error = self._validate_file(file_path)
        if error:
            return LoadResult(
                success=False,
                errors=[error],
                file_path=file_path,
                file_format="dxf",
            )

        # In a real implementation, this would use ezdxf to parse the file
        # For now, we provide a mock implementation for testing
        return self._load_mock(file_path, **options)

    def _load_mock(self, file_path: str, **options) -> LoadResult:
        """
        Mock implementation for testing.

        In production, this would be replaced with actual DXF parsing.
        For testing, we read from a JSON sidecar file if it exists.
        """
        import json

        # Check for sidecar JSON file with test data
        sidecar_path = Path(file_path).with_suffix(".json")
        if sidecar_path.exists():
            return self._load_from_sidecar(file_path, sidecar_path)

        # Return empty result for non-existent sidecar
        return LoadResult(
            success=True,
            constraint_set=ConstraintSet(
                constraints=[],
                source_file=file_path,
                source_format="dxf",
                import_notes=["Mock loader - no geometry extracted"],
            ),
            file_path=file_path,
            file_format="dxf",
            elements_found=0,
            elements_loaded=0,
        )

    def _load_from_sidecar(self, file_path: str, sidecar_path: Path) -> LoadResult:
        """Load constraints from JSON sidecar file (for testing)."""
        import json

        try:
            with open(sidecar_path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            return LoadResult(
                success=False,
                errors=[LoadError(
                    error_type=LoadErrorType.PARSE_ERROR,
                    message=f"Failed to parse sidecar JSON: {e}",
                )],
                file_path=file_path,
                file_format="dxf",
            )

        constraints = []
        errors = []

        for item in data.get("elements", []):
            try:
                vertices = [Point(v["x"], v["y"]) for v in item["vertices"]]
                geometry = Polygon(vertices)

                constraint = ImportedConstraint(
                    geometry=geometry,
                    constraint_type=ConstraintType.from_string(
                        item.get("type", "unknown")),
                    source_format="dxf",
                    source_layer_or_category=item.get("layer", "0"),
                    source_id=item.get("id"),
                    confidence=item.get("confidence", 1.0),
                )
                constraints.append(constraint)
            except Exception as e:
                errors.append(LoadError(
                    error_type=LoadErrorType.INVALID_GEOMETRY,
                    message=str(e),
                    source_element=item.get("id"),
                ))

        return LoadResult(
            success=len(constraints) > 0 or len(errors) == 0,
            constraint_set=ConstraintSet(
                constraints=constraints,
                source_file=file_path,
                source_format="dxf",
                rejected_count=len(errors),
            ),
            errors=errors,
            file_path=file_path,
            file_format="dxf",
            elements_found=len(data.get("elements", [])),
            elements_loaded=len(constraints),
            elements_rejected=len(errors),
        )

    def load_from_geometry(
        self,
        elements: List[Dict[str, Any]],
        source_file: str = "imported",
    ) -> LoadResult:
        """
        Load constraints from pre-parsed geometry data.

        Useful for programmatic constraint creation or testing.

        Args:
            elements: List of dicts with 'vertices', 'layer', optional 'type'
            source_file: Source file name for metadata

        Returns:
            LoadResult with constraints
        """
        from .classifiers import classify_by_layer

        constraints = []
        errors = []

        for idx, item in enumerate(elements):
            try:
                vertices = item.get("vertices", [])
                if len(vertices) < 3:
                    errors.append(LoadError(
                        error_type=LoadErrorType.INVALID_GEOMETRY,
                        message=f"Element {idx}: Need at least 3 vertices",
                        source_element=str(idx),
                    ))
                    continue

                # Convert vertices to Points
                points = []
                for v in vertices:
                    if isinstance(v, (list, tuple)):
                        points.append(Point(float(v[0]), float(v[1])))
                    elif isinstance(v, dict):
                        points.append(Point(float(v["x"]), float(v["y"])))
                    else:
                        raise ValueError(f"Invalid vertex format: {v}")

                geometry = Polygon(points)
                layer = item.get("layer", "0")

                # Classify by explicit type or layer name
                if "type" in item:
                    constraint_type = ConstraintType.from_string(item["type"])
                else:
                    constraint_type = classify_by_layer(layer)

                constraint = ImportedConstraint(
                    geometry=geometry,
                    constraint_type=constraint_type,
                    source_format="dxf",
                    source_layer_or_category=layer,
                    source_id=item.get("id", f"element_{idx}"),
                    confidence=item.get("confidence", 1.0),
                    metadata=item.get("metadata", {}),
                )
                constraints.append(constraint)

            except Exception as e:
                errors.append(LoadError(
                    error_type=LoadErrorType.INVALID_GEOMETRY,
                    message=str(e),
                    source_element=str(idx),
                ))

        return LoadResult(
            success=len(constraints) > 0 or len(errors) == 0,
            constraint_set=ConstraintSet(
                constraints=constraints,
                source_file=source_file,
                source_format="dxf",
                rejected_count=len(errors),
            ),
            errors=errors,
            file_path=source_file,
            file_format="dxf",
            elements_found=len(elements),
            elements_loaded=len(constraints),
            elements_rejected=len(errors),
        )


# =============================================================================
# DWG LOADER
# =============================================================================

class DWGLoader(CADLoader):
    """
    Loader for DWG (AutoCAD Drawing) files.

    DWG files require conversion to DXF or use of ODA SDK.
    This loader delegates to DXFLoader after conversion.
    """

    @property
    def supported_extensions(self) -> List[str]:
        return [".dwg"]

    @property
    def format_name(self) -> str:
        return "DWG"

    def load(self, file_path: str, **options) -> LoadResult:
        """
        Load constraints from a DWG file.

        Note: DWG parsing requires external tools (ODA SDK).
        This implementation checks for pre-converted DXF or JSON sidecar.
        """
        error = self._validate_file(file_path)
        if error:
            return LoadResult(
                success=False,
                errors=[error],
                file_path=file_path,
                file_format="dwg",
            )

        # Check for pre-converted DXF
        dxf_path = Path(file_path).with_suffix(".dxf")
        if dxf_path.exists():
            dxf_loader = DXFLoader()
            result = dxf_loader.load(str(dxf_path), **options)
            result.file_path = file_path
            result.file_format = "dwg"
            if result.constraint_set:
                result.constraint_set.source_file = file_path
                result.constraint_set.source_format = "dwg"
            return result

        # Check for JSON sidecar
        json_path = Path(file_path).with_suffix(".json")
        if json_path.exists():
            dxf_loader = DXFLoader()
            result = dxf_loader._load_from_sidecar(file_path, json_path)
            result.file_format = "dwg"
            if result.constraint_set:
                result.constraint_set.source_format = "dwg"
            return result

        return LoadResult(
            success=False,
            errors=[LoadError(
                error_type=LoadErrorType.PARSE_ERROR,
                message="DWG files require ODA SDK or pre-conversion to DXF",
                details={
                    "suggestion": "Convert to DXF using AutoCAD or ODA File Converter"},
            )],
            file_path=file_path,
            file_format="dwg",
        )


# =============================================================================
# RVT LOADER
# =============================================================================

class RVTLoader(CADLoader):
    """
    Loader for RVT (Revit) files.

    Extracts geometry from specific Revit categories:
        - Structural Columns
        - Walls
        - Rooms (Mechanical / Electrical)
        - Shafts

    Revit API access required for direct extraction.
    This implementation works with exported JSON data.
    """

    # Revit categories to extract
    SUPPORTED_CATEGORIES = [
        "OST_StructuralColumns",
        "OST_Columns",
        "OST_Walls",
        "OST_Rooms",
        "OST_Shafts",
        "OST_FloorOpening",
        "OST_ShaftOpening",
    ]

    @property
    def supported_extensions(self) -> List[str]:
        return [".rvt"]

    @property
    def format_name(self) -> str:
        return "RVT"

    def load(self, file_path: str, **options) -> LoadResult:
        """
        Load constraints from a Revit file.

        Options:
            level_name: Specific level to extract (None = all levels)
            categories: List of category names to include
            room_filter: Filter function for rooms
        """
        error = self._validate_file(file_path)
        if error:
            return LoadResult(
                success=False,
                errors=[error],
                file_path=file_path,
                file_format="rvt",
            )

        # Check for exported JSON
        json_path = Path(file_path).with_suffix(".json")
        if json_path.exists():
            return self._load_from_json(file_path, json_path, **options)

        return LoadResult(
            success=False,
            errors=[LoadError(
                error_type=LoadErrorType.PARSE_ERROR,
                message="RVT files require Revit API or pre-exported JSON",
                details={"suggestion": "Export geometry to JSON using Revit API"},
            )],
            file_path=file_path,
            file_format="rvt",
        )

    def _load_from_json(
        self,
        file_path: str,
        json_path: Path,
        **options,
    ) -> LoadResult:
        """Load constraints from Revit-exported JSON."""
        import json

        try:
            with open(json_path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            return LoadResult(
                success=False,
                errors=[LoadError(
                    error_type=LoadErrorType.PARSE_ERROR,
                    message=f"Failed to parse Revit JSON: {e}",
                )],
                file_path=file_path,
                file_format="rvt",
            )

        constraints = []
        errors = []
        category_filter = options.get("categories", self.SUPPORTED_CATEGORIES)
        level_filter = options.get("level_name")

        for item in data.get("elements", []):
            category = item.get("category", "")
            level = item.get("level", "")

            # Apply filters
            if category_filter and category not in category_filter:
                continue
            if level_filter and level != level_filter:
                continue

            try:
                # Extract 2D footprint
                footprint = item.get("footprint", item.get("vertices", []))
                if not footprint:
                    continue

                vertices = [Point(v["x"], v["y"]) for v in footprint]
                if len(vertices) < 3:
                    continue

                geometry = Polygon(vertices)

                # Classify by category
                constraint_type = self._classify_category(category, item)

                constraint = ImportedConstraint(
                    geometry=geometry,
                    constraint_type=constraint_type,
                    source_format="rvt",
                    source_layer_or_category=category,
                    source_id=item.get("element_id", item.get("id")),
                    confidence=1.0 if constraint_type != ConstraintType.UNKNOWN else 0.5,
                    metadata={
                        "level": level,
                        "family": item.get("family"),
                        "type": item.get("type_name"),
                    },
                )
                constraints.append(constraint)

            except Exception as e:
                errors.append(LoadError(
                    error_type=LoadErrorType.INVALID_GEOMETRY,
                    message=str(e),
                    source_element=item.get("element_id"),
                ))

        return LoadResult(
            success=len(constraints) > 0 or len(errors) == 0,
            constraint_set=ConstraintSet(
                constraints=constraints,
                source_file=file_path,
                source_format="rvt",
                rejected_count=len(errors),
            ),
            errors=errors,
            file_path=file_path,
            file_format="rvt",
            elements_found=len(data.get("elements", [])),
            elements_loaded=len(constraints),
            elements_rejected=len(errors),
        )

    def _classify_category(
        self,
        category: str,
        item: Dict[str, Any],
    ) -> ConstraintType:
        """Classify Revit category to constraint type."""
        category_lower = category.lower()

        if "column" in category_lower or category in ("OST_StructuralColumns", "OST_Columns"):
            return ConstraintType.COLUMN

        if "wall" in category_lower or category == "OST_Walls":
            return ConstraintType.WALL

        if "shaft" in category_lower or category in ("OST_Shafts", "OST_ShaftOpening"):
            return ConstraintType.SHAFT

        if "opening" in category_lower or category == "OST_FloorOpening":
            return ConstraintType.VOID

        if "room" in category_lower or category == "OST_Rooms":
            # Check room name/type for MEP classification
            room_name = item.get("name", "").lower()
            if any(kw in room_name for kw in ("mechanical", "electrical", "mep", "hvac", "utility")):
                return ConstraintType.MEP_ROOM
            # Check if room is a stair/elevator core
            if any(kw in room_name for kw in ("stair", "elevator", "lift", "egress")):
                return ConstraintType.CORE
            return ConstraintType.UNKNOWN

        return ConstraintType.UNKNOWN

    def load_from_geometry(
        self,
        elements: List[Dict[str, Any]],
        source_file: str = "imported.rvt",
    ) -> LoadResult:
        """
        Load constraints from pre-parsed Revit geometry data.

        Args:
            elements: List of dicts with 'footprint', 'category', optional 'element_id'
            source_file: Source file name for metadata

        Returns:
            LoadResult with constraints
        """
        constraints = []
        errors = []

        for idx, item in enumerate(elements):
            try:
                footprint = item.get("footprint", item.get("vertices", []))
                if len(footprint) < 3:
                    errors.append(LoadError(
                        error_type=LoadErrorType.INVALID_GEOMETRY,
                        message=f"Element {idx}: Need at least 3 vertices",
                        source_element=str(idx),
                    ))
                    continue

                # Convert vertices to Points
                points = []
                for v in footprint:
                    if isinstance(v, (list, tuple)):
                        points.append(Point(float(v[0]), float(v[1])))
                    elif isinstance(v, dict):
                        points.append(Point(float(v["x"]), float(v["y"])))
                    else:
                        raise ValueError(f"Invalid vertex format: {v}")

                geometry = Polygon(points)
                category = item.get("category", "")

                constraint_type = self._classify_category(category, item)

                constraint = ImportedConstraint(
                    geometry=geometry,
                    constraint_type=constraint_type,
                    source_format="rvt",
                    source_layer_or_category=category,
                    source_id=item.get("element_id", f"element_{idx}"),
                    confidence=1.0 if constraint_type != ConstraintType.UNKNOWN else 0.5,
                    metadata=item.get("metadata", {}),
                )
                constraints.append(constraint)

            except Exception as e:
                errors.append(LoadError(
                    error_type=LoadErrorType.INVALID_GEOMETRY,
                    message=str(e),
                    source_element=str(idx),
                ))

        return LoadResult(
            success=len(constraints) > 0 or len(errors) == 0,
            constraint_set=ConstraintSet(
                constraints=constraints,
                source_file=source_file,
                source_format="rvt",
                rejected_count=len(errors),
            ),
            errors=errors,
            file_path=source_file,
            file_format="rvt",
            elements_found=len(elements),
            elements_loaded=len(constraints),
            elements_rejected=len(errors),
        )


# =============================================================================
# UNIFIED LOADER
# =============================================================================

# Registry of available loaders
_LOADERS: Dict[str, CADLoader] = {
    ".dxf": DXFLoader(),
    ".dwg": DWGLoader(),
    ".rvt": RVTLoader(),
}


def load_constraints_from_file(
    file_path: str,
    **options,
) -> LoadResult:
    """
    Load constraints from a CAD/BIM file.

    Automatically selects the appropriate loader based on file extension.

    Args:
        file_path: Path to the CAD/BIM file
        **options: Format-specific loading options

    Returns:
        LoadResult containing constraints or errors

    Supported formats:
        - .dxf: AutoCAD Drawing Exchange Format
        - .dwg: AutoCAD Drawing Format
        - .rvt: Revit Project/Family
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext not in _LOADERS:
        return LoadResult(
            success=False,
            errors=[LoadError(
                error_type=LoadErrorType.UNSUPPORTED_FORMAT,
                message=f"Unsupported file format: {ext}",
                details={"supported_formats": list(_LOADERS.keys())},
            )],
            file_path=file_path,
        )

    loader = _LOADERS[ext]
    return loader.load(file_path, **options)


def get_supported_formats() -> List[str]:
    """Get list of supported file extensions."""
    return list(_LOADERS.keys())


def register_loader(extension: str, loader: CADLoader) -> None:
    """Register a custom loader for a file extension."""
    _LOADERS[extension.lower()] = loader
