from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from taekbae.analysis import assess_forecast_readiness, evaluate_forecast_models, write_report
from taekbae.config import KST
from taekbae.quality import build_quality_report
from taekbae.risk import (
    enrich_route,
    latest_risk_rows,
    load_route_csv,
    write_risk_csv,
    write_risk_json,
)
from taekbae.storage import connect


FINALIZATION_SCHEMA_VERSION = "0.1.0"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(value: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path.name}")
    return value


def _parse_kst(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"finalization artifact must stay inside repository: {path}") from exc


def _source_validation_issues(
    report: dict[str, Any], *, now: datetime, max_age_hours: float
) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    tested_at = _parse_kst(report.get("tested_at_kst"))
    if tested_at is None:
        blockers.append("source_validation_missing_or_invalid_timestamp")
    else:
        age_hours = (now - tested_at).total_seconds() / 3600
        if age_hours < -0.1:
            blockers.append("source_validation_timestamp_is_in_future")
        elif age_hours > max_age_hours:
            blockers.append("source_validation_is_stale")

    sources = report.get("sources")
    if not isinstance(sources, dict):
        return blockers + ["source_validation_missing_sources"], warnings

    tram = sources.get("daejeon_tram_web")
    if not isinstance(tram, dict) or tram.get("operational_usable") is not True:
        blockers.append("tram_observation_source_not_operational")

    node_link = sources.get("standard_node_link")
    if not isinstance(node_link, dict) or node_link.get("hash_verified") is not True:
        blockers.append("standard_node_link_hash_not_verified")

    mapping = sources.get("tram_event_scope_mapping")
    if not isinstance(mapping, dict) or mapping.get("operational_usable") is not True:
        blockers.append("tram_event_scope_mapping_not_operational")

    for optional_name in ("daejeon_openapi", "kma_asos_hourly"):
        optional = sources.get(optional_name)
        if not isinstance(optional, dict) or optional.get("operational_usable") is not True:
            warnings.append(f"optional_source_unavailable:{optional_name}")
    return blockers, warnings


def _mapping_validation_issues(
    mapping: dict[str, Any], evidence: dict[str, Any]
) -> list[str]:
    issues: list[str] = []
    if mapping.get("status") != "valid":
        issues.append("mapping_status_not_valid")
    if mapping.get("gate_2_status") != "passed":
        issues.append("mapping_gate_2_not_passed")
    if mapping.get("scope_evidence_status") != "valid":
        issues.append("mapping_scope_evidence_not_valid")
    if mapping.get("errors"):
        issues.append("mapping_has_errors")
    if evidence.get("status") != "valid":
        issues.append("mapping_evidence_status_not_valid")
    if evidence.get("errors"):
        issues.append("mapping_evidence_has_errors")
    verified = evidence.get("high_confidence_verified_events")
    if not isinstance(verified, list) or len(verified) < 2:
        issues.append("fewer_than_two_verified_scope_events")
    return issues


def _quality_findings(quality: dict[str, Any], *, source: str) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    overall = quality.get("overall")
    if not isinstance(overall, dict):
        return ["quality_report_missing_overall"], warnings
    if int(overall.get("invalid_speed_rows") or 0) > 0:
        blockers.append("invalid_speed_rows_present")
    if int(overall.get("zero_speed_rows") or 0) > 0:
        warnings.append("zero_speed_rows_present")

    continuity_rows = quality.get("continuity")
    continuity = None
    if isinstance(continuity_rows, list):
        continuity = next(
            (row for row in continuity_rows if isinstance(row, dict) and row.get("source") == source),
            None,
        )
    if continuity is None:
        blockers.append("quality_report_missing_source_continuity")
    else:
        if int(continuity.get("non_modal_snapshot_count") or 0) > 0:
            warnings.append("non_modal_snapshot_counts_present")
        if int(continuity.get("long_interval_count_gt_15") or 0) > 0:
            warnings.append("collection_gaps_over_15_minutes_present")

    run_rows = quality.get("run_summary")
    if isinstance(run_rows, list):
        run_summary = next(
            (row for row in run_rows if isinstance(row, dict) and row.get("source") == source),
            None,
        )
        if run_summary and int(run_summary.get("failed_runs") or 0) > 0:
            warnings.append("failed_collection_runs_present")
    return blockers, warnings


def _backup_database(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"refusing to overwrite frozen database: {target.name}")
    source_connection = sqlite3.connect(source)
    target_connection = sqlite3.connect(target)
    try:
        source_connection.backup(target_connection)
        result = target_connection.execute("PRAGMA integrity_check").fetchone()
        integrity = str(result[0]) if result else "missing_result"
    finally:
        target_connection.close()
        source_connection.close()
    return integrity


def _artifact(path: Path, *, root: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"required finalization artifact missing: {path.name}")
    return {
        "path": _relative(path, root),
        "bytes": path.stat().st_size,
        "sha256": sha256_path(path),
    }


def finalize_snapshot(
    *,
    repo_root: Path,
    db_path: Path,
    source_validation_path: Path,
    mapping_validation_path: Path,
    mapping_evidence_path: Path,
    route_input_path: Path,
    status_output: Path,
    manifest_output: Path,
    readiness_output: Path,
    quality_output: Path,
    model_report_output: Path,
    model_output: Path,
    risk_csv_output: Path,
    risk_json_output: Path,
    route_csv_output: Path,
    route_json_output: Path,
    frozen_db_dir: Path,
    source: str = "djtram_web",
    metric: str = "speed_kmh",
    min_snapshots: int = 288,
    min_span_hours: float = 48.0,
    min_examples: int = 5_000,
    min_distinct_dates: int = 3,
    max_validation_age_hours: float = 24.0,
    now: datetime | None = None,
    provenance_paths: tuple[Path, ...] = (),
) -> dict[str, Any]:
    generated_at = (now or datetime.now(KST)).astimezone(KST)
    generated_at_text = generated_at.isoformat(timespec="seconds")

    source_validation = _read_json(source_validation_path)
    mapping_validation = _read_json(mapping_validation_path)
    mapping_evidence = _read_json(mapping_evidence_path)

    connection = connect(db_path)
    try:
        readiness = assess_forecast_readiness(
            connection,
            source=source,
            metric=metric,
            min_snapshots=min_snapshots,
            min_span_hours=min_span_hours,
            min_examples=min_examples,
            min_distinct_dates=min_distinct_dates,
        )
        quality = build_quality_report(connection)
    finally:
        connection.close()

    source_blockers, source_warnings = _source_validation_issues(
        source_validation,
        now=generated_at,
        max_age_hours=max_validation_age_hours,
    )
    mapping_blockers = _mapping_validation_issues(mapping_validation, mapping_evidence)
    quality_blockers, quality_warnings = _quality_findings(quality, source=source)
    data_blockers = [
        f"readiness:{name}" for name in readiness.get("missing_requirements", [])
    ]
    non_data_blockers = source_blockers + mapping_blockers + quality_blockers
    blockers = data_blockers + non_data_blockers
    warnings = source_warnings + quality_warnings

    write_report(readiness, readiness_output)
    _write_json(quality, quality_output)

    base_report: dict[str, Any] = {
        "schema_version": FINALIZATION_SCHEMA_VERSION,
        "generated_at_kst": generated_at_text,
        "source": source,
        "metric": metric,
        "readiness": readiness,
        "preflight": {
            "blockers": blockers,
            "warnings": warnings,
            "source_validation": _relative(source_validation_path, repo_root),
            "mapping_validation": _relative(mapping_validation_path, repo_root),
            "mapping_evidence_validation": _relative(mapping_evidence_path, repo_root),
        },
    }
    if blockers:
        report = {
            **base_report,
            "status": "pending" if data_blockers and not non_data_blockers else "blocked",
            "finalized": False,
            "frozen_database_created": False,
            "model_evaluated": False,
            "prediction_fields_active": False,
            "claims_allowed": ["collector_operational", "current_observation_monitoring"],
            "claims_not_allowed": [
                "ai_outperforms_baseline",
                "30_minute_forecast_validated",
                "delivery_time_savings",
            ],
        }
        _write_json(report, status_output)
        return report

    freeze_stamp = generated_at.strftime("%Y%m%dT%H%M%S%f%z")
    frozen_db_path = frozen_db_dir / f"traffic_{freeze_stamp}.sqlite"
    integrity = _backup_database(db_path, frozen_db_path)
    if integrity.lower() != "ok":
        report = {
            **base_report,
            "status": "blocked",
            "finalized": False,
            "frozen_database_created": True,
            "frozen_database_integrity": integrity,
            "model_evaluated": False,
            "prediction_fields_active": False,
        }
        _write_json(report, status_output)
        return report

    frozen_connection = connect(frozen_db_path)
    try:
        frozen_readiness = assess_forecast_readiness(
            frozen_connection,
            source=source,
            metric=metric,
            min_snapshots=min_snapshots,
            min_span_hours=min_span_hours,
            min_examples=min_examples,
            min_distinct_dates=min_distinct_dates,
        )
        frozen_quality = build_quality_report(frozen_connection)
        model_report = evaluate_forecast_models(
            frozen_connection,
            source=source,
            metric=metric,
            min_snapshots=min_snapshots,
            min_span_hours=min_span_hours,
            min_examples=min_examples,
            min_distinct_dates=min_distinct_dates,
            model_output=model_output,
        )
        risk_rows = latest_risk_rows(frozen_connection, readiness=frozen_readiness)
        route_rows = enrich_route(
            frozen_connection,
            load_route_csv(route_input_path),
            readiness=frozen_readiness,
        )
    finally:
        frozen_connection.close()

    write_report(frozen_readiness, readiness_output)
    _write_json(frozen_quality, quality_output)
    if "model_output" in model_report:
        model_report["model_output"] = _relative(model_output, repo_root)
    write_report(model_report, model_report_output)

    matched = sum(bool(row.get("matched")) for row in route_rows)
    if model_report.get("status") != "evaluated" or matched != len(route_rows):
        failure_reasons = []
        if model_report.get("status") != "evaluated":
            failure_reasons.append(f"model_not_evaluated:{model_report.get('reason', 'unknown')}")
        if matched != len(route_rows):
            failure_reasons.append("route_rows_unmatched")
        report = {
            **base_report,
            "status": "blocked",
            "finalized": False,
            "frozen_database_created": True,
            "frozen_database": _relative(frozen_db_path, repo_root),
            "frozen_database_integrity": integrity,
            "model_evaluated": model_report.get("status") == "evaluated",
            "prediction_fields_active": False,
            "post_freeze_blockers": failure_reasons,
        }
        _write_json(report, status_output)
        return report

    write_risk_csv(risk_rows, risk_csv_output)
    write_risk_json(risk_rows, risk_json_output)
    write_risk_csv(route_rows, route_csv_output)
    write_risk_json(route_rows, route_json_output)

    ai_beats_baseline = model_report.get("ai_beats_best_baseline_on_mae") is True
    final_status = (
        "finalized_ai_candidate_validated"
        if ai_beats_baseline
        else "finalized_observation_only"
    )
    claims_allowed = [
        "collector_operational",
        "current_observation_monitoring",
        "chronological_model_evaluation_completed",
    ]
    claims_not_allowed = [
        "delivery_time_savings",
        "construction_caused_delivery_delay",
        "production_tms_integration",
    ]
    if ai_beats_baseline:
        claims_allowed.append("ai_candidate_outperformed_baselines_on_frozen_holdout")
    else:
        claims_not_allowed.extend(["ai_outperforms_baseline", "30_minute_forecast_validated"])

    artifact_paths = [
        frozen_db_path,
        readiness_output,
        quality_output,
        model_report_output,
        model_output,
        risk_csv_output,
        risk_json_output,
        route_csv_output,
        route_json_output,
        source_validation_path,
        mapping_validation_path,
        mapping_evidence_path,
        route_input_path,
    ] + list(provenance_paths)
    artifacts = [_artifact(path, root=repo_root) for path in artifact_paths]
    manifest = {
        "schema_version": FINALIZATION_SCHEMA_VERSION,
        "finalized_at_kst": generated_at_text,
        "status": final_status,
        "frozen_database_integrity": integrity,
        "readiness": frozen_readiness,
        "quality_summary": frozen_quality.get("overall", {}),
        "mapping_gate_2_status": mapping_validation.get("gate_2_status"),
        "verified_scope_events": mapping_validation.get("verified_high_scope_events", []),
        "model": {
            "status": model_report.get("status"),
            "ai_beats_best_baseline_on_mae": ai_beats_baseline,
            "claim": model_report.get("claim"),
        },
        "route_contract": {
            "records": len(route_rows),
            "matched": matched,
            "unmatched": len(route_rows) - matched,
        },
        "prediction_fields_active": False,
        "prediction_fields_note": (
            "모델 평가는 완료했으나 현재 위험계약은 관측 전용이다. "
            "검증된 추론 출력과 링크 길이/통행시간 계약을 별도로 연결하기 전에는 예측 필드를 채우지 않는다."
        ),
        "claims_allowed": claims_allowed,
        "claims_not_allowed": claims_not_allowed,
        "warnings": warnings,
        "artifacts": artifacts,
    }
    _write_json(manifest, manifest_output)

    report = {
        **base_report,
        "status": final_status,
        "finalized": True,
        "frozen_database_created": True,
        "frozen_database": _relative(frozen_db_path, repo_root),
        "frozen_database_sha256": sha256_path(frozen_db_path),
        "frozen_database_integrity": integrity,
        "model_evaluated": True,
        "ai_beats_best_baseline_on_mae": ai_beats_baseline,
        "prediction_fields_active": False,
        "route_records": len(route_rows),
        "route_matched": matched,
        "manifest_output": _relative(manifest_output, repo_root),
        "claims_allowed": claims_allowed,
        "claims_not_allowed": claims_not_allowed,
    }
    _write_json(report, status_output)
    return report
