"""Coordinate transformations: WGS84 → UTM Zone 32N → Godot local coordinates."""

import numpy as np
from pyproj import Transformer

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import CRS_WGS84, CRS_UTM, ORIGIN_LAT, ORIGIN_LON

# Reusable transformers (thread-safe in pyproj >= 3.0)
_wgs84_to_utm = Transformer.from_crs(CRS_WGS84, CRS_UTM, always_xy=True)
_utm_to_wgs84 = Transformer.from_crs(CRS_UTM, CRS_WGS84, always_xy=True)

# Pre-compute origin in UTM
ORIGIN_UTM_E, ORIGIN_UTM_N = _wgs84_to_utm.transform(ORIGIN_LON, ORIGIN_LAT)


def wgs84_to_utm(lon, lat):
    """Convert WGS84 (lon, lat) to UTM Zone 32N (easting, northing).

    Accepts scalars or arrays.
    """
    return _wgs84_to_utm.transform(lon, lat)


def utm_to_wgs84(easting, northing):
    """Convert UTM Zone 32N to WGS84 (lon, lat)."""
    return _utm_to_wgs84.transform(easting, northing)


def wgs84_to_local(lon, lat):
    """Convert WGS84 (lon, lat) to Godot local coordinates.

    Returns (x, z) where:
    - x = east (positive = east of Dom)
    - z = north (positive = north of Dom, note: Godot Z is typically negative-forward,
      but we use positive-north here and handle in Godot)

    Accepts scalars or numpy arrays.
    """
    e, n = wgs84_to_utm(lon, lat)
    x = np.asarray(e) - ORIGIN_UTM_E
    z = np.asarray(n) - ORIGIN_UTM_N
    return x, z


def utm_to_local(easting, northing):
    """Convert UTM to local coordinates (relative to Dom origin)."""
    x = np.asarray(easting) - ORIGIN_UTM_E
    z = np.asarray(northing) - ORIGIN_UTM_N
    return x, z


def local_to_utm(x, z):
    """Convert local coordinates back to UTM."""
    return x + ORIGIN_UTM_E, z + ORIGIN_UTM_N


def local_to_wgs84(x, z):
    """Convert local coordinates to WGS84."""
    e, n = local_to_utm(x, z)
    return utm_to_wgs84(e, n)


def bbox_to_local():
    """Convert the Paderborn bounding box to local coordinates.

    Returns (min_x, max_x, min_z, max_z) in local meters.
    """
    from config import BBOX_NORTH, BBOX_SOUTH, BBOX_EAST, BBOX_WEST

    # Southwest corner
    x_min, z_min = wgs84_to_local(BBOX_WEST, BBOX_SOUTH)
    # Northeast corner
    x_max, z_max = wgs84_to_local(BBOX_EAST, BBOX_NORTH)

    return float(x_min), float(x_max), float(z_min), float(z_max)


def coords_to_local_array(coords):
    """Convert a list of (lon, lat) tuples to local (x, z) numpy arrays.

    Returns (xs, zs) as numpy arrays.
    """
    if len(coords) == 0:
        return np.array([]), np.array([])

    lons = np.array([c[0] for c in coords])
    lats = np.array([c[1] for c in coords])
    return wgs84_to_local(lons, lats)


# === Dynamic origin functions for server mode ===

def wgs84_to_local_dynamic(lon, lat, origin_e, origin_n):
    """Convert WGS84 to local coordinates relative to a dynamic origin.

    Args:
        lon, lat: WGS84 coordinates (scalars or arrays)
        origin_e, origin_n: UTM easting/northing of the current origin

    Returns:
        (x, z) local coordinates relative to the given origin
    """
    e, n = wgs84_to_utm(lon, lat)
    x = np.asarray(e) - origin_e
    z = np.asarray(n) - origin_n
    return x, z


def utm_to_local_dynamic(easting, northing, origin_e, origin_n):
    """Convert UTM to local coordinates relative to a dynamic origin."""
    x = np.asarray(easting) - origin_e
    z = np.asarray(northing) - origin_n
    return x, z


def global_chunk_to_utm(cx, cz, chunk_size=256.0):
    """Convert global chunk coords to UTM center point.

    Global chunks are indexed relative to the default origin (Paderborner Dom).
    Returns (center_e, center_n) in UTM.
    """
    local_x = (cx + 0.5) * chunk_size
    local_z = (cz + 0.5) * chunk_size
    return local_x + ORIGIN_UTM_E, local_z + ORIGIN_UTM_N


def global_chunk_bbox_wgs84(cx, cz, chunk_size=256.0):
    """Get WGS84 bounding box for a global chunk.

    Returns (west, south, east, north) in WGS84.
    """
    min_x = cx * chunk_size
    max_x = min_x + chunk_size
    min_z = cz * chunk_size
    max_z = min_z + chunk_size

    min_e = min_x + ORIGIN_UTM_E
    min_n = min_z + ORIGIN_UTM_N
    max_e = max_x + ORIGIN_UTM_E
    max_n = max_z + ORIGIN_UTM_N

    lon_w, lat_s = utm_to_wgs84(min_e, min_n)
    lon_e, lat_n = utm_to_wgs84(max_e, max_n)

    return float(lon_w), float(lat_s), float(lon_e), float(lat_n)


def global_chunk_bbox_utm(cx, cz, chunk_size=256.0):
    """Get UTM bounding box for a global chunk.

    Returns (min_e, min_n, max_e, max_n) in UTM.
    """
    min_x = cx * chunk_size
    max_x = min_x + chunk_size
    min_z = cz * chunk_size
    max_z = min_z + chunk_size

    return (min_x + ORIGIN_UTM_E, min_z + ORIGIN_UTM_N,
            max_x + ORIGIN_UTM_E, max_z + ORIGIN_UTM_N)


def megatile_key(cx, cz, chunk_size=256.0, megatile_size=2048.0):
    """Compute the megatile key for a chunk.

    Megatiles are 2km x 2km blocks of OSM data (8x8 chunks at 256m).
    Returns (mt_x, mt_z) integer megatile coordinates.
    """
    # Chunk local center
    center_x = (cx + 0.5) * chunk_size
    center_z = (cz + 0.5) * chunk_size
    mt_x = int(np.floor(center_x / megatile_size))
    mt_z = int(np.floor(center_z / megatile_size))
    return mt_x, mt_z


def megatile_bbox_wgs84(mt_x, mt_z, megatile_size=2048.0):
    """Get WGS84 bounding box for a megatile.

    Returns (west, south, east, north).
    """
    min_x = mt_x * megatile_size
    max_x = min_x + megatile_size
    min_z = mt_z * megatile_size
    max_z = min_z + megatile_size

    min_e = min_x + ORIGIN_UTM_E
    min_n = min_z + ORIGIN_UTM_N
    max_e = max_x + ORIGIN_UTM_E
    max_n = max_z + ORIGIN_UTM_N

    lon_w, lat_s = utm_to_wgs84(min_e, min_n)
    lon_e, lat_n = utm_to_wgs84(max_e, max_n)

    return float(lon_w), float(lat_s), float(lon_e), float(lat_n)
