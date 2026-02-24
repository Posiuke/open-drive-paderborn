"""SRTM height data sampling with bilinear interpolation."""

import numpy as np
from pathlib import Path
from scipy.interpolate import RegularGridInterpolator

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import CACHE_DIR


class HeightSampler:
    """Samples elevation from SRTM GeoTIFF data."""

    def __init__(self, tiff_path=None):
        if tiff_path is None:
            tiff_path = CACHE_DIR / "srtm_paderborn.tif"

        self._interpolator = None
        self._loaded = False
        self._tiff_path = Path(tiff_path)

    def _load(self):
        if self._loaded:
            return

        if not self._tiff_path.exists():
            print(f"[HeightSampler] No SRTM data at {self._tiff_path}, using flat terrain (h=100m)")
            self._interpolator = None
            self._loaded = True
            return

        import rasterio

        with rasterio.open(self._tiff_path) as src:
            data = src.read(1).astype(np.float64)
            transform = src.transform

            # Build coordinate arrays for the grid
            nrows, ncols = data.shape
            # Pixel centers
            cols = np.arange(ncols)
            rows = np.arange(nrows)

            # Convert pixel indices to lon/lat
            lons = transform.c + (cols + 0.5) * transform.a
            lats = transform.f + (rows + 0.5) * transform.e  # e is negative

            # lats is descending, need ascending for interpolator
            if lats[0] > lats[-1]:
                lats = lats[::-1]
                data = data[::-1, :]

            # Handle nodata
            nodata = src.nodata
            if nodata is not None:
                data[data == nodata] = 100.0  # Default elevation for Paderborn area

            self._interpolator = RegularGridInterpolator(
                (lats, lons), data,
                method="linear",
                bounds_error=False,
                fill_value=100.0
            )

        self._loaded = True
        print(f"[HeightSampler] Loaded SRTM data: {data.shape}, "
              f"elevation range: {data.min():.1f}–{data.max():.1f}m")

    def sample(self, lon, lat):
        """Sample elevation at WGS84 coordinates.

        Args:
            lon: scalar or array of longitudes
            lat: scalar or array of latitudes

        Returns:
            Elevation in meters (scalar or array)
        """
        self._load()

        if self._interpolator is None:
            if np.isscalar(lon):
                return 100.0
            return np.full_like(np.asarray(lon, dtype=float), 100.0)

        lon = np.asarray(lon, dtype=float)
        lat = np.asarray(lat, dtype=float)
        scalar = lon.ndim == 0

        points = np.column_stack([lat.ravel(), lon.ravel()])
        heights = self._interpolator(points)

        if scalar:
            return float(heights[0])
        return heights.reshape(lon.shape)

    def sample_utm(self, easting, northing):
        """Sample elevation at UTM coordinates."""
        from utils.geo import utm_to_wgs84
        lon, lat = utm_to_wgs84(easting, northing)
        return self.sample(lon, lat)

    def sample_local(self, x, z):
        """Sample elevation at local coordinates."""
        from utils.geo import local_to_wgs84
        lon, lat = local_to_wgs84(x, z)
        return self.sample(lon, lat)


# Singleton
_sampler = None

def get_height_sampler():
    global _sampler
    if _sampler is None:
        _sampler = HeightSampler()
    return _sampler
