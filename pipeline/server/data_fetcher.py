"""Fetch OSM data from Overpass API and SRTM elevation data.

Uses megatile caching: one Overpass query per 2km x 2km block.
"""

import pickle
import time
import numpy as np
import requests

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.geo import (
    wgs84_to_local, megatile_bbox_wgs84, megatile_key,
    ORIGIN_UTM_E, ORIGIN_UTM_N,
)
from config import CHUNK_SIZE


OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Overpass query templates
OVERPASS_QUERY = """
[out:json][timeout:60][bbox:{south},{west},{north},{east}];
(
  way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link|residential|living_street|unclassified|service|pedestrian)$"];
  way["building"];
  way["landuse"];
  way["natural"~"^(water|wood|grassland|scrub)$"];
  way["leisure"~"^(park|garden|pitch|playground)$"];
  way["waterway"];
  relation["building"];
  relation["landuse"];
  relation["natural"="water"];
);
out body;
>;
out skel qt;
"""


class DataFetcher:
    """Fetches and caches OSM + SRTM data for megatiles."""

    def __init__(self, cache_manager):
        self.cache = cache_manager
        self._overpass_last_call = 0.0
        self._overpass_min_interval = 1.0  # Respect rate limits

    def fetch_megatile(self, mt_x, mt_z):
        """Fetch OSM data for a 2km megatile.

        Returns dict with 'roads', 'buildings', 'landuse' as lists of
        processed features ready for mesh building.
        """
        cache_key = f"mt_{mt_x}_{mt_z}"

        # Check cache
        cached = self.cache.get_raw("osm", cache_key)
        if cached is not None:
            return pickle.loads(cached)

        # Fetch from Overpass
        west, south, east, north = megatile_bbox_wgs84(mt_x, mt_z)

        # Add small buffer for features crossing boundaries
        buffer = 0.001  # ~100m
        raw_data = self._query_overpass(
            south - buffer, west - buffer,
            north + buffer, east + buffer
        )

        if raw_data is None:
            return {"roads": [], "buildings": [], "landuse": [], "water": []}

        # Parse into feature lists
        features = self._parse_overpass_response(raw_data)

        # Cache
        self.cache.put_raw("osm", cache_key, pickle.dumps(features))

        return features

    def get_megatile_for_chunk(self, cx, cz):
        """Get the megatile data covering a specific chunk."""
        mt_x, mt_z = megatile_key(cx, cz, CHUNK_SIZE)
        return self.fetch_megatile(mt_x, mt_z)

    def _query_overpass(self, south, west, north, east):
        """Execute an Overpass API query with rate limiting."""
        # Rate limit
        elapsed = time.time() - self._overpass_last_call
        if elapsed < self._overpass_min_interval:
            time.sleep(self._overpass_min_interval - elapsed)

        query = OVERPASS_QUERY.format(
            south=south, west=west, north=north, east=east
        )

        print(f"[DataFetcher] Overpass query: bbox=({south:.4f},{west:.4f},{north:.4f},{east:.4f})")

        try:
            resp = requests.post(
                OVERPASS_URL,
                data={"data": query},
                timeout=120,
            )
            self._overpass_last_call = time.time()

            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                print("[DataFetcher] Rate limited, waiting 30s...")
                time.sleep(30)
                return self._query_overpass(south, west, north, east)
            else:
                print(f"[DataFetcher] Overpass error: HTTP {resp.status_code}")
                return None
        except Exception as e:
            print(f"[DataFetcher] Overpass error: {e}")
            return None

    def _parse_overpass_response(self, data):
        """Parse Overpass JSON into categorized feature lists."""
        roads = []
        buildings = []
        landuse = []
        water = []

        # Build node lookup
        nodes = {}
        for elem in data.get("elements", []):
            if elem["type"] == "node":
                nodes[elem["id"]] = (elem["lon"], elem["lat"])

        # Process ways
        for elem in data.get("elements", []):
            if elem["type"] != "way":
                continue

            tags = elem.get("tags", {})
            node_ids = elem.get("nodes", [])

            # Resolve node coordinates
            coords = []
            for nid in node_ids:
                if nid in nodes:
                    coords.append(nodes[nid])

            if len(coords) < 2:
                continue

            # Categorize
            if "highway" in tags:
                roads.append({
                    "coords": coords,
                    "tags": tags,
                })
            elif "building" in tags:
                if len(coords) >= 3:
                    buildings.append({
                        "coords": coords,
                        "tags": tags,
                    })
            elif tags.get("natural") == "water" or tags.get("waterway"):
                if len(coords) >= 3:
                    water.append({
                        "coords": coords,
                        "tags": tags,
                    })
            elif any(k in tags for k in ("landuse", "natural", "leisure")):
                if len(coords) >= 3:
                    landuse.append({
                        "coords": coords,
                        "tags": tags,
                    })

        # Process relations (multipolygons)
        for elem in data.get("elements", []):
            if elem["type"] != "relation":
                continue

            tags = elem.get("tags", {})
            if tags.get("type") != "multipolygon":
                continue

            # Collect outer way coordinates
            outer_coords = []
            for member in elem.get("members", []):
                if member.get("role") == "outer" and member.get("type") == "way":
                    # Find this way in elements
                    for w_elem in data.get("elements", []):
                        if w_elem["type"] == "way" and w_elem["id"] == member["ref"]:
                            wcoords = []
                            for nid in w_elem.get("nodes", []):
                                if nid in nodes:
                                    wcoords.append(nodes[nid])
                            if wcoords:
                                outer_coords.extend(wcoords)

            if len(outer_coords) < 3:
                continue

            if "building" in tags:
                buildings.append({"coords": outer_coords, "tags": tags})
            elif tags.get("natural") == "water":
                water.append({"coords": outer_coords, "tags": tags})
            elif any(k in tags for k in ("landuse", "natural", "leisure")):
                landuse.append({"coords": outer_coords, "tags": tags})

        print(f"[DataFetcher] Parsed: {len(roads)} roads, "
              f"{len(buildings)} buildings, {len(landuse)} landuse, "
              f"{len(water)} water")

        return {
            "roads": roads,
            "buildings": buildings,
            "landuse": landuse,
            "water": water,
        }
