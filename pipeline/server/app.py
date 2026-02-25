#!/usr/bin/env python3
"""Dynamic chunk streaming server for Open Drive.

Generates terrain/building/road chunks on demand from OSM + SRTM data.
Designed to enable unlimited driving in any direction.

Usage:
    python -m server.app [--host 0.0.0.0] [--port 8090] [--workers 4]
"""

import argparse
import sys
import os

# Ensure pipeline directory is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aiohttp import web
from aiohttp.web import middleware

from server.routes import setup_routes
from server.cache_manager import CacheManager
from server.data_fetcher import DataFetcher
from server.chunk_builder import ChunkBuilder
from server.generation_queue import GenerationQueue
from utils.height_sampler import get_multi_height_sampler
from config import PROJECT_ROOT


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8090
DEFAULT_WORKERS = 4
DEFAULT_CACHE_DIR = str(PROJECT_ROOT / "pipeline" / "server_cache")


@middleware
async def cors_middleware(request, handler):
    """Add CORS headers for Godot HTTP requests."""
    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@middleware
async def error_middleware(request, handler):
    """Catch unhandled errors and return JSON."""
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        return web.json_response(
            {"error": str(e)}, status=500
        )


async def on_startup(app):
    """Initialize server components."""
    print(f"[Server] Initializing...")
    print(f"[Server] Cache dir: {app['cache_dir']}")
    print(f"[Server] Workers: {app['num_workers']}")

    # Initialize components
    cache = CacheManager(app["cache_dir"])
    height_sampler = get_multi_height_sampler(
        os.path.join(app["cache_dir"], "srtm")
    )
    data_fetcher = DataFetcher(cache)
    chunk_builder = ChunkBuilder(data_fetcher, height_sampler)
    queue = GenerationQueue(chunk_builder, cache, app["num_workers"])

    app["cache"] = cache
    app["height_sampler"] = height_sampler
    app["data_fetcher"] = data_fetcher
    app["chunk_builder"] = chunk_builder
    app["queue"] = queue

    stats = cache.get_stats()
    print(f"[Server] Ready. Cached chunks on disk: {stats['disk_cached']}")


async def on_shutdown(app):
    """Clean up on shutdown."""
    if "queue" in app:
        app["queue"].shutdown()
    print("[Server] Shut down.")


def create_app(cache_dir=DEFAULT_CACHE_DIR, num_workers=DEFAULT_WORKERS):
    """Create and configure the aiohttp application."""
    app = web.Application(middlewares=[cors_middleware, error_middleware])

    app["cache_dir"] = cache_dir
    app["num_workers"] = num_workers

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    setup_routes(app)

    return app


def main():
    parser = argparse.ArgumentParser(description="Open Drive Chunk Server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help="Number of chunk generation workers")
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR,
                        help="Cache directory path")
    args = parser.parse_args()

    app = create_app(
        cache_dir=args.cache_dir,
        num_workers=args.workers,
    )

    print(f"[Server] Starting on {args.host}:{args.port}")
    print(f"[Server] API: http://{args.host}:{args.port}/api/v1/")

    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
