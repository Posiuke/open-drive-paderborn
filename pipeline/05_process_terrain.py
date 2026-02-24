#!/usr/bin/env python3
"""Step 5: Generate terrain meshes from SRTM data."""

import pickle
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from config import CACHE_DIR, TERRAIN_RESOLUTION, TERRAIN_LOD1_RESOLUTION, CHUNK_SIZE
from utils.geo import bbox_to_local
from utils.mesh_builder import MeshData, build_terrain_mesh
from utils.height_sampler import get_height_sampler


def process_terrain():
    """Generate terrain mesh for the entire Paderborn area."""
    sampler = get_height_sampler()
    min_x, max_x, min_z, max_z = bbox_to_local()

    print(f"[Terrain] Area: {max_x - min_x:.0f}m × {max_z - min_z:.0f}m")
    print(f"[Terrain] Resolution: LOD0={TERRAIN_RESOLUTION}m, LOD1={TERRAIN_LOD1_RESOLUTION}m")

    # Generate terrain as chunk-sized tiles
    terrain_meshes = {}  # (cx, cz) → MeshData

    cx_min = int(np.floor(min_x / CHUNK_SIZE))
    cx_max = int(np.ceil(max_x / CHUNK_SIZE))
    cz_min = int(np.floor(min_z / CHUNK_SIZE))
    cz_max = int(np.ceil(max_z / CHUNK_SIZE))

    total = (cx_max - cx_min) * (cz_max - cz_min)
    count = 0

    print(f"[Terrain] Generating {total} terrain tiles...")

    for cx in range(cx_min, cx_max):
        for cz in range(cz_min, cz_max):
            tile_min_x = cx * CHUNK_SIZE
            tile_max_x = tile_min_x + CHUNK_SIZE
            tile_min_z = cz * CHUNK_SIZE
            tile_max_z = tile_min_z + CHUNK_SIZE

            mesh = build_terrain_mesh(
                tile_min_x, tile_max_x,
                tile_min_z, tile_max_z,
                TERRAIN_RESOLUTION,
                height_func=sampler.sample_local,
                color=(0.3, 0.5, 0.2),
            )

            terrain_meshes[(cx, cz)] = mesh
            count += 1

            if count % 100 == 0:
                print(f"  Generated {count}/{total} tiles...")

    print(f"[Terrain] Generated {count} terrain tiles")

    # Save
    output_file = CACHE_DIR / "terrain_meshes.pkl"
    with open(output_file, "wb") as f:
        pickle.dump(terrain_meshes, f)
    print(f"[Terrain] Saved → {output_file}")

    return terrain_meshes


def main():
    print("=" * 60)
    print("Step 5: Generate terrain meshes")
    print("=" * 60)
    process_terrain()
    print("Done!")


if __name__ == "__main__":
    main()
