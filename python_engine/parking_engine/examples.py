#!/usr/bin/env python3
"""
Parking Engine Usage Examples
=============================

Demonstrates how to use the surface parking layout engine.
"""

from parking_engine import (
    Polygon, Point,
    ParkingRules, AisleDirection,
    generate_surface_layout,
    compute_metrics,
)
from parking_engine.layout import evaluate_layout_options
from parking_engine.metrics import estimate_surface_capacity, compare_layouts


def example_basic_layout():
    """Generate a basic surface parking layout."""
    print("\n" + "=" * 60)
    print("EXAMPLE 1: Basic Surface Layout")
    print("=" * 60)

    # Define site boundary (300' x 200' = 1.38 acres)
    site = Polygon.from_bounds(0, 0, 300, 200)

    # Generate layout with default rules
    layout = generate_surface_layout(
        site_boundary=site,
        aisle_direction=AisleDirection.TWO_WAY,
        setback=5.0,
    )

    # Compute metrics
    metrics = compute_metrics(layout)

    print(f"\nSite: {site.width}' x {site.height}' ({site.area:,.0f} SF)")
    print(
        f"Configuration: {layout.orientation} orientation, {layout.aisle_direction.value} aisles")
    print(metrics.summary())


def example_custom_rules():
    """Generate layout with custom dimension rules."""
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Custom Parking Rules")
    print("=" * 60)

    # Define site
    site = Polygon.from_bounds(0, 0, 250, 180)

    # Custom rules with compact stalls and one-way aisles
    from parking_engine.rules import StallDimensions

    rules = ParkingRules(
        stall_standard=StallDimensions(
            width=8.5, length=17.0),  # Slightly smaller
        aisle_one_way=13.0,   # Slightly wider one-way
        aisle_two_way=24.0,
        setback_default=10.0,
    )

    layout = generate_surface_layout(
        site_boundary=site,
        rules=rules,
        aisle_direction=AisleDirection.ONE_WAY,
    )

    metrics = compute_metrics(layout)

    print(f"\nSite: {site.width}' x {site.height}'")
    print(f"Custom rules: 8.5' x 17' stalls, 13' one-way aisles")
    print(f"Total stalls: {metrics.total_stalls}")
    print(f"Efficiency: {metrics.efficiency_sf_per_stall:.0f} SF/stall")


def example_compare_options():
    """Compare multiple layout configurations."""
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Compare Layout Options")
    print("=" * 60)

    # Define site
    site = Polygon.from_bounds(0, 0, 280, 200)

    # Evaluate all configurations
    options = evaluate_layout_options(site, setback=5.0)

    print(f"\nSite: {site.width}' x {site.height}' ({site.area:,.0f} SF)")
    print(f"\nLayout options ranked by capacity:")
    print("-" * 50)

    for i, (layout, desc) in enumerate(options, 1):
        metrics = compute_metrics(layout)
        print(f"{i}. {desc}")
        print(
            f"   Stalls: {metrics.total_stalls} | Efficiency: {metrics.efficiency_sf_per_stall:.0f} SF/stall")
        print(
            f"   Bays: {metrics.num_bays} | ADA: {metrics.ada_provided}/{metrics.ada_required}")

    # Use comparison helper
    comparison = compare_layouts(options)
    best = comparison["best_by_capacity"]
    print(
        f"\n→ Best by capacity: {best['description']} ({best['total_stalls']} stalls)")


def example_quick_capacity_estimate():
    """Quick capacity estimate without full layout."""
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Quick Capacity Estimate")
    print("=" * 60)

    # 3-acre site
    site_area_sf = 3 * 43560  # 130,680 SF

    estimate = estimate_surface_capacity(
        site_area_sf=site_area_sf,
        efficiency_sf_per_stall=325,  # Typical target
        setback_pct=0.10,
    )

    print(f"\nSite area: {estimate['gross_site_sf']:,.0f} SF (3 acres)")
    print(f"Net parking area: {estimate['net_parking_sf']:,.0f} SF")
    print(f"\nCapacity estimates:")
    print(f"  Conservative: {estimate['capacity_low']} stalls")
    print(f"  Typical: {estimate['capacity_mid']} stalls")
    print(f"  Aggressive: {estimate['capacity_high']} stalls")
    print(f"\n{estimate['note']}")


def example_serialization():
    """Export layout and metrics to JSON-compatible format."""
    print("\n" + "=" * 60)
    print("EXAMPLE 5: Data Serialization")
    print("=" * 60)

    import json

    site = Polygon.from_bounds(0, 0, 200, 150)
    layout = generate_surface_layout(site)
    metrics = compute_metrics(layout)

    # Serialize to dict
    layout_data = layout.to_dict()
    metrics_data = metrics.to_dict()

    print(f"\nLayout JSON structure:")
    print(
        f"  - site_boundary: polygon with {len(layout_data['site_boundary']['vertices'])} vertices")
    print(f"  - bays: {len(layout_data['bays'])} bays")
    print(f"  - total_stalls: {layout_data['total_stalls']}")

    print(f"\nMetrics JSON structure:")
    print(json.dumps(metrics_data, indent=2)[:500] + "...")


def example_access_individual_elements():
    """Access individual stalls and bays."""
    print("\n" + "=" * 60)
    print("EXAMPLE 6: Access Individual Elements")
    print("=" * 60)

    site = Polygon.from_bounds(0, 0, 200, 150)
    layout = generate_surface_layout(site)

    print(f"\nLayout has {len(layout.bays)} bays:")
    for bay in layout.bays:
        print(f"\n  Bay {bay.id}:")
        print(
            f"    Aisle: {bay.aisle.geometry.width:.0f}' x {bay.aisle.geometry.height:.0f}'")
        print(f"    North stalls: {len(bay.north_stalls)}")
        print(f"    South stalls: {len(bay.south_stalls)}")
        print(f"    Double-loaded: {bay.is_double_loaded}")

    # Access first stall
    if layout.all_stalls:
        stall = layout.all_stalls[0]
        print(f"\nFirst stall ({stall.id}):")
        print(f"  Type: {stall.stall_type.value}")
        print(
            f"  Geometry: {stall.geometry.width:.1f}' x {stall.geometry.height:.1f}'")
        print(f"  Centroid: ({stall.centroid.x:.1f}, {stall.centroid.y:.1f})")


if __name__ == "__main__":
    example_basic_layout()
    example_custom_rules()
    example_compare_options()
    example_quick_capacity_estimate()
    example_serialization()
    example_access_individual_elements()

    print("\n" + "=" * 60)
    print("All examples completed successfully.")
    print("=" * 60)
