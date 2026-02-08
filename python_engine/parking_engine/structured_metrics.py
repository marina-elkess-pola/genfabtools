"""
Structured Parking Metrics (Skeleton)
=====================================

Metrics computation for structured parking layouts.
PHASE 2: Skeleton metrics only. No stall-based calculations.

All outputs are conceptual and advisory.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional

from .structured import StructuredParkingLayout, ParkingLevel


@dataclass
class StructuredMetrics:
    """
    Summary metrics for a structured parking layout (skeleton).

    PHASE 2: Does not include stall counts or stall-based efficiency.
    These are placeholders for future stall placement integration.
    """
    # Structure dimensions
    level_count: int
    floor_to_floor_height: float
    total_height: float

    # Gross areas
    footprint_area: float          # Single level footprint
    total_gross_area: float        # Sum of all level gross areas
    total_net_area: float          # Sum of all level net areas

    # Reserved areas
    total_ramp_area: float
    total_core_area: float
    total_reserved_area: float

    # Efficiency (area-based, not stall-based)
    net_to_gross_ratio: float      # Overall net/gross ratio
    avg_level_efficiency: float    # Average level efficiency

    # Per-level breakdown
    level_metrics: List[Dict]

    # Placeholders for future stall integration
    estimated_stalls_per_level: int = 0      # Placeholder
    estimated_total_stalls: int = 0          # Placeholder
    estimated_efficiency_sf_per_stall: float = 0.0  # Placeholder

    def to_dict(self) -> Dict:
        """Serialize metrics to dictionary."""
        return {
            "structure": {
                "level_count": self.level_count,
                "floor_to_floor_height_ft": self.floor_to_floor_height,
                "total_height_ft": self.total_height,
            },
            "areas": {
                "footprint_sf": round(self.footprint_area, 1),
                "total_gross_sf": round(self.total_gross_area, 1),
                "total_net_sf": round(self.total_net_area, 1),
                "total_ramp_sf": round(self.total_ramp_area, 1),
                "total_core_sf": round(self.total_core_area, 1),
                "total_reserved_sf": round(self.total_reserved_area, 1),
            },
            "efficiency": {
                "net_to_gross_ratio": round(self.net_to_gross_ratio, 3),
                "avg_level_efficiency": round(self.avg_level_efficiency, 3),
            },
            "levels": self.level_metrics,
            "stall_estimates": {
                "estimated_stalls_per_level": self.estimated_stalls_per_level,
                "estimated_total_stalls": self.estimated_total_stalls,
                "estimated_sf_per_stall": self.estimated_efficiency_sf_per_stall,
                "note": "Stall counts are placeholders. Actual stall placement not yet implemented.",
            },
        }

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            "=== Structured Parking Metrics (Skeleton) ===",
            "",
            f"Levels: {self.level_count}",
            f"Floor-to-floor: {self.floor_to_floor_height}' | Total height: {self.total_height}'",
            "",
            f"Footprint: {self.footprint_area:,.0f} SF",
            f"Total Gross Area: {self.total_gross_area:,.0f} SF ({self.level_count} levels)",
            f"Total Net Area: {self.total_net_area:,.0f} SF",
            "",
            f"Reserved Areas:",
            f"  Ramps: {self.total_ramp_area:,.0f} SF",
            f"  Cores: {self.total_core_area:,.0f} SF",
            f"  Total: {self.total_reserved_area:,.0f} SF",
            "",
            f"Net-to-Gross Ratio: {self.net_to_gross_ratio:.1%}",
            "",
            "Per-Level Breakdown:",
        ]

        for lm in self.level_metrics:
            level_str = f"  L{lm['level_index']}: {lm['gross_area_sf']:,.0f} SF gross"
            if lm['is_ground']:
                level_str += " (ground)"
            if lm['is_roof']:
                level_str += " (roof)"
            lines.append(level_str)

        lines.extend([
            "",
            "Note: Stall placement not yet implemented.",
            "This is a structural skeleton for feasibility analysis.",
        ])

        return "\n".join(lines)


def compute_structured_metrics(layout: StructuredParkingLayout) -> StructuredMetrics:
    """
    Compute metrics for a structured parking layout.

    PHASE 2: Computes area-based metrics only.
    Stall counts are placeholders (not computed).

    Args:
        layout: StructuredParkingLayout to analyze

    Returns:
        StructuredMetrics with computed values
    """
    # Aggregate areas
    footprint_area = layout.footprint.area
    total_gross = sum(level.gross_area for level in layout.levels)
    total_net = sum(level.net_area for level in layout.levels)

    # Reserved areas (per level, summed)
    # Note: Same ramp/core penetrates all levels, so we count once per level
    total_ramp_area = layout.total_ramp_area * layout.level_count
    total_core_area = layout.total_core_area * layout.level_count
    total_reserved = total_ramp_area + total_core_area

    # Efficiency ratios
    net_to_gross = total_net / total_gross if total_gross > 0 else 0.0

    level_efficiencies = [level.efficiency_ratio for level in layout.levels]
    avg_efficiency = sum(level_efficiencies) / \
        len(level_efficiencies) if level_efficiencies else 0.0

    # Per-level metrics
    level_metrics = []
    for level in layout.levels:
        level_metrics.append({
            "level_index": level.level_index,
            "elevation_ft": level.elevation,
            "is_ground": level.is_ground,
            "is_roof": level.is_roof,
            "gross_area_sf": round(level.gross_area, 1),
            "net_area_sf": round(level.net_area, 1),
            "reserved_area_sf": round(level.reserved_area, 1),
            "efficiency_ratio": round(level.efficiency_ratio, 3),
        })

    # Placeholder stall estimates (rule-of-thumb only)
    # Typical structured parking: 300-350 SF/stall
    placeholder_sf_per_stall = 325.0
    estimated_per_level = int(
        footprint_area / placeholder_sf_per_stall) if footprint_area > 0 else 0
    estimated_total = estimated_per_level * layout.level_count

    return StructuredMetrics(
        level_count=layout.level_count,
        floor_to_floor_height=layout.floor_to_floor_height,
        total_height=layout.total_height,
        footprint_area=footprint_area,
        total_gross_area=total_gross,
        total_net_area=total_net,
        total_ramp_area=total_ramp_area,
        total_core_area=total_core_area,
        total_reserved_area=total_reserved,
        net_to_gross_ratio=net_to_gross,
        avg_level_efficiency=avg_efficiency,
        level_metrics=level_metrics,
        estimated_stalls_per_level=estimated_per_level,
        estimated_total_stalls=estimated_total,
        estimated_efficiency_sf_per_stall=placeholder_sf_per_stall,
    )


def estimate_structured_capacity(
    footprint_area_sf: float,
    level_count: int,
    efficiency_sf_per_stall: float = 325.0,
    ramp_loss_pct: float = 0.05,
    core_loss_pct: float = 0.03,
) -> Dict:
    """
    Quick capacity estimate for structured parking.

    This is a rule-of-thumb calculation for early feasibility.
    Actual capacity depends on layout geometry.

    Args:
        footprint_area_sf: Gross footprint area in square feet
        level_count: Number of parking levels
        efficiency_sf_per_stall: Target efficiency (default 325 SF/stall)
        ramp_loss_pct: Percentage lost to ramps per level (default 5%)
        core_loss_pct: Percentage lost to cores per level (default 3%)

    Returns:
        Capacity estimate dictionary
    """
    total_loss_pct = ramp_loss_pct + core_loss_pct
    net_area_per_level = footprint_area_sf * (1 - total_loss_pct)
    total_net_area = net_area_per_level * level_count

    # Calculate range
    low_efficiency = 375.0   # Conservative
    mid_efficiency = efficiency_sf_per_stall
    high_efficiency = 280.0  # Aggressive

    return {
        "footprint_sf": footprint_area_sf,
        "level_count": level_count,
        "net_area_per_level_sf": net_area_per_level,
        "total_net_area_sf": total_net_area,
        "capacity_low": int(total_net_area / low_efficiency),
        "capacity_mid": int(total_net_area / mid_efficiency),
        "capacity_high": int(total_net_area / high_efficiency),
        "efficiency_assumptions": {
            "low": f"{low_efficiency} SF/stall (conservative)",
            "mid": f"{mid_efficiency} SF/stall (typical)",
            "high": f"{high_efficiency} SF/stall (aggressive)",
        },
        "loss_factors": {
            "ramp_pct": ramp_loss_pct,
            "core_pct": core_loss_pct,
            "total_pct": total_loss_pct,
        },
        "note": "Conceptual estimate only. Actual capacity varies by layout.",
    }
