"""
api/app.py - FastAPI Application

Main application factory and configuration for the SiteFit REST API.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Dict, Any
import time


# Version info
VERSION = "0.1.0"
TITLE = "SiteFit API"
DESCRIPTION = """
## Real Estate Feasibility Engine API

SiteFit provides automated site analysis and feasibility testing for real estate development.

### Features

- **Parking Analysis**: Generate and optimize parking layouts
- **Building Massing**: Create building forms within zoning constraints  
- **Feasibility Studies**: Full site feasibility with units, parking, and compliance
- **Optimization**: Find optimal configurations for various objectives
- **Export**: Export results in multiple formats (JSON, GeoJSON, DXF, SVG)

### Units

All dimensions are in **feet** unless otherwise specified.
"""


# =============================================================================
# LIFESPAN CONTEXT
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    app.state.start_time = time.time()
    yield
    # Shutdown (cleanup if needed)


# =============================================================================
# APPLICATION FACTORY
# =============================================================================

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title=TITLE,
        description=DESCRIPTION,
        version=VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json"
    )

    # Configure CORS - expose headers for binary file downloads
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition",
                        "Content-Type", "Content-Length"],
    )

    # Include routers
    from sitefit.api.routes import parking_router, building_router, feasibility_router, export_router, parking_engine_router
    from sitefit.api.routes.legacy import router as legacy_router
    from sitefit.api.routes.sitegen import router as sitegen_router

    app.include_router(parking_router, prefix="/parking", tags=["Parking"])
    app.include_router(building_router, prefix="/building", tags=["Building"])
    app.include_router(feasibility_router,
                       prefix="/feasibility", tags=["Feasibility"])
    app.include_router(export_router, prefix="/export", tags=["Export"])
    app.include_router(sitegen_router, prefix="/sitegen", tags=["SiteGen"])

    # Parking Engine routes (GenFabTools integration)
    # Frontend calls /api/parking/evaluate, Vite proxy rewrites to /parking/evaluate
    app.include_router(parking_engine_router,
                       prefix="/parking", tags=["Parking Engine"])

    # Legacy routes for python_engine compatibility (mount at /parking to override)
    # These provide /parking/generate and /parking/circulation matching old API format
    app.include_router(legacy_router, prefix="/parking", tags=["Legacy"])

    # Root endpoint
    @app.get("/", tags=["Health"])
    async def root() -> Dict[str, str]:
        """API root endpoint."""
        return {
            "name": TITLE,
            "version": VERSION,
            "status": "running",
            "docs": "/docs"
        }

    # Health check
    @app.get("/health", tags=["Health"])
    async def health_check() -> Dict[str, Any]:
        """Health check endpoint."""
        uptime = time.time() - app.state.start_time if hasattr(app.state, 'start_time') else 0
        return {
            "status": "healthy",
            "version": VERSION,
            "uptime_seconds": round(uptime, 2)
        }

    return app


# =============================================================================
# APPLICATION INSTANCE
# =============================================================================

# Create the application instance
app = create_app()
