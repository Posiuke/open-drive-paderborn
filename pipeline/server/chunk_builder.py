"""Build a single chunk's GLB from raw OSM + SRTM data.

This is the mini-pipeline that runs per chunk request:
1. Determine megatile -> fetch OSM data
2. Filter features to chunk bounds
3. Build meshes (roads, buildings, terrain, landuse, water)
4. Export as GLB bytes
"""

import numpy as np

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import (
    CHUNK_SIZE, TERRAIN_RESOLUTION, TERRAIN_LOD1_RESOLUTION,
    ROAD_WIDTHS, DEFAULT_LANES, DEFAULT_BUILDING_HEIGHT,
    BUILDING_FLOOR_HEIGHT, BUILDING_HEIGHTS, LANDUSE_COLORS,
)
from utils.geo import wgs84_to_local, global_chunk_bbox_wgs84
from utils.mesh_builder import (
    MeshData, build_road_mesh, build_building_mesh,
    build_terrain_mesh, build_landuse_mesh, build_water_mesh,
)
from utils.glb_exporter import mesh_to_glb_bytes


def _normalize_highway(val):
    if isinstance(val, list):
        return val[0] if val else "residential"
    return val or "residential"


def _get_road_width(tags):
    highway = _normalize_highway(tags.get("highway", "residential"))
    width = tags.get("width")
    if width:
        try:
            w = width if not isinstance(width, list) else width[0]
            return float(str(w).replace("m", "").strip())
        except (ValueError, TypeError):
            pass
    lanes = tags.get("lanes")
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


def _get_road_color(highway_type):
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


def _get_building_height(tags):
    height = tags.get("height")
    if height:
        try:
            h = str(height).replace("m", "").strip()
            val = float(h)
            if val == val:  # not NaN
                return val
        except (ValueError, TypeError):
            pass
    levels = tags.get("building:levels")
    if levels:
        try:
            val = int(float(str(levels)))
            if val > 0:
                return val * BUILDING_FLOOR_HEIGHT
        except (ValueError, TypeError):
            pass
    building_type = tags.get("building", "yes")
    if building_type in BUILDING_HEIGHTS:
        return BUILDING_HEIGHTS[building_type]
    if tags.get("amenity") == "place_of_worship":
        return BUILDING_HEIGHTS.get("church", 20.0)
    return DEFAULT_BUILDING_HEIGHT


def _get_building_color(tags):
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


def _get_landuse_type(tags):
    landuse = tags.get("landuse")
    if landuse:
        return landuse
    natural = tags.get("natural")
    if natural == "water":
        return "water"
    if natural in ("wood", "scrub"):
        return "forest"
    if natural == "grassland":
        return "grass"
    leisure = tags.get("leisure")
    if leisure in ("park", "garden"):
        return "park"
    if leisure in ("pitch", "playground"):
        return "recreation_ground"
    if tags.get("waterway"):
        return "water"
    return None


def _coords_in_chunk(coords_local, min_x, max_x, min_z, max_z, margin=50.0):
    """Check if any coordinate falls within chunk bounds + margin."""
    for x, z in coords_local:
        if (min_x - margin <= x <= max_x + margin and
                min_z - margin <= z <= max_z + margin):
            return True
    return False


class ChunkBuilder:
    """Builds a single chunk's GLB from fetched data."""

    def __init__(self, data_fetcher, height_sampler):
        self.data_fetcher = data_fetcher
        self.height_sampler = height_sampler

    def build_chunk(self, cx, cz, lod=0):
        """Build a chunk and return GLB bytes.

        Args:
            cx, cz: global chunk coordinates
            lod: 0 for full detail, 1 for simplified

        Returns:
            bytes of GLB data, or None if chunk is empty.
        """
        # Chunk bounds in local coordinates
        min_x = cx * CHUNK_SIZE
        max_x = min_x + CHUNK_SIZE
        min_z = cz * CHUNK_SIZE
        max_z = min_z + CHUNK_SIZE

        # Fetch megatile data
        features = self.data_fetcher.get_megatile_for_chunk(cx, cz)

        layers = {}

        # Build terrain (always present)
        resolution = TERRAIN_RESOLUTION if lod == 0 else TERRAIN_LOD1_RESOLUTION
        terrain_mesh = build_terrain_mesh(
            min_x, max_x, min_z, max_z,
            resolution,
            height_func=self.height_sampler.sample_local,
            color=(0.3, 0.5, 0.2),
        )
        if not terrain_mesh.is_empty():
            layers["terrain"] = terrain_mesh

        # Build roads (LOD0 only)
        if lod == 0:
            roads_mesh = self._build_roads(
                features.get("roads", []),
                min_x, max_x, min_z, max_z
            )
            if not roads_mesh.is_empty():
                layers["roads"] = roads_mesh

        # Build buildings
        buildings_mesh = self._build_buildings(
            features.get("buildings", []),
            min_x, max_x, min_z, max_z
        )
        if not buildings_mesh.is_empty():
            layers["buildings"] = buildings_mesh

        # Build landuse (LOD0 only)
        if lod == 0:
            landuse_mesh = self._build_landuse(
                features.get("landuse", []),
                min_x, max_x, min_z, max_z
            )
            if not landuse_mesh.is_empty():
                layers["landuse"] = landuse_mesh

            water_mesh = self._build_water(
                features.get("water", []),
                min_x, max_x, min_z, max_z
            )
            if not water_mesh.is_empty():
                layers["water"] = water_mesh

        if not layers:
            return None

        return mesh_to_glb_bytes(layers)

    def _build_roads(self, road_features, min_x, max_x, min_z, max_z):
        """Build road meshes for features within chunk bounds."""
        mesh = MeshData()

        for feature in road_features:
            coords = feature["coords"]
            tags = feature["tags"]

            # Convert to local
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            xs, zs = wgs84_to_local(np.array(lons), np.array(lats))
            points_xz = list(zip(xs, zs))

            if not _coords_in_chunk(points_xz, min_x, max_x, min_z, max_z):
                continue

            highway = _normalize_highway(tags.get("highway", "residential"))
            width = _get_road_width(tags)
            color = _get_road_color(highway)

            road_mesh = build_road_mesh(
                points_xz, width,
                height_func=self.height_sampler.sample_local,
                color=color,
            )
            if not road_mesh.is_empty():
                mesh.merge(road_mesh)

        return mesh

    def _build_buildings(self, building_features, min_x, max_x, min_z, max_z):
        """Build building meshes for features within chunk bounds."""
        mesh = MeshData()

        for feature in building_features:
            coords = feature["coords"]
            tags = feature["tags"]

            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            xs, zs = wgs84_to_local(np.array(lons), np.array(lats))
            footprint = list(zip(xs, zs))

            # Check if building centroid is in chunk
            cx_b = np.mean(xs)
            cz_b = np.mean(zs)
            if not (min_x <= cx_b <= max_x and min_z <= cz_b <= max_z):
                continue

            height = _get_building_height(tags)
            color = _get_building_color(tags)
            base_height = self.height_sampler.sample_local(cx_b, cz_b)

            bldg_mesh = build_building_mesh(footprint, height, base_height, color)
            if not bldg_mesh.is_empty():
                mesh.merge(bldg_mesh)

        return mesh

    def _build_landuse(self, landuse_features, min_x, max_x, min_z, max_z):
        """Build landuse meshes for features within chunk bounds."""
        mesh = MeshData()

        for feature in landuse_features:
            coords = feature["coords"]
            tags = feature["tags"]

            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            xs, zs = wgs84_to_local(np.array(lons), np.array(lats))
            points = list(zip(xs, zs))

            if not _coords_in_chunk(points, min_x, max_x, min_z, max_z, margin=10.0):
                continue

            ltype = _get_landuse_type(tags)
            if ltype is None:
                continue

            color = LANDUSE_COLORS.get(ltype, (0.4, 0.5, 0.3))
            lu_mesh = build_landuse_mesh(
                points,
                height_func=self.height_sampler.sample_local,
                color=color,
            )
            if not lu_mesh.is_empty():
                mesh.merge(lu_mesh)

        return mesh

    def _build_water(self, water_features, min_x, max_x, min_z, max_z):
        """Build water meshes for features within chunk bounds."""
        mesh = MeshData()

        for feature in water_features:
            coords = feature["coords"]

            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            xs, zs = wgs84_to_local(np.array(lons), np.array(lats))
            points = list(zip(xs, zs))

            if not _coords_in_chunk(points, min_x, max_x, min_z, max_z, margin=10.0):
                continue

            if len(points) < 3:
                continue

            w_mesh = build_water_mesh(
                points,
                height_func=self.height_sampler.sample_local,
            )
            if not w_mesh.is_empty():
                mesh.merge(w_mesh)

        return mesh
