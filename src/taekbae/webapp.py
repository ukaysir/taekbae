from __future__ import annotations

import csv
import json
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from taekbae.analysis import assess_forecast_readiness
from taekbae.quality import build_quality_report
from taekbae.risk import latest_risk_rows
from taekbae.storage import connect


def load_events(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def build_dashboard_status(readiness: dict[str, Any]) -> dict[str, str]:
    if readiness.get("status") == "ready":
        return {
            "mode": "evaluation_ready_observation_only",
            "model_status": "ready_for_evaluation",
            "notice": (
                "AI 시간순 평가 조건은 충족됐지만 모델 우월성과 추론 출력은 아직 별도 검증 대상입니다. "
                "현재 위험은 계속 공식 페이지의 관측 상태이며 예측이 아닙니다."
            ),
        }
    return {
        "mode": "observation_monitoring",
        "model_status": str(readiness.get("status", "unknown")),
        "notice": "AI 예측 준비 중 — 현재 위험은 공식 페이지의 관측 상태이며 예측이 아닙니다.",
    }


def build_dashboard_payload(
    connection: sqlite3.Connection,
    *,
    events_path: Path,
    exposure_path: Path | None = None,
) -> dict[str, Any]:
    quality = build_quality_report(connection)
    readiness = assess_forecast_readiness(connection)
    segments = latest_risk_rows(connection, exposure_path=exposure_path)
    events = load_events(events_path)
    return {
        "status": build_dashboard_status(readiness),
        "quality": quality,
        "readiness": readiness,
        "segments": segments,
        "events": events,
    }


def dashboard_html() -> str:
    return """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:,">
<title>트램 물류영향 관측판</title>
<style>
:root{--ink:#15211d;--muted:#65736c;--paper:#f5f3ed;--card:#fff;--line:#dce2dd;--green:#0a7050;--orange:#c96c22;--red:#b43b3b;--blue:#2f6690}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:Pretendard,"Noto Sans KR",system-ui,sans-serif}.wrap{max-width:1180px;margin:auto;padding:34px 22px 60px}header{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:22px}h1{font-size:clamp(28px,4vw,46px);letter-spacing:-.045em;margin:0 0 9px}.sub{color:var(--muted);max-width:720px;line-height:1.6}.badge{padding:9px 13px;border-radius:999px;background:#e3eee8;color:var(--green);font-weight:700;white-space:nowrap}.notice{border-left:4px solid var(--orange);background:#fff7e9;padding:14px 16px;border-radius:8px;margin:20px 0;color:#704312}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 8px 25px rgba(26,48,38,.04)}.stat-label{font-size:13px;color:var(--muted)}.stat-value{font-size:28px;font-weight:800;margin-top:6px}.section-title{display:flex;justify-content:space-between;align-items:end;margin:30px 0 12px}.section-title h2{margin:0;font-size:21px}.filters{display:flex;gap:8px}.filters button{border:1px solid var(--line);background:#fff;border-radius:999px;padding:8px 12px;cursor:pointer}.filters button.active{background:var(--ink);color:#fff}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid var(--line);font-size:14px}th{color:var(--muted);font-weight:600}.risk{display:inline-flex;align-items:center;gap:6px;font-weight:700}.dot{width:9px;height:9px;border-radius:50%;background:#9aa6a0}.risk.low .dot{background:var(--green)}.risk.medium .dot{background:var(--orange)}.risk.high .dot{background:var(--red)}.events{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.event h3{margin:0 0 8px;font-size:16px}.event p{margin:4px 0;color:var(--muted);font-size:14px;line-height:1.45}.empty{color:var(--muted);padding:22px}.footer{margin-top:30px;color:var(--muted);font-size:13px;line-height:1.6}@media(max-width:800px){header{display:block}.badge{display:inline-block;margin-top:12px}.stats{grid-template-columns:repeat(2,1fr)}.events{grid-template-columns:1fr}.table-wrap{overflow:auto}}
</style>
</head>
<body><main class="wrap">
<header><div><h1>트램 물류영향 관측판</h1><div class="sub">대전 트램 공사를 첫 사례로, 공사구간의 교통상태와 데이터 축적·AI 검증 준비도를 분리해 보여주는 배차 검토용 프로토타입입니다.</div></div><div id="mode" class="badge">불러오는 중</div></header>
<div id="notice" class="notice">데이터 상태를 확인하고 있습니다.</div>
<section class="stats"><div class="card"><div class="stat-label">수집 스냅샷</div><div id="snapshots" class="stat-value">-</div></div><div class="card"><div class="stat-label">관측 구간</div><div id="segments" class="stat-value">-</div></div><div class="card"><div class="stat-label">학습 예제</div><div id="examples" class="stat-value">-</div></div><div class="card"><div class="stat-label">관측 기간</div><div id="span" class="stat-value">-</div></div></section>
<div class="section-title"><h2>현재 구간 상태</h2><div class="filters"><button class="active" data-zone="all">전체</button><button data-zone="1">1공구</button><button data-zone="12">12공구</button></div></div>
<div class="card table-wrap"><table><thead><tr><th>공구</th><th>구간</th><th>상태</th><th>속도</th><th>배송노출*</th><th>갱신시각</th></tr></thead><tbody id="segmentRows"><tr><td colspan="6" class="empty">불러오는 중</td></tr></tbody></table></div>
<div class="section-title"><h2>공사 통제 기준표</h2></div><section id="events" class="events"></section>
<p class="footer">현재 화면은 주문·기사·차량·경로를 관리하는 TMS가 아닙니다. 정식 교통 OpenAPI 승인 전에는 공식 트램 페이지의 현재 상태만 표시하며, 예상 지연시간과 30분 AI 예측 성능은 검증 전까지 비워 둡니다. *배송노출은 공사 이벤트 250m 안의 영업 중 상가 수로, 실제 택배 물량이 아닙니다.</p>
</main>
<script>
let payload=null;let zone='all';
const gradeLabel={low:'낮음',medium:'주의',high:'높음',unknown:'미확인'};
function renderSegments(){const rows=payload.segments.filter(x=>zone==='all'||String(x.zone)===zone);document.querySelector('#segmentRows').innerHTML=rows.length?rows.map(x=>`<tr><td>${x.zone??'-'}공구</td><td>${x.segment_label??x.segment_id}</td><td><span class="risk ${x.risk_grade}"><i class="dot"></i>${gradeLabel[x.risk_grade]||x.risk_grade}</span></td><td>${x.observed_speed_kmh??'-'} km/h</td><td>${x.exposure_proxy??'-'}${x.exposure_proxy==null?'':'곳'}</td><td>${(x.source_updated_at_kst||'-').replace('T',' ')}</td></tr>`).join(''):'<tr><td colspan="6" class="empty">해당 공구 자료가 없습니다.</td></tr>'}
fetch('/api/dashboard').then(r=>r.json()).then(data=>{payload=data;document.querySelector('#mode').textContent=data.status.mode==='evaluation_ready_observation_only'?'평가 준비·관측 전용':'관측 모니터링';document.querySelector('#notice').textContent=data.status.notice;const a=data.readiness.actual;document.querySelector('#snapshots').textContent=a.snapshots.toLocaleString();document.querySelector('#segments').textContent=a.segments.toLocaleString();document.querySelector('#examples').textContent=a.forecast_examples.toLocaleString();document.querySelector('#span').textContent=a.span_hours.toFixed(1)+'시간';renderSegments();document.querySelector('#events').innerHTML=data.events.map(e=>`<article class="card event"><h3>${e.contract_section} · ${e.location}</h3><p>${e.start_date} ~ ${e.end_date}</p><p>${e.control_detail} · ${e.direction}</p><p>확인 상태: ${e.status_as_of_2026_07_14}</p></article>`).join('')||'<div class="card empty">공사 이벤트가 없습니다.</div>'}).catch(err=>{document.querySelector('#notice').textContent='데이터를 불러오지 못했습니다: '+err});
document.querySelectorAll('[data-zone]').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('[data-zone]').forEach(x=>x.classList.remove('active'));button.classList.add('active');zone=button.dataset.zone;renderSegments()}));
</script></body></html>"""


def make_handler(
    db_path: Path, events_path: Path, exposure_path: Path | None = None
) -> type[BaseHTTPRequestHandler]:
    class DashboardHandler(BaseHTTPRequestHandler):
        def _send_json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = urlparse(self.path).path
            if path == "/":
                encoded = dashboard_html().encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(encoded)
                return
            if path == "/healthz":
                self._send_json({"status": "ok"})
                return
            if path == "/api/dashboard":
                connection = connect(db_path)
                try:
                    self._send_json(
                        build_dashboard_payload(
                            connection,
                            events_path=events_path,
                            exposure_path=exposure_path,
                        )
                    )
                finally:
                    connection.close()
                return
            self._send_json({"error": "not_found", "path": path}, HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: object) -> None:
            return

    return DashboardHandler


def serve(
    db_path: Path,
    events_path: Path,
    exposure_path: Path | None,
    host: str,
    port: int,
) -> None:
    server = ThreadingHTTPServer(
        (host, port), make_handler(db_path, events_path, exposure_path)
    )
    print(f"Dashboard listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
