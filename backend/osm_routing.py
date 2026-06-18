"""
osm_routing.py
---------------------------------------------------------------------------
Module bo sung: lay HINH DANG DUONG DI THUC TE giua hai nut giao tu du lieu
OpenStreetMap, thay vi noi thang hai toa do lai voi nhau.

Truoc day, moi canh (u, v) trong PFIGGraph chi co 1 khoang cach "uoc luong"
va khi ve len ban do, frontend noi thang toa do cua u va v -> duong ve
khong bam theo pho thuc te.

Module nay dung OSRM (Open Source Routing Machine) - mot engine dinh tuyen
mien phi, ma nguon mo, chay tren du lieu OpenStreetMap - de lay:
  - "geometry": day cac diem [lat, lon] noi tiep theo dung hinh dang con pho
  - "distance_km": khoang cach thuc te theo duong di (khong phai duong chim bay)

OSRM co server demo cong khai (do FOSSGIS tai tro), du lieu toan cau, dung
de minh hoa/hoc tap la phu hop. Ket qua duoc cache xuong file JSON de:
  1. Khong phai goi lai API moi lan khoi dong server (chi goi 1 lan dau).
  2. Van chay duoc o che do offline cho cac lan sau (doc lai cache).

Neu khong co Internet hoac OSRM khong phan hoi, ham se fallback ve hanh vi
cu (noi thang 2 diem + khoang cach Haversine) de toan bo ung dung khong bi
crash - chi mat di phan "bam duong" truc quan.
"""

import json
import math
import os
import time

import requests

# File cache nam canh module nay, trong thu muc backend/
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "osm_route_cache.json")

# May chu demo OSRM cong khai (FOSSGIS tai tro), du lieu OpenStreetMap toan cau.
# Thu lan luot, neu may chu dau khong phan hoi thi chuyen sang may chu thay the.
OSRM_HOSTS = [
    "https://router.project-osrm.org",
    "https://routing.openstreetmap.de/routed-car",
]

REQUEST_TIMEOUT_SECONDS = 6
# Demo server cong khai gioi han ~1 request/giay -> nghi giua cac lan goi thuc
# de khong bi chan (chi anh huong lan khoi dong dau tien, cac lan sau doc cache).
POLITE_DELAY_SECONDS = 1.0

_cache = None  # cache trong bo nho cho ca tien trinh (process), nap 1 lan tu file


def _load_cache():
    global _cache
    if _cache is None:
        if os.path.exists(CACHE_PATH):
            try:
                with open(CACHE_PATH, "r", encoding="utf-8") as f:
                    _cache = json.load(f)
            except (json.JSONDecodeError, OSError):
                _cache = {}
        else:
            _cache = {}
    return _cache


def _save_cache():
    if _cache is None:
        return
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False)
    except OSError as e:
        print(f"[osm_routing] Khong the luu cache vao {CACHE_PATH}: {e}")


def _haversine_km(lat1, lon1, lat2, lon2):
    """Khoang cach duong chim bay (fallback khi khong goi duoc OSRM)."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _fetch_osrm_route(lat1, lon1, lat2, lon2):
    """
    Goi API OSRM /route de lay duong di thuc te giua 2 diem.
    Tra ve (distance_km, geometry[[lat, lon], ...]) hoac None neu that bai
    o tat ca cac may chu.
    """
    coords = f"{lon1},{lat1};{lon2},{lat2}"
    for host in OSRM_HOSTS:
        url = f"{host}/route/v1/driving/{coords}"
        try:
            resp = requests.get(
                url,
                params={"overview": "full", "geometries": "geojson"},
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={"User-Agent": "PFIG-Fuzzy-Routing-Demo/1.0"},
            )
            data = resp.json()
            if data.get("code") == "Ok" and data.get("routes"):
                route = data["routes"][0]
                distance_km = route["distance"] / 1000.0
                # OSRM tra ve [lon, lat] theo chuan GeoJSON -> doi sang [lat, lon] cho Leaflet
                geometry = [[lat, lon] for lon, lat in route["geometry"]["coordinates"]]
                if len(geometry) >= 2:
                    return distance_km, geometry
        except Exception as e:
            print(f"[osm_routing] Goi {host} loi: {e}")
            continue
    return None


def get_road_geometry(name_u, name_v, lat1, lon1, lat2, lon2):
    """
    Tra ve (distance_km, geometry) la hinh dang duong di THUC TE giua hai
    nut giao (name_u toa do lat1,lon1 va name_v toa do lat2,lon2), lay tu
    OpenStreetMap qua OSRM. Co cache de chi goi API 1 lan cho moi cap nut.

    Neu khong the lien lac voi OSRM (offline, mat mang...), fallback ve
    duong thang + khoang cach Haversine, dam bao ung dung luon chay duoc.
    """
    cache = _load_cache()
    key = "|".join(sorted([name_u, name_v]))

    if key in cache:
        entry = cache[key]
        return entry["distance_km"], entry["geometry"]

    result = _fetch_osrm_route(lat1, lon1, lat2, lon2)
    if result is None:
        print(
            f"[osm_routing] Khong lay duoc duong OSM thuc te cho "
            f"'{name_u}' <-> '{name_v}'. Dung tam duong thang (fallback)."
        )
        distance_km = _haversine_km(lat1, lon1, lat2, lon2)
        geometry = [[lat1, lon1], [lat2, lon2]]
        # Chi nho trong bo nho cho phien chay nay (de khong spam lai OSRM
        # nhieu lan trong cung 1 lan chay) - KHONG ghi xuong file, de lan
        # khoi dong server sau van thu lay du lieu thuc thay vi ket dinh
        # vinh vien o duong thang neu day chi la loi mang tam thoi.
        cache[key] = {"distance_km": distance_km, "geometry": geometry, "source": "straight_line_fallback"}
        return distance_km, geometry

    distance_km, geometry = result
    cache[key] = {"distance_km": distance_km, "geometry": geometry, "source": "osrm"}
    _save_cache()
    time.sleep(POLITE_DELAY_SECONDS)
    return distance_km, geometry


def clear_cache():
    """Xoa cache (vi du khi muon force tinh toan lai toan bo hinh dang duong)."""
    global _cache
    _cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            os.remove(CACHE_PATH)
        except OSError:
            pass
