"""Open geodata for the grid layer: OSM power infrastructure + building
footprints via Overpass, with built-in fallbacks so nothing breaks offline.

Only free/open sources: OpenStreetMap (ODbL). Overture/Microsoft open
footprints are the documented production path for bulk building geometry.
No Google Maps/Earth extraction.
"""

from __future__ import annotations

import math

import httpx

from .assets import EXAMPLE_ASSETS
from .geo_sources import OVERPASS_URL
from .grid_assets import POWER_STATIONS, TRANSMISSION_CORRIDORS
from .models import GRID_DISCLAIMER

KUWAIT_BBOX = (28.5, 46.5, 30.1, 48.6)  # south, west, north, east
MAX_ELEMENTS = 300
_cache: dict[str, dict] = {}  # naive per-process cache keyed by query string

# OSM building tag -> SCORCH demand class
_DEMAND_CLASS = {
    "house": "residential", "residential": "residential", "apartments": "residential",
    "detached": "residential", "terrace": "residential", "bungalow": "residential",
    "school": "school", "kindergarten": "school", "university": "school",
    "hospital": "hospital", "clinic": "hospital",
    "mosque": "mosque",
    "mall": "mall", "retail": "commercial", "commercial": "commercial",
    "office": "commercial", "supermarket": "commercial", "hotel": "commercial",
    "industrial": "industrial", "warehouse": "industrial", "factory": "industrial",
}


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float]:
    """Parse 'south,west,north,east'; default to Kuwait; clamp size."""
    if not bbox:
        return KUWAIT_BBOX
    try:
        s, w, n, e = (float(x) for x in bbox.split(","))
    except ValueError:
        return KUWAIT_BBOX
    if not (s < n and w < e):
        return KUWAIT_BBOX
    # Clamp to a sane query size (Overpass etiquette).
    if (n - s) > 2.0 or (e - w) > 2.5:
        return KUWAIT_BBOX
    return (s, w, n, e)


def _ring_area_m2(ring: list[list[float]]) -> float:
    """Approximate polygon area via the shoelace formula on projected deg."""
    if len(ring) < 4:
        return 0.0
    lat0 = math.radians(ring[0][1])
    mx, my = 111_320.0 * math.cos(lat0), 111_320.0
    pts = [(lon * mx, lat * my) for lon, lat in ring]
    area = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def _overpass(query: str) -> dict:
    if query in _cache:
        return _cache[query]
    with httpx.Client(timeout=25.0) as client:
        resp = client.post(OVERPASS_URL, data={"data": query})
        resp.raise_for_status()
        data = resp.json()
    _cache[query] = data
    return data


# ---------------------------------------------------------------------------
# Power infrastructure
# ---------------------------------------------------------------------------

def fetch_osm_power(bbox: str | None = None) -> dict:
    """OSM power infrastructure in bbox as GeoJSON. Raises on failure."""
    s, w, n, e = _parse_bbox(bbox)
    bb = f"({s},{w},{n},{e})"
    query = (
        f"[out:json][timeout:20];("
        f'node["power"~"plant|substation|tower|transformer|pole"]{bb};'
        f'way["power"~"plant|substation|line|minor_line|cable"]{bb};'
        f");out geom {MAX_ELEMENTS};"
    )
    data = _overpass(query)

    features = []
    for el in data.get("elements", [])[:MAX_ELEMENTS]:
        tags = el.get("tags", {})
        power = tags.get("power", "unknown")
        props = {
            "source": "openstreetmap-overpass",
            "power": power,
            "name": tags.get("name"),
            "voltage": tags.get("voltage"),
            "osm_id": el.get("id"),
            "attribution": "© OpenStreetMap contributors (ODbL)",
        }
        if el["type"] == "node":
            geom = {"type": "Point", "coordinates": [el["lon"], el["lat"]]}
        elif el.get("geometry"):
            coords = [[p["lon"], p["lat"]] for p in el["geometry"]]
            if power in ("line", "minor_line", "cable"):
                geom = {"type": "LineString", "coordinates": coords}
            else:  # plant/substation areas
                if coords[0] != coords[-1]:
                    coords.append(coords[0])
                geom = {"type": "Polygon", "coordinates": [coords]}
        else:
            continue
        features.append({"type": "Feature", "geometry": geom, "properties": props})

    if not features:
        raise ValueError("Overpass returned no power features")
    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {"source": "openstreetmap-overpass", "is_live": True,
                       "disclaimer": GRID_DISCLAIMER,
                       "attribution": "© OpenStreetMap contributors (ODbL)"},
    }


def fallback_grid_skeleton() -> dict:
    """Built-in simplified Kuwait grid: stations + illustrative corridors."""
    features = [
        {"type": "Feature",
         "geometry": {"type": "Point", "coordinates": [st["longitude"], st["latitude"]]},
         "properties": {"source": "fallback_public_assumption", "power": "plant",
                        "name": st["name"], "slug": st["slug"],
                        "disclaimer": GRID_DISCLAIMER}}
        for st in POWER_STATIONS
    ] + [
        {"type": "Feature",
         "geometry": {"type": "LineString", "coordinates": c["coordinates"]},
         "properties": {"source": "fallback_public_assumption", "power": "line",
                        "name": c["name"],
                        "note": "Illustrative corridor, not a surveyed route.",
                        "disclaimer": GRID_DISCLAIMER}}
        for c in TRANSMISSION_CORRIDORS
    ]
    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {"source": "fallback_public_assumption", "is_live": False,
                       "disclaimer": GRID_DISCLAIMER},
    }


def osm_power_or_fallback(bbox: str | None = None) -> dict:
    try:
        return fetch_osm_power(bbox)
    except Exception:
        return fallback_grid_skeleton()


# ---------------------------------------------------------------------------
# Building footprints
# ---------------------------------------------------------------------------

def fetch_osm_buildings_bbox(bbox: str | None, limit: int) -> dict:
    """OSM building footprints in bbox with demand-class labels. Raises."""
    s, w, n, e = _parse_bbox(bbox)
    query = (
        f"[out:json][timeout:20];"
        f'way["building"]({s},{w},{n},{e});'
        f"out geom {limit};"
    )
    data = _overpass(query)

    features = []
    for el in data.get("elements", [])[:limit]:
        if el.get("type") != "way" or not el.get("geometry"):
            continue
        coords = [[p["lon"], p["lat"]] for p in el["geometry"]]
        if len(coords) < 4:
            continue
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        tags = el.get("tags", {})
        btag = tags.get("building", "yes")
        demand_class = _DEMAND_CLASS.get(btag, "unknown")
        if demand_class == "unknown" and tags.get("amenity") == "place_of_worship":
            demand_class = "mosque"
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {
                "source": "openstreetmap-overpass",
                "building": btag,
                "demand_class": demand_class,
                "approx_area_m2": round(_ring_area_m2(coords), 0),
                "confidence": "medium (OSM footprint; class from tags)",
                "attribution": "© OpenStreetMap contributors (ODbL)",
            },
        })
    if not features:
        raise ValueError("Overpass returned no buildings")
    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "source": "openstreetmap-overpass", "is_live": True,
            "disclaimer": GRID_DISCLAIMER,
            "note": "Public building footprint coverage — OSM completeness varies; "
                    "not every building is mapped.",
            "attribution": "© OpenStreetMap contributors (ODbL)",
        },
    }


def fallback_building_blocks(bbox: str | None, limit: int) -> dict:
    """Synthetic residential blocks around the bbox centre (offline demo)."""
    s, w, n, e = _parse_bbox(bbox)
    clat, clon = (s + n) / 2, (w + e) / 2
    side = 20.0 / 111_320.0  # ~20 m squares
    gap = side * 2.2
    features = []
    count = min(limit, 36)
    per_row = max(int(math.sqrt(count)), 1)
    for i in range(count):
        r, c = divmod(i, per_row)
        lat = clat + (r - per_row / 2) * gap
        lon = clon + (c - per_row / 2) * gap / max(math.cos(math.radians(clat)), 0.1)
        ring = [[lon, lat], [lon + side, lat], [lon + side, lat + side],
                [lon, lat + side], [lon, lat]]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {
                "source": "fallback_public_assumption",
                "building": "synthetic_block",
                "demand_class": "residential",
                "approx_area_m2": 400.0,
                "confidence": "none (synthetic placeholder blocks)",
            },
        })
    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "source": "fallback_public_assumption", "is_live": False,
            "disclaimer": GRID_DISCLAIMER,
            "note": "Synthetic placeholder blocks (Overpass unavailable). "
                    "For demand, homes are aggregated to district cells only.",
        },
    }


def buildings_or_fallback(bbox: str | None, limit: int) -> dict:
    limit = max(10, min(limit, 500))
    try:
        return fetch_osm_buildings_bbox(bbox, limit)
    except Exception:
        return fallback_building_blocks(bbox, limit)


# ---------------------------------------------------------------------------
# Combined grid asset collection
# ---------------------------------------------------------------------------

def power_stations_fc() -> dict:
    """Built-in power stations as GeoJSON (public-data profiles)."""
    features = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [st["longitude"], st["latitude"]]},
        "properties": {
            "layer": "power_station",
            **{k: st[k] for k in ("slug", "name", "fuel_type", "generation_type",
                                  "capacity_mw", "capacity_note", "confidence")},
            "source": "public reports (approximate values)",
            "assumptions": [
                "Coordinates are approximate public locations.",
                st["capacity_note"],
                "Fuel/technology labelled 'mixed'/'unknown' where not confidently public.",
            ],
            "disclaimer": GRID_DISCLAIMER,
        },
    } for st in POWER_STATIONS]
    return {"type": "FeatureCollection", "features": features,
            "properties": {"disclaimer": GRID_DISCLAIMER,
                           "source": "public reports (approximate values)"}}


def grid_assets_fc(demand_fc: dict) -> dict:
    """All grid-relevant assets in one FeatureCollection, tagged by layer."""
    features = list(power_stations_fc()["features"])
    features += [
        {"type": "Feature",
         "geometry": {"type": "LineString", "coordinates": c["coordinates"]},
         "properties": {"layer": "transmission_corridor",
                        "name": c["name"],
                        "source": "fallback_public_assumption",
                        "note": "Illustrative corridor, not a surveyed route.",
                        "disclaimer": GRID_DISCLAIMER}}
        for c in TRANSMISSION_CORRIDORS
    ]
    for slug, a in EXAMPLE_ASSETS.items():
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [a["longitude"], a["latitude"]]},
            "properties": {"layer": "example_building", "slug": slug, "name": a["name"],
                           "building_type": a["building_type"], "area_m2": a["area_m2"],
                           "source": "public assumptions",
                           "disclaimer": GRID_DISCLAIMER},
        })
    for f in demand_fc["features"]:
        features.append({
            "type": "Feature", "geometry": f["geometry"],
            "properties": {"layer": "district_demand_cell", **f["properties"]},
        })
    return {"type": "FeatureCollection", "features": features,
            "properties": {"disclaimer": GRID_DISCLAIMER}}
