"""Pure-Python shapefile parser for Polyline (type 3) shapefiles.

Reads .shp files without any external GIS dependencies (no geopandas,
no fiona, no pyshp).  Uses only the Python standard library (struct).

References:
    ESRI Shapefile Technical Description (1998), July 1998.
    https://www.esri.com/library/whitepapers/pdfs/shapefile.pdf

Only supports shape type 3 (PolyLine) which is what we need for street
network data from swisstopo.
"""

import struct
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
Coord = Tuple[float, float]          # (x, y) in file CRS
Polyline = List[List[Coord]]         # list of parts, each part a list of coords


def read_shp(path: str) -> List[Polyline]:
    """Read all polyline geometries from a .shp file.

    Parameters
    ----------
    path : str
        Path to the .shp file (shape type must be 3 = PolyLine).

    Returns
    -------
    List[Polyline]
        Each element is a polyline: a list of parts, where each part
        is a list of (x, y) coordinate tuples.

    Raises
    ------
    ValueError
        If the shape type is not 3 (PolyLine).
    """
    polylines: List[Polyline] = []

    with open(path, 'rb') as f:
        # --- File header (100 bytes) ---
        magic = struct.unpack('>i', f.read(4))[0]
        if magic != 9994:
            raise ValueError(f"Not a valid shapefile (magic = {magic})")

        f.seek(24)
        file_length = struct.unpack('>i', f.read(4))[0] * 2  # in bytes
        _version = struct.unpack('<i', f.read(4))[0]
        shape_type = struct.unpack('<i', f.read(4))[0]

        if shape_type != 3:
            raise ValueError(
                f"Expected PolyLine (type 3), got type {shape_type}")

        # Skip rest of header (bounding box etc.)
        f.seek(100)

        # --- Record reading ---
        while f.tell() < file_length:
            # Record header: 8 bytes
            header_data = f.read(8)
            if len(header_data) < 8:
                break

            _record_number = struct.unpack('>i', header_data[0:4])[0]
            content_length = struct.unpack('>i', header_data[4:8])[0] * 2

            # Record content
            record_data = f.read(content_length)
            if len(record_data) < content_length:
                break

            offset = 0
            rec_shape_type = struct.unpack_from('<i', record_data, offset)[0]
            offset += 4

            if rec_shape_type == 0:
                # Null shape – skip
                continue

            if rec_shape_type != 3:
                # Unexpected shape type in record – skip
                continue

            # Bounding box: 4 doubles (xmin, ymin, xmax, ymax) = 32 bytes
            offset += 32

            num_parts = struct.unpack_from('<i', record_data, offset)[0]
            offset += 4
            num_points = struct.unpack_from('<i', record_data, offset)[0]
            offset += 4

            # Part indices
            parts = []
            for _ in range(num_parts):
                idx = struct.unpack_from('<i', record_data, offset)[0]
                parts.append(idx)
                offset += 4

            # Points
            points = []
            for _ in range(num_points):
                x = struct.unpack_from('<d', record_data, offset)[0]
                offset += 8
                y = struct.unpack_from('<d', record_data, offset)[0]
                offset += 8
                points.append((x, y))

            # Split points into parts
            polyline: Polyline = []
            for i in range(num_parts):
                start = parts[i]
                end = parts[i + 1] if i + 1 < num_parts else num_points
                polyline.append(points[start:end])

            polylines.append(polyline)

    return polylines


def count_records(path: str) -> int:
    """Count the number of records in a .shp file without loading all data."""
    count = 0
    with open(path, 'rb') as f:
        f.seek(24)
        file_length = struct.unpack('>i', f.read(4))[0] * 2
        f.seek(100)
        while f.tell() < file_length:
            header_data = f.read(8)
            if len(header_data) < 8:
                break
            content_length = struct.unpack('>i', header_data[4:8])[0] * 2
            f.seek(content_length, 1)  # skip content
            count += 1
    return count
