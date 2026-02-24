#!/usr/bin/env python3
"""Step 1: Download OpenStreetMap data for Paderborn."""

import pickle
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    BBOX, CACHE_DIR,
    OSM_BUILDING_TAGS, OSM_ROAD_TAGS, OSM_LANDUSE_TAGS,
    BBOX_NORTH, BBOX_SOUTH, BBOX_EAST, BBOX_WEST,
)


def download_roads():
    """Download road network."""
    import osmnx as ox

    # Increase max query area to avoid excessive subdivision
    ox.settings.max_query_area_size = 50 * 1000 * 50 * 1000  # 50km x 50km

    cache_file = CACHE_DIR / "roads.graphml"
    if cache_file.exists():
        print(f"[Roads] Loading cached: {cache_file}")
        return ox.load_graphml(cache_file)

    print("[Roads] Downloading road network from OSM...")

    G = ox.graph_from_bbox(
        bbox=BBOX,
        network_type="drive",
        retain_all=True,
        truncate_by_edge=True,
    )

    ox.save_graphml(G, cache_file)
    print(f"[Roads] Saved {len(G.edges)} edges, {len(G.nodes)} nodes → {cache_file}")
    return G


def download_buildings():
    """Download building footprints."""
    import osmnx as ox
    ox.settings.max_query_area_size = 50 * 1000 * 50 * 1000

    cache_file = CACHE_DIR / "buildings.pkl"
    if cache_file.exists():
        print(f"[Buildings] Loading cached: {cache_file}")
        with open(cache_file, "rb") as f:
            return pickle.load(f)

    print("[Buildings] Downloading building footprints from OSM...")
    gdf = ox.features_from_bbox(
        bbox=BBOX,
        tags=OSM_BUILDING_TAGS,
    )

    with open(cache_file, "wb") as f:
        pickle.dump(gdf, f)

    print(f"[Buildings] Saved {len(gdf)} buildings → {cache_file}")
    return gdf


def download_landuse():
    """Download landuse and natural features."""
    import osmnx as ox
    ox.settings.max_query_area_size = 50 * 1000 * 50 * 1000

    cache_file = CACHE_DIR / "landuse.pkl"
    if cache_file.exists():
        print(f"[Landuse] Loading cached: {cache_file}")
        with open(cache_file, "rb") as f:
            return pickle.load(f)

    print("[Landuse] Downloading landuse data from OSM...")
    gdf = ox.features_from_bbox(
        bbox=BBOX,
        tags=OSM_LANDUSE_TAGS,
    )

    with open(cache_file, "wb") as f:
        pickle.dump(gdf, f)

    print(f"[Landuse] Saved {len(gdf)} features → {cache_file}")
    return gdf


def main():
    print("=" * 60)
    print("Step 1: Download OSM data for Paderborn")
    print(f"  BBox: N={BBOX_NORTH}, S={BBOX_SOUTH}, E={BBOX_EAST}, W={BBOX_WEST}")
    print("=" * 60)

    roads = download_roads()
    buildings = download_buildings()
    landuse = download_landuse()

    print("\n[Summary]")
    print(f"  Roads: {len(roads.edges)} edges")
    print(f"  Buildings: {len(buildings)} features")
    print(f"  Landuse: {len(landuse)} features")
    print("Done!")


if __name__ == "__main__":
    main()
