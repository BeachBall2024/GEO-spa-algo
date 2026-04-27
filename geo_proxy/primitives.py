import math
from typing import List

class Point:
    def __init__(self, x: float, y: float):
        self.x = x  # longitude
        self.y = y  # latitude

    def __eq__(self, other) -> bool:
        if not isinstance(other, Point):
            return False
        return self.x == other.x and self.y == other.y

    def haversine_distance_to(self, other_point: 'Point') -> float:
        R = 6371000  # radius of Earth in meters
        phi_1 = math.radians(self.y)
        phi_2 = math.radians(other_point.y)
        delta_phi = math.radians(other_point.y - self.y)
        delta_lambda = math.radians(other_point.x - self.x)

        a = math.sin(delta_phi / 2.0) ** 2 + \
            math.cos(phi_1) * math.cos(phi_2) * \
            math.sin(delta_lambda / 2.0) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

class BoundingBox:
    def __init__(self, min_x: float, max_x: float, min_y: float, max_y: float):
        self.min_x = min_x
        self.max_x = max_x
        self.min_y = min_y
        self.max_y = max_y

    def contains_point(self, point: Point) -> bool:
        return (self.min_x <= point.x <= self.max_x) and \
               (self.min_y <= point.y <= self.max_y)

    def intersects_bbox(self, other: 'BoundingBox') -> bool:
        return not (self.max_x < other.min_x or \
                    self.min_x > other.max_x or \
                    self.max_y < other.min_y or \
                    self.min_y > other.max_y)

class Segment:
    def __init__(self, p1: Point, p2: Point):
        self.p1 = p1
        self.p2 = p2
        self.bbox = BoundingBox(
            min(p1.x, p2.x), max(p1.x, p2.x),
            min(p1.y, p2.y), max(p1.y, p2.y)
        )

    def length(self) -> float:
        return self.p1.haversine_distance_to(self.p2)

    def turn_test(self, p: Point) -> int:
        # Cross product of vectors (p2 - p1) and (p - p1)
        val = (self.p2.x - self.p1.x) * (p.y - self.p1.y) - \
              (self.p2.y - self.p1.y) * (p.x - self.p1.x)
        if val > 0:
            return 1  # left turn
        elif val < 0:
            return -1 # right turn
        else:
            return 0  # collinear

class Polygon:
    def __init__(self, vertices: List[Point]):
        self.vertices = vertices
        self.segments = [Segment(vertices[i], vertices[(i + 1) % len(vertices)]) for i in range(len(vertices))]
        
        min_x = min(v.x for v in vertices)
        max_x = max(v.x for v in vertices)
        min_y = min(v.y for v in vertices)
        max_y = max(v.y for v in vertices)
        self.bbox = BoundingBox(min_x, max_x, min_y, max_y)

    def calculate_centroid(self) -> Point:
        """Area-weighted centroid using the Shoelace-derived formula (Lecture 2).

        Cx = (1 / 6A) * Σ (xi + xi+1)(xi * yi+1 - xi+1 * yi)
        Cy = (1 / 6A) * Σ (yi + yi+1)(xi * yi+1 - xi+1 * yi)

        Complexity: O(n) where n = number of vertices.
        """
        n = len(self.vertices)
        signed_area = 0.0
        cx = 0.0
        cy = 0.0
        for i in range(n):
            j = (i + 1) % n
            cross = (self.vertices[i].x * self.vertices[j].y
                     - self.vertices[j].x * self.vertices[i].y)
            signed_area += cross
            cx += (self.vertices[i].x + self.vertices[j].x) * cross
            cy += (self.vertices[i].y + self.vertices[j].y) * cross
        signed_area *= 0.5
        if abs(signed_area) < 1e-18:
            # Fallback to simple mean if area is zero (degenerate polygon)
            return Point(sum(v.x for v in self.vertices) / n, sum(v.y for v in self.vertices) / n)
        cx /= (6.0 * signed_area)
        cy /= (6.0 * signed_area)
        return Point(cx, cy)

    def calculate_area(self) -> float:
        # Shoelace formula for area (returns area in square degrees, needs projection for accurate m^2)
        n = len(self.vertices)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += self.vertices[i].x * self.vertices[j].y
            area -= self.vertices[j].x * self.vertices[i].y
        return abs(area) / 2.0
