from __future__ import annotations

import csv
import hashlib
import heapq
import itertools
import json
from pathlib import Path
from typing import Any


def _source_files(source_dir: Path) -> tuple[Path, Path]:
    node_path = source_dir / "MOCT_NODE"
    link_path = source_dir / "MOCT_LINK"
    if not (node_path.with_suffix(".shp").exists() and link_path.with_suffix(".shp").exists()):
        raise FileNotFoundError(f"standard node-link shapefiles not found under {source_dir}")
    return node_path, link_path


def _shortest_path(
    adjacency: dict[str, list[tuple[float, str, dict[str, Any]]]],
    start: str,
    end: str,
) -> tuple[float, list[dict[str, Any]]] | None:
    serial = itertools.count()
    queue: list[tuple[float, int, str, list[dict[str, Any]]]] = [
        (0.0, next(serial), start, [])
    ]
    best: dict[str, float] = {}
    while queue:
        distance, _, node, path = heapq.heappop(queue)
        if distance >= best.get(node, float("inf")):
            continue
        best[node] = distance
        if node == end:
            return distance, path
        for length, target, link in adjacency.get(node, []):
            heapq.heappush(
                queue,
                (distance + length, next(serial), target, path + [link]),
            )
    return None


def build_corridor_evidence(
    *,
    source_dir: Path,
    event_id: str,
    start_name: str,
    end_name: str,
    bbox: tuple[float, float, float, float],
    source_version: str,
    source_sha256: str,
) -> dict[str, Any]:
    try:
        import shapefile
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install geographic support: python -m pip install -e .[geo]") from exc
    node_path, link_path = _source_files(source_dir)
    xmin, ymin, xmax, ymax = bbox
    nodes: dict[str, dict[str, Any]] = {}
    node_reader = shapefile.Reader(str(node_path), encoding="cp949")
    try:
        for shape_record in node_reader.iterShapeRecords():
            x, y = shape_record.shape.points[0]
            if xmin <= x <= xmax and ymin <= y <= ymax:
                record = shape_record.record.as_dict()
                nodes[str(record["NODE_ID"])] = {
                    "node_id": str(record["NODE_ID"]),
                    "node_name": str(record["NODE_NAME"] or ""),
                    "x": float(x),
                    "y": float(y),
                }
    finally:
        node_reader.close()
    starts = [node for node in nodes.values() if node["node_name"] == start_name]
    ends = [node for node in nodes.values() if node["node_name"] == end_name]
    if not starts or not ends:
        raise ValueError(f"corridor endpoints not found: {start_name}, {end_name}")

    adjacency: dict[str, list[tuple[float, str, dict[str, Any]]]] = {
        node_id: [] for node_id in nodes
    }
    link_reader = shapefile.Reader(str(link_path), encoding="cp949")
    try:
        for record in link_reader.iterRecords():
            values = record.as_dict()
            from_node = str(values["F_NODE"])
            to_node = str(values["T_NODE"])
            if from_node not in nodes or to_node not in nodes:
                continue
            link = {
                "link_id": str(values["LINK_ID"]),
                "from_node_id": from_node,
                "to_node_id": to_node,
                "road_name": str(values["ROAD_NAME"] or ""),
                "lanes": int(values["LANES"] or 0),
                "max_speed_kmh": int(values["MAX_SPD"] or 0),
                "length_m": float(values["LENGTH"] or 0),
            }
            adjacency[from_node].append((link["length_m"], to_node, link))
    finally:
        link_reader.close()

    best_pair: tuple[float, dict[str, Any], dict[str, Any], list[dict[str, Any]]] | None = None
    for start in starts:
        for end in ends:
            path = _shortest_path(adjacency, start["node_id"], end["node_id"])
            if path is None:
                continue
            distance, links = path
            candidate = (distance, start, end, links)
            if best_pair is None or distance < best_pair[0]:
                best_pair = candidate
    if best_pair is None:
        raise ValueError("no directed path found between corridor endpoints")
    forward_distance, start, end, forward_links = best_pair
    reverse = _shortest_path(adjacency, end["node_id"], start["node_id"])
    if reverse is None:
        raise ValueError("no reverse directed path found between corridor endpoints")
    reverse_distance, reverse_links = reverse

    evidence = []
    for direction, links in (("forward", forward_links), ("reverse", reverse_links)):
        for sequence, link in enumerate(links, start=1):
            evidence.append(
                {
                    "event_id": event_id,
                    "direction": direction,
                    "sequence": sequence,
                    **link,
                    "from_node_name": nodes[link["from_node_id"]]["node_name"],
                    "to_node_name": nodes[link["to_node_id"]]["node_name"],
                    "source_version": source_version,
                    "source_sha256": source_sha256,
                    "derivation": "directed_shortest_path_by_official_link_length",
                }
            )
    return {
        "event_id": event_id,
        "start": start,
        "end": end,
        "forward_distance_m": round(forward_distance, 3),
        "reverse_distance_m": round(reverse_distance, 3),
        "forward_link_count": len(forward_links),
        "reverse_link_count": len(reverse_links),
        "road_names": sorted({row["road_name"] for row in evidence}),
        "evidence": evidence,
        "source_version": source_version,
        "source_sha256": source_sha256,
        "crs": "ITRF2000_Central_Belt_60 (EPSG:5186)",
    }


def write_corridor_evidence(report: dict[str, Any], csv_path: Path, json_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    rows = report["evidence"]
    fields = list(rows[0]) if rows else []
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
