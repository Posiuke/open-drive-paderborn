"""Mesh generation utilities for roads, buildings, and terrain."""

import numpy as np
from typing import Optional


class MeshData:
    """Container for mesh vertex/index data."""

    def __init__(self):
        self.vertices = []    # [(x, y, z), ...]
        self.normals = []     # [(nx, ny, nz), ...]
        self.uvs = []         # [(u, v), ...]
        self.indices = []     # [i0, i1, i2, ...]
        self.colors = []      # [(r, g, b), ...] optional vertex colors

    def add_vertex(self, pos, normal=(0, 1, 0), uv=(0, 0), color=None):
        idx = len(self.vertices)
        self.vertices.append(tuple(pos))
        self.normals.append(tuple(normal))
        self.uvs.append(tuple(uv))
        if color is not None:
            self.colors.append(tuple(color))
        return idx

    def add_triangle(self, i0, i1, i2):
        self.indices.extend([i0, i1, i2])

    def add_quad(self, i0, i1, i2, i3):
        """Add a quad as two triangles (CCW winding)."""
        self.indices.extend([i0, i1, i2, i0, i2, i3])

    def vertex_count(self):
        return len(self.vertices)

    def triangle_count(self):
        return len(self.indices) // 3

    def to_numpy(self):
        """Return numpy arrays for export."""
        return {
            "vertices": np.array(self.vertices, dtype=np.float32),
            "normals": np.array(self.normals, dtype=np.float32) if self.normals else None,
            "uvs": np.array(self.uvs, dtype=np.float32) if self.uvs else None,
            "indices": np.array(self.indices, dtype=np.uint32),
            "colors": np.array(self.colors, dtype=np.float32) if self.colors else None,
        }

    def merge(self, other):
        """Merge another MeshData into this one."""
        offset = len(self.vertices)
        self.vertices.extend(other.vertices)
        self.normals.extend(other.normals)
        self.uvs.extend(other.uvs)
        self.indices.extend([i + offset for i in other.indices])
        if other.colors:
            # Pad our colors if we didn't have them
            while len(self.colors) < offset:
                self.colors.append((0.5, 0.5, 0.5))
            self.colors.extend(other.colors)

    def is_empty(self):
        return len(self.vertices) == 0


def build_road_mesh(points_xz, width, height_func=None, color=(0.3, 0.3, 0.3)):
    """Build a road strip mesh from a polyline.

    Args:
        points_xz: list of (x, z) local coordinates along the road centerline
        width: total road width in meters
        height_func: callable(x, z) → y elevation, or None for flat
        color: RGB tuple for vertex color

    Returns:
        MeshData
    """
    mesh = MeshData()
    pts = np.array(points_xz, dtype=np.float64)

    if len(pts) < 2:
        return mesh

    half_w = width / 2.0
    cumulative_dist = 0.0

    for i in range(len(pts)):
        # Compute tangent direction
        if i == 0:
            tangent = pts[1] - pts[0]
        elif i == len(pts) - 1:
            tangent = pts[-1] - pts[-2]
        else:
            tangent = pts[i + 1] - pts[i - 1]

        length = np.linalg.norm(tangent)
        if length < 1e-6:
            tangent = np.array([1.0, 0.0])
        else:
            tangent /= length

        # Perpendicular (right side)
        perp = np.array([-tangent[1], tangent[0]])

        # Left and right positions
        left = pts[i] - perp * half_w
        right = pts[i] + perp * half_w

        # Height
        y_left = height_func(left[0], left[1]) if height_func else 0.0
        y_right = height_func(right[0], right[1]) if height_func else 0.0

        # Raise road slightly above terrain
        y_left += 0.05
        y_right += 0.05

        # UV: u across width, v along length
        if i > 0:
            cumulative_dist += np.linalg.norm(pts[i] - pts[i - 1])

        v = cumulative_dist / width  # Scale v so texture isn't stretched

        # In Godot: Y is up, X is right, Z is forward/north
        # Our local: x=east, z=north, y=up
        mesh.add_vertex(
            pos=(left[0], y_left, left[1]),
            normal=(0, 1, 0),
            uv=(0, v),
            color=color,
        )
        mesh.add_vertex(
            pos=(right[0], y_right, right[1]),
            normal=(0, 1, 0),
            uv=(1, v),
            color=color,
        )

    # Create triangles
    for i in range(len(pts) - 1):
        bl = i * 2
        br = i * 2 + 1
        tl = (i + 1) * 2
        tr = (i + 1) * 2 + 1
        mesh.add_quad(bl, br, tr, tl)

    return mesh


def build_building_mesh(footprint_xz, height, base_height=0.0,
                        color=(0.7, 0.65, 0.6)):
    """Build an extruded building mesh from a polygon footprint.

    Args:
        footprint_xz: list of (x, z) local coords (closed polygon, CCW)
        height: building height in meters
        base_height: ground elevation
        color: RGB tuple

    Returns:
        MeshData
    """
    mesh = MeshData()
    pts = np.array(footprint_xz, dtype=np.float64)

    if len(pts) < 3:
        return mesh

    # Ensure the polygon is closed (remove closing vertex if duplicate)
    if np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]

    if len(pts) < 3:
        return mesh

    n = len(pts)
    top_y = base_height + height

    # === Walls ===
    for i in range(n):
        j = (i + 1) % n

        x0, z0 = pts[i]
        x1, z1 = pts[j]

        # Wall normal (outward)
        dx = x1 - x0
        dz = z1 - z0
        wall_len = np.sqrt(dx * dx + dz * dz)
        if wall_len < 1e-6:
            continue

        nx = dz / wall_len
        nz = -dx / wall_len
        normal = (nx, 0, nz)

        # UV: u = along wall, v = height
        u0 = 0.0
        u1 = wall_len / 3.0  # Repeat texture every 3m

        v_top = height / 3.0

        # Four vertices per wall face
        bl = mesh.add_vertex((x0, base_height, z0), normal, (u0, 0), color)
        br = mesh.add_vertex((x1, base_height, z1), normal, (u1, 0), color)
        tr = mesh.add_vertex((x1, top_y, z1), normal, (u1, v_top), color)
        tl = mesh.add_vertex((x0, top_y, z0), normal, (u0, v_top), color)

        mesh.add_quad(bl, br, tr, tl)

    # === Roof (flat, simple triangulation using ear clipping or fan) ===
    # Simple fan triangulation from first vertex (works for convex polygons)
    # For concave polygons we'd need proper ear clipping, but this is OK for most buildings
    roof_start = mesh.vertex_count()
    for i in range(n):
        x, z = pts[i]
        mesh.add_vertex(
            (x, top_y, z),
            normal=(0, 1, 0),
            uv=(x / 10.0, z / 10.0),  # World-space UV
            color=color,
        )

    # Fan triangulation
    for i in range(1, n - 1):
        mesh.add_triangle(roof_start, roof_start + i, roof_start + i + 1)

    return mesh


def build_terrain_mesh(min_x, max_x, min_z, max_z, resolution,
                       height_func=None, color=(0.3, 0.5, 0.2)):
    """Build a terrain grid mesh.

    Args:
        min_x, max_x, min_z, max_z: bounds in local coordinates
        resolution: spacing between vertices in meters
        height_func: callable(x, z) → y, or None for flat
        color: RGB tuple

    Returns:
        MeshData
    """
    mesh = MeshData()

    nx = max(2, int((max_x - min_x) / resolution) + 1)
    nz = max(2, int((max_z - min_z) / resolution) + 1)

    xs = np.linspace(min_x, max_x, nx)
    zs = np.linspace(min_z, max_z, nz)

    # Create vertices
    for iz in range(nz):
        for ix in range(nx):
            x = xs[ix]
            z = zs[iz]
            y = height_func(x, z) if height_func else 0.0

            u = (x - min_x) / (max_x - min_x)
            v = (z - min_z) / (max_z - min_z)

            mesh.add_vertex(
                pos=(x, y, z),
                normal=(0, 1, 0),
                uv=(u, v),
                color=color,
            )

    # Create triangles
    for iz in range(nz - 1):
        for ix in range(nx - 1):
            bl = iz * nx + ix
            br = bl + 1
            tl = bl + nx
            tr = tl + 1
            mesh.add_quad(bl, br, tr, tl)

    # Compute normals from triangles
    _recompute_normals(mesh)

    return mesh


def build_landuse_mesh(polygon_xz, height_func=None, color=(0.3, 0.5, 0.2)):
    """Build a flat mesh for a landuse polygon.

    Args:
        polygon_xz: list of (x, z) coords
        height_func: callable(x, z) → y
        color: RGB tuple

    Returns:
        MeshData
    """
    mesh = MeshData()
    pts = np.array(polygon_xz, dtype=np.float64)

    if len(pts) < 3:
        return mesh

    if np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]

    if len(pts) < 3:
        return mesh

    n = len(pts)

    for i in range(n):
        x, z = pts[i]
        y = height_func(x, z) if height_func else 0.0
        y -= 0.02  # Slightly below road level

        mesh.add_vertex(
            pos=(x, y, z),
            normal=(0, 1, 0),
            uv=(x / 50.0, z / 50.0),
            color=color,
        )

    # Fan triangulation
    for i in range(1, n - 1):
        mesh.add_triangle(0, i, i + 1)

    return mesh


def build_water_mesh(polygon_xz, water_height=None, height_func=None):
    """Build a water surface mesh."""
    if water_height is None:
        # Sample center height
        pts = np.array(polygon_xz)
        cx, cz = pts.mean(axis=0)
        water_height = height_func(cx, cz) if height_func else 0.0
        water_height -= 0.5  # Water slightly below terrain

    return build_landuse_mesh(
        polygon_xz,
        height_func=lambda x, z: water_height,
        color=(0.2, 0.4, 0.7),
    )


def _recompute_normals(mesh):
    """Recompute vertex normals from face normals (smooth shading)."""
    verts = np.array(mesh.vertices, dtype=np.float64)
    indices = np.array(mesh.indices, dtype=np.int32)
    normals = np.zeros_like(verts)

    for i in range(0, len(indices), 3):
        i0, i1, i2 = indices[i], indices[i + 1], indices[i + 2]
        v0, v1, v2 = verts[i0], verts[i1], verts[i2]
        e1 = v1 - v0
        e2 = v2 - v0
        n = np.cross(e1, e2)
        normals[i0] += n
        normals[i1] += n
        normals[i2] += n

    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths = np.where(lengths < 1e-10, 1.0, lengths)
    normals /= lengths

    mesh.normals = [tuple(n) for n in normals]


def simplify_polygon(points, tolerance=2.0):
    """Simplify a polygon using Ramer-Douglas-Peucker (for LOD1)."""
    from shapely.geometry import Polygon
    poly = Polygon(points)
    simplified = poly.simplify(tolerance, preserve_topology=True)
    return list(simplified.exterior.coords)
