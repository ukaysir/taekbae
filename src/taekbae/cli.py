from __future__ import annotations

import argparse
import json
import math
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from taekbae.analysis import assess_forecast_readiness, evaluate_forecast_models, write_report
from taekbae.config import DEFAULT_DB_PATH, KST, RAW_ROOT, REPO_ROOT, ensure_data_dirs, require_env
from taekbae.mapping import validate_event_mapping, write_mapping_report
from taekbae.nodelink import build_corridor_evidence, sha256_file, write_corridor_evidence
from taekbae.quality import build_quality_report
from taekbae.risk import enrich_route, latest_risk_rows, load_route_csv, write_risk_csv, write_risk_json
from taekbae.sources.daejeon_api import DaejeonApiError, fetch_api_page
from taekbae.sources.djtram import fetch_zone
from taekbae.sources.kma import KmaApiError, fetch_weather_page
from taekbae.storage import (
    connect,
    insert_observations,
    insert_weather_observations,
    record_run,
    save_raw_response,
)
from taekbae.webapp import serve


def _zones(value: str) -> list[int]:
    try:
        zones = sorted({int(part.strip()) for part in value.split(",") if part.strip()})
    except ValueError as exc:
        raise argparse.ArgumentTypeError("zones must be comma-separated integers") from exc
    if not zones or any(zone < 1 or zone > 14 for zone in zones):
        raise argparse.ArgumentTypeError("zones must be between 1 and 14")
    return zones


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def collect_djtram_once(zones: list[int], db_path: Path) -> dict[str, object]:
    ensure_data_dirs()
    started = datetime.now(KST).replace(microsecond=0)
    run_id = str(uuid.uuid4())
    observations = []
    pages: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    warning_count = 0

    for zone in zones:
        try:
            page = fetch_zone(zone, observed_at=started)
            raw_path, metadata_path = save_raw_response(
                RAW_ROOT,
                source="djtram_web",
                observed_at=started,
                suffix=f"zone{zone:02d}",
                raw=page.raw,
                metadata={
                    "source": "djtram_web",
                    "zone": zone,
                    "source_url": page.url,
                    "observed_at_kst": page.fetched_at_kst,
                    "record_count": len(page.observations),
                    "duplicate_label_count": page.duplicate_label_count,
                    "source_sha256": page.observations[0].source_hash,
                },
            )
            observations.extend(page.observations)
            warning_count += page.duplicate_label_count
            pages.append(
                {
                    "zone": zone,
                    "records": len(page.observations),
                    "duplicate_labels": page.duplicate_label_count,
                    "raw_path": _display_path(raw_path),
                    "metadata_path": _display_path(metadata_path),
                }
            )
        except Exception as exc:  # continue other zones and preserve partial evidence
            errors.append({"zone": zone, "error_type": type(exc).__name__, "message": str(exc)})

    ended = datetime.now(KST).replace(microsecond=0)
    connection = connect(db_path)
    try:
        inserted = insert_observations(connection, observations)
        status = "success" if not errors else ("partial" if observations else "failed")
        details = {"zones": zones, "pages": pages, "errors": errors, "inserted": inserted}
        record_run(
            connection,
            run_id=run_id,
            source="djtram_web",
            started_at_kst=started.isoformat(),
            ended_at_kst=ended.isoformat(),
            status=status,
            record_count=len(observations),
            warning_count=warning_count,
            details=details,
        )
    finally:
        connection.close()

    return {
        "run_id": run_id,
        "status": status,
        "started_at_kst": started.isoformat(),
        "ended_at_kst": ended.isoformat(),
        "requested_zones": zones,
        "records": len(observations),
        "inserted": inserted,
        "warnings": warning_count,
        "pages": pages,
        "errors": errors,
        "db_path": str(db_path),
    }


def command_collect(args: argparse.Namespace) -> int:
    result = collect_djtram_once(args.zones, args.db)
    _print_json(result)
    return 0 if result["status"] == "success" else 2


def command_daemon(args: argparse.Namespace) -> int:
    iteration = 0
    while args.iterations == 0 or iteration < args.iterations:
        cycle_started = time.monotonic()
        result = collect_djtram_once(args.zones, args.db)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
        iteration += 1
        if args.iterations and iteration >= args.iterations:
            break
        elapsed = time.monotonic() - cycle_started
        time.sleep(max(1.0, args.interval - elapsed))
    return 0


def command_quality(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    try:
        report = build_quality_report(connection)
    finally:
        connection.close()
    _print_json(report)
    return 0


def collect_api_once(
    service_key: str,
    *,
    db_path: Path,
    num_rows: int,
    max_pages: int,
) -> dict[str, object]:
    ensure_data_dirs()
    started = datetime.now(KST).replace(microsecond=0)
    run_id = str(uuid.uuid4())
    observations = []
    pages: list[dict[str, object]] = []
    error: dict[str, object] | None = None
    try:
        first = fetch_api_page(
            service_key, page_no=1, num_rows=num_rows, observed_at=started
        )
        expected_pages = max(1, math.ceil(first.total_count / max(1, num_rows)))
        if expected_pages > max_pages:
            raise RuntimeError(
                f"API requires {expected_pages} pages, exceeding --max-pages={max_pages}"
            )
        api_pages = [first]
        for page_no in range(2, expected_pages + 1):
            api_pages.append(
                fetch_api_page(
                    service_key,
                    page_no=page_no,
                    num_rows=num_rows,
                    observed_at=started,
                )
            )
        for page in api_pages:
            raw_path, metadata_path = save_raw_response(
                RAW_ROOT,
                source="daejeon_openapi",
                observed_at=started,
                suffix=f"page{page.page_no:03d}",
                raw=page.raw,
                metadata={
                    "source": "daejeon_openapi",
                    "page_no": page.page_no,
                    "num_rows": page.num_rows,
                    "total_count": page.total_count,
                    "link_count": page.link_count,
                    "record_count": len(page.observations),
                    "observed_at_kst": started.isoformat(),
                    "source_url": page.observations[0].source_url if page.observations else None,
                },
            )
            observations.extend(page.observations)
            pages.append(
                {
                    "page_no": page.page_no,
                    "records": len(page.observations),
                    "total_count": page.total_count,
                    "raw_path": _display_path(raw_path),
                    "metadata_path": _display_path(metadata_path),
                }
            )
        status = "success"
    except DaejeonApiError as exc:
        status = "failed"
        error = {"error_type": "DaejeonApiError", "code": exc.code, "message": exc.message}
    except Exception as exc:
        status = "failed"
        error = {"error_type": type(exc).__name__, "message": str(exc)}

    ended = datetime.now(KST).replace(microsecond=0)
    connection = connect(db_path)
    try:
        inserted = insert_observations(connection, observations)
        record_run(
            connection,
            run_id=run_id,
            source="daejeon_openapi",
            started_at_kst=started.isoformat(),
            ended_at_kst=ended.isoformat(),
            status=status,
            record_count=len(observations),
            warning_count=0,
            details={"pages": pages, "error": error, "inserted": inserted},
        )
    finally:
        connection.close()
    return {
        "run_id": run_id,
        "status": status,
        "started_at_kst": started.isoformat(),
        "ended_at_kst": ended.isoformat(),
        "records": len(observations),
        "inserted": inserted,
        "pages": pages,
        "error": error,
        "db_path": str(db_path),
    }


def command_collect_api(args: argparse.Namespace) -> int:
    key = require_env("DATA_GO_KR_SERVICE_KEY")
    result = collect_api_once(
        key, db_path=args.db, num_rows=args.num_rows, max_pages=args.max_pages
    )
    _print_json(result)
    return 0 if result["status"] == "success" else 2


def command_readiness(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    try:
        report = assess_forecast_readiness(
            connection,
            source=args.source,
            metric=args.metric,
            min_snapshots=args.min_snapshots,
            min_span_hours=args.min_span_hours,
            min_examples=args.min_examples,
            min_distinct_dates=args.min_distinct_dates,
        )
    finally:
        connection.close()
    _print_json(report)
    return 0 if report["status"] == "ready" else 3


def command_evaluate(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    try:
        report = evaluate_forecast_models(
            connection,
            source=args.source,
            metric=args.metric,
            min_snapshots=args.min_snapshots,
            min_span_hours=args.min_span_hours,
            min_examples=args.min_examples,
            min_distinct_dates=args.min_distinct_dates,
            model_output=args.model_output,
        )
    finally:
        connection.close()
    write_report(report, args.report_output)
    _print_json(report)
    return 0 if report["status"] == "evaluated" else 3


def command_export_risk(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    try:
        rows = latest_risk_rows(connection)
    finally:
        connection.close()
    write_risk_csv(rows, args.csv_output)
    write_risk_json(rows, args.json_output)
    _print_json(
        {
            "status": "success",
            "records": len(rows),
            "csv_output": _display_path(args.csv_output),
            "json_output": _display_path(args.json_output),
        }
    )
    return 0


def command_enrich_route(args: argparse.Namespace) -> int:
    route_rows = load_route_csv(args.input)
    connection = connect(args.db)
    try:
        rows = enrich_route(connection, route_rows)
    finally:
        connection.close()
    write_risk_csv(rows, args.csv_output)
    write_risk_json(rows, args.json_output)
    matched = sum(bool(row["matched"]) for row in rows)
    _print_json(
        {
            "status": "success",
            "records": len(rows),
            "matched": matched,
            "unmatched": len(rows) - matched,
            "csv_output": _display_path(args.csv_output),
            "json_output": _display_path(args.json_output),
        }
    )
    return 0 if matched == len(rows) else 4


def command_serve(args: argparse.Namespace) -> int:
    serve(args.db, args.events, args.host, args.port)
    return 0


def command_validate_mapping(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    try:
        report = validate_event_mapping(
            connection, events_path=args.events, mapping_path=args.mapping
        )
    finally:
        connection.close()
    write_mapping_report(report, args.output)
    _print_json(report)
    return 0 if report["status"] == "valid" else 5


def command_build_corridor_evidence(args: argparse.Namespace) -> int:
    actual_sha256 = sha256_file(args.source_zip)
    if args.expected_sha256 and actual_sha256.lower() != args.expected_sha256.lower():
        _print_json(
            {
                "status": "hash_mismatch",
                "source_zip": _display_path(args.source_zip),
                "expected_sha256": args.expected_sha256.lower(),
                "actual_sha256": actual_sha256.lower(),
            }
        )
        return 6
    report = build_corridor_evidence(
        source_dir=args.source_dir,
        event_id=args.event_id,
        start_name=args.start_name,
        end_name=args.end_name,
        bbox=tuple(args.bbox),
        source_version=args.source_version,
        source_sha256=actual_sha256,
    )
    write_corridor_evidence(report, args.csv_output, args.json_output)
    _print_json(
        {
            "status": "success",
            "event_id": report["event_id"],
            "start": report["start"],
            "end": report["end"],
            "forward_distance_m": report["forward_distance_m"],
            "reverse_distance_m": report["reverse_distance_m"],
            "forward_link_count": report["forward_link_count"],
            "reverse_link_count": report["reverse_link_count"],
            "road_names": report["road_names"],
            "source_sha256": report["source_sha256"],
            "csv_output": _display_path(args.csv_output),
            "json_output": _display_path(args.json_output),
        }
    )
    return 0


def command_smoke_api(args: argparse.Namespace) -> int:
    try:
        key = require_env("DATA_GO_KR_SERVICE_KEY")
        page = fetch_api_page(key, page_no=1, num_rows=args.num_rows)
        result = {
            "status": "success",
            "page_no": page.page_no,
            "num_rows": page.num_rows,
            "total_count": page.total_count,
            "link_count": page.link_count,
            "records": len(page.observations),
            "fields": sorted(page.observations[0].to_dict()) if page.observations else [],
        }
        _print_json(result)
        return 0
    except DaejeonApiError as exc:
        _print_json(
            {"status": "api_error", "result_code": exc.code, "result_message": exc.message}
        )
        return 2
    except Exception as exc:
        _print_json({"status": "error", "error_type": type(exc).__name__, "message": str(exc)})
        return 2


def command_smoke_weather(args: argparse.Namespace) -> int:
    try:
        key = require_env("DATA_GO_KR_SERVICE_KEY")
        page = fetch_weather_page(
            key,
            start_dt=args.start_dt,
            end_dt=args.end_dt,
            station_id=args.station_id,
            num_rows=args.num_rows,
        )
        result = {
            "status": "success",
            "station_id": args.station_id,
            "start_dt": args.start_dt,
            "end_dt": args.end_dt,
            "total_count": page.total_count,
            "records": len(page.observations),
            "fields": sorted(page.observations[0].to_dict()) if page.observations else [],
        }
        _print_json(result)
        return 0
    except KmaApiError as exc:
        _print_json(
            {"status": "api_error", "result_code": exc.code, "result_message": exc.message}
        )
        return 2
    except Exception as exc:
        _print_json({"status": "error", "error_type": type(exc).__name__, "message": str(exc)})
        return 2


def collect_weather_once(
    service_key: str,
    *,
    db_path: Path,
    start_dt: str,
    end_dt: str,
    station_id: int,
    num_rows: int,
    max_pages: int,
) -> dict[str, object]:
    ensure_data_dirs()
    started = datetime.now(KST).replace(microsecond=0)
    run_id = str(uuid.uuid4())
    observations = []
    pages: list[dict[str, object]] = []
    error: dict[str, object] | None = None
    try:
        first = fetch_weather_page(
            service_key,
            start_dt=start_dt,
            end_dt=end_dt,
            station_id=station_id,
            page_no=1,
            num_rows=num_rows,
        )
        expected_pages = max(1, math.ceil(first.total_count / max(1, num_rows)))
        if expected_pages > max_pages:
            raise RuntimeError(
                f"API requires {expected_pages} pages, exceeding --max-pages={max_pages}"
            )
        weather_pages = [first]
        for page_no in range(2, expected_pages + 1):
            weather_pages.append(
                fetch_weather_page(
                    service_key,
                    start_dt=start_dt,
                    end_dt=end_dt,
                    station_id=station_id,
                    page_no=page_no,
                    num_rows=num_rows,
                )
            )
        for page in weather_pages:
            raw_path, metadata_path = save_raw_response(
                RAW_ROOT,
                source="kma_asos",
                observed_at=started,
                suffix=f"stn{station_id}_page{page.page_no:03d}",
                raw=page.raw,
                metadata={
                    "source": "kma_asos",
                    "station_id": station_id,
                    "start_dt": start_dt,
                    "end_dt": end_dt,
                    "page_no": page.page_no,
                    "num_rows": page.num_rows,
                    "total_count": page.total_count,
                    "record_count": len(page.observations),
                },
            )
            observations.extend(page.observations)
            pages.append(
                {
                    "page_no": page.page_no,
                    "records": len(page.observations),
                    "raw_path": _display_path(raw_path),
                    "metadata_path": _display_path(metadata_path),
                }
            )
        status = "success"
    except KmaApiError as exc:
        status = "failed"
        error = {"error_type": "KmaApiError", "code": exc.code, "message": exc.message}
    except Exception as exc:
        status = "failed"
        error = {"error_type": type(exc).__name__, "message": str(exc)}

    ended = datetime.now(KST).replace(microsecond=0)
    connection = connect(db_path)
    try:
        inserted = insert_weather_observations(connection, observations)
        record_run(
            connection,
            run_id=run_id,
            source="kma_asos",
            started_at_kst=started.isoformat(),
            ended_at_kst=ended.isoformat(),
            status=status,
            record_count=len(observations),
            warning_count=0,
            details={
                "station_id": station_id,
                "start_dt": start_dt,
                "end_dt": end_dt,
                "pages": pages,
                "error": error,
                "inserted": inserted,
            },
        )
    finally:
        connection.close()
    return {
        "run_id": run_id,
        "status": status,
        "station_id": station_id,
        "start_dt": start_dt,
        "end_dt": end_dt,
        "records": len(observations),
        "inserted": inserted,
        "pages": pages,
        "error": error,
    }


def command_collect_weather(args: argparse.Namespace) -> int:
    key = require_env("DATA_GO_KR_SERVICE_KEY")
    result = collect_weather_once(
        key,
        db_path=args.db,
        start_dt=args.start_dt,
        end_dt=args.end_dt,
        station_id=args.station_id,
        num_rows=args.num_rows,
        max_pages=args.max_pages,
    )
    _print_json(result)
    return 0 if result["status"] == "success" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="taekbae")
    subparsers = parser.add_subparsers(dest="command", required=True)
    yesterday = (datetime.now(KST) - timedelta(days=1)).strftime("%Y%m%d")

    collect = subparsers.add_parser("collect-djtram", help="collect official tram-page traffic")
    collect.add_argument("--zones", type=_zones, default=[1, 12])
    collect.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    collect.set_defaults(func=command_collect)

    daemon = subparsers.add_parser("collect-daemon", help="run repeated tram-page collection")
    daemon.add_argument("--zones", type=_zones, default=[1, 12])
    daemon.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    daemon.add_argument("--interval", type=int, default=600)
    daemon.add_argument("--iterations", type=int, default=0, help="0 means run until stopped")
    daemon.set_defaults(func=command_daemon)

    quality = subparsers.add_parser("quality", help="summarize collected data quality")
    quality.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    quality.set_defaults(func=command_quality)

    collect_api = subparsers.add_parser(
        "collect-api", help="collect all pages from the Daejeon traffic OpenAPI"
    )
    collect_api.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    collect_api.add_argument("--num-rows", type=int, default=4000)
    collect_api.add_argument("--max-pages", type=int, default=20)
    collect_api.set_defaults(func=command_collect_api)

    smoke = subparsers.add_parser("smoke-api", help="test Daejeon traffic API without printing key")
    smoke.add_argument("--num-rows", type=int, default=10)
    smoke.set_defaults(func=command_smoke_api)

    weather_smoke = subparsers.add_parser(
        "smoke-weather", help="test the KMA ASOS hourly API without printing the key"
    )
    weather_smoke.add_argument("--start-dt", default=yesterday)
    weather_smoke.add_argument("--end-dt", default=yesterday)
    weather_smoke.add_argument("--station-id", type=int, default=133)
    weather_smoke.add_argument("--num-rows", type=int, default=100)
    weather_smoke.set_defaults(func=command_smoke_weather)

    weather_collect = subparsers.add_parser(
        "collect-weather", help="collect KMA ASOS hourly observations"
    )
    weather_collect.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    weather_collect.add_argument("--start-dt", default=yesterday)
    weather_collect.add_argument("--end-dt", default=yesterday)
    weather_collect.add_argument("--station-id", type=int, default=133)
    weather_collect.add_argument("--num-rows", type=int, default=100)
    weather_collect.add_argument("--max-pages", type=int, default=20)
    weather_collect.set_defaults(func=command_collect_weather)

    readiness = subparsers.add_parser(
        "readiness", help="report whether chronological AI evaluation is defensible"
    )
    readiness.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    readiness.add_argument("--source", default="djtram_web")
    readiness.add_argument("--metric", choices=["speed_kmh", "travel_time_sec"], default="speed_kmh")
    readiness.add_argument("--min-snapshots", type=int, default=288)
    readiness.add_argument("--min-span-hours", type=float, default=48.0)
    readiness.add_argument("--min-examples", type=int, default=5000)
    readiness.add_argument("--min-distinct-dates", type=int, default=3)
    readiness.set_defaults(func=command_readiness)

    evaluate = subparsers.add_parser(
        "evaluate-model", help="compare chronological baselines and an AI candidate"
    )
    evaluate.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    evaluate.add_argument("--source", default="djtram_web")
    evaluate.add_argument("--metric", choices=["speed_kmh", "travel_time_sec"], default="speed_kmh")
    evaluate.add_argument("--min-snapshots", type=int, default=288)
    evaluate.add_argument("--min-span-hours", type=float, default=48.0)
    evaluate.add_argument("--min-examples", type=int, default=5000)
    evaluate.add_argument("--min-distinct-dates", type=int, default=3)
    evaluate.add_argument(
        "--report-output", type=Path, default=REPO_ROOT / "outputs/tables/model_evaluation.json"
    )
    evaluate.add_argument(
        "--model-output", type=Path, default=REPO_ROOT / "outputs/models/forecast.joblib"
    )
    evaluate.set_defaults(func=command_evaluate)

    risk = subparsers.add_parser("export-risk", help="export current observational risk")
    risk.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    risk.add_argument(
        "--csv-output", type=Path, default=REPO_ROOT / "outputs/api/current_risk.csv"
    )
    risk.add_argument(
        "--json-output", type=Path, default=REPO_ROOT / "outputs/api/current_risk.json"
    )
    risk.set_defaults(func=command_export_risk)

    route = subparsers.add_parser(
        "enrich-route", help="join a route CSV to current risk and write CSV/JSON"
    )
    route.add_argument("--input", type=Path, required=True)
    route.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    route.add_argument(
        "--csv-output", type=Path, default=REPO_ROOT / "outputs/api/route_risk.csv"
    )
    route.add_argument(
        "--json-output", type=Path, default=REPO_ROOT / "outputs/api/route_risk.json"
    )
    route.set_defaults(func=command_enrich_route)

    dashboard = subparsers.add_parser("serve", help="serve the local risk dashboard")
    dashboard.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    dashboard.add_argument("--events", type=Path, default=REPO_ROOT / "data/manual/urban_events.csv")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8765)
    dashboard.set_defaults(func=command_serve)

    mapping = subparsers.add_parser(
        "validate-mapping", help="validate manual event-to-segment mapping evidence"
    )
    mapping.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    mapping.add_argument(
        "--events", type=Path, default=REPO_ROOT / "data/manual/urban_events.csv"
    )
    mapping.add_argument(
        "--mapping",
        type=Path,
        default=REPO_ROOT / "data/manual/event_segment_mapping.csv",
    )
    mapping.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs/tables/mapping_validation.json",
    )
    mapping.set_defaults(func=command_validate_mapping)

    corridor = subparsers.add_parser(
        "build-corridor-evidence",
        help="derive a reproducible directed corridor from the official standard node-link data",
    )
    corridor.add_argument(
        "--source-dir",
        type=Path,
        default=REPO_ROOT / "data/external/nodelink_2024_11_29",
    )
    corridor.add_argument(
        "--source-zip",
        type=Path,
        default=REPO_ROOT / "data/external/NODELINKDATA_2024-11-29.zip",
    )
    corridor.add_argument(
        "--expected-sha256",
        default="4ddd6632756204c7fc8a429bfc57a91215f38138f1e78e65d65778e4b9187e90",
    )
    corridor.add_argument("--event-id", default="tram-z12-01")
    corridor.add_argument("--start-name", default="서대전역네거리")
    corridor.add_argument("--end-name", default="서대전네거리")
    corridor.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        metavar=("XMIN", "YMIN", "XMAX", "YMAX"),
        default=(230000.0, 405000.0, 245000.0, 425000.0),
    )
    corridor.add_argument("--source-version", default="2024-11-29")
    corridor.add_argument(
        "--csv-output",
        type=Path,
        default=REPO_ROOT / "data/manual/standard_corridor_evidence.csv",
    )
    corridor.add_argument(
        "--json-output",
        type=Path,
        default=REPO_ROOT / "outputs/tables/standard_corridor_evidence.json",
    )
    corridor.set_defaults(func=command_build_corridor_evidence)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
