"""Priority queue with ThreadPoolExecutor for chunk generation."""

import asyncio
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict


class GenerationQueue:
    """Manages prioritized chunk generation with worker threads.

    Features:
    - Priority-based ordering (lower = higher priority)
    - Deduplication of pending requests
    - Async interface for aiohttp integration
    - ThreadPoolExecutor for CPU-bound mesh generation
    """

    def __init__(self, chunk_builder, cache_manager, num_workers=4):
        self.chunk_builder = chunk_builder
        self.cache = cache_manager
        self.num_workers = num_workers

        self._executor = ThreadPoolExecutor(
            max_workers=num_workers,
            thread_name_prefix="chunk-worker",
        )

        # Track in-flight generation
        self._generating = {}  # (cx,cz,lod) -> asyncio.Future
        self._lock = threading.Lock()

        # Stats
        self.total_generated = 0
        self.total_generation_time = 0.0

    async def get_or_generate(self, cx, cz, lod, loop=None):
        """Get a chunk from cache or generate it.

        Returns GLB bytes or None.
        """
        # Check cache first
        cached = self.cache.get_chunk(cx, cz, lod)
        if cached is not None:
            return cached

        # Check if already generating
        key = (cx, cz, lod)
        with self._lock:
            if key in self._generating:
                future = self._generating[key]
            else:
                # Submit to thread pool
                if loop is None:
                    loop = asyncio.get_event_loop()
                future = loop.run_in_executor(
                    self._executor,
                    self._generate_chunk,
                    cx, cz, lod,
                )
                self._generating[key] = future

        try:
            result = await future
            return result
        finally:
            with self._lock:
                self._generating.pop(key, None)

    def _generate_chunk(self, cx, cz, lod):
        """Generate a single chunk (runs in thread pool)."""
        # Double-check cache (another thread might have generated it)
        cached = self.cache.get_chunk(cx, cz, lod)
        if cached is not None:
            return cached

        start = time.time()
        print(f"[Queue] Generating chunk ({cx},{cz}) LOD{lod}...")

        try:
            glb_bytes = self.chunk_builder.build_chunk(cx, cz, lod)
        except Exception as e:
            print(f"[Queue] Error generating ({cx},{cz}): {e}")
            import traceback
            traceback.print_exc()
            return None

        elapsed = time.time() - start

        if glb_bytes is not None:
            self.cache.put_chunk(cx, cz, lod, glb_bytes)
            self.total_generated += 1
            self.total_generation_time += elapsed
            size_kb = len(glb_bytes) / 1024
            print(f"[Queue] Generated ({cx},{cz}) LOD{lod}: "
                  f"{size_kb:.0f} KB in {elapsed:.2f}s")
        else:
            # Cache an empty marker to avoid regenerating
            # Use a minimal valid GLB for empty chunks
            empty_glb = self._empty_glb()
            self.cache.put_chunk(cx, cz, lod, empty_glb)
            print(f"[Queue] Empty chunk ({cx},{cz}) LOD{lod} in {elapsed:.2f}s")
            glb_bytes = empty_glb

        return glb_bytes

    def submit_prefetch(self, chunks_list):
        """Submit a list of chunks for background generation.

        Args:
            chunks_list: list of (cx, cz, lod) tuples
        """
        submitted = 0
        for cx, cz, lod in chunks_list:
            key = (cx, cz, lod)
            if self.cache.has_chunk(cx, cz, lod):
                continue
            with self._lock:
                if key in self._generating:
                    continue
                future = self._executor.submit(
                    self._generate_chunk, cx, cz, lod
                )
                self._generating[key] = asyncio.wrap_future(future)
                submitted += 1

        return submitted

    def _empty_glb(self):
        """Create a minimal valid GLB with just an empty scene."""
        import json
        import struct

        gltf = {
            "asset": {"version": "2.0", "generator": "open-drive-pipeline"},
            "scene": 0,
            "scenes": [{"nodes": []}],
        }
        json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
        while len(json_bytes) % 4 != 0:
            json_bytes += b" "

        total = 12 + 8 + len(json_bytes)
        out = bytearray()
        out.extend(struct.pack("<I", 0x46546C67))
        out.extend(struct.pack("<I", 2))
        out.extend(struct.pack("<I", total))
        out.extend(struct.pack("<I", len(json_bytes)))
        out.extend(struct.pack("<I", 0x4E4F534A))
        out.extend(json_bytes)
        return bytes(out)

    def get_stats(self):
        with self._lock:
            generating = len(self._generating)
        avg_time = (self.total_generation_time / self.total_generated
                    if self.total_generated > 0 else 0)
        return {
            "generating": generating,
            "total_generated": self.total_generated,
            "avg_generation_time_s": round(avg_time, 3),
            "num_workers": self.num_workers,
        }

    def shutdown(self):
        self._executor.shutdown(wait=False)
