"""Named swatch polygons in native DAT sensor coordinates."""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import cv2
import numpy as np


def load_layout(path, width, height):
    layout = json.loads(Path(path).read_text())
    if (layout["width"], layout["height"]) != (width, height):
        raise ValueError(f"ROI layout {path} does not match the {width} x {height} sensor.")
    polygons = {}
    labels = {}
    for name, region in layout["rois"].items():
        points = np.asarray(region["points"])
        if (points.ndim != 2 or points.shape[1] != 2 or len(points) < 3
                or not np.issubdtype(points.dtype, np.integer)
                or np.any(points < 0) or np.any(points >= [width, height])):
            raise ValueError(f"Invalid polygon for {name} in {path}.")
        points = points.astype(np.int32)
        if not cv2.contourArea(points):
            raise ValueError(f"Empty polygon for {name} in {path}.")
        polygons[name] = points
        labels[name] = region["swatch"]
    if not polygons:
        raise ValueError(f"Empty ROI layout in {path}.")
    return polygons, labels


def save_layout(path, batch, source, width, height, polygons, labels):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    layout = dict(batch=batch, source=source, width=width, height=height, rois={
        name: dict(swatch=labels[name], points=points.tolist()) for name, points in polygons.items()
    })
    # A cancelled or failed draw must leave any previously saved layout intact.
    with NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as stream:
        temporary = Path(stream.name)
        try:
            json.dump(layout, stream, indent=2)
            stream.write("\n")
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
