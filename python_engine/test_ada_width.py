"""Test to trace ADA width accounting issue."""
from parking_engine.geometry import Polygon
from parking_engine.layout import generate_surface_layout
from parking_engine.rules import ParkingRules

# Test with a row that should have 3 ADA + 4 standard stalls
# Based on user's CAD scenario

# First, let's understand the dimensions:
# Van stall: 11ft + 8ft aisle = 19ft
# ADA stall (shared aisle): 11ft (shares van's 8ft aisle)
# ADA stall (trailing aisle): 11ft + 5ft = 16ft
# Total ADA footprint: 11 + 8 + 11 + 11 + 5 = 46ft

# Standard stall: 9ft
# 4 standard stalls: 36ft

# Total for row: 46 + 36 = 82ft width needed

# Let's create a lot that results in a single row
site = Polygon.from_bounds(0, 0, 200, 100)
rules = ParkingRules()
result = generate_surface_layout(site, rules)

print("=" * 60)
print("STALL LAYOUT ANALYSIS")
print("=" * 60)

stalls = result.all_stalls
by_type = {}
for s in stalls:
    t = s.stall_type.value
    by_type[t] = by_type.get(t, 0) + 1

print(f"Total stalls: {len(stalls)}")
print(f"By type: {by_type}")

# Get first bay's south row
bay = result.bays[0] if result.bays else None
if bay:
    print(f"\n--- Bay 0 South Row ({len(bay.south_stalls)} stalls) ---")

    ada_stalls = [
        s for s in bay.south_stalls if 'ada' in s.stall_type.value.lower()]
    std_stalls = [
        s for s in bay.south_stalls if s.stall_type.value == 'standard']

    # Determine orientation from first stall
    if bay.south_stalls:
        first = bay.south_stalls[0].geometry.bounds
        w = first[2] - first[0]
        h = first[3] - first[1]
        # stall width < depth means horizontal layout (stalls along X)
        horizontal = w < h
        coord_name = 'x' if horizontal else 'y'
        print(
            f"Stalls oriented: {'horizontal (along X)' if horizontal else 'vertical (along Y)'}")

    print(f"\nADA stalls: {len(ada_stalls)}")
    for i, s in enumerate(ada_stalls):
        b = s.geometry.bounds
        if horizontal:
            start, end = b[0], b[2]
        else:
            start, end = b[1], b[3]
        width = end - start
        print(
            f"  {i}: {s.stall_type.value} {coord_name}={start:.1f}-{end:.1f} (w={width:.1f}ft)")
        if hasattr(s, 'access_aisle') and s.access_aisle:
            ab = s.access_aisle.bounds
            if horizontal:
                a_start, a_end = ab[0], ab[2]
            else:
                a_start, a_end = ab[1], ab[3]
            aisle_w = a_end - a_start
            print(
                f"      aisle: {coord_name}={a_start:.1f}-{a_end:.1f} (w={aisle_w:.1f}ft)")

    print(f"\nStandard stalls in first bay south: {len(std_stalls)}")
    if std_stalls:
        for s in std_stalls[:3]:
            b = s.geometry.bounds
            if horizontal:
                print(f"  x={b[0]:.1f}-{b[2]:.1f}")
            else:
                print(f"  y={b[1]:.1f}-{b[3]:.1f}")
        if len(std_stalls) > 6:
            print("  ...")
        for s in std_stalls[-3:]:
            b = s.geometry.bounds
            if horizontal:
                print(f"  x={b[0]:.1f}-{b[2]:.1f}")
            else:
                print(f"  y={b[1]:.1f}-{b[3]:.1f}")

    # Calculate actual physical footprint
    print("\n--- Physical Footprint Analysis ---")
    all_south = bay.south_stalls
    if all_south:
        if horizontal:
            min_coord = min(s.geometry.bounds[0] for s in all_south)
            max_coord = max(s.geometry.bounds[2] for s in all_south)
            for s in all_south:
                if hasattr(s, 'access_aisle') and s.access_aisle:
                    ab = s.access_aisle.bounds
                    max_coord = max(max_coord, ab[2])
        else:
            min_coord = min(s.geometry.bounds[1] for s in all_south)
            max_coord = max(s.geometry.bounds[3] for s in all_south)
            for s in all_south:
                if hasattr(s, 'access_aisle') and s.access_aisle:
                    ab = s.access_aisle.bounds
                    max_coord = max(max_coord, ab[3])

        print(
            f"Row spans: {coord_name}={min_coord:.1f} to {coord_name}={max_coord:.1f}")
        print(f"Row width: {max_coord - min_coord:.1f}ft")

        # Calculate expected
        n_ada = len(ada_stalls)
        n_std = len(std_stalls)
        # Expected ADA footprint for 3 stalls: 11+8+11+11+5 = 46ft
        # Each std stall: 9ft
        expected_ada = 46 if n_ada == 3 else (30 if n_ada == 2 else 19)
        expected_std = n_std * 9
        expected_total = expected_ada + expected_std
        print(f"\nExpected ADA footprint: {expected_ada}ft")
        print(f"Expected std footprint: {expected_std}ft ({n_std} × 9ft)")
        print(f"Expected total: {expected_total}ft")
        print(f"Actual total: {max_x - min_x:.1f}ft")
        print(f"Difference: {(max_x - min_x) - expected_total:.1f}ft")
