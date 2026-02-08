"""
Run the SiteFit API server.

Usage:
    python run_server.py
    
Or with uvicorn directly:
    cd sitefit
    python -m uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
"""

import sys
import os

# Add sitefit to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("  SiteFit API Server")
    print("  Real Estate Feasibility Engine")
    print("=" * 60)
    print()
    print("Starting server on http://localhost:8001")
    print("API docs available at http://localhost:8001/docs")
    print()
    print("Legacy endpoints (ParkCore compatible):")
    print("  POST /parking/generate")
    print("  POST /parking/circulation")
    print()
    print("Press Ctrl+C to stop")
    print("-" * 60)

    uvicorn.run(
        "sitefit.api.app:app",
        host="0.0.0.0",
        port=8001,
        reload=True
    )
