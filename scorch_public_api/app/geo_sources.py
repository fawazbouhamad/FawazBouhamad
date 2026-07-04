"""Free/open geospatial sources for the SCORCH map layer.

Priority:
  1. OpenStreetMap building footprints via the public Overpass API
     (free, no key). OPTIONAL: never required for the app to work.
  2. Fallback geometry built from public assumptions (asset point plus an
     approximate square buffer sized from the asset's public area), so the
     map works fully offline.

No Google Maps/Earth, paid APIs, keys, or scraped imagery are used.
"""

from __future__ import annotations

import math

import httpx

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
MAX_FOOTPRINTS = 80  # keep responses light; this is a prototype layer

FALLBACK_SOURCE = "fallback_public_assumption"
FOOTPRINT_DISCLAIMER = (
    "This is a public-data estimate, not a verified floor plan/BIM."
)


def fetch_overpass_buildings(lat: float, lon: float, radius_m: int = 500) -> list[dict]:
    """Fetch OSM building footprints around a point as GeoJSON features.

    Raises on network errors or empty results; callers should fall back to
    fallback_footprint(). Overpass is community-run — be gentle (small
    radius, capped result count).
    """
    query = (
        f"[out:json][timeout:15];"
        f'way["building"](around:{radius_m},{lat},{lon});'
        f"out geom {MAX_FOOTPRINTS};"
    )
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(OVERPASS_URL, data={"data": query})
        resp.raise_for_status()
        data = resp.json()

    features: list[dict] = []
    for el in data.get("elements", []):
        if el.get("type") != "way" or not el.get("geometry"):
            continue
        coords = [[p["lon"], p["lat"]] for p in el["geometry"]]
        if len(coords) < 4:
            continue
        if coords[0] != coords[-1]:
            coords.append(coords[0])  # close the ring
        tags = el.get("tags", {})
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [coords]},
                "properties": {
                    "source": "openstreetmap-overpass",
                    "osm_id": el.get("id"),
                    "building": tags.get("building", "yes"),
                    "name": tags.get("name"),
                    "attribution": "© OpenStreetMap contributors (ODbL)",
                },
            }
        )
    if not features:
        raise ValueError("Overpass returned no building footprints")
    return features


def _square_ring(lat: float, lon: float, area_m2: float) -> list[list[float]]:
    """Closed ring for a square of the given area centred on (lat, lon)."""
    half_side_m = math.sqrt(max(area_m2, 100.0)) / 2.0
    dlat = half_side_m / 111_320.0
    dlon = half_side_m / (111_320.0 * max(math.cos(math.radians(lat)), 0.1))
    return [
        [lon - dlon, lat - dlat],
        [lon + dlon, lat - dlat],
        [lon + dlon, lat + dlat],
        [lon - dlon, lat + dlat],
        [lon - dlon, lat - dlat],
    ]


def fallback_footprint(lat: float, lon: float, area_m2: float, name: str) -> list[dict]:
    """Offline fallback: asset point + approximate square buffer polygon."""
    common = {
        "source": FALLBACK_SOURCE,
        "name": name,
        "disclaimer": FOOTPRINT_DISCLAIMER,
    }
    return [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {**common, "role": "asset_location"},
        },
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [_square_ring(lat, lon, area_m2)],
            },
            "properties": {
                **common,
                "role": "approximate_area_buffer",
                "approx_area_m2": area_m2,
                "note": "Square buffer sized from public area assumption, not a real footprint.",
            },
        },
    ]


def nearby_buildings(lat: float, lon: float, radius_m: int, area_m2: float, name: str) -> dict:
    """Best-effort footprints: live Overpass, else public-assumption fallback."""
    try:
        features = fetch_overpass_buildings(lat, lon, radius_m)
        source, live = "openstreetmap-overpass", True
    except Exception:
        features = fallback_footprint(lat, lon, area_m2, name)
        source, live = FALLBACK_SOURCE, False
    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "source": source,
            "is_live": live,
            "disclaimer": FOOTPRINT_DISCLAIMER,
            "attribution": "© OpenStreetMap contributors (ODbL)" if live else None,
        },
    }
