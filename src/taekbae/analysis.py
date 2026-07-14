from __future__ import annotations

import bisect
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

from taekbae.config import KST


SUPPORTED_METRICS = {"speed_kmh", "travel_time_sec"}


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def _metric_column(metric: str) -> str:
    if metric not in SUPPORTED_METRICS:
        raise ValueError(f"unsupported metric: {metric}")
    return metric


def _nearest_index(
    times: list[datetime], target: datetime, *, tolerance_seconds: int
) -> int | None:
    position = bisect.bisect_left(times, target)
    candidates = [index for index in (position - 1, position) if 0 <= index < len(times)]
    if not candidates:
        return None
    closest = min(candidates, key=lambda index: abs((times[index] - target).total_seconds()))
    if abs((times[closest] - target).total_seconds()) > tolerance_seconds:
        return None
    return closest


def build_forecast_examples(
    connection: sqlite3.Connection,
    *,
    source: str = "djtram_web",
    metric: str = "speed_kmh",
    horizon_minutes: int = 30,
    interval_minutes: int = 10,
    tolerance_seconds: int = 180,
) -> list[dict[str, Any]]:
    """Build leakage-safe rows using only values known at the forecast timestamp."""

    column = _metric_column(metric)
    rows = connection.execute(
        f"""
        SELECT observed_at_kst, segment_id, zone, {column} AS value
        FROM traffic_observations
        WHERE source = ? AND {column} IS NOT NULL
        ORDER BY segment_id, observed_at_kst
        """,
        (source,),
    ).fetchall()
    grouped: dict[str, list[tuple[datetime, float, int | None]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["segment_id"])].append(
            (_parse_time(str(row["observed_at_kst"])), float(row["value"]), row["zone"])
        )

    examples: list[dict[str, Any]] = []
    for segment_id, observations in grouped.items():
        times = [item[0] for item in observations]
        values = [item[1] for item in observations]
        zone = observations[0][2]
        for current_index, current_time in enumerate(times):
            lag_10_index = _nearest_index(
                times,
                current_time - timedelta(minutes=interval_minutes),
                tolerance_seconds=tolerance_seconds,
            )
            lag_20_index = _nearest_index(
                times,
                current_time - timedelta(minutes=interval_minutes * 2),
                tolerance_seconds=tolerance_seconds,
            )
            target_index = _nearest_index(
                times,
                current_time + timedelta(minutes=horizon_minutes),
                tolerance_seconds=tolerance_seconds,
            )
            if None in (lag_10_index, lag_20_index, target_index):
                continue
            if target_index <= current_index:
                continue
            window_start = current_time - timedelta(minutes=30)
            window_left = bisect.bisect_left(times, window_start)
            history = values[window_left : current_index + 1]
            if len(history) < 3:
                continue
            history_mean = sum(history) / len(history)
            history_variance = sum((value - history_mean) ** 2 for value in history) / len(
                history
            )
            minute_of_day = current_time.hour * 60 + current_time.minute
            examples.append(
                {
                    "forecast_at_kst": current_time.isoformat(timespec="seconds"),
                    "target_at_kst": times[target_index].isoformat(timespec="seconds"),
                    "segment_id": segment_id,
                    "zone": zone if zone is not None else -1,
                    "value_now": values[current_index],
                    "value_lag_10": values[lag_10_index],
                    "value_lag_20": values[lag_20_index],
                    "rolling_mean_30": history_mean,
                    "rolling_std_30": math.sqrt(history_variance),
                    "hour_sin": math.sin(2 * math.pi * minute_of_day / 1440),
                    "hour_cos": math.cos(2 * math.pi * minute_of_day / 1440),
                    "dow_sin": math.sin(2 * math.pi * current_time.weekday() / 7),
                    "dow_cos": math.cos(2 * math.pi * current_time.weekday() / 7),
                    "weekday": current_time.weekday(),
                    "hour": current_time.hour,
                    "minute": current_time.minute,
                    "target_value": values[target_index],
                }
            )
    return sorted(examples, key=lambda row: (row["target_at_kst"], row["segment_id"]))


def assess_forecast_readiness(
    connection: sqlite3.Connection,
    *,
    source: str = "djtram_web",
    metric: str = "speed_kmh",
    min_snapshots: int = 288,
    min_span_hours: float = 48.0,
    min_examples: int = 5_000,
    min_distinct_dates: int = 3,
) -> dict[str, Any]:
    column = _metric_column(metric)
    summary = connection.execute(
        f"""
        SELECT COUNT(*) AS records,
               COUNT(DISTINCT observed_at_kst) AS snapshots,
               COUNT(DISTINCT segment_id) AS segments,
               MIN(observed_at_kst) AS first_at,
               MAX(observed_at_kst) AS last_at
        FROM traffic_observations
        WHERE source = ? AND {column} IS NOT NULL
        """,
        (source,),
    ).fetchone()
    first_at = _parse_time(summary["first_at"]) if summary and summary["first_at"] else None
    last_at = _parse_time(summary["last_at"]) if summary and summary["last_at"] else None
    span_hours = (
        round((last_at - first_at).total_seconds() / 3600, 3)
        if first_at is not None and last_at is not None
        else 0.0
    )
    timestamp_rows = connection.execute(
        f"""
        SELECT DISTINCT observed_at_kst
        FROM traffic_observations
        WHERE source = ? AND {column} IS NOT NULL
        ORDER BY observed_at_kst
        """,
        (source,),
    ).fetchall()
    timestamps = [_parse_time(row["observed_at_kst"]) for row in timestamp_rows]
    intervals = [
        (right - left).total_seconds() / 60 for left, right in zip(timestamps, timestamps[1:])
    ]
    examples = build_forecast_examples(connection, source=source, metric=metric)
    actual = {
        "records": int(summary["records"] if summary else 0),
        "snapshots": int(summary["snapshots"] if summary else 0),
        "segments": int(summary["segments"] if summary else 0),
        "first_observed_at_kst": first_at.isoformat(timespec="seconds") if first_at else None,
        "last_observed_at_kst": last_at.isoformat(timespec="seconds") if last_at else None,
        "span_hours": span_hours,
        "distinct_dates": len({timestamp.date() for timestamp in timestamps}),
        "forecast_examples": len(examples),
        "median_interval_minutes": round(median(intervals), 3) if intervals else None,
    }
    required = {
        "snapshots": min_snapshots,
        "span_hours": min_span_hours,
        "distinct_dates": min_distinct_dates,
        "forecast_examples": min_examples,
    }
    checks = {
        "snapshots": actual["snapshots"] >= min_snapshots,
        "span_hours": actual["span_hours"] >= min_span_hours,
        "distinct_dates": actual["distinct_dates"] >= min_distinct_dates,
        "forecast_examples": actual["forecast_examples"] >= min_examples,
    }
    missing = [name for name, passed in checks.items() if not passed]
    return {
        "status": "ready" if not missing else "insufficient_data",
        "source": source,
        "metric": metric,
        "horizon_minutes": 30,
        "actual": actual,
        "required": required,
        "checks": checks,
        "missing_requirements": missing,
        "interpretation": (
            "시간순 기준모델·AI 비교를 실행할 수 있음"
            if not missing
            else "현재 자료로 AI 성능을 주장하지 않으며 관측 모니터링만 제공"
        ),
    }


def _metrics(actual: list[float], predicted: list[float]) -> dict[str, float | None]:
    if not actual:
        return {"mae": None, "rmse": None, "wape_percent": None}
    errors = [truth - estimate for truth, estimate in zip(actual, predicted)]
    mae = sum(abs(error) for error in errors) / len(errors)
    rmse = math.sqrt(sum(error**2 for error in errors) / len(errors))
    denominator = sum(abs(value) for value in actual)
    wape = 100 * sum(abs(error) for error in errors) / denominator if denominator else None
    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "wape_percent": round(wape, 4) if wape is not None else None,
    }


def evaluate_forecast_models(
    connection: sqlite3.Connection,
    *,
    source: str = "djtram_web",
    metric: str = "speed_kmh",
    min_snapshots: int = 288,
    min_span_hours: float = 48.0,
    min_examples: int = 5_000,
    min_distinct_dates: int = 3,
    model_output: Path | None = None,
) -> dict[str, Any]:
    readiness = assess_forecast_readiness(
        connection,
        source=source,
        metric=metric,
        min_snapshots=min_snapshots,
        min_span_hours=min_span_hours,
        min_examples=min_examples,
        min_distinct_dates=min_distinct_dates,
    )
    if readiness["status"] != "ready":
        return {
            "status": "not_evaluated",
            "reason": "insufficient_data",
            "readiness": readiness,
            "claims_allowed": ["collector_operational", "current_observation_monitoring"],
            "claims_not_allowed": ["ai_outperforms_baseline", "30_minute_forecast_validated"],
        }

    try:
        import joblib
        import pandas as pd
        from sklearn.compose import ColumnTransformer
        from sklearn.ensemble import HistGradientBoostingRegressor
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder
    except ImportError as exc:  # pragma: no cover - depends on optional environment
        return {
            "status": "not_evaluated",
            "reason": "missing_analysis_dependency",
            "missing_module": exc.name,
            "install": "python -m pip install -e .[analysis]",
            "readiness": readiness,
        }

    examples = build_forecast_examples(connection, source=source, metric=metric)
    frame = pd.DataFrame(examples)
    target_times = sorted(frame["target_at_kst"].unique())
    split_index = max(1, int(len(target_times) * 0.8))
    if split_index >= len(target_times):
        return {"status": "not_evaluated", "reason": "no_holdout_window", "readiness": readiness}
    first_test_time = target_times[split_index]
    train = frame[frame["target_at_kst"] < first_test_time].copy()
    test = frame[frame["target_at_kst"] >= first_test_time].copy()
    if train.empty or test.empty:
        return {"status": "not_evaluated", "reason": "empty_time_split", "readiness": readiness}

    feature_columns = [
        "segment_id",
        "zone",
        "value_now",
        "value_lag_10",
        "value_lag_20",
        "rolling_mean_30",
        "rolling_std_30",
        "hour_sin",
        "hour_cos",
        "dow_sin",
        "dow_cos",
    ]
    categorical = ["segment_id", "zone"]
    numeric = [column for column in feature_columns if column not in categorical]
    preprocessing = ColumnTransformer(
        [
            (
                "category",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                categorical,
            ),
            ("number", "passthrough", numeric),
        ]
    )
    model = Pipeline(
        [
            ("preprocess", preprocessing),
            (
                "regressor",
                HistGradientBoostingRegressor(
                    learning_rate=0.05,
                    max_iter=200,
                    max_leaf_nodes=31,
                    l2_regularization=0.1,
                    random_state=42,
                ),
            ),
        ]
    )
    model.fit(train[feature_columns], train["target_value"])
    ai_predictions = [float(value) for value in model.predict(test[feature_columns])]
    actual = [float(value) for value in test["target_value"]]
    persistence = [float(value) for value in test["value_now"]]

    global_median = float(train["target_value"].median())
    segment_medians = train.groupby("segment_id")["target_value"].median().to_dict()
    same_time = (
        train.groupby(["segment_id", "weekday", "hour", "minute"])["target_value"]
        .median()
        .to_dict()
    )
    historical_predictions = []
    for row in test.to_dict("records"):
        key = (row["segment_id"], row["weekday"], row["hour"], row["minute"])
        historical_predictions.append(
            float(same_time.get(key, segment_medians.get(row["segment_id"], global_median)))
        )

    metric_results = {
        "persistence_baseline": _metrics(actual, persistence),
        "same_time_baseline": _metrics(actual, historical_predictions),
        "hist_gradient_boosting": _metrics(actual, ai_predictions),
    }
    baseline_mae = min(
        result["mae"]
        for name, result in metric_results.items()
        if name != "hist_gradient_boosting" and result["mae"] is not None
    )
    ai_mae = metric_results["hist_gradient_boosting"]["mae"]
    beats_baseline = bool(ai_mae is not None and baseline_mae is not None and ai_mae < baseline_mae)
    report: dict[str, Any] = {
        "status": "evaluated",
        "source": source,
        "metric": metric,
        "horizon_minutes": 30,
        "generated_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "split": {
            "method": "chronological_80_20_by_target_timestamp",
            "train_rows": int(len(train)),
            "test_rows": int(len(test)),
            "train_first_target_at_kst": str(train["target_at_kst"].min()),
            "train_last_target_at_kst": str(train["target_at_kst"].max()),
            "test_first_target_at_kst": str(test["target_at_kst"].min()),
            "test_last_target_at_kst": str(test["target_at_kst"].max()),
        },
        "metrics": metric_results,
        "ai_beats_best_baseline_on_mae": beats_baseline,
        "claim": (
            "시험기간 MAE에서 AI 후보가 두 기준모델보다 낮음"
            if beats_baseline
            else "AI 후보가 기준모델을 이겼다고 주장할 수 없음"
        ),
        "readiness": readiness,
    }
    if model_output is not None:
        model_output.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "pipeline": model,
                "source": source,
                "metric": metric,
                "feature_columns": feature_columns,
                "trained_at_kst": report["generated_at_kst"],
                "report": report,
            },
            model_output,
        )
        report["model_output"] = str(model_output)
    return report


def write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
