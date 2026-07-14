from __future__ import annotations

import os
from datetime import timedelta, timezone
from pathlib import Path


KST = timezone(timedelta(hours=9), name="KST")
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "data"
RAW_ROOT = DATA_ROOT / "raw"
PROCESSED_ROOT = DATA_ROOT / "processed"
DEFAULT_DB_PATH = PROCESSED_ROOT / "traffic.sqlite"

DAEJEON_TRAFFIC_ENDPOINT = (
    "https://apis.data.go.kr/6300000/rest/getTrafficInfoAll"
)
KMA_ASOS_HOURLY_ENDPOINT = (
    "https://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList"
)
DJTRAM_ZONE_ENDPOINT = (
    "https://www.daejeon.go.kr/djTram/getConstInfo.do?menuSeq=7699&zone={zone}"
)
USER_AGENT = "taekbae-tram-risk/0.1 (+https://github.com/ukaysir/taekbae)"


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def ensure_data_dirs() -> None:
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    PROCESSED_ROOT.mkdir(parents=True, exist_ok=True)
