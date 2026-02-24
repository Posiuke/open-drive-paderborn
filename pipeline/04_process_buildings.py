#!/usr/bin/env python3
"""Step 4: Process buildings into extruded 3D meshes."""

import pickle
import sys
import os
import numpy as np
from shapely.geometry import Polygon, MultiPolygon

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    CACHE_DIR, DEFAULT_BUILDING_HEIGHT, BUILDING_FLOOR_HEIGHT,
    BUILDING_HEIGHTS,
)
from utils.geo import wgs84_to_local
from utils.mesh_builder import MeshData, build_building_mesh
from utils.height_sampler import get_height_sampler


def get_building_height(tags):
    """Determine building height from OSM tags."""
    # Explicit height tag
    height = tags.get("height")
    if height:
        try:
            h = str(height).replace("m", "").strip()
            val = float(h)
            if not (val != val):  # Check for NaN
                return val
        except (ValueError, TypeError):
            pass

    # Levels tag
    levels = tags.get("building:levels")
    if levels:
        try:
            val = int(float(str(levels)))
            if val > 0:
                return val * BUILDING_FLOOR_HEIGHT
        except (ValueError, TypeError):
            pass

    # Building type
    building_type = tags.get("building", "yes")
    if building_type in BUILDING_HEIGHTS:
        return BUILDING_HEIGHTS[building_type]

    # Check for special tags
    if tags.get("amenity") == "place_of_worship":
        return BUILDING_HEIGHTS.get("church", 20.0)

    if tags.get("historic") == "castle":
        return BUILDING_HEIGHTS.get("castle", 18.0)

    return DEFAULT_BUILDING_HEIGHT


def get_building_color(tags):
    """Get building color from type."""
    building_type = tags.get("building", "yes")

    colors = {
        "cathedral": (0.65, 0.55, 0.45),
        "church": (0.65, 0.55, 0.45),
        "civic": (0.6, 0.6, 0.65),
        "commercial": (0.6, 0.58, 0.6),
        "industrial": (0.55, 0.55, 0.55),
        "residential": (0.72, 0.68, 0.62),
        "apartments": (0.7, 0.65, 0.6),
        "retail": (0.65, 0.6, 0.55),
        "university": (0.6, 0.58, 0.55),
        "school": (0.65, 0.6, 0.55),
        "garage": (0.5, 0.5, 0.5),
        "garages": (0.5, 0.5, 0.5),
    }
    return colors.get(building_type, (0.7, 0.65, 0.6))


def extract_polygon_coords(geom):
    """Extract exterior coordinates from a geometry, handling multi-polygons."""
    polygons = []

    if geom.geom_type == "Polygon":
        if geom.is_valid and not geom.is_empty:
            polygons.append(list(geom.exterior.coords))
    elif geom.geom_type == "MultiPolygon":
        for poly in geom.geoms:
            if poly.is_valid and not poly.is_empty:
                polygons.append(list(poly.exterior.coords))

    return polygons


def process_buildings():
    """Process building footprints into 3D meshes."""
    cache_file = CACHE_DIR / "buildings.pkl"
    if not cache_file.exists():
        print("[Buildings] ERROR: Run 01_download_osm.py first!")
        return None

    print("[Buildings] Loading building data...")
    with open(cache_file, "rb") as f:
        gdf = pickle.load(f)

    sampler = get_height_sampler()
    all_buildings_mesh = MeshData()

    count = 0
    skip_count = 0
    special_buildings = []

    print(f"[Buildings] Processing {len(gdf)} buildings...")

    for idx, row in gdf.iterrows():
        geom = row.geometry

        if geom is None or geom.is_empty:
            skip_count += 1
            continue

        # Get polygons from geometry
        polygons = extract_polygon_coords(geom)

        if not polygons:
            skip_count += 1
            continue

        # Get building properties from tags
        tags = row.to_dict()
        height = get_building_height(tags)
        color = get_building_color(tags)

        for poly_coords in polygons:
            # Convert to local coordinates
            lons = [c[0] for c in poly_coords]
            lats = [c[1] for c in poly_coords]
            xs, zs = wgs84_to_local(np.array(lons), np.array(lats))
            footprint = list(zip(xs, zs))

            # Sample ground height at centroid
            cx = np.mean(xs)
            cz = np.mean(zs)
            base_height = sampler.sample_local(cx, cz)

            # Build mesh
            mesh = build_building_mesh(footprint, height, base_height, color)

            if not mesh.is_empty():
                all_buildings_mesh.merge(mesh)
                count += 1

                # Track special buildings
                building_type = tags.get("building", "yes")
                if building_type in ("cathedral", "church", "castle", "civic"):
                    name = tags.get("name", "unnamed")
                    special_buildings.append(
                        f"  {building_type}: {name} (h={height}m)"
                    )

        if count % 5000 == 0 and count > 0:
            print(f"  Processed {count} buildings...")

    print(f"[Buildings] Processed {count} buildings ({skip_count} skipped)")
    print(f"[Buildings] Total vertices: {all_buildings_mesh.vertex_count()}, "
          f"triangles: {all_buildings_mesh.triangle_count()}")

    if special_buildings:
        print("[Buildings] Notable buildings:")
        for b in special_buildings[:20]:
            print(b)

    # Save
    output_file = CACHE_DIR / "buildings_mesh.pkl"
    with open(output_file, "wb") as f:
        pickle.dump(all_buildings_mesh, f)
    print(f"[Buildings] Saved → {output_file}")

    return all_buildings_mesh


def main():
    print("=" * 60)
    print("Step 4: Process buildings into 3D meshes")
    print("=" * 60)
    process_buildings()
    print("Done!")


if __name__ == "__main__":
    main()
