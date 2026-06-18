import requests
import time
import random

class GoogleMapsTrafficClient:
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.intersections = {
            "My Dinh": "21.0284,105.7782",
            "Cau Giay": "21.0264,105.8013",
            "Nguyen Chi Thanh": "21.0205,105.8080",
            "Duong Lang": "21.0064,105.8005",
            "Nga Tu So": "21.0008,105.8155",
            "Xa Dan": "21.0195,105.8285",
            "HUST": "21.0065,105.8428"
        }

    def fetch_live_traffic_data(self, origin_name, destination_name, weather="sunny", time_of_day="off_peak", distance_km=None):
        """Fetches live travel time & distance from Google Maps API with environment context."""
        if not self.api_key:
            return self.simulate_traffic_data(origin_name, destination_name, weather, time_of_day, distance_km)
            
        origin = self.intersections.get(origin_name)
        destination = self.intersections.get(destination_name)
        if not origin or not destination:
            return self.simulate_traffic_data(origin_name, destination_name, weather, time_of_day, distance_km)
            
        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {
            "origins": origin,
            "destinations": destination,
            "departure_time": "now",
            "traffic_model": "best_guess",
            "key": self.api_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            if data.get("status") == "OK":
                element = data["rows"][0]["elements"][0]
                if element.get("status") == "OK":
                    distance_m = element["distance"]["value"] 
                    duration_s = element["duration"]["value"] 
                    duration_in_traffic_s = element.get("duration_in_traffic", {}).get("value", duration_s)
                    
                    distance_km = distance_m / 1000.0
                    duration_mins = duration_s / 60.0
                    duration_in_traffic_mins = duration_in_traffic_s / 60.0
                    
                    speed_kph = (distance_km / (duration_in_traffic_mins / 60.0)) if duration_in_traffic_mins > 0 else 30.0
                    free_flow_speed_kph = (distance_km / (duration_mins / 60.0)) if duration_mins > 0 else 40.0
                    
                    pair = tuple(sorted([origin_name, destination_name]))
                    p, n, neg = self.map_speed_to_fuzzy(speed_kph, free_flow_speed_kph, weather, time_of_day, pair)
                    
                    return {
                        "distance_km": round(distance_km, 2),
                        "duration_mins": round(duration_in_traffic_mins, 1),
                        "delay_mins": round(max(0.0, duration_in_traffic_mins - duration_mins), 1),
                        "speed_kph": round(speed_kph, 1),
                        "fuzzy": (p, n, neg),
                        "source": "Google Maps API"
                    }
        except Exception as e:
            print(f"Error fetching Google Maps API data: {e}")
        return self.simulate_traffic_data(origin_name, destination_name, weather, time_of_day, distance_km)

    def simulate_traffic_data(self, origin_name, destination_name, weather="sunny", time_of_day="off_peak", distance_km=None):
        """Simulates consistent and reliable traffic data with dynamic environment impact."""
        baseline_distances = {
            ("My Dinh", "Cau Giay"): 3.0,
            ("My Dinh", "Nguyen Chi Thanh"): 4.5,
            ("My Dinh", "Duong Lang"): 4.0,
            ("Cau Giay", "Duong Lang"): 1.5,
            ("Cau Giay", "Kim Ma"): 1.2,
            ("Nguyen Chi Thanh", "Duong Lang"): 0.8,
            ("Nguyen Chi Thanh", "Kim Ma"): 1.0,
            ("Nguyen Chi Thanh", "La Thanh"): 1.4,
            ("Kim Ma", "La Thanh"): 1.6,
            ("Duong Lang", "Nga Tu So"): 2.5,
            ("La Thanh", "Xa Dan"): 1.8,
            ("Nga Tu So", "Truong Chinh"): 1.7,
            ("Truong Chinh", "Dai Co Viet"): 2.0,
            ("Xa Dan", "Dai Co Viet"): 1.2,
            ("Dai Co Viet", "HUST"): 0.5
        }
        
        pair = tuple(sorted([origin_name, destination_name]))
        # Uu tien khoang cach THUC TE duoc truyen vao tu PFIGGraph (lay tu OpenStreetMap).
        # Bang baseline_distances chi con dung lam fallback khi khong co gia tri nao duoc truyen.
        dist = distance_km if distance_km is not None else baseline_distances.get(pair, 2.0)
        
        time_multipliers = {"morning_rush": 0.32, "evening_rush": 0.28, "off_peak": 0.85, "night": 1.2}
        weather_multipliers = {"sunny": 1.0, "rainy": 0.60, "stormy": 0.40}
        
        bottleneck_factor = 1.0
        congested_nodes = ["Nga Tu So", "Cau Giay", "Nguyen Chi Thanh", "Duong Lang", "La Thanh"]
        for node in congested_nodes:
            if node in pair:
                bottleneck_factor *= 0.75  # Tăng mức độ ảnh hưởng của điểm nghẽn hạ tầng
                
        free_flow_speed = 45.0  
        time_mult = time_multipliers.get(time_of_day, 0.8)
        weather_mult = weather_multipliers.get(weather, 1.0)
        
        random.seed(int(time.time() * 1000) % 10000)
        noise = random.uniform(0.92, 1.08)
        
        actual_speed = free_flow_speed * time_mult * weather_mult * bottleneck_factor * noise
        actual_speed = max(4.0, min(actual_speed, 60.0)) 
        
        duration_mins = (dist / actual_speed) * 60.0
        free_flow_duration_mins = (dist / free_flow_speed) * 60.0
        delay_mins = max(0.0, duration_mins - free_flow_duration_mins)
        
        p, n, neg = self.map_speed_to_fuzzy(actual_speed, free_flow_speed, weather, time_of_day, pair)
        
        return {
            "distance_km": round(dist, 2),
            "duration_mins": round(duration_mins, 1),
            "delay_mins": round(delay_mins, 1),
            "speed_kph": round(actual_speed, 1),
            "fuzzy": (p, n, neg),
            "source": "Traffic Simulator"
        }

    def map_speed_to_fuzzy(self, speed, free_flow_speed, weather="sunny", time_of_day="off_peak", edge_nodes=None):
        """
        Chiến lược phân phối không gian số mờ cải tiến (Non-linear Fuzzy Mapping).
        Bảo toàn cường độ phạt kẹt xe để ép thuật toán bẻ hướng rõ rệt.
        """
        ratio = speed / free_flow_speed
        
        # 1. Xác định mức phạt kẹt xe thực tế trước (Chỉ số n tiêu cực)
        if ratio >= 0.85:
            neg_val = 0.05
        elif ratio >= 0.6:
            neg_val = 0.25
        elif ratio >= 0.35:
            neg_val = 0.55
        else:
            neg_val = 0.85 # Tăng mạnh trần phạt kẹt xe khi tốc độ giảm sâu
            
        # 2. Tính toán chỉ số lưỡng lự (Chỉ số N trung lập) dựa trên bối cảnh
        u_val = 0.10
        if weather == "rainy": u_val += 0.25
        elif weather == "stormy": u_val += 0.45
        if time_of_day in ["morning_rush", "evening_rush"]: u_val += 0.15
        if edge_nodes and ("Nga Tu So" in edge_nodes or "Cau Giay" in edge_nodes):
            u_val += 0.15
            
        # Giới hạn trần cho điểm trung lập để tránh nuốt chửng không gian mờ
        u_val = min(u_val, 1.0 - neg_val - 0.05)
        
        # 3. Thành phần tích cực (Chỉ số P) nhận phần dung lượng còn lại nhằm bảo toàn tổng = 1.0
        p_val = max(0.05, 1.0 - neg_val - u_val)
        
        return round(p_val, 2), round(u_val, 2), round(neg_val, 2)