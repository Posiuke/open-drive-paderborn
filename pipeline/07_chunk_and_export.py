#!/usr/bin/env python3
"""Step 7: Chunk geometry and export as glTF/GLB files."""

import json
import pickle
import struct
import sys
import os
import numpy as np
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    CACHE_DIR, CHUNKS_EXPORT_DIR, EXPORT_DIR, CHUNK_SIZE,
    GODOT_CHUNKS_DIR,
)
from utils.geo import bbox_to_local
from utils.mesh_builder import MeshData, simplify_polygon
from utils.chunk_manager import ChunkManager


def clip_mesh_to_chunk(mesh, min_x, max_x, min_z, max_z):
    """Clip a mesh to chunk bounds (simple vertex-based inclusion).

    Returns a new MeshData with only triangles that have at least one vertex
    inside the chunk bounds.
    """
    if mesh is None or mesh.is_empty():
        return MeshData()

    result = MeshData()
    verts = mesh.vertices
    has_colors = len(mesh.colors) == len(mesh.vertices)

    # Map old vertex indices to new ones
    vertex_map = {}

    for i in range(0, len(mesh.indices), 3):
        i0, i1, i2 = mesh.indices[i], mesh.indices[i + 1], mesh.indices[i + 2]

        # Check if any vertex is within chunk bounds (with margin)
        margin = 2.0  # Small overlap to avoid seams
        in_chunk = False
        for vi in (i0, i1, i2):
            vx, vy, vz = verts[vi]
            if (min_x - margin <= vx <= max_x + margin and
                    min_z - margin <= vz <= max_z + margin):
                in_chunk = True
                break

        if not in_chunk:
            continue

        # Add vertices (deduplicating)
        new_indices = []
        for vi in (i0, i1, i2):
            if vi not in vertex_map:
                new_idx = result.vertex_count()
                vertex_map[vi] = new_idx
                result.vertices.append(verts[vi])
                result.normals.append(mesh.normals[vi] if vi < len(mesh.normals) else (0, 1, 0))
                result.uvs.append(mesh.uvs[vi] if vi < len(mesh.uvs) else (0, 0))
                if has_colors:
                    result.colors.append(mesh.colors[vi])
            new_indices.append(vertex_map[vi])

        result.add_triangle(*new_indices)

    return result


def mesh_to_glb(meshes_by_layer, output_path):
    """Export multiple mesh layers as a single GLB file.

    Args:
        meshes_by_layer: dict of layer_name → MeshData
        output_path: output .glb file path
    """
    # Filter empty layers
    layers = {k: v for k, v in meshes_by_layer.items()
              if v is not None and not v.is_empty()}

    if not layers:
        return False

    # Build glTF structure
    gltf = {
        "asset": {"version": "2.0", "generator": "open-drive-pipeline"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(layers)))}],
        "nodes": [],
        "meshes": [],
        "accessors": [],
        "bufferViews": [],
        "buffers": [],
        "materials": [],
    }

    binary_data = bytearray()
    accessor_idx = 0
    material_idx = 0

    # Material colors per layer
    material_colors = {
        "roads": [0.35, 0.35, 0.35, 1.0],
        "buildings": [0.7, 0.65, 0.6, 1.0],
        "terrain": [0.3, 0.5, 0.2, 1.0],
        "landuse": [0.35, 0.55, 0.25, 1.0],
        "water": [0.2, 0.4, 0.7, 1.0],
    }

    for layer_name, mesh in layers.items():
        data = mesh.to_numpy()
        verts = data["vertices"]
        normals = data["normals"]
        uvs = data["uvs"]
        indices = data["indices"]

        if len(verts) == 0 or len(indices) == 0:
            continue

        # Create material
        mat_color = material_colors.get(layer_name, [0.5, 0.5, 0.5, 1.0])
        gltf["materials"].append({
            "name": layer_name,
            "pbrMetallicRoughness": {
                "baseColorFactor": mat_color,
                "metallicFactor": 0.0,
                "roughnessFactor": 0.9 if layer_name != "water" else 0.3,
            },
            "doubleSided": True,
        })

        # Node → Mesh
        node_idx = len(gltf["nodes"])
        mesh_idx = len(gltf["meshes"])

        gltf["nodes"].append({
            "name": layer_name,
            "mesh": mesh_idx,
        })

        # === Buffer data ===
        # Indices
        indices_bytes = indices.astype(np.uint32).tobytes()
        indices_offset = len(binary_data)
        binary_data.extend(indices_bytes)
        # Pad to 4-byte alignment
        while len(binary_data) % 4 != 0:
            binary_data.append(0)

        indices_bv_idx = len(gltf["bufferViews"])
        gltf["bufferViews"].append({
            "buffer": 0,
            "byteOffset": indices_offset,
            "byteLength": len(indices_bytes),
            "target": 34963,  # ELEMENT_ARRAY_BUFFER
        })

        indices_acc_idx = len(gltf["accessors"])
        gltf["accessors"].append({
            "bufferView": indices_bv_idx,
            "componentType": 5125,  # UNSIGNED_INT
            "count": len(indices),
            "type": "SCALAR",
            "max": [int(indices.max())],
            "min": [int(indices.min())],
        })

        # Vertices
        verts_bytes = verts.astype(np.float32).tobytes()
        verts_offset = len(binary_data)
        binary_data.extend(verts_bytes)
        while len(binary_data) % 4 != 0:
            binary_data.append(0)

        verts_bv_idx = len(gltf["bufferViews"])
        gltf["bufferViews"].append({
            "buffer": 0,
            "byteOffset": verts_offset,
            "byteLength": len(verts_bytes),
            "target": 34962,  # ARRAY_BUFFER
            "byteStride": 12,
        })

        verts_acc_idx = len(gltf["accessors"])
        gltf["accessors"].append({
            "bufferView": verts_bv_idx,
            "componentType": 5126,  # FLOAT
            "count": len(verts),
            "type": "VEC3",
            "max": verts.max(axis=0).tolist(),
            "min": verts.min(axis=0).tolist(),
        })

        # Normals
        normals_bytes = normals.astype(np.float32).tobytes()
        normals_offset = len(binary_data)
        binary_data.extend(normals_bytes)
        while len(binary_data) % 4 != 0:
            binary_data.append(0)

        normals_bv_idx = len(gltf["bufferViews"])
        gltf["bufferViews"].append({
            "buffer": 0,
            "byteOffset": normals_offset,
            "byteLength": len(normals_bytes),
            "target": 34962,
            "byteStride": 12,
        })

        normals_acc_idx = len(gltf["accessors"])
        gltf["accessors"].append({
            "bufferView": normals_bv_idx,
            "componentType": 5126,
            "count": len(normals),
            "type": "VEC3",
        })

        # UVs
        uvs_bytes = uvs.astype(np.float32).tobytes()
        uvs_offset = len(binary_data)
        binary_data.extend(uvs_bytes)
        while len(binary_data) % 4 != 0:
            binary_data.append(0)

        uvs_bv_idx = len(gltf["bufferViews"])
        gltf["bufferViews"].append({
            "buffer": 0,
            "byteOffset": uvs_offset,
            "byteLength": len(uvs_bytes),
            "target": 34962,
            "byteStride": 8,
        })

        uvs_acc_idx = len(gltf["accessors"])
        gltf["accessors"].append({
            "bufferView": uvs_bv_idx,
            "componentType": 5126,
            "count": len(uvs),
            "type": "VEC2",
        })

        # Mesh primitive
        gltf["meshes"].append({
            "name": f"{layer_name}_mesh",
            "primitives": [{
                "attributes": {
                    "POSITION": verts_acc_idx,
                    "NORMAL": normals_acc_idx,
                    "TEXCOORD_0": uvs_acc_idx,
                },
                "indices": indices_acc_idx,
                "material": material_idx,
            }],
        })

        material_idx += 1

    if not gltf["meshes"]:
        return False

    # Update scenes node list
    gltf["scenes"][0]["nodes"] = list(range(len(gltf["nodes"])))

    # Buffer
    gltf["buffers"] = [{"byteLength": len(binary_data)}]

    # Encode GLB
    json_str = json.dumps(gltf, separators=(",", ":"))
    json_bytes = json_str.encode("utf-8")
    # Pad JSON to 4-byte alignment
    while len(json_bytes) % 4 != 0:
        json_bytes += b" "

    # GLB header: magic(4) + version(4) + length(4)
    # JSON chunk: length(4) + type(4) + data
    # BIN chunk: length(4) + type(4) + data
    total_length = (
        12 +  # header
        8 + len(json_bytes) +  # JSON chunk
        8 + len(binary_data)  # BIN chunk
    )

    # Pad binary data to 4-byte alignment
    while len(binary_data) % 4 != 0:
        binary_data.append(0)
    total_length = 12 + 8 + len(json_bytes) + 8 + len(binary_data)

    with open(output_path, "wb") as f:
        # Header
        f.write(struct.pack("<I", 0x46546C67))  # glTF magic
        f.write(struct.pack("<I", 2))  # version
        f.write(struct.pack("<I", total_length))  # total length

        # JSON chunk
        f.write(struct.pack("<I", len(json_bytes)))
        f.write(struct.pack("<I", 0x4E4F534A))  # JSON
        f.write(json_bytes)

        # BIN chunk
        f.write(struct.pack("<I", len(binary_data)))
        f.write(struct.pack("<I", 0x004E4942))  # BIN
        f.write(binary_data)

    return True


def chunk_and_export():
    """Main chunking and export function."""
    print("[Export] Loading processed meshes...")

    # Load all mesh data
    meshes = {}
    for name in ["roads_mesh", "buildings_mesh", "terrain_meshes", "landuse_mesh", "water_mesh"]:
        path = CACHE_DIR / f"{name}.pkl"
        if path.exists():
            with open(path, "rb") as f:
                meshes[name] = pickle.load(f)
            print(f"  Loaded {name}")
        else:
            print(f"  WARNING: {name} not found, skipping")
            meshes[name] = None

    # Get terrain meshes (already per-chunk)
    terrain_meshes = meshes.get("terrain_meshes", {})
    if terrain_meshes is None:
        terrain_meshes = {}

    # Determine chunk grid
    min_x, max_x, min_z, max_z = bbox_to_local()
    cx_min = int(np.floor(min_x / CHUNK_SIZE))
    cx_max = int(np.ceil(max_x / CHUNK_SIZE))
    cz_min = int(np.floor(min_z / CHUNK_SIZE))
    cz_max = int(np.ceil(max_z / CHUNK_SIZE))

    total_chunks = (cx_max - cx_min) * (cz_max - cz_min)
    print(f"[Export] Chunk grid: {cx_max - cx_min}×{cz_max - cz_min} = {total_chunks} chunks")

    CHUNKS_EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    exported = 0
    empty = 0
    manifest_chunks = {}

    for cx in range(cx_min, cx_max):
        for cz in range(cz_min, cz_max):
            chunk_min_x = cx * CHUNK_SIZE
            chunk_max_x = chunk_min_x + CHUNK_SIZE
            chunk_min_z = cz * CHUNK_SIZE
            chunk_max_z = chunk_min_z + CHUNK_SIZE

            # Clip each layer to this chunk
            chunk_layers = {}

            # Roads
            if meshes.get("roads_mesh") is not None:
                chunk_layers["roads"] = clip_mesh_to_chunk(
                    meshes["roads_mesh"],
                    chunk_min_x, chunk_max_x, chunk_min_z, chunk_max_z,
                )

            # Buildings
            if meshes.get("buildings_mesh") is not None:
                chunk_layers["buildings"] = clip_mesh_to_chunk(
                    meshes["buildings_mesh"],
                    chunk_min_x, chunk_max_x, chunk_min_z, chunk_max_z,
                )

            # Terrain (already per-chunk)
            if isinstance(terrain_meshes, dict) and (cx, cz) in terrain_meshes:
                chunk_layers["terrain"] = terrain_meshes[(cx, cz)]

            # Landuse
            if meshes.get("landuse_mesh") is not None:
                chunk_layers["landuse"] = clip_mesh_to_chunk(
                    meshes["landuse_mesh"],
                    chunk_min_x, chunk_max_x, chunk_min_z, chunk_max_z,
                )

            # Water
            if meshes.get("water_mesh") is not None:
                chunk_layers["water"] = clip_mesh_to_chunk(
                    meshes["water_mesh"],
                    chunk_min_x, chunk_max_x, chunk_min_z, chunk_max_z,
                )

            # Check if chunk has any data
            has_data = any(
                m is not None and not m.is_empty()
                for m in chunk_layers.values()
            )

            if not has_data:
                empty += 1
                continue

            # Export LOD0
            key = f"{cx}_{cz}"
            lod0_file = CHUNKS_EXPORT_DIR / f"chunk_{key}_lod0.glb"
            success = mesh_to_glb(chunk_layers, lod0_file)

            if success:
                exported += 1

                # Compute LOD1 (simplified - just terrain for now)
                lod1_layers = {}
                if "terrain" in chunk_layers and chunk_layers["terrain"] is not None:
                    lod1_layers["terrain"] = chunk_layers["terrain"]

                # Simplified buildings (just keep them, Godot will handle LOD)
                if "buildings" in chunk_layers and chunk_layers["buildings"] is not None:
                    lod1_layers["buildings"] = chunk_layers["buildings"]

                lod1_file = CHUNKS_EXPORT_DIR / f"chunk_{key}_lod1.glb"
                mesh_to_glb(lod1_layers, lod1_file)

                # Manifest entry
                layers_present = [
                    k for k, v in chunk_layers.items()
                    if v is not None and not v.is_empty()
                ]
                manifest_chunks[key] = {
                    "cx": cx,
                    "cz": cz,
                    "bounds": [chunk_min_x, chunk_max_x, chunk_min_z, chunk_max_z],
                    "layers": layers_present,
                    "lod0": f"chunk_{key}_lod0.glb",
                    "lod1": f"chunk_{key}_lod1.glb",
                }

            if (exported + empty) % 100 == 0:
                print(f"  Progress: {exported + empty}/{total_chunks} "
                      f"({exported} exported, {empty} empty)")

    # Write manifest
    manifest = {
        "chunk_size": CHUNK_SIZE,
        "origin_lat": 51.7189,
        "origin_lon": 8.7544,
        "grid_min": [cx_min, cz_min],
        "grid_max": [cx_max, cz_max],
        "total_chunks": exported,
        "chunks": manifest_chunks,
    }

    manifest_path = EXPORT_DIR / "chunk_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n[Export] Done!")
    print(f"  Exported: {exported} chunks")
    print(f"  Empty: {empty} chunks")
    print(f"  Manifest: {manifest_path}")

    # Copy to Godot assets directory
    if GODOT_CHUNKS_DIR.exists() or True:
        GODOT_CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
        import shutil

        # Copy manifest
        shutil.copy2(manifest_path, GODOT_CHUNKS_DIR.parent / "chunk_manifest.json")

        # Copy GLB files
        for glb_file in CHUNKS_EXPORT_DIR.glob("*.glb"):
            shutil.copy2(glb_file, GODOT_CHUNKS_DIR / glb_file.name)

        print(f"  Copied to Godot: {GODOT_CHUNKS_DIR}")


def main():
    print("=" * 60)
    print("Step 7: Chunk and export to glTF")
    print("=" * 60)
    chunk_and_export()
    print("Done!")


if __name__ == "__main__":
    main()
