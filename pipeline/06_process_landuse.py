#!/usr/bin/env python3
"""Step 6: Process landuse and natural features."""

import pickle
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from config import CACHE_DIR, LANDUSE_COLORS
from utils.geo import wgs84_to_local
from utils.mesh_builder import MeshData, build_landuse_mesh, build_water_mesh
from utils.height_sampler import get_height_sampler


def get_landuse_type(tags):
    """Determine the landuse category from OSM tags."""
    # Check landuse
    landuse = tags.get("landuse")
    if landuse:
        return landuse

    # Check natural
    natural = tags.get("natural")
    if natural == "water":
        return "water"
    if natural in ("wood", "scrub"):
        return "forest"
    if natural == "grassland":
        return "grass"

    # Check leisure
    leisure = tags.get("leisure")
    if leisure in ("park", "garden"):
        return "park"
    if leisure in ("pitch", "playground"):
        return "recreation_ground"

    # Check waterway
    if tags.get("waterway"):
        return "water"

    return None


def process_landuse():
    """Process landuse features into flat meshes."""
    cache_file = CACHE_DIR / "landuse.pkl"
    if not cache_file.exists():
        print("[Landuse] ERROR: Run 01_download_osm.py first!")
        return None, None

    print("[Landuse] Loading landuse data...")
    with open(cache_file, "rb") as f:
        gdf = pickle.load(f)

    sampler = get_height_sampler()
    landuse_mesh = MeshData()
    water_mesh = MeshData()

    count = 0
    water_count = 0
    skip_count = 0

    print(f"[Landuse] Processing {len(gdf)} features...")

    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            skip_count += 1
            continue

        tags = row.to_dict()
        ltype = get_landuse_type(tags)

        if ltype is None:
            skip_count += 1
            continue

        # Get polygons
        polygons = []
        if geom.geom_type == "Polygon":
            if geom.is_valid and not geom.is_empty:
                polygons.append(list(geom.exterior.coords))
        elif geom.geom_type == "MultiPolygon":
            for poly in geom.geoms:
                if poly.is_valid and not poly.is_empty:
                    polygons.append(list(poly.exterior.coords))
        else:
            # Skip lines, points etc.
            skip_count += 1
            continue

        color = LANDUSE_COLORS.get(ltype, (0.4, 0.5, 0.3))
        is_water = ltype in ("water", "basin", "reservoir", "river")

        for poly_coords in polygons:
            if len(poly_coords) < 3:
                continue

            # Convert to local coords
            lons = [c[0] for c in poly_coords]
            lats = [c[1] for c in poly_coords]
            xs, zs = wgs84_to_local(np.array(lons), np.array(lats))
            points = list(zip(xs, zs))

            if is_water:
                mesh = build_water_mesh(
                    points,
                    height_func=sampler.sample_local,
                )
                water_mesh.merge(mesh)
                water_count += 1
            else:
                mesh = build_landuse_mesh(
                    points,
                    height_func=sampler.sample_local,
                    color=color,
                )
                landuse_mesh.merge(mesh)
                count += 1

    print(f"[Landuse] Processed {count} landuse + {water_count} water features "
          f"({skip_count} skipped)")
    print(f"[Landuse] Vertices: landuse={landuse_mesh.vertex_count()}, "
          f"water={water_mesh.vertex_count()}")

    # Save
    output_file = CACHE_DIR / "landuse_mesh.pkl"
    with open(output_file, "wb") as f:
        pickle.dump(landuse_mesh, f)

    water_file = CACHE_DIR / "water_mesh.pkl"
    with open(water_file, "wb") as f:
        pickle.dump(water_mesh, f)

    print(f"[Landuse] Saved → {output_file}, {water_file}")

    return landuse_mesh, water_mesh


def main():
    print("=" * 60)
    print("Step 6: Process landuse and water features")
    print("=" * 60)
    process_landuse()
    print("Done!")


if __name__ == "__main__":
    main()
