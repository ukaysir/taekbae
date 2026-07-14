from __future__ import annotations

import csv
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from taekbae.config import KST


STORE_REQUIRED_FIELDS = {
    "상가업소번호",
    "시도명",
    "경도",
    "위도",
}
GEOMETRY_REQUIRED_FIELDS = {
    "event_id",
    "geometry_type",
    "reference_ids",
    "buffer_m",
    "source_dataset",
    "source_version",
    "source_sha256",
    "confidence",
    "derivation",
    "checked_at_kst",
}
MAPPING_REQUIRED_FIELDS = {
    "event_id",
    "segment_id",
    "segment_label",
    "confidence",
    "decision",
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _require_fields(path: Path, actual: Iterable[str], required: set[str]) -> None:
    missing = sorted(required - set(actual))
    if missing:
        raise ValueError(f"{path.name} missing required fields: {', '.join(missing)}")


def _shape_parts(shape: Any) -> list[list[tuple[float, float]]]:
    starts = list(shape.parts) + [len(shape.points)]
    result = []
    for index in range(len(starts) - 1):
        points = [
            (float(x), float(y))
            for x, y in shape.points[starts[index] : starts[index + 1]]
        ]
        if points:
            result.append(points)
    return result


def _point_segment_distance_squared(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    px, py = point
    ax, ay = start
    bx, by = end
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return (px - ax) ** 2 + (py - ay) ** 2
    position = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    position = max(0.0, min(1.0, position))
    closest_x = ax + position * dx
    closest_y = ay + position * dy
    return (px - closest_x) ** 2 + (py - closest_y) ** 2


def _distance_squared(
    point: tuple[float, float],
    *,
    geometry_type: str,
    parts: list[list[tuple[float, float]]],
) -> float:
    if geometry_type == "node":
        target = parts[0][0]
        return (point[0] - target[0]) ** 2 + (point[1] - target[1]) ** 2
    distances = []
    for part in parts:
        if len(part) == 1:
            distances.append(
                (point[0] - part[0][0]) ** 2 + (point[1] - part[0][1]) ** 2
            )
            continue
        distances.extend(
            _point_segment_distance_squared(point, start, end)
            for start, end in zip(part, part[1:])
        )
    if not distances:
        raise ValueError("empty exposure geometry")
    return min(distances)


def _load_geometry_specs(path: Path) -> list[dict[str, Any]]:
    rows = _read_csv(path)
    if not rows:
        raise ValueError("exposure geometry CSV has no rows")
    _require_fields(path, rows[0], GEOMETRY_REQUIRED_FIELDS)
    event_ids: set[str] = set()
    result = []
    for index, row in enumerate(rows, start=2):
        event_id = row["event_id"].strip()
        geometry_type = row["geometry_type"].strip()
        reference_ids = [value.strip() for value in row["reference_ids"].split("|") if value.strip()]
        if not event_id or event_id in event_ids:
            raise ValueError(f"invalid or duplicate event_id at geometry row {index}")
        if geometry_type not in {"link_path", "node"}:
            raise ValueError(f"unsupported geometry_type at row {index}: {geometry_type}")
        if not reference_ids or (geometry_type == "node" and len(reference_ids) != 1):
            raise ValueError(f"invalid reference_ids at geometry row {index}")
        try:
            buffer_m = float(row["buffer_m"])
        except ValueError as exc:
            raise ValueError(f"invalid buffer_m at geometry row {index}") from exc
        if not 0 < buffer_m <= 2_000:
            raise ValueError(f"buffer_m outside allowed range at geometry row {index}")
        event_ids.add(event_id)
        result.append(
            {
                **row,
                "event_id": event_id,
                "geometry_type": geometry_type,
                "reference_ids": reference_ids,
                "buffer_m": buffer_m,
            }
        )
    return result


def _load_reference_geometries(
    source_dir: Path, specs: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    try:
        import shapefile
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install geographic support: python -m pip install -e .[geo]") from exc

    needed_links = {
        reference
        for spec in specs
        if spec["geometry_type"] == "link_path"
        for reference in spec["reference_ids"]
    }
    needed_nodes = {
        spec["reference_ids"][0]
        for spec in specs
        if spec["geometry_type"] == "node"
    }
    found_links: dict[str, list[list[tuple[float, float]]]] = {}
    found_nodes: dict[str, tuple[float, float]] = {}

    if needed_links:
        link_reader = shapefile.Reader(str(source_dir / "MOCT_LINK"), encoding="cp949")
        try:
            for shape_record in link_reader.iterShapeRecords():
                record = shape_record.record.as_dict()
                link_id = str(record["LINK_ID"])
                if link_id in needed_links:
                    found_links[link_id] = _shape_parts(shape_record.shape)
                    if len(found_links) == len(needed_links):
                        break
        finally:
            link_reader.close()
    if needed_nodes:
        node_reader = shapefile.Reader(str(source_dir / "MOCT_NODE"), encoding="cp949")
        try:
            for shape_record in node_reader.iterShapeRecords():
                record = shape_record.record.as_dict()
                node_id = str(record["NODE_ID"])
                if node_id in needed_nodes:
                    x, y = shape_record.shape.points[0]
                    found_nodes[node_id] = (float(x), float(y))
                    if len(found_nodes) == len(needed_nodes):
                        break
        finally:
            node_reader.close()

    missing_links = sorted(needed_links - set(found_links))
    missing_nodes = sorted(needed_nodes - set(found_nodes))
    if missing_links or missing_nodes:
        raise ValueError(
            "standard node-link references not found: "
            f"links={missing_links}, nodes={missing_nodes}"
        )

    result: dict[str, dict[str, Any]] = {}
    for spec in specs:
        if spec["geometry_type"] == "link_path":
            parts = [
                part
                for reference in spec["reference_ids"]
                for part in found_links[reference]
            ]
        else:
            parts = [[found_nodes[spec["reference_ids"][0]]]]
        points = [point for part in parts for point in part]
        result[spec["event_id"]] = {
            **spec,
            "parts": parts,
            "bounds": (
                min(point[0] for point in points),
                min(point[1] for point in points),
                max(point[0] for point in points),
                max(point[1] for point in points),
            ),
        }
    return result


def _load_store_points(path: Path) -> tuple[list[tuple[str, float, float]], dict[str, int]]:
    try:
        from pyproj import Transformer
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install geographic support: python -m pip install -e .[geo]") from exc

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:5186", always_xy=True)
    points: list[tuple[str, float, float]] = []
    seen: set[str] = set()
    total_rows = 0
    invalid_coordinate_rows = 0
    duplicate_store_rows = 0
    wrong_region_rows = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        _require_fields(path, reader.fieldnames or [], STORE_REQUIRED_FIELDS)
        for row in reader:
            total_rows += 1
            if row["시도명"].strip() != "대전광역시":
                wrong_region_rows += 1
                continue
            store_id = row["상가업소번호"].strip()
            if not store_id or store_id in seen:
                duplicate_store_rows += 1
                continue
            try:
                longitude = float(row["경도"])
                latitude = float(row["위도"])
                if not (124 <= longitude <= 132 and 33 <= latitude <= 39):
                    raise ValueError
                x, y = transformer.transform(longitude, latitude)
                if not (math.isfinite(x) and math.isfinite(y)):
                    raise ValueError
            except (TypeError, ValueError):
                invalid_coordinate_rows += 1
                continue
            seen.add(store_id)
            points.append((store_id, float(x), float(y)))
    if not points:
        raise ValueError("store CSV contains no valid Daejeon coordinates")
    return points, {
        "source_rows": total_rows,
        "valid_coordinate_rows": len(points),
        "invalid_coordinate_rows": invalid_coordinate_rows,
        "duplicate_store_rows": duplicate_store_rows,
        "wrong_region_rows": wrong_region_rows,
    }


def build_exposure_report(
    *,
    store_csv: Path,
    geometry_csv: Path,
    mapping_csv: Path,
    node_link_dir: Path,
    store_source_date: str,
    store_zip_sha256: str,
    store_csv_sha256: str,
    node_link_sha256: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated = (generated_at or datetime.now(KST)).astimezone(KST)
    specs = _load_geometry_specs(geometry_csv)
    mismatched_geometry_hashes = [
        spec["event_id"]
        for spec in specs
        if spec["source_sha256"].strip().lower() != node_link_sha256.lower()
    ]
    if mismatched_geometry_hashes:
        raise ValueError(
            "geometry specs reference a different node-link hash: "
            + ", ".join(mismatched_geometry_hashes)
        )
    geometries = _load_reference_geometries(node_link_dir, specs)
    stores, store_quality = _load_store_points(store_csv)

    event_rows = []
    for spec in specs:
        geometry = geometries[spec["event_id"]]
        xmin, ymin, xmax, ymax = geometry["bounds"]
        buffer_m = float(spec["buffer_m"])
        radius_squared = buffer_m * buffer_m
        count = 0
        for _, x, y in stores:
            if not (
                xmin - buffer_m <= x <= xmax + buffer_m
                and ymin - buffer_m <= y <= ymax + buffer_m
            ):
                continue
            if (
                _distance_squared(
                    (x, y),
                    geometry_type=spec["geometry_type"],
                    parts=geometry["parts"],
                )
                <= radius_squared
            ):
                count += 1
        event_rows.append(
            {
                "event_id": spec["event_id"],
                "geometry_type": spec["geometry_type"],
                "reference_ids": "|".join(spec["reference_ids"]),
                "road_name": spec.get("road_name", ""),
                "start_name": spec.get("start_name", ""),
                "end_name": spec.get("end_name", ""),
                "buffer_m": int(buffer_m) if buffer_m.is_integer() else buffer_m,
                "exposure_proxy": count,
                "exposure_proxy_unit": f"active_store_count_within_{int(buffer_m)}m",
                "store_source_date": store_source_date,
                "geometry_confidence": spec["confidence"],
                "calculation": "EPSG:5186 point-to-event-geometry distance",
            }
        )

    event_lookup = {row["event_id"]: row for row in event_rows}
    mappings = _read_csv(mapping_csv)
    if not mappings:
        raise ValueError("event segment mapping CSV has no rows")
    _require_fields(mapping_csv, mappings[0], MAPPING_REQUIRED_FIELDS)
    segment_rows = []
    seen_segments: set[str] = set()
    for mapping in mappings:
        if mapping["decision"].strip() != "include_pilot":
            continue
        event = event_lookup.get(mapping["event_id"].strip())
        if event is None:
            continue
        segment_id = mapping["segment_id"].strip()
        if segment_id in seen_segments:
            raise ValueError(f"segment maps to more than one exposure event: {segment_id}")
        seen_segments.add(segment_id)
        segment_rows.append(
            {
                "segment_id": segment_id,
                "event_id": event["event_id"],
                "segment_label": mapping["segment_label"].strip(),
                "exposure_proxy": event["exposure_proxy"],
                "exposure_proxy_unit": event["exposure_proxy_unit"],
                "buffer_m": event["buffer_m"],
                "store_source_date": store_source_date,
                "store_source_sha256": store_csv_sha256,
                "geometry_confidence": event["geometry_confidence"],
                "mapping_confidence": mapping["confidence"].strip(),
                "calculation": event["calculation"],
            }
        )

    return {
        "schema_version": "0.1.0",
        "status": "valid",
        "generated_at_kst": generated.isoformat(timespec="seconds"),
        "definition": (
            "공식 상가정보의 영업 중 상가 좌표 중 공사 이벤트 점·링크 경계에서 "
            "250m 이내인 업소 수. 실제 택배 물량·주문량이 아님."
        ),
        "store_source": {
            "dataset_id": "15083033",
            "dataset_name": "소상공인시장진흥공단_상가(상권)정보",
            "source_date": store_source_date,
            "official_page": "https://www.data.go.kr/data/15083033/fileData.do",
            "zip_sha256": store_zip_sha256,
            "daejeon_csv_sha256": store_csv_sha256,
            **store_quality,
        },
        "geometry_source": {
            "dataset": "ITS 국가표준 노드·링크",
            "version": specs[0]["source_version"],
            "crs": "EPSG:5186",
            "sha256": node_link_sha256,
            "geometry_spec": geometry_csv.name,
        },
        "events": event_rows,
        "segments": segment_rows,
        "event_count": len(event_rows),
        "segment_count": len(segment_rows),
    }


def write_exposure_outputs(
    report: dict[str, Any],
    *,
    event_csv: Path,
    segment_csv: Path,
    report_json: Path,
) -> None:
    for path, rows in (
        (event_csv, report["events"]),
        (segment_csv, report["segments"]),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = list(rows[0]) if rows else []
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
