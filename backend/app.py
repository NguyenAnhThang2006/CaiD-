import os
from flask import Flask, request, jsonify, send_from_directory
from pfig_core import PFIGGraph
from google_maps_client import GoogleMapsTrafficClient
from vov_parser import VOVTrafficParser
from gemini_client import GeminiTrafficClient

# Initialize Flask app
# Serve static files from the 'frontend' directory
app = Flask(__name__, static_folder='../frontend', static_url_path='')

# Initialize PFIG Graph, Google Maps simulator and VOV parser
pfig = PFIGGraph()
maps_client = GoogleMapsTrafficClient()
vov_parser = VOVTrafficParser()

# Current environment settings
current_weather = "sunny"
current_time_of_day = "off_peak"

def update_all_graph_traffic(weather, time_of_day):
    """Updates all edge and vertex fuzzy values based on physical attributes, weather, and time."""
    global current_weather, current_time_of_day
    current_weather = weather
    current_time_of_day = time_of_day
    
    from real_world_converter import convert_physical_to_fuzzy
    
    # Update all edges based on their physical attributes
    for u, v in pfig.G.edges():
        attrs = pfig.G[u][v]
        r_type = attrs.get("road_type", "urban")
        density = attrs.get("traffic_density", 0.3)
        risk = attrs.get("accident_risk", 0.1)
        
        # Adjust traffic density based on time of day multiplier
        eff_density = density
        if time_of_day in ["morning_rush", "evening_rush"]:
            eff_density = min(1.0, density + 0.25)
        elif time_of_day == "night":
            eff_density = max(0.05, density - 0.15)
            
        p, n_val, neg = convert_physical_to_fuzzy(r_type, eff_density, weather, risk)
        pfig.update_fuzzy_parameters("edge", (u, v), p, n_val, neg)
        
    # Update nodes based on neighboring edge values
    for node in pfig.G.nodes():
        neighbors = list(pfig.G.neighbors(node))
        if neighbors:
            avg_p = sum(pfig.G[node][nbr]["P"] for nbr in neighbors) / len(neighbors)
            avg_n = sum(pfig.G[node][nbr]["N"] for nbr in neighbors) / len(neighbors)
            avg_neg = sum(pfig.G[node][nbr]["n"] for nbr in neighbors) / len(neighbors)
            # Make nodes slightly more neutral/uncertain than edges to reflect human decision hesitation
            node_n = min(0.9, avg_n + 0.1)
            node_p = max(0.05, avg_p - 0.05)
            node_neg = max(0.05, avg_neg - 0.05)
            
            # Normalize
            tot = node_p + node_n + node_neg
            if tot > 1.0:
                node_p /= tot
                node_n /= tot
                node_neg /= tot
                
            pfig.update_fuzzy_parameters("node", node, node_p, node_n, node_neg)

# Initialize graph with default traffic simulation
update_all_graph_traffic("sunny", "off_peak")

@app.route('/')
def index():
    """Serves the frontend application."""
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/graph', methods=['GET'])
def get_graph():
    """Returns the current state of the graph nodes, edges, and incidence pairs."""
    nodes = []
    for node, attrs in pfig.G.nodes(data=True):
        nodes.append({
            "id": node,
            "coords": attrs["coords"],
            "P": round(attrs["P"], 2),
            "N": round(attrs["N"], 2),
            "n": round(attrs["n"], 2),
            "road_type": attrs.get("road_type", "urban"),
            "traffic_density": round(attrs.get("traffic_density", 0.3), 2),
            "accident_risk": round(attrs.get("accident_risk", 0.1), 2)
        })
        
    edges = []
    for u, v, attrs in pfig.G.edges(data=True):
        edge_name = tuple(sorted([u, v]))
        inc_u = pfig.incidence_data.get((u, edge_name), (0.0, 0.0, 1.0))
        inc_v = pfig.incidence_data.get((v, edge_name), (0.0, 0.0, 1.0))

        fallback_geometry = [
            list(pfig.G.nodes[u]["coords"]),
            list(pfig.G.nodes[v]["coords"]),
        ]

        edges.append({
            "source": u,
            "target": v,
            "distance_km": attrs["distance"],
            "estimated_distance_km": attrs.get("estimated_distance_km"),
            "geometry": attrs.get("geometry", fallback_geometry),
            "P": round(attrs["P"], 2),
            "N": round(attrs["N"], 2),
            "n": round(attrs["n"], 2),
            "road_type": attrs.get("road_type", "urban"),
            "traffic_density": round(attrs.get("traffic_density", 0.3), 2),
            "accident_risk": round(attrs.get("accident_risk", 0.1), 2),
            "incidence_u": [round(x, 2) for x in inc_u],
            "incidence_v": [round(x, 2) for x in inc_v]
        })
        
    return jsonify({
        "nodes": nodes,
        "edges": edges,
        "weather": current_weather,
        "time_of_day": current_time_of_day
    })

@app.route('/api/convert_real_world', methods=['POST'])
def convert_real_world():
    """Calculates step-by-step conversion logic from real-world physical inputs to fuzzy numbers."""
    data = request.json or {}
    road_type = data.get("road_type", "urban")
    traffic_density = float(data.get("traffic_density", 0.3))
    weather = data.get("weather", "sunny")
    accident_risk = float(data.get("accident_risk", 0.1))
    
    from real_world_converter import get_formula_explanation
    explanation = get_formula_explanation(road_type, traffic_density, weather, accident_risk)
    return jsonify(explanation)

@app.route('/api/update_element_physical', methods=['POST'])
def update_element_physical():
    """Updates physical attributes of a node/edge and updates the PFIG graph weights."""
    data = request.json or {}
    entity_type = data.get("entity_type")  # 'node' or 'edge'
    name = data.get("name")  # node name (str) or edge vertices [u, v]
    road_type = data.get("road_type", "urban")
    traffic_density = float(data.get("traffic_density", 0.3))
    accident_risk = float(data.get("accident_risk", 0.1))
    
    from real_world_converter import convert_physical_to_fuzzy
    p, n_val, neg = convert_physical_to_fuzzy(road_type, traffic_density, current_weather, accident_risk)
    
    if entity_type == "node":
        if name in pfig.G.nodes:
            pfig.G.nodes[name]["road_type"] = road_type
            pfig.G.nodes[name]["traffic_density"] = traffic_density
            pfig.G.nodes[name]["accident_risk"] = accident_risk
            pfig.update_fuzzy_parameters("node", name, p, n_val, neg)
    elif entity_type == "edge":
        u, v = name
        if pfig.G.has_edge(u, v):
            pfig.G[u][v]["road_type"] = road_type
            pfig.G[u][v]["traffic_density"] = traffic_density
            pfig.G[u][v]["accident_risk"] = accident_risk
            pfig.update_fuzzy_parameters("edge", (u, v), p, n_val, neg)
            
    # Also update neighboring node fuzzy values based on new edges
    update_all_graph_traffic(current_weather, current_time_of_day)
            
    return jsonify({
        "status": "success",
        "fuzzy": [p, n_val, neg]
    })

@app.route('/api/route', methods=['POST'])
def calculate_route():
    """Calculates PFIG route vs. Traditional Dijkstra route."""
    data = request.json or {}
    source = data.get("source", "My Dinh")
    target = data.get("target", "HUST")
    
    alpha = float(data.get("alpha", 0.5))
    beta = float(data.get("beta", 0.3))
    gamma = float(data.get("gamma", 0.2))
    
    # 1. PFIG Route
    pfig_path, pfig_dist, pfig_cost = pfig.compute_pfig_route(source, target, alpha, beta, gamma)
    pfig_intensity_data = pfig.get_path_intensity(pfig_path)
    
    # Calculate travel duration based on current edge speeds
    pfig_duration = 0.0
    pfig_delay = 0.0
    for i in range(len(pfig_path) - 1):
        u = pfig_path[i]
        v = pfig_path[i+1]
        sim = maps_client.simulate_traffic_data(u, v, current_weather, current_time_of_day, distance_km=pfig.G[u][v]["distance"])
        pfig_duration += sim["duration_mins"]
        pfig_delay += sim["delay_mins"]
        
    # 2. Dijkstra Route
    dijkstra_path, dijkstra_dist = pfig.compute_shortest_path_dijkstra(source, target)
    dijkstra_intensity_data = pfig.get_path_intensity(dijkstra_path)
    
    dijkstra_duration = 0.0
    dijkstra_delay = 0.0
    for i in range(len(dijkstra_path) - 1):
        u = dijkstra_path[i]
        v = dijkstra_path[i+1]
        sim = maps_client.simulate_traffic_data(u, v, current_weather, current_time_of_day, distance_km=pfig.G[u][v]["distance"])
        dijkstra_duration += sim["duration_mins"]
        dijkstra_delay += sim["delay_mins"]
        
    # 3. Identify Avoided Bottlenecks
    # Look at nodes on Dijkstra path not present in PFIG path
    avoided_bottlenecks = []
    if dijkstra_path and pfig_path:
        pfig_nodes = set(pfig_path)
        for node in dijkstra_path:
            if node not in pfig_nodes:
                node_attr = pfig.G.nodes[node]
                # If negative flow (congestion) or neutral (hesitation) is high, it's a bottleneck
                if node_attr["n"] > 0.3 or node_attr["N"] > 0.4:
                    avoided_bottlenecks.append({
                        "node": node,
                        "P": round(node_attr["P"], 2),
                        "N": round(node_attr["N"], 2),
                        "n": round(node_attr["n"], 2)
                    })
                    
    # 4. Identify structural issues (Bridges, Cut Pairs) for user analysis
    bridges, cut_pairs = pfig.identify_structural_vulnerabilities(source, target)
    
    # Serialize bridges/cut-pairs
    formatted_bridges = []
    for b in bridges:
        formatted_bridges.append({
            "edge": b["edge"],
            "reason": b["reason"]
        })
    formatted_cut_pairs = []
    for cp in cut_pairs:
        formatted_cut_pairs.append({
            "node": cp["node"],
            "edge": cp["edge"],
            "reason": cp["reason"]
        })

    return jsonify({
        "pfig": {
            "path": pfig_path,
            "distance_km": round(pfig_dist, 2),
            "duration_mins": round(pfig_duration, 1),
            "delay_mins": round(pfig_delay, 1),
            "intensity": pfig_intensity_data["intensity"],
            "steps": pfig_intensity_data["steps"]
        },
        "dijkstra": {
            "path": dijkstra_path,
            "distance_km": round(dijkstra_dist, 2),
            "duration_mins": round(dijkstra_duration, 1),
            "delay_mins": round(dijkstra_delay, 1),
            "intensity": dijkstra_intensity_data["intensity"],
            "steps": dijkstra_intensity_data["steps"]
        },
        "avoided_bottlenecks": avoided_bottlenecks,
        "structural": {
            "bridges": formatted_bridges,
            "cut_pairs": formatted_cut_pairs
        }
    })

@app.route('/api/update_traffic', methods=['POST'])
def update_traffic():
    """Updates weather and time parameters, modifying the PFIG weights."""
    data = request.json or {}
    weather = data.get("weather", "sunny")
    time_of_day = data.get("time_of_day", "off_peak")
    
    update_all_graph_traffic(weather, time_of_day)
    
    return jsonify({
        "status": "success",
        "weather": current_weather,
        "time_of_day": current_time_of_day,
        "message": f"Graph weights updated for {weather} weather during {time_of_day} hours."
    })

@app.route('/api/parse_report', methods=['POST'])
def parse_report():
    """Parses a Vietnamese text traffic report and injects fuzzy parameters into the graph."""
    data = request.json or {}
    text = data.get("text", "")
    api_key = data.get("api_key")
    
    gemini_client = GeminiTrafficClient(api_key=api_key)
    parsed = gemini_client.parse_traffic_text_to_fuzzy(text)
    
    location = parsed.get("location")
    fuzzy = parsed.get("fuzzy")
    
    # Apply update to the graph if location matches
    if location in pfig.G.nodes:
        pfig.update_fuzzy_parameters("node", location, fuzzy[0], fuzzy[1], fuzzy[2])
        # Also update incident edges
        for neighbor in pfig.G.neighbors(location):
            # Make neighbors slightly worse
            curr_p = pfig.G[location][neighbor]["P"]
            curr_n = pfig.G[location][neighbor]["N"]
            curr_neg = pfig.G[location][neighbor]["n"]
            
            new_p = max(0.05, curr_p - 0.1 if fuzzy[2] > 0.4 else curr_p)
            new_n = min(0.9, curr_n + 0.1 if fuzzy[1] > 0.4 else curr_n)
            new_neg = min(0.9, curr_neg + 0.15 if fuzzy[2] > 0.4 else curr_neg)
            
            # Normalize
            tot = new_p + new_n + new_neg
            if tot > 1.0:
                new_p /= tot
                new_n /= tot
                new_neg /= tot
                
            pfig.update_fuzzy_parameters("edge", (location, neighbor), new_p, new_n, new_neg)
            
        success = True
        msg = f"Đã cập nhật chỉ số mờ cho {location} thành P={fuzzy[0]}, N={fuzzy[1]}, n={fuzzy[2]}."
    else:
        success = False
        msg = f"Không tìm thấy địa điểm '{location}' trên bản đồ case study."
        
    return jsonify({
        "success": success,
        "parsed": parsed,
        "message": msg
    })

@app.route('/api/explain', methods=['POST'])
def explain_route():
    """Generates the natural language explanation from Gemini."""
    data = request.json or {}
    api_key = data.get("api_key")
    source = data.get("source", "My Dinh")
    target = data.get("target", "HUST")
    pfig_route = data.get("pfig_route", [])
    dijkstra_route = data.get("dijkstra_route", [])
    pfig_metrics = data.get("pfig_metrics", {})
    dijkstra_metrics = data.get("dijkstra_metrics", {})
    avoided_bottlenecks = data.get("avoided_bottlenecks", [])
    
    gemini_client = GeminiTrafficClient(api_key=api_key)
    explanation = gemini_client.generate_route_explanation(
        source=source,
        target=target,
        pfig_route=pfig_route,
        dijkstra_route=dijkstra_route,
        pfig_metrics=pfig_metrics,
        dijkstra_metrics=dijkstra_metrics,
        avoided_bottlenecks=avoided_bottlenecks,
        weather=current_weather,
        time_of_day=current_time_of_day
    )
    
    return jsonify({
        "explanation": explanation
    })

@app.route('/api/vov_samples', methods=['GET'])
def get_vov_samples():
    """Returns the list of sample VOV Traffic text reports."""
    return jsonify(vov_parser.get_all_samples())

if __name__ == '__main__':
    # Run on port 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
