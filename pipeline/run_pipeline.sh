#!/bin/bash
# Run the complete data pipeline for Open Drive Paderborn
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  Open Drive Paderborn - Data Pipeline"
echo "=========================================="
echo ""

# Activate venv if it exists
if [ -d "../venv" ]; then
    source ../venv/bin/activate
    echo "Using venv: $(which python)"
fi

echo ""
echo "[1/7] Downloading OSM data..."
python 01_download_osm.py

echo ""
echo "[2/7] Downloading terrain data..."
python 02_download_terrain.py

echo ""
echo "[3/7] Processing roads..."
python 03_process_roads.py

echo ""
echo "[4/7] Processing buildings..."
python 04_process_buildings.py

echo ""
echo "[5/7] Processing terrain..."
python 05_process_terrain.py

echo ""
echo "[6/7] Processing landuse..."
python 06_process_landuse.py

echo ""
echo "[7/7] Chunking and exporting..."
python 07_chunk_and_export.py

echo ""
echo "=========================================="
echo "  Pipeline complete!"
echo "  Chunks exported to: ../data/export/chunks/"
echo "  Copied to Godot:    ../godot/assets/chunks/"
echo "=========================================="
