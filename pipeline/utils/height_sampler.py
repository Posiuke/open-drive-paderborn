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


class MultiTileHeightSampler:
    """Height sampler that loads arbitrary SRTM tiles on demand.

    Unlike HeightSampler (single pre-cropped GeoTIFF), this loads raw .hgt
    tiles covering any location in Germany and beyond.
    """

    def __init__(self, cache_dir=None):
        if cache_dir is None:
            cache_dir = CACHE_DIR
        self._cache_dir = Path(cache_dir)
        self._tiles = {}  # "N51E008" -> RegularGridInterpolator
        self._loading = set()  # tiles currently being fetched

    def _tile_name(self, lon, lat):
        """Get SRTM tile name for a coordinate."""
        lat_i = int(np.floor(lat))
        lon_i = int(np.floor(lon))
        ns = "N" if lat_i >= 0 else "S"
        ew = "E" if lon_i >= 0 else "W"
        return f"{ns}{abs(lat_i):02d}{ew}{abs(lon_i):03d}"

    def _ensure_tile(self, tile_name):
        """Load or download an SRTM tile."""
        if tile_name in self._tiles:
            return

        hgt_file = self._cache_dir / f"{tile_name}.hgt"

        if not hgt_file.exists():
            # Download from S3
            self._download_tile(tile_name, hgt_file)

        if not hgt_file.exists():
            # Mark as unavailable (flat fallback)
            self._tiles[tile_name] = None
            return

        # Parse HGT
        file_size = hgt_file.stat().st_size
        if file_size >= 3601 * 3601 * 2:
            size = 3601
        else:
            size = 1201

        data = np.fromfile(hgt_file, dtype=">i2").reshape(size, size).astype(np.float64)
        data[data < -100] = 100.0  # void values

        # Build coordinate arrays
        lat = int(tile_name[1:3])
        lon = int(tile_name[4:7])
        if tile_name[0] == "S":
            lat = -lat
        if tile_name[3] == "W":
            lon = -lon

        lats = np.linspace(lat + 1, lat, size)  # top to bottom
        lons = np.linspace(lon, lon + 1, size)

        # lats must be ascending for interpolator
        if lats[0] > lats[-1]:
            lats = lats[::-1]
            data = data[::-1, :]

        self._tiles[tile_name] = RegularGridInterpolator(
            (lats, lons), data,
            method="linear",
            bounds_error=False,
            fill_value=100.0,
        )
        print(f"[MultiTileHeightSampler] Loaded {tile_name}: "
              f"elevation {data.min():.0f}-{data.max():.0f}m")

    def _download_tile(self, tile_name, hgt_file):
        """Download an SRTM tile from S3."""
        import requests
        import gzip

        url = (f"https://elevation-tiles-prod.s3.amazonaws.com"
               f"/skadi/{tile_name[:3]}/{tile_name}.hgt.gz")

        print(f"[MultiTileHeightSampler] Downloading {tile_name}...")
        try:
            resp = requests.get(url, timeout=60, stream=True)
            if resp.status_code == 200:
                gz_file = self._cache_dir / f"{tile_name}.hgt.gz"
                with open(gz_file, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                with gzip.open(gz_file, "rb") as gz:
                    with open(hgt_file, "wb") as out:
                        out.write(gz.read())
                gz_file.unlink()
                print(f"[MultiTileHeightSampler] Downloaded {tile_name}")
            else:
                print(f"[MultiTileHeightSampler] HTTP {resp.status_code} for {tile_name}")
        except Exception as e:
            print(f"[MultiTileHeightSampler] Error downloading {tile_name}: {e}")

    def sample(self, lon, lat):
        """Sample elevation at WGS84 coordinates."""
        lon = np.asarray(lon, dtype=float)
        lat = np.asarray(lat, dtype=float)
        scalar = lon.ndim == 0

        if scalar:
            tile = self._tile_name(float(lon), float(lat))
            self._ensure_tile(tile)
            interp = self._tiles.get(tile)
            if interp is None:
                return 100.0
            return float(interp(np.array([[float(lat), float(lon)]]))[0])

        # Array input - may span multiple tiles
        results = np.full(lon.shape, 100.0)
        flat_lon = lon.ravel()
        flat_lat = lat.ravel()

        # Group by tile
        tile_groups = {}
        for i in range(len(flat_lon)):
            tile = self._tile_name(flat_lon[i], flat_lat[i])
            if tile not in tile_groups:
                tile_groups[tile] = []
            tile_groups[tile].append(i)

        for tile, indices in tile_groups.items():
            self._ensure_tile(tile)
            interp = self._tiles.get(tile)
            if interp is None:
                continue
            pts = np.column_stack([flat_lat[indices], flat_lon[indices]])
            heights = interp(pts)
            for j, idx in enumerate(indices):
                results.ravel()[idx] = heights[j]

        return results.reshape(lon.shape)

    def sample_utm(self, easting, northing):
        """Sample elevation at UTM coordinates."""
        from utils.geo import utm_to_wgs84
        lon, lat = utm_to_wgs84(easting, northing)
        return self.sample(lon, lat)

    def sample_local(self, x, z):
        """Sample elevation at local coordinates (relative to default origin)."""
        from utils.geo import local_to_wgs84
        lon, lat = local_to_wgs84(x, z)
        return self.sample(lon, lat)


# Singleton for multi-tile sampler
_multi_sampler = None

def get_multi_height_sampler(cache_dir=None):
    global _multi_sampler
    if _multi_sampler is None:
        _multi_sampler = MultiTileHeightSampler(cache_dir)
    return _multi_sampler
