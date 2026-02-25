"""GLB export utilities - extracted from 07_chunk_and_export.py.

Provides both file-based and in-memory GLB generation.
"""

import json
import struct
import numpy as np


# Material colors per layer
MATERIAL_COLORS = {
    "roads": [0.35, 0.35, 0.35, 1.0],
    "buildings": [0.7, 0.65, 0.6, 1.0],
    "terrain": [0.3, 0.5, 0.2, 1.0],
    "landuse": [0.35, 0.55, 0.25, 1.0],
    "water": [0.2, 0.4, 0.7, 1.0],
}


def _build_glb_bytes(meshes_by_layer):
    """Build GLB binary data from mesh layers.

    Args:
        meshes_by_layer: dict of layer_name -> MeshData

    Returns:
        bytes of the GLB file, or None if no data.
    """
    # Filter empty layers
    layers = {k: v for k, v in meshes_by_layer.items()
              if v is not None and not v.is_empty()}

    if not layers:
        return None

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
    material_idx = 0

    for layer_name, mesh in layers.items():
        data = mesh.to_numpy()
        verts = data["vertices"]
        normals = data["normals"]
        uvs = data["uvs"]
        indices = data["indices"]

        if len(verts) == 0 or len(indices) == 0:
            continue

        # Create material
        mat_color = MATERIAL_COLORS.get(layer_name, [0.5, 0.5, 0.5, 1.0])
        gltf["materials"].append({
            "name": layer_name,
            "pbrMetallicRoughness": {
                "baseColorFactor": mat_color,
                "metallicFactor": 0.0,
                "roughnessFactor": 0.9 if layer_name != "water" else 0.3,
            },
            "doubleSided": True,
        })

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
        while len(binary_data) % 4 != 0:
            binary_data.append(0)

        indices_bv_idx = len(gltf["bufferViews"])
        gltf["bufferViews"].append({
            "buffer": 0,
            "byteOffset": indices_offset,
            "byteLength": len(indices_bytes),
            "target": 34963,
        })

        indices_acc_idx = len(gltf["accessors"])
        gltf["accessors"].append({
            "bufferView": indices_bv_idx,
            "componentType": 5125,
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
            "target": 34962,
            "byteStride": 12,
        })

        verts_acc_idx = len(gltf["accessors"])
        gltf["accessors"].append({
            "bufferView": verts_bv_idx,
            "componentType": 5126,
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
        return None

    # Update scenes node list
    gltf["scenes"][0]["nodes"] = list(range(len(gltf["nodes"])))

    # Buffer
    gltf["buffers"] = [{"byteLength": len(binary_data)}]

    # Encode GLB
    json_str = json.dumps(gltf, separators=(",", ":"))
    json_bytes = json_str.encode("utf-8")
    while len(json_bytes) % 4 != 0:
        json_bytes += b" "

    # Pad binary data to 4-byte alignment
    while len(binary_data) % 4 != 0:
        binary_data.append(0)

    total_length = 12 + 8 + len(json_bytes) + 8 + len(binary_data)

    out = bytearray()
    # GLB Header
    out.extend(struct.pack("<I", 0x46546C67))  # glTF magic
    out.extend(struct.pack("<I", 2))            # version
    out.extend(struct.pack("<I", total_length))  # total length
    # JSON chunk
    out.extend(struct.pack("<I", len(json_bytes)))
    out.extend(struct.pack("<I", 0x4E4F534A))  # JSON
    out.extend(json_bytes)
    # BIN chunk
    out.extend(struct.pack("<I", len(binary_data)))
    out.extend(struct.pack("<I", 0x004E4942))  # BIN
    out.extend(binary_data)

    return bytes(out)


def mesh_to_glb(meshes_by_layer, output_path):
    """Export multiple mesh layers as a single GLB file.

    Args:
        meshes_by_layer: dict of layer_name -> MeshData
        output_path: output .glb file path

    Returns:
        True if file was written successfully.
    """
    glb_bytes = _build_glb_bytes(meshes_by_layer)
    if glb_bytes is None:
        return False

    with open(output_path, "wb") as f:
        f.write(glb_bytes)
    return True


def mesh_to_glb_bytes(meshes_by_layer):
    """Export multiple mesh layers as GLB bytes (for HTTP streaming).

    Args:
        meshes_by_layer: dict of layer_name -> MeshData

    Returns:
        bytes of the GLB file, or None if no geometry.
    """
    return _build_glb_bytes(meshes_by_layer)
