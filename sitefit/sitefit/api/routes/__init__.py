"""
api/routes/__init__.py - Route Package

Aggregates all API route handlers.
"""

from .parking import router as parking_router
from .building import router as building_router
from .feasibility import router as feasibility_router
from .export import router as export_router
from .parking_engine import router as parking_engine_router

__all__ = [
    "parking_router",
    "building_router",
    "feasibility_router",
    "export_router",
    "parking_engine_router",
]
