"""
real_world_converter.py
---------------------------------------------------------------------------
Module for converting physical, real-world data feeds into Picture Fuzzy Number 
triples (P, N, n) using membership functions.

Sources & Data Inputs:
1. OpenStreetMap (OSM): Distance and Road Type (highway, urban, local)
2. VietMap Traffic API: Traffic Density (0.0 to 1.0, representing congestion index)
3. OpenWeatherMap API: Weather state (sunny, rainy, stormy)
4. Hanoi Open Data / Local Cameras: Accident / Safety Risk level (0.0 to 1.0)
"""

def convert_physical_to_fuzzy(road_type: str, traffic_density: float, weather: str, accident_risk: float) -> tuple:
    """
    Converts physical variables from real-world APIs to Picture Fuzzy Numbers (P, N, n).
    
    Constraints:
    - 0 <= P, N, n <= 1.0
    - P + N + n <= 1.0
    
    Logic:
    - Road Type (OSM) sets the initial baseline memberships.
    - Traffic Density (VietMap) penalizes P (flow) and boosts n (congestion).
    - Weather (OpenWeather) boosts N (hesitation/uncertainty) and penalizes P.
    - Accident Risk (Hanoi Open Data) boosts both n (avoidance) and N, and penalizes P.
    """
    # 1. Base membership values based on OpenStreetMap Road Type
    if road_type == "highway":
        # Highways: High flow, low hesitation, low baseline congestion
        p_base = 0.75
        n_base = 0.15
        neg_base = 0.10
    elif road_type == "local":
        # Local roads/alleys: Low speed capacity, high hesitation, higher congestion baseline
        p_base = 0.35
        n_base = 0.35
        neg_base = 0.30
    else:
        # Urban roads / Arterials (default)
        p_base = 0.55
        n_base = 0.25
        neg_base = 0.20
        
    # 2. Adjustments based on VietMap Traffic Density (0.0 = free flow, 1.0 = bumper-to-bumper)
    p_traffic_penalty = 0.50 * traffic_density
    neg_traffic_boost = 0.60 * traffic_density
    
    # 3. Adjustments based on OpenWeatherMap weather state
    if weather == "rainy":
        p_weather_penalty = 0.15
        n_weather_boost = 0.25
        neg_weather_boost = 0.05
    elif weather == "stormy":
        # Storms cause major visibility issues (high hesitation) and water ponding (congestion)
        p_weather_penalty = 0.30
        n_weather_boost = 0.45
        neg_weather_boost = 0.15
    else:  # sunny / clear
        p_weather_penalty = 0.0
        n_weather_boost = 0.0
        neg_weather_boost = 0.0
        
    # 4. Adjustments based on local Open Data safety and accident rates (0.0 = safe, 1.0 = active crash)
    p_safety_penalty = 0.40 * accident_risk
    n_safety_boost = 0.20 * accident_risk
    neg_safety_boost = 0.50 * accident_risk
    
    # 5. Calculate raw values, ensuring bounds are at least 0.05 to avoid division by zero or absolute zero probabilities
    p_raw = max(0.05, p_base - p_traffic_penalty - p_weather_penalty - p_safety_penalty)
    n_raw = max(0.05, n_base + n_weather_boost + n_safety_boost)
    neg_raw = max(0.05, neg_base + neg_traffic_boost + neg_weather_boost + neg_safety_boost)
    
    # 6. Normalize to satisfy the picture fuzzy constraint: P + N + n = 1.0
    total = p_raw + n_raw + neg_raw
    p_final = p_raw / total
    n_final = n_raw / total
    neg_final = neg_raw / total
    
    return round(p_final, 3), round(n_final, 3), round(neg_final, 3)


def get_formula_explanation(road_type: str, traffic_density: float, weather: str, accident_risk: float) -> dict:
    """
    Returns a step-by-step description of the calculations for front-end math panels.
    """
    if road_type == "highway":
        p_base, n_base, neg_base = 0.75, 0.15, 0.10
    elif road_type == "local":
        p_base, n_base, neg_base = 0.35, 0.35, 0.30
    else:
        p_base, n_base, neg_base = 0.55, 0.25, 0.20

    p_traffic_penalty = 0.50 * traffic_density
    neg_traffic_boost = 0.60 * traffic_density

    if weather == "rainy":
        p_weather_penalty, n_weather_boost, neg_weather_boost = 0.15, 0.25, 0.05
    elif weather == "stormy":
        p_weather_penalty, n_weather_boost, neg_weather_boost = 0.30, 0.45, 0.15
    else:
        p_weather_penalty, n_weather_boost, neg_weather_boost = 0.0, 0.0, 0.0

    p_safety_penalty = 0.40 * accident_risk
    n_safety_boost = 0.20 * accident_risk
    neg_safety_boost = 0.50 * accident_risk

    p_raw = max(0.05, p_base - p_traffic_penalty - p_weather_penalty - p_safety_penalty)
    n_raw = max(0.05, n_base + n_weather_boost + n_safety_boost)
    neg_raw = max(0.05, neg_base + neg_traffic_boost + neg_weather_boost + neg_safety_boost)
    total = p_raw + n_raw + neg_raw

    return {
        "inputs": {
            "road_type": road_type,
            "traffic_density": traffic_density,
            "weather": weather,
            "accident_risk": accident_risk
        },
        "baselines": {"P": p_base, "N": n_base, "n": neg_base},
        "traffic_effects": {"P_penalty": round(p_traffic_penalty, 3), "n_boost": round(neg_traffic_boost, 3)},
        "weather_effects": {"P_penalty": round(p_weather_penalty, 3), "N_boost": round(n_weather_boost, 3), "n_boost": round(neg_weather_boost, 3)},
        "safety_effects": {"P_penalty": round(p_safety_penalty, 3), "N_boost": round(n_safety_boost, 3), "n_boost": round(neg_safety_boost, 3)},
        "raw_sums": {"P": round(p_raw, 3), "N": round(n_raw, 3), "n": round(neg_raw, 3), "sum": round(total, 3)},
        "normalized": {"P": round(p_raw / total, 3), "N": round(n_raw / total, 3), "n": round(neg_raw / total, 3)}
    }
