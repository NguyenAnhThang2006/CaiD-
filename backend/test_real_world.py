import sys
import os

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from real_world_converter import convert_physical_to_fuzzy, get_formula_explanation

def test_conversion_constraints():
    test_cases = [
        # (road_type, density, weather, risk)
        ("highway", 0.0, "sunny", 0.0),
        ("highway", 1.0, "sunny", 0.0),
        ("urban", 0.5, "rainy", 0.2),
        ("local", 0.8, "stormy", 0.9),
        ("local", 1.0, "stormy", 1.0),
    ]
    
    print("Running conversion mathematical integrity tests...")
    passed = True
    for road, density, weather, risk in test_cases:
        p, n, neg = convert_physical_to_fuzzy(road, density, weather, risk)
        total = p + n + neg
        print(f"Input: {road}, traffic={density}, weather={weather}, safety={risk} => P={p}, N={n}, n={neg} (Sum={total:.3f})")
        
        # Verify constraints
        if not (0.0 <= p <= 1.0 and 0.0 <= n <= 1.0 and 0.0 <= neg <= 1.0):
            print("  FAIL: Values out of bounds [0, 1]")
            passed = False
        if abs(total - 1.0) > 0.005:
            print("  FAIL: Sum of P + N + n does not equal 1.0")
            passed = False
            
    # Verify get_formula_explanation works
    try:
        explanation = get_formula_explanation("urban", 0.5, "rainy", 0.3)
        assert explanation["normalized"]["P"] + explanation["normalized"]["N"] + explanation["normalized"]["n"] - 1.0 < 0.01
        print("Formula explanation data structure verified successfully.")
    except Exception as e:
        print(f"Formula explanation test failed: {e}")
        passed = False

    if passed:
        print("\nALL CONVERSION TESTS PASSED SUCCESSFULLY!")
    else:
        print("\nSOME CONVERSION TESTS FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    test_conversion_constraints()
