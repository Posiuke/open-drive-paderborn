"""REST API route handlers for the chunk server."""

import json
import math
from aiohttp import web


def setup_routes(app):
    """Register all API routes."""
    app.router.add_get("/api/v1/chunk/{cx}/{cz}/{lod}", handle_get_chunk)
    app.router.add_post("/api/v1/chunks/batch", handle_batch_chunks)
    app.router.add_post("/api/v1/prefetch", handle_prefetch)
    app.router.add_get("/api/v1/status", handle_status)
    app.router.add_get("/api/v1/health", handle_health)


async def handle_get_chunk(request):
    """GET /api/v1/chunk/{cx}/{cz}/{lod}

    Returns the GLB binary for a chunk, generating it if needed.

    Query params:
        origin_e, origin_n: optional UTM origin for coordinate rebasing
    """
    try:
        cx = int(request.match_info["cx"])
        cz = int(request.match_info["cz"])
        lod = int(request.match_info["lod"])
    except (ValueError, KeyError):
        return web.json_response(
            {"error": "Invalid chunk coordinates"}, status=400
        )

    if lod not in (0, 1):
        return web.json_response(
            {"error": "LOD must be 0 or 1"}, status=400
        )

    queue = request.app["queue"]

    try:
        glb_bytes = await queue.get_or_generate(cx, cz, lod)
    except Exception as e:
        return web.json_response(
            {"error": f"Generation failed: {str(e)}"}, status=500
        )

    if glb_bytes is None:
        return web.json_response(
            {"error": "Chunk generation failed"}, status=500
        )

    return web.Response(
        body=glb_bytes,
        content_type="model/gltf-binary",
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Chunk-Coords": f"{cx},{cz}",
            "X-Chunk-LOD": str(lod),
        },
    )


async def handle_batch_chunks(request):
    """POST /api/v1/chunks/batch

    Check status of multiple chunks at once.

    Body: {
        "chunks": [{"cx": 0, "cz": 0, "lod": 0}, ...],
    }

    Returns: {
        "ready": [{"cx": 0, "cz": 0, "lod": 0}, ...],
        "pending": [{"cx": 1, "cz": 1, "lod": 0}, ...],
    }
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    chunks = body.get("chunks", [])
    cache = request.app["cache"]

    ready = []
    pending = []

    for c in chunks:
        cx = c.get("cx", 0)
        cz = c.get("cz", 0)
        lod = c.get("lod", 0)
        if cache.has_chunk(cx, cz, lod):
            ready.append({"cx": cx, "cz": cz, "lod": lod})
        else:
            pending.append({"cx": cx, "cz": cz, "lod": lod})

    return web.json_response({"ready": ready, "pending": pending})


async def handle_prefetch(request):
    """POST /api/v1/prefetch

    Submit chunks for background generation based on player movement.

    Body: {
        "player_cx": 0,
        "player_cz": 0,
        "heading_deg": 45.0,  // 0=north, 90=east
        "speed_kmh": 100.0,
        "load_radius_lod0": 2,
        "load_radius_lod1": 4,
    }
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    pcx = body.get("player_cx", 0)
    pcz = body.get("player_cz", 0)
    heading = body.get("heading_deg", 0.0)
    speed = body.get("speed_kmh", 0.0)
    r0 = body.get("load_radius_lod0", 2)
    r1 = body.get("load_radius_lod1", 4)

    # Build prefetch list: standard grid + direction corridor
    chunks_to_prefetch = []

    # Standard LOD grid
    for dx in range(-r1, r1 + 1):
        for dz in range(-r1, r1 + 1):
            dist = max(abs(dx), abs(dz))
            lod = 0 if dist <= r0 else 1
            chunks_to_prefetch.append((pcx + dx, pcz + dz, lod))

    # Direction-based corridor (look-ahead based on speed)
    if speed > 10.0:
        # How many chunks ahead to look (at current speed)
        look_ahead = max(3, int(speed / 40.0))  # ~3 at 40 km/h, ~8 at 130 km/h
        heading_rad = math.radians(heading)
        # heading: 0=north(+z), 90=east(+x)
        dx_dir = math.sin(heading_rad)
        dz_dir = math.cos(heading_rad)

        for dist in range(1, look_ahead + 1):
            center_cx = pcx + round(dx_dir * dist)
            center_cz = pcz + round(dz_dir * dist)
            # 3-wide corridor
            perp_x = -dz_dir
            perp_z = dx_dir
            for w in range(-1, 2):
                fx = center_cx + round(perp_x * w)
                fz = center_cz + round(perp_z * w)
                chunks_to_prefetch.append((fx, fz, 0))

    # Deduplicate
    chunks_to_prefetch = list(set(chunks_to_prefetch))

    queue = request.app["queue"]
    submitted = queue.submit_prefetch(chunks_to_prefetch)

    return web.json_response({
        "submitted": submitted,
        "total_requested": len(chunks_to_prefetch),
    })


async def handle_status(request):
    """GET /api/v1/status

    Returns server status and statistics.
    """
    cache = request.app["cache"]
    queue = request.app["queue"]

    cache_stats = cache.get_stats()
    queue_stats = queue.get_stats()

    return web.json_response({
        "status": "running",
        "cache": cache_stats,
        "queue": queue_stats,
    })


async def handle_health(request):
    """GET /api/v1/health - Simple health check."""
    return web.json_response({"status": "ok"})
