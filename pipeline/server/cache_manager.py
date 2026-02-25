"""Disk + in-memory cache for generated chunks and raw data."""

import hashlib
import time
import threading
from collections import OrderedDict
from pathlib import Path


class CacheManager:
    """Three-layer caching: in-memory LRU, disk GLB, disk raw data."""

    def __init__(self, cache_dir, memory_limit=200):
        self.cache_dir = Path(cache_dir)
        self.chunks_dir = self.cache_dir / "chunks"
        self.raw_dir = self.cache_dir / "raw"
        self.chunks_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        # In-memory LRU for GLB bytes
        self._memory_limit = memory_limit
        self._memory_cache = OrderedDict()  # key -> bytes
        self._lock = threading.Lock()

        # Stats
        self.hits_memory = 0
        self.hits_disk = 0
        self.misses = 0

    # === GLB Chunk Cache ===

    def _chunk_key(self, cx, cz, lod):
        return f"chunk_{cx}_{cz}_lod{lod}"

    def _chunk_path(self, cx, cz, lod):
        return self.chunks_dir / f"{self._chunk_key(cx, cz, lod)}.glb"

    def get_chunk(self, cx, cz, lod):
        """Get a cached chunk GLB.

        Returns bytes or None.
        """
        key = self._chunk_key(cx, cz, lod)

        # Check memory
        with self._lock:
            if key in self._memory_cache:
                self._memory_cache.move_to_end(key)
                self.hits_memory += 1
                return self._memory_cache[key]

        # Check disk
        path = self._chunk_path(cx, cz, lod)
        if path.exists():
            data = path.read_bytes()
            self._put_memory(key, data)
            self.hits_disk += 1
            return data

        self.misses += 1
        return None

    def put_chunk(self, cx, cz, lod, glb_bytes):
        """Store a chunk GLB in both disk and memory cache."""
        key = self._chunk_key(cx, cz, lod)

        # Disk
        path = self._chunk_path(cx, cz, lod)
        path.write_bytes(glb_bytes)

        # Memory
        self._put_memory(key, glb_bytes)

    def has_chunk(self, cx, cz, lod):
        """Check if chunk exists in any cache layer."""
        key = self._chunk_key(cx, cz, lod)
        with self._lock:
            if key in self._memory_cache:
                return True
        return self._chunk_path(cx, cz, lod).exists()

    def _put_memory(self, key, data):
        with self._lock:
            self._memory_cache[key] = data
            self._memory_cache.move_to_end(key)
            while len(self._memory_cache) > self._memory_limit:
                self._memory_cache.popitem(last=False)

    # === Raw Data Cache (Megatile OSM + SRTM) ===

    def get_raw(self, category, key):
        """Get cached raw data (pickle bytes).

        Args:
            category: e.g. "osm", "srtm"
            key: e.g. "mt_3_22"
        """
        path = self.raw_dir / category / f"{key}.pkl"
        if path.exists():
            return path.read_bytes()
        return None

    def put_raw(self, category, key, data_bytes):
        """Store raw data."""
        cat_dir = self.raw_dir / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        path = cat_dir / f"{key}.pkl"
        path.write_bytes(data_bytes)

    def has_raw(self, category, key):
        path = self.raw_dir / category / f"{key}.pkl"
        return path.exists()

    # === Stats ===

    def get_stats(self):
        with self._lock:
            memory_count = len(self._memory_cache)
        disk_count = len(list(self.chunks_dir.glob("*.glb")))
        return {
            "memory_cached": memory_count,
            "disk_cached": disk_count,
            "hits_memory": self.hits_memory,
            "hits_disk": self.hits_disk,
            "misses": self.misses,
        }
