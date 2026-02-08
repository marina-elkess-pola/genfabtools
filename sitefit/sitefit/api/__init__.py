"""
api - FastAPI Web Application

This package provides a REST API for the SiteFit engine:
- /parking/* - Parking layout endpoints
- /building/* - Building massing endpoints
- /feasibility/* - Full site feasibility analysis
- /export/* - Export to various formats
"""

from .app import create_app, app

__all__ = [
    "create_app",
    "app",
]
