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
