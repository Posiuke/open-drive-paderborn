"""Spatial chunk management for the world grid."""

import json
import numpy as np
from collections import defaultdict
from pathlib import Path

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import CHUNK_SIZE, CHUNKS_EXPORT_DIR
from utils.geo import bbox_to_local


class ChunkManager:
    """Manages the spatial grid of chunks and assigns geometry to chunks."""

    def __init__(self):
        self.chunk_size = CHUNK_SIZE
        min_x, max_x, min_z, max_z = bbox_to_local()

        # Compute chunk grid bounds
        self.min_cx = int(np.floor(min_x / self.chunk_size))
        self.max_cx = int(np.ceil(max_x / self.chunk_size))
        self.min_cz = int(np.floor(min_z / self.chunk_size))
        self.max_cz = int(np.ceil(max_z / self.chunk_size))

        self.num_chunks_x = self.max_cx - self.min_cx
        self.num_chunks_z = self.max_cz - self.min_cz

        print(f"[ChunkManager] Grid: x=[{self.min_cx}..{self.max_cx}], "
              f"z=[{self.min_cz}..{self.max_cz}], "
              f"total={self.num_chunks_x * self.num_chunks_z} chunks")

        # Storage: chunk_key → { "roads": MeshData, "buildings": MeshData, ... }
        self.chunks = defaultdict(lambda: {
            "roads": None,
            "buildings": None,
            "terrain": None,
            "landuse": None,
            "water": None,
        })

    def world_to_chunk(self, x, z):
        """Get the chunk coordinate (cx, cz) for a world position."""
        cx = int(np.floor(x / self.chunk_size))
        cz = int(np.floor(z / self.chunk_size))
        return cx, cz

    def chunk_bounds(self, cx, cz):
        """Get world-space bounds for a chunk.

        Returns (min_x, max_x, min_z, max_z).
        """
        min_x = cx * self.chunk_size
        max_x = min_x + self.chunk_size
        min_z = cz * self.chunk_size
        max_z = min_z + self.chunk_size
        return min_x, max_x, min_z, max_z

    def chunk_key(self, cx, cz):
        return f"{cx}_{cz}"

    def get_chunks_for_line(self, points_xz):
        """Find all chunks that a polyline passes through.

        Args:
            points_xz: list of (x, z) points

        Returns:
            set of (cx, cz) tuples
        """
        chunks = set()
        for x, z in points_xz:
            chunks.add(self.world_to_chunk(x, z))

        # Also check intermediate points for long segments
        pts = np.array(points_xz)
        for i in range(len(pts) - 1):
            p0 = pts[i]
            p1 = pts[i + 1]
            seg_len = np.linalg.norm(p1 - p0)
            if seg_len > self.chunk_size / 2:
                num_samples = int(seg_len / (self.chunk_size / 4)) + 1
                for t in np.linspace(0, 1, num_samples):
                    p = p0 + t * (p1 - p0)
                    chunks.add(self.world_to_chunk(p[0], p[1]))

        return chunks

    def get_chunks_for_polygon(self, points_xz):
        """Find all chunks that a polygon overlaps.

        Uses the bounding box of the polygon.
        """
        pts = np.array(points_xz)
        min_x, min_z = pts.min(axis=0)
        max_x, max_z = pts.max(axis=0)

        chunks = set()
        cx_min = int(np.floor(min_x / self.chunk_size))
        cx_max = int(np.floor(max_x / self.chunk_size))
        cz_min = int(np.floor(min_z / self.chunk_size))
        cz_max = int(np.floor(max_z / self.chunk_size))

        for cx in range(cx_min, cx_max + 1):
            for cz in range(cz_min, cz_max + 1):
                chunks.add((cx, cz))

        return chunks

    def assign_mesh(self, cx, cz, layer, mesh_data):
        """Assign a mesh to a chunk layer, merging if data already exists."""
        key = self.chunk_key(cx, cz)
        if self.chunks[key][layer] is None:
            self.chunks[key][layer] = mesh_data
        else:
            self.chunks[key][layer].merge(mesh_data)

    def get_all_chunk_coords(self):
        """Get all valid chunk coordinates."""
        coords = []
        for cx in range(self.min_cx, self.max_cx):
            for cz in range(self.min_cz, self.max_cz):
                coords.append((cx, cz))
        return coords

    def get_populated_chunks(self):
        """Get chunk coordinates that have any geometry."""
        populated = []
        for key, layers in self.chunks.items():
            if any(m is not None and not m.is_empty() for m in layers.values()):
                parts = key.split("_")
                cx, cz = int(parts[0]), int(parts[1])
                populated.append((cx, cz))
        return populated

    def generate_manifest(self):
        """Generate chunk_manifest.json for Godot.

        Returns dict with chunk metadata.
        """
        manifest = {
            "chunk_size": self.chunk_size,
            "origin_lat": 51.7189,
            "origin_lon": 8.7544,
            "grid_min": [self.min_cx, self.min_cz],
            "grid_max": [self.max_cx, self.max_cz],
            "chunks": {},
        }

        for cx, cz in self.get_populated_chunks():
            key = self.chunk_key(cx, cz)
            bounds = self.chunk_bounds(cx, cz)
            layers = []
            for layer_name, mesh in self.chunks[key].items():
                if mesh is not None and not mesh.is_empty():
                    layers.append(layer_name)

            manifest["chunks"][key] = {
                "cx": cx,
                "cz": cz,
                "bounds": list(bounds),
                "layers": layers,
                "lod0": f"chunk_{key}_lod0.glb",
                "lod1": f"chunk_{key}_lod1.glb",
            }

        return manifest
