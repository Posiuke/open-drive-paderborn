#!/usr/bin/env python3
"""Step 3: Process road network into 3D meshes."""

import pickle
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    CACHE_DIR, ROAD_WIDTHS, DEFAULT_LANES,
)
from utils.geo import wgs84_to_local
from utils.mesh_builder import MeshData, build_road_mesh
from utils.height_sampler import get_height_sampler


def _normalize_highway(val):
    """Normalize highway tag which can be a string or list."""
    if isinstance(val, list):
        return val[0] if val else "residential"
    return val or "residential"


def get_road_width(edge_data):
    """Determine road width from OSM tags."""
    highway = _normalize_highway(edge_data.get("highway", "residential"))

    # Check explicit width tag
    width = edge_data.get("width")
    if width:
        try:
            w = width if not isinstance(width, list) else width[0]
            return float(str(w).replace("m", "").strip())
        except (ValueError, TypeError):
            pass

    # Determine from lanes
    lanes = edge_data.get("lanes")
    if lanes:
        try:
            l = lanes if not isinstance(lanes, list) else lanes[0]
            n_lanes = int(l)
        except (ValueError, TypeError):
            n_lanes = DEFAULT_LANES.get(highway, 1)
    else:
        n_lanes = DEFAULT_LANES.get(highway, 1)

    lane_width = ROAD_WIDTHS.get(highway, 2.75)
    return n_lanes * lane_width


def get_road_color(highway_type):
    """Get road color based on type."""
    colors = {
        "motorway": (0.25, 0.25, 0.3),
        "motorway_link": (0.25, 0.25, 0.3),
        "trunk": (0.28, 0.28, 0.3),
        "trunk_link": (0.28, 0.28, 0.3),
        "primary": (0.3, 0.3, 0.32),
        "primary_link": (0.3, 0.3, 0.32),
        "secondary": (0.32, 0.32, 0.33),
        "secondary_link": (0.32, 0.32, 0.33),
        "tertiary": (0.33, 0.33, 0.34),
        "tertiary_link": (0.33, 0.33, 0.34),
        "residential": (0.35, 0.35, 0.35),
        "living_street": (0.4, 0.38, 0.35),
        "service": (0.38, 0.38, 0.38),
        "pedestrian": (0.5, 0.48, 0.45),
    }
    return colors.get(highway_type, (0.35, 0.35, 0.35))


def process_roads():
    """Process road graph into 3D meshes."""
    import osmnx as ox

    # Load road graph
    graph_file = CACHE_DIR / "roads.graphml"
    if not graph_file.exists():
        print("[Roads] ERROR: Run 01_download_osm.py first!")
        return None

    print("[Roads] Loading road graph...")
    G = ox.load_graphml(graph_file)

    sampler = get_height_sampler()

    road_meshes = {}  # (cx, cz) → MeshData (we'll chunk later)
    all_roads_mesh = MeshData()

    edge_count = 0
    skip_count = 0

    print(f"[Roads] Processing {len(G.edges)} edges...")

    for u, v, data in G.edges(data=True):
        # Get geometry
        if "geometry" in data:
            coords = list(data["geometry"].coords)
        else:
            # Straight line between nodes
            n1 = G.nodes[u]
            n2 = G.nodes[v]
            coords = [(n1["x"], n1["y"]), (n2["x"], n2["y"])]

        if len(coords) < 2:
            skip_count += 1
            continue

        # Convert to local coordinates
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        xs, zs = wgs84_to_local(np.array(lons), np.array(lats))
        points_xz = list(zip(xs, zs))

        # Road properties
        highway = _normalize_highway(data.get("highway", "residential"))
        width = get_road_width(data)
        color = get_road_color(highway)

        # Build mesh
        mesh = build_road_mesh(
            points_xz, width,
            height_func=sampler.sample_local,
            color=color,
        )

        if not mesh.is_empty():
            all_roads_mesh.merge(mesh)
            edge_count += 1

        if edge_count % 1000 == 0 and edge_count > 0:
            print(f"  Processed {edge_count} roads...")

    print(f"[Roads] Processed {edge_count} edges ({skip_count} skipped)")
    print(f"[Roads] Total vertices: {all_roads_mesh.vertex_count()}, "
          f"triangles: {all_roads_mesh.triangle_count()}")

    # Save processed mesh
    output_file = CACHE_DIR / "roads_mesh.pkl"
    with open(output_file, "wb") as f:
        pickle.dump(all_roads_mesh, f)
    print(f"[Roads] Saved → {output_file}")

    return all_roads_mesh


def main():
    print("=" * 60)
    print("Step 3: Process roads into 3D meshes")
    print("=" * 60)
    process_roads()
    print("Done!")


if __name__ == "__main__":
    main()
