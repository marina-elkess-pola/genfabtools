"""
Metrics Calculator
==================

Computes parking layout metrics for feasibility analysis.

All metrics are conceptual and for planning purposes only.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional

from .layout import SurfaceParkingLayout
from .rules import StallType


@dataclass
class LayoutMetrics:
    """
    Summary metrics for a parking layout.

    All areas in square feet. All values are advisory.
    """
    # Stall counts
    total_stalls: int
    standard_stalls: int
    compact_stalls: int
    ada_stalls: int
    ada_van_stalls: int

    # Areas
    gross_site_area: float      # Total site boundary area
    net_parking_area: float     # Area after setbacks
    stall_area: float           # Total area of all stalls
    aisle_area: float           # Total area of all aisles
    circulation_area: float     # Aisles + drive lanes

    # Efficiency metrics
    efficiency_sf_per_stall: float   # Net area / total stalls
    stall_area_ratio: float          # Stall area / net area
    circulation_ratio: float         # Circulation area / net area

    # Bay statistics
    num_bays: int
    avg_stalls_per_bay: float
    double_loaded_bays: int
    single_loaded_bays: int

    # ADA compliance (rule-based check, not certification)
    ada_required: int
    ada_provided: int
    ada_compliant: bool  # Meets rule-of-thumb requirement

    def to_dict(self) -> Dict:
        """Serialize metrics to dictionary."""
        return {
            "stalls": {
                "total": self.total_stalls,
                "standard": self.standard_stalls,
                "compact": self.compact_stalls,
                "ada": self.ada_stalls,
                "ada_van": self.ada_van_stalls,
            },
            "areas": {
                "gross_site_sf": round(self.gross_site_area, 1),
                "net_parking_sf": round(self.net_parking_area, 1),
                "stall_sf": round(self.stall_area, 1),
                "aisle_sf": round(self.aisle_area, 1),
                "circulation_sf": round(self.circulation_area, 1),
            },
            "efficiency": {
                "sf_per_stall": round(self.efficiency_sf_per_stall, 1),
                "stall_area_ratio": round(self.stall_area_ratio, 3),
                "circulation_ratio": round(self.circulation_ratio, 3),
            },
            "bays": {
                "count": self.num_bays,
                "avg_stalls_per_bay": round(self.avg_stalls_per_bay, 1),
                "double_loaded": self.double_loaded_bays,
                "single_loaded": self.single_loaded_bays,
            },
            "ada_compliance": {
                "required": self.ada_required,
                "provided": self.ada_provided,
                "meets_requirement": self.ada_compliant,
            },
        }

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            "=== Parking Layout Metrics ===",
            "",
            f"Total Stalls: {self.total_stalls}",
            f"  Standard: {self.standard_stalls}",
            f"  Compact: {self.compact_stalls}",
            f"  ADA: {self.ada_stalls + self.ada_van_stalls} (Van: {self.ada_van_stalls})",
            "",
            f"Gross Site Area: {self.gross_site_area:,.0f} SF",
            f"Net Parking Area: {self.net_parking_area:,.0f} SF",
            f"Efficiency: {self.efficiency_sf_per_stall:.0f} SF/stall",
            "",
            f"Parking Bays: {self.num_bays}",
            f"  Double-loaded: {self.double_loaded_bays}",
            f"  Single-loaded: {self.single_loaded_bays}",
            "",
            f"ADA Compliance: {'PASS' if self.ada_compliant else 'CHECK REQUIRED'}",
            f"  Required: {self.ada_required} | Provided: {self.ada_provided}",
            "",
            "Note: All values are conceptual estimates for feasibility analysis.",
            "This is not a compliance certification.",
        ]
        return "\n".join(lines)


def compute_metrics(layout: SurfaceParkingLayout) -> LayoutMetrics:
    """
    Compute comprehensive metrics for a parking layout.

    Args:
        layout: Generated parking layout

    Returns:
        LayoutMetrics with computed values
    """
    from .rules import calculate_ada_stall_requirement

    # Count stalls by type
    stall_counts = {
        StallType.STANDARD: 0,
        StallType.COMPACT: 0,
        StallType.ADA: 0,
        StallType.ADA_VAN: 0,
    }

    total_stall_area = 0.0
    for stall in layout.all_stalls:
        stall_counts[stall.stall_type] = stall_counts.get(
            stall.stall_type, 0) + 1
        total_stall_area += stall.geometry.area

    # Calculate aisle area
    total_aisle_area = sum(bay.aisle.geometry.area for bay in layout.bays)

    # Calculate drive lane area
    drive_lane_area = sum(dl.area for dl in layout.drive_lanes)

    # Total circulation
    circulation_area = total_aisle_area + drive_lane_area

    # Areas
    gross_area = layout.site_boundary.area
    net_area = layout.net_parking_area.area

    # Bay statistics
    num_bays = len(layout.bays)
    double_loaded = sum(1 for bay in layout.bays if bay.is_double_loaded)
    single_loaded = num_bays - double_loaded

    total_stalls = layout.total_stalls
    avg_stalls_per_bay = total_stalls / num_bays if num_bays > 0 else 0

    # Efficiency
    efficiency = net_area / total_stalls if total_stalls > 0 else 0
    stall_ratio = total_stall_area / net_area if net_area > 0 else 0
    circulation_ratio = circulation_area / net_area if net_area > 0 else 0

    # ADA check
    ada_req = calculate_ada_stall_requirement(total_stalls)
    ada_required = ada_req["total_ada"]
    ada_provided = stall_counts[StallType.ADA] + \
        stall_counts[StallType.ADA_VAN]
    ada_compliant = ada_provided >= ada_required

    return LayoutMetrics(
        total_stalls=total_stalls,
        standard_stalls=stall_counts[StallType.STANDARD],
        compact_stalls=stall_counts[StallType.COMPACT],
        ada_stalls=stall_counts[StallType.ADA],
        ada_van_stalls=stall_counts[StallType.ADA_VAN],
        gross_site_area=gross_area,
        net_parking_area=net_area,
        stall_area=total_stall_area,
        aisle_area=total_aisle_area,
        circulation_area=circulation_area,
        efficiency_sf_per_stall=efficiency,
        stall_area_ratio=stall_ratio,
        circulation_ratio=circulation_ratio,
        num_bays=num_bays,
        avg_stalls_per_bay=avg_stalls_per_bay,
        double_loaded_bays=double_loaded,
        single_loaded_bays=single_loaded,
        ada_required=ada_required,
        ada_provided=ada_provided,
        ada_compliant=ada_compliant,
    )


def compare_layouts(layouts: list) -> Dict:
    """
    Compare multiple layouts and return comparison summary.

    Args:
        layouts: List of (SurfaceParkingLayout, description) tuples

    Returns:
        Comparison dictionary with ranked results
    """
    comparisons = []

    for layout, description in layouts:
        metrics = compute_metrics(layout)
        comparisons.append({
            "description": description,
            "total_stalls": metrics.total_stalls,
            "efficiency_sf_per_stall": metrics.efficiency_sf_per_stall,
            "ada_compliant": metrics.ada_compliant,
            "num_bays": metrics.num_bays,
            "orientation": layout.orientation,
            "aisle_direction": layout.aisle_direction.value,
        })

    # Sort by stall count
    comparisons.sort(key=lambda x: x["total_stalls"], reverse=True)

    # Add ranking
    for i, comp in enumerate(comparisons):
        comp["rank"] = i + 1

    return {
        "layouts": comparisons,
        "best_by_capacity": comparisons[0] if comparisons else None,
        "best_by_efficiency": min(comparisons, key=lambda x: x["efficiency_sf_per_stall"]) if comparisons else None,
    }


def estimate_surface_capacity(
    site_area_sf: float,
    efficiency_sf_per_stall: float = 325.0,
    setback_pct: float = 0.10,
) -> Dict:
    """
    Quick estimate of surface parking capacity from site area.

    This is a rule-of-thumb calculation for early feasibility.
    Actual capacity depends on site geometry and layout.

    Args:
        site_area_sf: Gross site area in square feet
        efficiency_sf_per_stall: Target efficiency (default 325 SF/stall)
        setback_pct: Estimated setback reduction (default 10%)

    Returns:
        Capacity estimate with range
    """
    net_area = site_area_sf * (1 - setback_pct)

    # Calculate range based on efficiency
    low_efficiency = 375.0    # Conservative (large stalls, two-way aisles)
    mid_efficiency = efficiency_sf_per_stall
    high_efficiency = 280.0   # Aggressive (compact stalls, one-way aisles)

    return {
        "gross_site_sf": site_area_sf,
        "net_parking_sf": net_area,
        "capacity_low": int(net_area / low_efficiency),
        "capacity_mid": int(net_area / mid_efficiency),
        "capacity_high": int(net_area / high_efficiency),
        "efficiency_assumptions": {
            "low": f"{low_efficiency} SF/stall (conservative)",
            "mid": f"{mid_efficiency} SF/stall (typical)",
            "high": f"{high_efficiency} SF/stall (aggressive)",
        },
        "note": "Conceptual estimate only. Actual capacity varies by site geometry.",
    }
