#!/usr/bin/env python3
"""Step 2: Download SRTM elevation data for Paderborn."""

import sys
import os
import requests
import numpy as np
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    CACHE_DIR, BBOX_NORTH, BBOX_SOUTH, BBOX_EAST, BBOX_WEST,
)


def download_srtm():
    """Download SRTM data covering Paderborn.

    SRTM tiles are 1°×1° tiles. Paderborn (lat ~51.7, lon ~8.75)
    needs tile N51E008.
    """
    output_file = CACHE_DIR / "srtm_paderborn.tif"

    if output_file.exists():
        print(f"[SRTM] Already cached: {output_file}")
        return output_file

    # Determine which SRTM tiles we need
    lat_min = int(np.floor(BBOX_SOUTH))
    lat_max = int(np.floor(BBOX_NORTH))
    lon_min = int(np.floor(BBOX_WEST))
    lon_max = int(np.floor(BBOX_EAST))

    tiles_needed = []
    for lat in range(lat_min, lat_max + 1):
        for lon in range(lon_min, lon_max + 1):
            ns = "N" if lat >= 0 else "S"
            ew = "E" if lon >= 0 else "W"
            tile_name = f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}"
            tiles_needed.append(tile_name)

    print(f"[SRTM] Tiles needed: {tiles_needed}")

    # Try downloading from OpenTopography or NASA Earthdata
    # Using the SRTM 90m (SRTM3) data from CGIAR-CSI mirror
    for tile_name in tiles_needed:
        hgt_file = CACHE_DIR / f"{tile_name}.hgt"

        if not hgt_file.exists():
            # Try USGS/NASA SRTM GL1 (30m) via OpenTopography
            urls = [
                f"https://elevation-tiles-prod.s3.amazonaws.com/skadi/{tile_name[:3]}/{tile_name}.hgt.gz",
            ]

            downloaded = False
            for url in urls:
                print(f"[SRTM] Trying: {url}")
                try:
                    resp = requests.get(url, timeout=60, stream=True)
                    if resp.status_code == 200:
                        gz_file = CACHE_DIR / f"{tile_name}.hgt.gz"
                        with open(gz_file, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=8192):
                                f.write(chunk)

                        # Decompress
                        import gzip
                        with gzip.open(gz_file, "rb") as gz:
                            with open(hgt_file, "wb") as out:
                                out.write(gz.read())
                        gz_file.unlink()

                        print(f"[SRTM] Downloaded: {tile_name}")
                        downloaded = True
                        break
                    else:
                        print(f"  HTTP {resp.status_code}")
                except Exception as e:
                    print(f"  Error: {e}")

            if not downloaded:
                print(f"[SRTM] WARNING: Could not download {tile_name}")
                print("[SRTM] Creating flat terrain fallback (100m elevation)")
                _create_flat_tif(output_file)
                return output_file

    # Convert HGT to GeoTIFF using rasterio
    _hgt_to_geotiff(tiles_needed, output_file)

    return output_file


def _hgt_to_geotiff(tile_names, output_file):
    """Convert .hgt SRTM files to a single GeoTIFF cropped to Paderborn bbox."""
    try:
        import rasterio
        from rasterio.transform import from_bounds
    except ImportError:
        print("[SRTM] rasterio not available, creating flat terrain")
        _create_flat_tif(output_file)
        return

    # For simplicity, handle single tile (which covers our area)
    hgt_file = CACHE_DIR / f"{tile_names[0]}.hgt"

    if not hgt_file.exists():
        _create_flat_tif(output_file)
        return

    # SRTM3 (90m): 1201×1201, SRTM1 (30m): 3601×3601
    file_size = hgt_file.stat().st_size
    if file_size >= 3601 * 3601 * 2:
        size = 3601
    else:
        size = 1201

    data = np.fromfile(hgt_file, dtype=">i2").reshape(size, size).astype(np.float32)

    # SRTM HGT: top-left is (lat+1, lon), bottom-right is (lat, lon+1)
    tile_name = tile_names[0]
    lat = int(tile_name[1:3])
    lon = int(tile_name[4:7])
    if tile_name[0] == "S":
        lat = -lat
    if tile_name[3] == "W":
        lon = -lon

    # Crop to Paderborn bbox
    # Pixel coordinates for our bbox
    res = 1.0 / (size - 1)  # degrees per pixel

    col_min = int((BBOX_WEST - lon) / res)
    col_max = int((BBOX_EAST - lon) / res) + 1
    row_min = int(((lat + 1) - BBOX_NORTH) / res)
    row_max = int(((lat + 1) - BBOX_SOUTH) / res) + 1

    col_min = max(0, col_min)
    col_max = min(size, col_max)
    row_min = max(0, row_min)
    row_max = min(size, row_max)

    cropped = data[row_min:row_max, col_min:col_max]

    # Handle void (-32768)
    cropped[cropped < -100] = 100.0

    # Write GeoTIFF
    transform = from_bounds(
        BBOX_WEST + col_min * res,
        (lat + 1) - row_max * res,
        BBOX_WEST + col_max * res,
        (lat + 1) - row_min * res,
        cropped.shape[1],
        cropped.shape[0],
    )

    with rasterio.open(
        output_file, "w",
        driver="GTiff",
        height=cropped.shape[0],
        width=cropped.shape[1],
        count=1,
        dtype=np.float32,
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(cropped, 1)

    print(f"[SRTM] Saved GeoTIFF: {output_file} ({cropped.shape})")
    print(f"[SRTM] Elevation range: {cropped.min():.0f}–{cropped.max():.0f}m")


def _create_flat_tif(output_file):
    """Create a flat terrain GeoTIFF as fallback."""
    try:
        import rasterio
        from rasterio.transform import from_bounds
    except ImportError:
        print("[SRTM] Cannot create GeoTIFF (rasterio missing). Using flat terrain.")
        return

    nrows, ncols = 100, 100
    data = np.full((nrows, ncols), 100.0, dtype=np.float32)

    transform = from_bounds(
        BBOX_WEST, BBOX_SOUTH, BBOX_EAST, BBOX_NORTH,
        ncols, nrows,
    )

    with rasterio.open(
        output_file, "w",
        driver="GTiff",
        height=nrows,
        width=ncols,
        count=1,
        dtype=np.float32,
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(data, 1)

    print(f"[SRTM] Created flat terrain fallback: {output_file}")


def main():
    print("=" * 60)
    print("Step 2: Download SRTM elevation data")
    print("=" * 60)

    tif_path = download_srtm()

    # Verify
    from utils.height_sampler import HeightSampler
    sampler = HeightSampler(tif_path)
    dom_h = sampler.sample(8.7544, 51.7189)
    print(f"\n[Verify] Dom elevation: {dom_h:.1f}m")
    print("Done!")


if __name__ == "__main__":
    main()
