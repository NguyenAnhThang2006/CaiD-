// PFIG-LLM Traffic Optimizer Frontend Controller - Vanilla JS

let map;
let pathLayers = { pfig: null, dijkstra: null };
let nodeMarkers = {};
let edgeLines = [];
let comparisonChart = null;

// Graph state
let graphData = { nodes: [], edges: [] };
let currentRouteData = null;

// VOV News reports state
let vovReports = [];
let activeTickerIndex = 0;

document.addEventListener("DOMContentLoaded", () => {
    initApp();
});

function initApp() {
    initMap();
    initSliders();
    fetchGraphData();
    setupEventListeners();
    fetchVOVReports();
}

// 1. Initialize Leaflet Map with Dark Theme tiles
function initMap() {
    // Center at Nguyen Chi Thanh, Hanoi
    map = L.map('map', {
        center: [21.018, 105.815],
        zoom: 13,
        zoomControl: true
    });

    // CartoDB Dark Matter tiles match the premium dark theme
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 20
    }).addTo(map);
}

// 2. Initialize weights sliders to sum to 1.0 dynamically
function initSliders() {
    const alpha = document.getElementById("alpha-slider");
    const beta = document.getElementById("beta-slider");
    const gamma = document.getElementById("gamma-slider");
    
    const alphaVal = document.getElementById("alpha-val");
    const betaVal = document.getElementById("beta-val");
    const gammaVal = document.getElementById("gamma-val");

    function adjustSliders(changedSlider) {
        let a = parseFloat(alpha.value);
        let b = parseFloat(beta.value);
        let g = parseFloat(gamma.value);
        
        let sum = a + b + g;
        
        if (sum !== 1.0) {
            // Adjust the other two sliders proportionally
            const diff = 1.0 - sum;
            if (changedSlider === 'alpha') {
                const totalOthers = b + g;
                if (totalOthers > 0) {
                    b += diff * (b / totalOthers);
                    g += diff * (g / totalOthers);
                } else {
                    b += diff / 2;
                    g += diff / 2;
                }
            } else if (changedSlider === 'beta') {
                const totalOthers = a + g;
                if (totalOthers > 0) {
                    a += diff * (a / totalOthers);
                    g += diff * (g / totalOthers);
                } else {
                    a += diff / 2;
                    g += diff / 2;
                }
            } else {
                const totalOthers = a + b;
                if (totalOthers > 0) {
                    a += diff * (a / totalOthers);
                    b += diff * (b / totalOthers);
                } else {
                    a += diff / 2;
                    b += diff / 2;
                }
            }
            
            // Clamp and update values
            alpha.value = Math.max(0, Math.min(1, a)).toFixed(2);
            beta.value = Math.max(0, Math.min(1, b)).toFixed(2);
            gamma.value = Math.max(0, Math.min(1, g)).toFixed(2);
        }

        // Update display text
        alphaVal.innerText = parseFloat(alpha.value).toFixed(2);
        betaVal.innerText = parseFloat(beta.value).toFixed(2);
        gammaVal.innerText = parseFloat(gamma.value).toFixed(2);
    }

    alpha.addEventListener("input", () => adjustSliders('alpha'));
    beta.addEventListener("input", () => adjustSliders('beta'));
    gamma.addEventListener("input", () => adjustSliders('gamma'));
}

// 3. Fetch nodes and edges and render network
function fetchGraphData() {
    fetch('/api/graph')
        .then(res => res.json())
        .then(data => {
            graphData = data;
            
            // Set environment selects in header
            document.getElementById("weather-select").value = data.weather;
            document.getElementById("time-select").value = data.time_of_day;
            
            renderGraphOnMap();
            populateNodeDropdowns();
        })
        .catch(err => console.error("Error fetching graph data:", err));
}

// 4. Render nodes and edges
function renderGraphOnMap() {
    // Clear old layers
    edgeLines.forEach(line => map.removeLayer(line));
    edgeLines = [];
    
    Object.values(nodeMarkers).forEach(marker => map.removeLayer(marker));
    nodeMarkers = {};

    // Render edges first so nodes appear on top
    graphData.edges.forEach(edge => {
        const sourceNode = graphData.nodes.find(n => n.id === edge.source);
        const targetNode = graphData.nodes.find(n => n.id === edge.target);
        
        if (sourceNode && targetNode) {
            // Determine color based on congestion negative degree
            // red: congestion, green: clear, orange: medium
            let color = '#475569'; // default dark gray
            if (edge.n > 0.5) {
                color = '#ea5455';
            } else if (edge.N > 0.45) {
                color = '#ff9f43';
            } else if (edge.P > 0.5) {
                color = '#28c76f';
            }
            
            // Bam theo hinh dang duong thuc te tu OpenStreetMap (edge.geometry).
            // Neu vi ly do nao do khong co, fallback ve noi thang 2 nut nhu cu.
            const lineCoords = (edge.geometry && edge.geometry.length >= 2)
                ? edge.geometry
                : [sourceNode.coords, targetNode.coords];

            const line = L.polyline(lineCoords, {
                color: color,
                weight: 4,
                opacity: 0.6,
                dashArray: '5, 10'
            }).addTo(map);
            
            // Add popup showing fuzzy state and physical OSM/VietMap details
            line.bindPopup(`
                <div class="map-popup-title">${edge.source} &harr; ${edge.target}</div>
                <div class="map-popup-fuzzy">
                    <div>Khoảng cách thực tế (OSM): <strong>${edge.distance_km} km</strong></div>
                    <div>Loại đường: <strong>${edge.road_type.toUpperCase()}</strong></div>
                    <div>Kẹt xe (VietMap): <strong>${Math.round(edge.traffic_density * 100)}%</strong></div>
                    <div>Nguy cơ tai nạn: <strong>${Math.round(edge.accident_risk * 100)}%</strong></div>
                    <div style="border-top: 1px dashed rgba(255,255,255,0.1); margin-top: 4px; padding-top: 4px;">
                        <span class="popup-p">Độ chảy (P): <strong>${edge.P}</strong></span> | 
                        <span class="popup-n">Độ do dự (N): <strong>${edge.N}</strong></span> | 
                        <span class="popup-neg">Độ kẹt (n): <strong>${edge.n}</strong></span>
                    </div>
                </div>
            `);
            
            // Edge click selects it for the real-world input editor
            line.on('click', (e) => {
                selectElementForRealWorld('edge', edge);
                // Keep popup open but trigger UI updates
            });
            
            edgeLines.push(line);
        }
    });

    // Render nodes
    graphData.nodes.forEach(node => {
        // Custom circle marker
        let markerColor = '#7367f0'; // default brand color
        if (node.n > 0.5) markerColor = '#ea5455'; // Red for congested
        else if (node.N > 0.5) markerColor = '#ff9f43'; // Orange for uncertain
        
        const marker = L.circleMarker(node.coords, {
            radius: 8,
            fillColor: markerColor,
            color: '#ffffff',
            weight: 2,
            opacity: 1,
            fillOpacity: 0.8
        }).addTo(map);
        
        marker.bindPopup(`
            <div class="map-popup-title">Nút: ${node.id}</div>
            <div class="map-popup-fuzzy">
                <span class="popup-p">Lưu lượng (P): <strong>${node.P}</strong></span> | 
                <span class="popup-n">Độ do dự (N): <strong>${node.N}</strong></span> | 
                <span class="popup-neg">Tránh kẹt (n): <strong>${node.n}</strong></span>
            </div>
            <div class="popup-actions" style="margin-top: 10px; display: flex; gap: 6px;">
                <button class="secondary-btn small-btn" style="padding: 4px 6px; font-size: 0.75rem; flex-grow: 1; justify-content: center; height: 26px;" onclick="setAsStart('${node.id}')">
                    <i class="fa-solid fa-circle-play" style="color: var(--flow-emerald);"></i> Đi từ đây
                </button>
                <button class="secondary-btn small-btn" style="padding: 4px 6px; font-size: 0.75rem; flex-grow: 1; justify-content: center; height: 26px;" onclick="setAsEnd('${node.id}')">
                    <i class="fa-solid fa-flag-checkered" style="color: var(--congestion-crimson);"></i> Đến đây
                </button>
            </div>
        `);
        
        // Node click selects it for real-world input editor
        marker.on('click', () => {
            selectElementForRealWorld('node', node);
        });
        
        nodeMarkers[node.id] = marker;
    });
}

// 5. Populate start & destination selects
function populateNodeDropdowns() {
    const sourceSelect = document.getElementById("source-select");
    const targetSelect = document.getElementById("target-select");
    
    // Clear old options
    sourceSelect.innerHTML = "";
    targetSelect.innerHTML = "";
    
    graphData.nodes.forEach(node => {
        const opt1 = document.createElement("option");
        opt1.value = node.id;
        opt1.innerText = node.id;
        sourceSelect.appendChild(opt1);
        
        const opt2 = document.createElement("option");
        opt2.value = node.id;
        opt2.innerText = node.id;
        targetSelect.appendChild(opt2);
    });
    
    // Set default selections
    sourceSelect.value = "My Dinh";
    targetSelect.value = "HUST";
}

// 6. Setup event listeners
function setupEventListeners() {
    // Route computation trigger
    document.getElementById("route-btn").addEventListener("click", computeRoute);
    
    // Explain trigger
    document.getElementById("explain-btn").addEventListener("click", requestRouteExplanation);
    
    // Weather & time parameters changing
    document.getElementById("weather-select").addEventListener("change", handleEnvironmentChange);
    document.getElementById("time-select").addEventListener("change", handleEnvironmentChange);
    
    // Ticker refresh
    document.getElementById("refresh-vov-btn").addEventListener("click", fetchVOVReports);
    
    // Math header fold/unfold
    document.getElementById("math-header").addEventListener("click", () => {
        const mathBox = document.getElementById("math-box");
        const icon = document.querySelector("#math-header .fold-icon");
        mathBox.classList.toggle("hidden");
        icon.classList.toggle("rotated");
    });
    
    // Save keys
    document.getElementById("save-keys-btn").addEventListener("click", () => {
        const key = document.getElementById("gemini-key").value.trim();
        if (key) {
            localStorage.setItem("gemini_api_key", key);
            alert("Đã lưu Gemini API Key cục bộ!");
        } else {
            localStorage.removeItem("gemini_api_key");
            alert("Đã xóa Gemini API Key cục bộ.");
        }
    });
    
    // Real-world inputs listeners
    const rwDensity = document.getElementById("rw-density");
    if (rwDensity) {
        rwDensity.addEventListener("input", (e) => {
            document.getElementById("rw-density-val").innerText = Math.round(e.target.value * 100) + "%";
            updateMathTransitionPreview();
        });
    }
    const rwSafety = document.getElementById("rw-safety");
    if (rwSafety) {
        rwSafety.addEventListener("input", (e) => {
            document.getElementById("rw-safety-val").innerText = Math.round(e.target.value * 100) + "%";
            updateMathTransitionPreview();
        });
    }
    const rwRoadType = document.getElementById("rw-road-type");
    if (rwRoadType) {
        rwRoadType.addEventListener("change", updateMathTransitionPreview);
    }
    const rwUpdateBtn = document.getElementById("rw-update-btn");
    if (rwUpdateBtn) {
        rwUpdateBtn.addEventListener("click", updateElementPhysicalData);
    }
    
    // Auto load key from storage if present
    const savedKey = localStorage.getItem("gemini_api_key");
    if (savedKey) {
        document.getElementById("gemini-key").value = savedKey;
    }
}

// 7. Handle environment (weather, hour) parameters update
function handleEnvironmentChange() {
    const weather = document.getElementById("weather-select").value;
    const timeOfDay = document.getElementById("time-select").value;
    
    // Map overlay loading indicator
    document.getElementById("map").style.opacity = 0.5;
    
    fetch('/api/update_traffic', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ weather, time_of_day: timeOfDay })
    })
    .then(res => res.json())
    .then(data => {
        document.getElementById("map").style.opacity = 1;
        fetchGraphData(); // reload graph nodes & edges
        
        // If a route was already calculated, recalculate it dynamically
        const start = document.getElementById("source-select").value;
        const stop = document.getElementById("target-select").value;
        if (start !== stop) {
            computeRoute();
        }
    })
    .catch(err => {
        document.getElementById("map").style.opacity = 1;
        console.error("Error updating environment:", err);
    });
}

// 8. Main route finding call
function computeRoute() {
    const source = document.getElementById("source-select").value;
    const target = document.getElementById("target-select").value;
    
    if (source === target) {
        alert("Điểm đi và điểm đến không thể trùng nhau!");
        return;
    }
    
    const alpha = parseFloat(document.getElementById("alpha-slider").value);
    const beta = parseFloat(document.getElementById("beta-slider").value);
    const gamma = parseFloat(document.getElementById("gamma-slider").value);
    
    const routeBtn = document.getElementById("route-btn");
    routeBtn.innerHTML = '<i class="fa-solid fa-spinner loading-dots"></i> Đang tính toán...';
    routeBtn.disabled = true;
    
    fetch('/api/route', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source, target, alpha, beta, gamma })
    })
    .then(res => res.json())
    .then(data => {
        routeBtn.innerHTML = '<i class="fa-solid fa-compass"></i> Tìm lộ trình tối ưu';
        routeBtn.disabled = false;
        
        currentRouteData = data;
        currentRouteData.source = source;
        currentRouteData.target = target;
        
        // Enable XAI explanation button
        document.getElementById("explain-btn").disabled = false;
        
        // Render paths on map
        drawRoutes(data.pfig.path, data.dijkstra.path);
        
        // Update comparison table & stats
        updateComparisonStats(data);
        
        // Render comparison chart
        renderChart(data);
        
        // Render step by step PFIG logic math log
        renderMathLogs(data.pfig.steps, data.pfig.intensity);
        
        // Auto trigger explanation generating
        requestRouteExplanation();
    })
    .catch(err => {
        routeBtn.innerHTML = '<i class="fa-solid fa-compass"></i> Tìm lộ trình tối ưu';
        routeBtn.disabled = false;
        console.error("Error computing routes:", err);
    });
}

// 9. Ghep cac doan hinh dang duong thuc te (OSM) cua tung canh lien tiep
// trong path thanh 1 day toa do lien tuc, bam sat duong di thuc te.
function buildPathCoordinates(path) {
    const coords = [];
    for (let i = 0; i < path.length - 1; i++) {
        const a = path[i];
        const b = path[i + 1];
        const edge = graphData.edges.find(e =>
            (e.source === a && e.target === b) || (e.source === b && e.target === a)
        );

        let segment;
        if (edge && edge.geometry && edge.geometry.length >= 2) {
            segment = edge.geometry;
            // Canh duoc luu theo huong "source -> target"; neu path dang di
            // theo huong nguoc lai thi dao lai thu tu diem cho dung huong.
            if (edge.source === b && edge.target === a) {
                segment = segment.slice().reverse();
            }
        } else {
            // Fallback: khong co du lieu hinh dang -> noi thang nhu truoc day
            const nodeA = graphData.nodes.find(n => n.id === a);
            const nodeB = graphData.nodes.find(n => n.id === b);
            segment = [nodeA.coords, nodeB.coords];
        }

        // Bo diem dau cua doan sau de khong bi lap diem noi giua 2 canh
        if (coords.length > 0) {
            coords.push(...segment.slice(1));
        } else {
            coords.push(...segment);
        }
    }
    return coords;
}

// 10. Draw paths on map with parallel offset to prevent overlaps
function drawRoutes(pfigPath, dijkstraPath) {
    if (pathLayers.pfig) map.removeLayer(pathLayers.pfig);
    if (pathLayers.dijkstra) map.removeLayer(pathLayers.dijkstra);
    
    // Clear old start/end markers
    if (window.startMarker) map.removeLayer(window.startMarker);
    if (window.endMarker) map.removeLayer(window.endMarker);
    
    const dijkstraCoords = buildPathCoordinates(dijkstraPath);
    const pfigCoords = buildPathCoordinates(pfigPath);
    
    // Check if paths share segment sections or are identical.
    // To be clean and avoid any overlaps, we shift Dijkstra slightly to the left and PFIG slightly to the right.
    const offsetDijkstraCoords = offsetCoordinates(dijkstraCoords, -0.0001);
    const offsetPfigCoords = offsetCoordinates(pfigCoords, 0.0001);
    
    // Draw Dijkstra (Standard Google shortest path) in Cyan, dashed
    pathLayers.dijkstra = L.polyline(offsetDijkstraCoords, {
        color: '#00cfe8',
        weight: 5,
        opacity: 0.85,
        dashArray: '8, 8',
        lineCap: 'round',
        lineJoin: 'round'
    }).addTo(map);
    
    // Draw PFIG Route (Fuzzy) in Orange, solid, glowing
    pathLayers.pfig = L.polyline(offsetPfigCoords, {
        color: '#ff9f43',
        weight: 6,
        opacity: 0.95,
        lineCap: 'round',
        lineJoin: 'round'
    }).addTo(map);
    
    // Add Start (A) and End (B) beautiful markers
    const startNode = graphData.nodes.find(n => n.id === pfigPath[0]);
    const endNode = graphData.nodes.find(n => n.id === pfigPath[pfigPath.length - 1]);
    
    if (startNode) {
        const startIcon = L.divIcon({
            className: 'custom-route-marker marker-start',
            html: `<div style="background-color: var(--flow-emerald); color: white; width: 28px; height: 28px; border-radius: 50%; border: 3px solid white; display: flex; align-items: center; justify-content: center; font-weight: bold; font-family: var(--font-mono); box-shadow: 0 0 10px rgba(40, 199, 111, 0.7);">A</div>`,
            iconSize: [28, 28],
            iconAnchor: [14, 14]
        });
        window.startMarker = L.marker(startNode.coords, { icon: startIcon }).addTo(map);
        window.startMarker.bindPopup(`<strong>Điểm xuất phát (A):</strong> ${startNode.id}`);
    }
    
    if (endNode) {
        const endIcon = L.divIcon({
            className: 'custom-route-marker marker-end',
            html: `<div style="background-color: var(--congestion-crimson); color: white; width: 28px; height: 28px; border-radius: 50%; border: 3px solid white; display: flex; align-items: center; justify-content: center; font-weight: bold; font-family: var(--font-mono); box-shadow: 0 0 10px rgba(234, 84, 85, 0.7);">B</div>`,
            iconSize: [28, 28],
            iconAnchor: [14, 14]
        });
        window.endMarker = L.marker(endNode.coords, { icon: endIcon }).addTo(map);
        window.endMarker.bindPopup(`<strong>Điểm kết thúc (B):</strong> ${endNode.id}`);
    }
    
    // Adjust map viewport to cover routes
    const bounds = L.latLngBounds([...pfigCoords, ...dijkstraCoords]);
    map.fitBounds(bounds, { padding: [50, 50] });
}

// Helper function to shift a line coordinates perpendicular to its segments
function offsetCoordinates(coords, offsetVal) {
    if (coords.length < 2) return coords;
    const result = [];
    for (let i = 0; i < coords.length; i++) {
        let dx = 0;
        let dy = 0;
        
        if (i === 0) {
            dx = coords[1][0] - coords[0][0];
            dy = coords[1][1] - coords[0][1];
        } else if (i === coords.length - 1) {
            dx = coords[coords.length - 1][0] - coords[coords.length - 2][0];
            dy = coords[coords.length - 1][1] - coords[coords.length - 2][1];
        } else {
            dx = (coords[i + 1][0] - coords[i - 1][0]) / 2;
            dy = (coords[i + 1][1] - coords[i - 1][1]) / 2;
        }
        
        const len = Math.sqrt(dx * dx + dy * dy);
        if (len === 0) {
            result.push([coords[i][0], coords[i][1]]);
            continue;
        }
        
        // Perpendicular vector (-dy, dx)
        const nx = -dy / len;
        const ny = dx / len;
        
        result.push([
            coords[i][0] + nx * offsetVal,
            coords[i][1] + ny * offsetVal
        ]);
    }
    return result;
}

// 11. Update table metrics
function updateComparisonStats(data) {
    document.getElementById("m-dijkstra-dist").innerText = `${data.dijkstra.distance_km} km`;
    document.getElementById("m-pfig-dist").innerText = `${data.pfig.distance_km} km`;
    
    const distDiff = data.pfig.distance_km - data.dijkstra.distance_km;
    const distCell = document.getElementById("m-dist-diff");
    distCell.innerText = distDiff === 0 ? "Bằng nhau" : `+${distDiff.toFixed(2)} km`;
    distCell.className = distDiff === 0 ? "neutral" : "negative"; // going further is negative
    
    document.getElementById("m-dijkstra-time").innerText = `${data.dijkstra.duration_mins} phút`;
    document.getElementById("m-pfig-time").innerText = `${data.pfig.duration_mins} phút`;
    
    const timeSaved = data.dijkstra.duration_mins - data.pfig.duration_mins;
    const timeCell = document.getElementById("m-time-diff");
    if (timeSaved > 0) {
        timeCell.innerText = `Nhanh hơn -${timeSaved.toFixed(1)}m`;
        timeCell.className = "positive";
    } else if (timeSaved < 0) {
        timeCell.innerText = `Chậm hơn +${Math.abs(timeSaved).toFixed(1)}m`;
        timeCell.className = "negative";
    } else {
        timeCell.innerText = "Bằng nhau";
        timeCell.className = "neutral";
    }
    
    document.getElementById("m-dijkstra-delay").innerText = `${data.dijkstra.delay_mins} phút`;
    document.getElementById("m-pfig-delay").innerText = `${data.pfig.delay_mins} phút`;
    
    const delaySaved = data.dijkstra.delay_mins - data.pfig.delay_mins;
    const delayCell = document.getElementById("m-delay-diff");
    if (delaySaved > 0) {
        delayCell.innerText = `Giảm kẹt -${delaySaved.toFixed(1)}m`;
        delayCell.className = "positive";
    } else if (delaySaved < 0) {
        delayCell.innerText = `Tăng kẹt +${Math.abs(delaySaved).toFixed(1)}m`;
        delayCell.className = "negative";
    } else {
        delayCell.innerText = "Bằng nhau";
        delayCell.className = "neutral";
    }
    
    document.getElementById("m-dijkstra-fuzzy").innerText = `(${data.dijkstra.intensity.join(', ')})`;
    document.getElementById("m-pfig-fuzzy").innerText = `(${data.pfig.intensity.join(', ')})`;
}

// 12. Render Comparison Bar Chart
function renderChart(data) {
    const ctx = document.getElementById('comparison-chart').getContext('2d');
    
    // Destroy previous chart instance if exists
    if (comparisonChart) {
        comparisonChart.destroy();
    }
    
    comparisonChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Tổng thời gian di chuyển (phút)', 'Thời gian kẹt xe/trễ (phút)'],
            datasets: [
                {
                    label: 'Dijkstra (Mặc định)',
                    data: [data.dijkstra.duration_mins, data.dijkstra.delay_mins],
                    backgroundColor: 'rgba(0, 207, 232, 0.6)',
                    borderColor: '#00cfe8',
                    borderWidth: 2,
                    borderRadius: 4
                },
                {
                    label: 'Lõi PFIG (Fuzzy)',
                    data: [data.pfig.duration_mins, data.pfig.delay_mins],
                    backgroundColor: 'rgba(255, 159, 67, 0.6)',
                    borderColor: '#ff9f43',
                    borderWidth: 2,
                    borderRadius: 4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: {
                        color: '#94a3b8',
                        font: { family: 'Outfit' }
                    }
                }
            },
            scales: {
                x: {
                    ticks: { color: '#94a3b8', font: { family: 'Outfit' } },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' }
                },
                y: {
                    ticks: { color: '#94a3b8', font: { family: 'Outfit' } },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    beginAtZero: true
                }
            }
        }
    });
}

// 13. Render math formulas details in log card
// 12. Render math formulas details in log card
function renderMathLogs(steps, finalIntensity) {
    const mathBox = document.getElementById("math-box");
    mathBox.innerHTML = "";
    
    // Kiểm tra an toàn phòng trường hợp mảng dữ liệu bị rỗng
    if (!steps || steps.length === 0) {
        mathBox.innerHTML = '<div class="empty-state"><p>Không có dữ liệu các bước tính toán mờ.</p></div>';
        return;
    }
    
    let html = '';
    
    // Đổ dữ liệu từng bước dựa chính xác vào cấu trúc mảng 'step_fuzzy' từ Backend trả về
    steps.forEach((step, idx) => {
        html += `
            <div class="math-step" style="margin-bottom: 12px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px;">
                <div class="math-step-header" style="color: var(--primary); font-weight: 600; margin-bottom: 6px;">
                    Bước ${idx + 1}: Di chuyển từ nút [${step.from}] &rarr; đến nút [${step.to}]
                </div>
                <div class="math-step-calc" style="color: var(--text-secondary); line-height: 1.6; font-size: 0.85rem;">
                    Sử dụng toán tử liên thuộc toán học PFIG để trích xuất cường độ mờ cho bước di chuyển này:<br>
                    &bull; Cường độ dòng chảy tích cực: $ic_1 = \\min(P_{\\text{start}}, P_{\\text{end}}) = ${step.step_fuzzy[0]}$<br>
                    &bull; Cường độ do dự trung lập: $ic_2 = \\min(N_{\\text{start}}, N_{\\text{end}}) = ${step.step_fuzzy[1]}$<br>
                    &bull; Cường độ ùn tắc tiêu cực: $ic_3 = \\max(n_{\\text{start}}, n_{\\text{end}}) = ${step.step_fuzzy[2]}$
                </div>
                <div class="math-step-result" style="color: var(--pfig-route); font-weight: 600; margin-top: 6px;">
                    Kết quả bộ ba số mờ liên thuộc của bước: $ic_{${idx+1}} = (${step.step_fuzzy.join(', ')})$
                </div>
            </div>
        `;
    });
    
    // Đóng gói giá trị tích lũy toàn lộ trình theo nguyên lý thắt nút cổ chai (Bottleneck Principle)
    html += `
        <div class="math-step" style="border-left: 3px solid var(--pfig-route); background: rgba(255, 159, 67, 0.04); padding: 12px; border-radius: 0 8px 8px 0;">
            <div class="math-step-header" style="color: var(--pfig-route); font-weight: 600;">
                Tích lũy toàn lộ trình (Path Intensity Accumulation)
            </div>
            <div class="math-step-calc" style="color: var(--text-secondary); line-height: 1.6; font-size: 0.85rem;">
                Áp dụng nguyên lý đóng không gian mờ bức tranh (Picture Fuzzy Graph Bottleneck):<br>
                &bull; $I_{s1} = \\min_j(ic_{j, 1}) = ${finalIntensity[0]}$ (Lưu lượng tích cực tối thiểu trên tuyến)<br>
&bull; $I_{s2} = \\min_j(ic_{j, 2}) = ${finalIntensity[1]}$ (Độ bất định do dự tối thiểu trên tuyến)<br>
                &bull; $I_{s3} = \\max_j(ic_{j, 3}) = ${finalIntensity[2]}$ (Rủi ro kẹt xe tiêu cực tối đa trên tuyến)<br>
            </div>
            <div class="math-step-result" style="color: var(--pfig-route); font-size: 0.9rem; font-weight: 700; margin-top: 6px;">
                Độ mờ tích lũy lộ trình tối ưu $I_s(P^*) = (${finalIntensity.join(', ')})$
            </div>
        </div>
    `;
    
    mathBox.innerHTML = html;

    // Ép MathJax biên dịch lại toàn bộ các ký hiệu toán học $...$ vừa được append vào DOM
    if (window.MathJax && window.MathJax.typeset) {
        window.MathJax.typeset();
    }
}

// 14. Call Gemini to get routes explanation
function requestRouteExplanation() {
    if (!currentRouteData) return;
    
    const explainBox = document.getElementById("explain-box");
    explainBox.innerHTML = `
        <div class="empty-state">
            <i class="fa-solid fa-spinner fa-spin" style="color: var(--primary);"></i>
            <p>Hệ thống AI đang phân tích dữ liệu mờ và tổng hợp lời giải trình bằng tiếng Việt...</p>
        </div>
    `;
    
    const apiKey = document.getElementById("gemini-key").value;
    
    fetch('/api/explain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            api_key: apiKey,
            source: currentRouteData.source,
            target: currentRouteData.target,
            pfig_route: currentRouteData.pfig.path,
            dijkstra_route: currentRouteData.dijkstra.path,
            pfig_metrics: currentRouteData.pfig,
            dijkstra_metrics: currentRouteData.dijkstra,
            avoided_bottlenecks: currentRouteData.avoided_bottlenecks
        })
    })
    .then(res => res.json())
    .then(data => {
        // Parse simple markdown to HTML tags
        explainBox.innerHTML = formatMarkdownToHTML(data.explanation);
    })
    .catch(err => {
        explainBox.innerHTML = `<p class="error-text">Có lỗi xảy ra khi kết nối tới mô hình AI: ${err.message}</p>`;
    });
}

// Helper to translate basic markdown syntax returned by Gemini to HTML
function formatMarkdownToHTML(text) {
    let formatted = text
        .replace(/### (.*)/g, '<h3>$1</h3>')
        .replace(/## (.*)/g, '<h2>$1</h2>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/\* (.*)/g, '<li>$1</li>')
        .replace(/&bull; (.*)/g, '<li>$1</li>')
        .replace(/> \[\!IMPORTANT\]/g, '<blockquote><strong>Lưu ý quan trọng:</strong><br>')
        .replace(/> \[\!NOTE\]/g, '<blockquote><strong>Ghi chú:</strong><br>')
        .replace(/> (.*)/g, '$1')
        .replace(/\n\n/g, '<p></p>')
        .replace(/\n/g, '<br>');
        
    // wrap lists in <ul>
    if (formatted.includes('<li>')) {
        // Simple regex to group adjacent <li> tags inside <ul>
        formatted = formatted.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
    }
    
    return formatted;
}

// 15. Fetch VOV simulated reports list
function fetchVOVReports() {
    fetch('/api/vov_samples')
        .then(res => res.json())
        .then(data => {
            vovReports = data;
            activeTickerIndex = 0;
            renderTicker();
        })
        .catch(err => console.error("Error fetching VOV reports:", err));
}

// 16. Render active ticker report
function renderTicker() {
    const ticker = document.getElementById("vov-ticker");
    ticker.innerHTML = "";
    
    if (vovReports.length === 0) {
        ticker.innerHTML = '<div class="ticker-item">Đang tải bản tin...</div>';
        return;
    }
    
    const activeReport = vovReports[activeTickerIndex];
    
    const tickerItem = document.createElement("div");
    tickerItem.className = "ticker-item";
    tickerItem.innerHTML = `<strong>[BẢN TIN MỚI]</strong> ${activeReport.text} <em>(Nhấp vào đây để cập nhật bản đồ)</em>`;
    
    // When user clicks the ticker, parse the text using Gemini and update weights!
    tickerItem.addEventListener("click", () => handleTickerClick(activeReport));
    
    ticker.appendChild(tickerItem);
    
    // Ticker scroll animation timer
    setTimeout(() => {
        activeTickerIndex = (activeTickerIndex + 1) % vovReports.length;
        renderTicker();
    }, 12000); // 12 seconds per report
}

// 17. Click ticker report -> parse fuzzy & update graph!
function handleTickerClick(report) {
    const ticker = document.getElementById("vov-ticker");
    ticker.innerHTML = `<div class="ticker-item" style="color: var(--primary);"><i class="fa-solid fa-spinner fa-spin"></i> Gemini đang phân dịch ngữ nghĩa báo cáo giao thông...</div>`;
    
    const apiKey = document.getElementById("gemini-key").value;
    
    fetch('/api/parse_report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: report.text, api_key: apiKey })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            alert(`Thành công!\n\nAI nhận dạng địa điểm: ${data.parsed.location}\nSố mờ PFIG mới trích xuất: P=${data.parsed.fuzzy[0]}, N=${data.parsed.fuzzy[1]}, n=${data.parsed.fuzzy[2]}\n\nTrọng số mờ của đồ thị đã cập nhật!`);
            fetchGraphData(); // reload map markers and lines
            
            // Recalculate if active
            const start = document.getElementById("source-select").value;
            const stop = document.getElementById("target-select").value;
            if (start !== stop) {
                computeRoute();
            }
        } else {
            alert(`Không cập nhật được: ${data.message}`);
        }
        renderTicker(); // restore scroll
    })
    .catch(err => {
        alert("Lỗi khi kết nối với máy chủ phân tích: " + err.message);
        renderTicker();
    });
}

// 18. Expose global window hooks for popup action buttons
window.setAsStart = function(nodeId) {
    const select = document.getElementById("source-select");
    select.value = nodeId;
    map.closePopup();
    computeRoute();
};

window.setAsEnd = function(nodeId) {
    const select = document.getElementById("target-select");
    select.value = nodeId;
    map.closePopup();
    computeRoute();
};

// 19. Handle element selection for physical real-world inputs
let selectedElement = null;

function selectElementForRealWorld(type, data) {
    selectedElement = {
        entity_type: type,
        name: type === 'node' ? data.id : [data.source, data.target],
        data: data
    };
    
    // UI elements visibility
    document.getElementById("realworld-select-node-edge").classList.add("hidden");
    document.getElementById("realworld-controls").classList.remove("hidden");
    document.getElementById("math-transition-section").classList.remove("hidden");
    
    const title = type === 'node' ? `Nút giao: ${data.id}` : `Tuyến: ${data.source} ↔ ${data.target}`;
    document.getElementById("rw-target-title").innerText = title;
    
    // Set field values
    document.getElementById("rw-road-type").value = data.road_type || "urban";
    document.getElementById("rw-density").value = data.traffic_density || 0.3;
    document.getElementById("rw-density-val").innerText = Math.round((data.traffic_density || 0.3) * 100) + "%";
    document.getElementById("rw-safety").value = data.accident_risk || 0.1;
    document.getElementById("rw-safety-val").innerText = Math.round((data.accident_risk || 0.1) * 100) + "%";
    
    // Weather label from header selector
    const weather = document.getElementById("weather-select").value;
    document.getElementById("rw-weather-val").innerText = weather.toUpperCase() + " (Đồng bộ theo thời tiết chung)";
    
    updateMathTransitionPreview();
}

// 20. Update math transition preview calculation in real-time
function updateMathTransitionPreview() {
    if (!selectedElement) return;
    
    const roadType = document.getElementById("rw-road-type").value;
    const trafficDensity = parseFloat(document.getElementById("rw-density").value);
    const weather = document.getElementById("weather-select").value;
    const accidentRisk = parseFloat(document.getElementById("rw-safety").value);
    
    fetch('/api/convert_real_world', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ road_type: roadType, traffic_density: trafficDensity, weather, accident_risk: accidentRisk })
    })
    .then(res => res.json())
    .then(data => {
        const box = document.getElementById("math-transition-box");
        
        box.innerHTML = `
            <div style="color: var(--primary); font-weight: bold; margin-bottom: 6px; font-size: 0.8rem;">CÔNG THỨC CHUYỂN ĐỔI MỜ:</div>
            
            <div style="margin-top: 4px; color: var(--text-primary);"><strong>1. Trọng số cơ sở (${data.inputs.road_type.toUpperCase()}):</strong></div>
            <span class="popup-p">&bull; P_base = ${data.baselines.P}</span><br>
            <span class="popup-n">&bull; N_base = ${data.baselines.N}</span><br>
            <span class="popup-neg">&bull; n_base = ${data.baselines.n}</span><br>
            
            <div style="margin-top: 6px; color: var(--text-primary);"><strong>2. Mật độ VietMap Traffic (${Math.round(data.inputs.traffic_density * 100)}%):</strong></div>
            <span class="popup-p">&bull; Phạt dòng chảy: -0.50 * density = -${data.traffic_effects.P_penalty}</span><br>
            <span class="popup-neg">&bull; Tăng kẹt xe: +0.60 * density = +${data.traffic_effects.n_boost}</span><br>
            
            <div style="margin-top: 6px; color: var(--text-primary);"><strong>3. Thời tiết OpenWeather (${data.inputs.weather.toUpperCase()}):</strong></div>
            <span class="popup-p">&bull; Phạt dòng chảy: -${data.weather_effects.P_penalty}</span><br>
            <span class="popup-n">&bull; Tăng do dự (mưa): +${data.weather_effects.N_boost}</span><br>
            <span class="popup-neg">&bull; Tăng cản trở: +${data.weather_effects.n_boost}</span><br>
            
            <div style="margin-top: 6px; color: var(--text-primary);"><strong>4. Nguy cơ tai nạn Hanoi Open Data (${Math.round(data.inputs.accident_risk * 100)}%):</strong></div>
            <span class="popup-p">&bull; Phạt dòng chảy: -0.40 * risk = -${data.safety_effects.P_penalty}</span><br>
            <span class="popup-n">&bull; Tăng lo ngại: +0.20 * risk = +${data.safety_effects.N_boost}</span><br>
            <span class="popup-neg">&bull; Tránh né kẹt: +0.50 * risk = +${data.safety_effects.n_boost}</span><br>
            
            <div style="margin-top: 8px; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 6px; color: var(--text-primary);"><strong>5. Giá trị mờ thô (Raw values):</strong></div>
            <span class="popup-p">&bull; P_raw = max(0.05, ${data.baselines.P} - ${data.traffic_effects.P_penalty} - ${data.weather_effects.P_penalty} - ${data.safety_effects.P_penalty}) = ${data.raw_sums.P}</span><br>
            <span class="popup-n">&bull; N_raw = max(0.05, ${data.baselines.N} + ${data.weather_effects.N_boost} + ${data.safety_effects.N_boost}) = ${data.raw_sums.N}</span><br>
            <span class="popup-neg">&bull; n_raw = max(0.05, ${data.baselines.n} + ${data.traffic_effects.n_boost} + ${data.weather_effects.n_boost} + ${data.safety_effects.n_boost}) = ${data.raw_sums.n}</span><br>
            <div>&bull; Tổng Raw = ${data.raw_sums.sum}</div>
            
            <div style="margin-top: 8px; border-top: 1px dashed rgba(255,255,255,0.12); padding-top: 6px; color: var(--pfig-route); font-weight: bold;"><strong>6. Số mờ chuẩn hóa (P + N + n = 1.0):</strong></div>
            <span class="popup-p">P = ${data.normalized.P} (Độ lưu thông)</span><br>
            <span class="popup-n">N = ${data.normalized.N} (Độ không xác định)</span><br>
            <span class="popup-neg">n = ${data.normalized.n} (Độ cản trở/kẹt xe)</span>
        `;
    })
    .catch(err => console.error("Error updates transition preview:", err));
}

// 21. Update element physical data on backend and reload
function updateElementPhysicalData() {
    if (!selectedElement) return;
    
    const roadType = document.getElementById("rw-road-type").value;
    const trafficDensity = parseFloat(document.getElementById("rw-density").value);
    const accidentRisk = parseFloat(document.getElementById("rw-safety").value);
    
    const rwUpdateBtn = document.getElementById("rw-update-btn");
    rwUpdateBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang lưu...';
    rwUpdateBtn.disabled = true;
    
    fetch('/api/update_element_physical', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            entity_type: selectedElement.entity_type,
            name: selectedElement.name,
            road_type: roadType,
            traffic_density: trafficDensity,
            accident_risk: accidentRisk
        })
    })
    .then(res => res.json())
    .then(data => {
        rwUpdateBtn.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> Cập nhật & Tính mờ';
        rwUpdateBtn.disabled = false;
        
        // Reload graph
        fetchGraphData();
        
        // If a route was already calculated, recalculate it dynamically
        const start = document.getElementById("source-select").value;
        const stop = document.getElementById("target-select").value;
        if (start !== stop) {
            computeRoute();
        }
    })
    .catch(err => {
        rwUpdateBtn.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> Cập nhật & Tính mờ';
        rwUpdateBtn.disabled = false;
        alert("Lỗi khi cập nhật dữ liệu: " + err.message);
    });
}
