"""Configuration for Paderborn Open Drive Game data pipeline."""

import os
from pathlib import Path

# === Project Paths ===
PROJECT_ROOT = Path(__file__).parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
EXPORT_DIR = DATA_DIR / "export"
CHUNKS_EXPORT_DIR = EXPORT_DIR / "chunks"
GODOT_CHUNKS_DIR = PROJECT_ROOT / "godot" / "assets" / "chunks"

# Ensure directories exist
for d in [CACHE_DIR, CHUNKS_EXPORT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# === Paderborn Bounding Box (WGS84) ===
BBOX_NORTH = 51.755
BBOX_SOUTH = 51.685
BBOX_EAST = 8.820
BBOX_WEST = 8.690

# osmnx >= 2.0 expects (west, south, east, north)
BBOX = (BBOX_WEST, BBOX_SOUTH, BBOX_EAST, BBOX_NORTH)

# === World Origin: Paderborner Dom ===
ORIGIN_LAT = 51.7189
ORIGIN_LON = 8.7544

# === Coordinate Reference System ===
CRS_WGS84 = "EPSG:4326"
CRS_UTM = "EPSG:32632"  # UTM Zone 32N

# === Chunk Settings ===
CHUNK_SIZE = 256.0  # meters

# === LOD Settings ===
LOD0_RADIUS = 2  # chunks in each direction (5x5 grid)
LOD1_RADIUS = 4  # outer ring of simplified chunks

# === Building Defaults ===
DEFAULT_BUILDING_HEIGHT = 9.0  # meters (~ 3 floors)
BUILDING_FLOOR_HEIGHT = 3.0  # meters per floor

# Special building heights (approximate)
BUILDING_HEIGHTS = {
    "cathedral": 33.0,
    "church": 20.0,
    "castle": 18.0,
    "civic": 15.0,
    "university": 15.0,
    "industrial": 10.0,
    "residential": 9.0,
    "commercial": 12.0,
    "retail": 8.0,
    "garage": 6.0,
    "garages": 4.0,
    "shed": 3.5,
    "roof": 4.0,
    "hut": 3.0,
}

# === Road Widths (meters per lane) ===
ROAD_WIDTHS = {
    "motorway": 3.75,
    "motorway_link": 3.5,
    "trunk": 3.5,
    "trunk_link": 3.25,
    "primary": 3.5,
    "primary_link": 3.25,
    "secondary": 3.25,
    "secondary_link": 3.0,
    "tertiary": 3.0,
    "tertiary_link": 2.75,
    "residential": 2.75,
    "living_street": 2.5,
    "unclassified": 2.75,
    "service": 2.5,
    "pedestrian": 2.0,
    "footway": 1.5,
    "cycleway": 1.5,
    "path": 1.0,
    "track": 2.5,
}

DEFAULT_LANES = {
    "motorway": 2,
    "trunk": 2,
    "primary": 2,
    "secondary": 2,
    "tertiary": 1,
    "residential": 1,
    "living_street": 1,
    "unclassified": 1,
    "service": 1,
}

# === Terrain ===
TERRAIN_RESOLUTION = 16.0  # meters per vertex in terrain mesh
TERRAIN_LOD1_RESOLUTION = 64.0

# === Landuse Colors (RGB 0-1) ===
LANDUSE_COLORS = {
    "grass": (0.3, 0.6, 0.2),
    "forest": (0.15, 0.4, 0.1),
    "meadow": (0.35, 0.65, 0.25),
    "farmland": (0.6, 0.55, 0.3),
    "residential": (0.7, 0.65, 0.6),
    "commercial": (0.65, 0.6, 0.65),
    "industrial": (0.55, 0.55, 0.55),
    "retail": (0.7, 0.6, 0.55),
    "water": (0.2, 0.4, 0.7),
    "basin": (0.2, 0.4, 0.7),
    "reservoir": (0.2, 0.4, 0.7),
    "river": (0.2, 0.4, 0.7),
    "park": (0.25, 0.55, 0.2),
    "recreation_ground": (0.3, 0.55, 0.25),
}

# === Physics (for reference, actual values in Godot) ===
PHYSICS_TICKRATE = 120  # Hz
TARGET_FPS = 60

# === Server Settings ===
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8090
SERVER_WORKERS = 4
SERVER_CACHE_DIR = PROJECT_ROOT / "pipeline" / "server_cache"
MEGATILE_SIZE = 2048.0  # 2km x 2km OSM fetch blocks (8x8 chunks)

# === OSM Tags to Download ===
OSM_BUILDING_TAGS = {"building": True}
OSM_ROAD_TAGS = {
    "highway": [
        "motorway", "motorway_link", "trunk", "trunk_link",
        "primary", "primary_link", "secondary", "secondary_link",
        "tertiary", "tertiary_link", "residential", "living_street",
        "unclassified", "service", "pedestrian",
    ]
}
OSM_LANDUSE_TAGS = {
    "landuse": True,
    "natural": ["water", "wood", "grassland", "scrub"],
    "leisure": ["park", "garden", "pitch", "playground"],
    "waterway": True,
}
