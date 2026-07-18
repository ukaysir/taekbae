# 대전 트램 물류영향 예보 프로토타입

대전 트램 공사를 첫 실증사례로 삼아 계획공사 구간의 교통위험을 수집하고 조건을 통과할 때만 예측하며, 특정 TMS에 종속되지 않은 CSV·JSON 위험정보로 변환하는 공모전 프로젝트다. 주문·송장·기사·차량·정산이나 최종 배차경로를 관리하는 TMS를 대체하지 않는다.

## 현재 검증 상태

1. **현재 사용:** 대전 트램 공식 1·12공구 페이지의 현재 교통상황
2. **승인 필요:** 대전광역시 대전교통정보 OpenAPI 데이터셋 `15157924`
3. **공간근거:** ITS 표준 노드·링크 2024-11-29 배포본
4. **범위근거:** 1공구 공식 공사이미지·공지문을 URL·문구·SHA-256으로 검증
5. **노출 대리값:** 소상공인시장진흥공단 2026-03-31 상가정보 대전 78,607행을 해시·좌표 검증 후 250m 상가 수로 사용

2026-07-15 실제 호출에서 최신 대전 교통 API와 기상청 ASOS는 모두 HTTP 403이었다. 승인 전에는 공사 통제정보가 구체적인 1·12공구만 10분 간격으로 수집한다. 이 경로에는 링크 ID·통행시간·좌표가 없으므로 정식 API와 동등한 데이터라고 주장하지 않는다. AI 예측은 최소 48시간·3개 날짜·288스냅숏·5,000예제를 충족할 때까지 비활성화한다.

## 빠른 시작

~~~powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[analysis,browser,geo,pdf]"
.\.venv\Scripts\python -m unittest discover -s tests -v

# 공식 트램 페이지에서 1·12공구를 한 번 수집
.\.venv\Scripts\python -m taekbae collect-djtram --zones 1,12

# 저장된 데이터 품질 요약
.\.venv\Scripts\python -m taekbae quality

# 환경변수의 키로 정식 API 인증 시험(키 값은 출력하지 않음)
.\.venv\Scripts\python -m taekbae smoke-api

# 모든 데이터원의 실제 사용성 보고서 생성
.\scripts\validate_sources.ps1

# 표준 노드·링크로 서대전 통행축 근거 재생성
.\.venv\Scripts\python -m taekbae build-corridor-evidence

# 공식 공사범위 근거와 이벤트–관측구간 매핑 검증
.\.venv\Scripts\python -m taekbae validate-mapping

# 공식 상가정보와 표준 링크/노드로 250m 배송노출 대리값 재생성
.\.venv\Scripts\python -m taekbae build-exposure

# 현재 관측 위험과 샘플 계획경로 결합
.\.venv\Scripts\python -m taekbae export-risk
.\.venv\Scripts\python -m taekbae enrich-route --input examples\route_sample.csv
~~~

백그라운드 수집은 다음 스크립트를 사용한다.

~~~powershell
.\scripts\start_collector.ps1
.\scripts\collector_status.ps1
.\scripts\stop_collector.ps1
~~~

로컬 PC를 계속 켜둘 수 없을 때는 GitHub Actions가 약 10분 간격으로 수집하고 초안 Release 자산에 최신·직전 상태를 보존한다. 실행기간, 복구와 중단 방법은 [GitHub Actions 클라우드 수집](docs/cloud_collection.md)을 따른다.

48시간 자료 게이트와 최종 동결은 한 명령으로 재검증한다.

~~~powershell
.\scripts\finalize_submission.ps1
~~~

이 명령은 먼저 API·공식 페이지·이미지 해시·매핑 근거를 갱신한다. 288스냅숏·48시간·3개 날짜·5,000예제 중 하나라도 부족하면 종료코드 3과 `pending`을 기록하고 DB 복제본·모델·최종 매니페스트를 만들지 않는다. 모두 통과하면 일관된 SQLite 복제본을 만든 뒤 시간순 모델평가, 현재 위험정보, 샘플 경로 결합과 SHA-256 매니페스트를 생성한다.

대시보드:

~~~powershell
.\scripts\start_dashboard.ps1
.\scripts\dashboard_status.ps1
.\.venv\Scripts\python.exe .\scripts\verify_dashboard.py
.\scripts\stop_dashboard.ps1
~~~

문서 초안 재생성:

~~~powershell
.\.venv\Scripts\python -m pip install -e ".[pdf,documents]"
.\.venv\Scripts\python scripts\render_submission.py --input docs\submission\proposal_draft.md --output "outputs\submission\[DRAFT]제안서.pdf" --type proposal
.\.venv\Scripts\python scripts\render_submission.py --input docs\submission\analysis_report_draft.md --output "outputs\submission\[DRAFT]분석과정보고서.pdf" --type report
.\.venv\Scripts\python scripts\verify_submission.py --input "outputs\submission\[DRAFT]제안서.pdf" --type proposal --render-dir .tmp\submission_verify\proposal
.\.venv\Scripts\python scripts\verify_submission.py --input "outputs\submission\[DRAFT]분석과정보고서.pdf" --type report --render-dir .tmp\submission_verify\report
~~~

PDF는 `[DRAFT]` 워터마크와 사용자 입력 자리표시자를 포함한 내용 초안이다. HWP 자동 편집은 원본 표의 인라인 개체와 다중 문단 셀을 안전하게 보존하지 못해 중단했으며, 상태와 수동 마감 항목은 [hwp_specs/README.md](hwp_specs/README.md)에 기록했다.

공식 제출 전에는 [평가·제출 감사](docs/submission/evaluation_audit.md), [주최기관 문의 초안](docs/submission/organizer_question_draft.md), [참가자 입력 템플릿](docs/submission/participant_input_template.md)을 확인한다. 실제 개인정보가 든 파일과 제출 매니페스트는 `.private/`에 두고 Git에 커밋하지 않는다.

최종 파일이 모두 준비된 뒤에만 다음 사전검사기로 ZIP을 만든다.

~~~powershell
New-Item -ItemType Directory -Force .private | Out-Null
Copy-Item docs\submission\submission_package.example.json .private\submission_package.json
# .private\submission_package.json의 팀명·파일경로·확인값을 실제 제출본에 맞게 수정
.\.venv\Scripts\python scripts\package_submission.py --manifest .private\submission_package.json --report outputs\tables\submission_preflight.json --output-dir outputs\submission\final --create-zip
~~~

검사기는 필수 7개 실제 파일, HWP/PDF 시그니처, 제안서 10쪽, 보고서 권장 3~5쪽, DRAFT·자리표시자·비밀값, 필수 확인사항을 검사한다. 하나라도 실패하면 ZIP을 만들지 않으며, 통과한 경우에만 `[공모전_팀명].zip`을 생성하고 50,000,000바이트 미만과 CRC를 다시 확인한다.

## 데이터 보존 원칙

- 원응답은 `data/raw/`에 gzip으로 보존한다.
- 정규화 관측치는 `data/processed/traffic.sqlite`에 저장한다.
- 원자료·DB·로그·모델은 Git에 커밋하지 않는다.
- 대용량 상가·노드링크 원본은 `data/external/`에만 두고 Git에는 해시·계보·소규모 결과만 기록한다.
- 수집시각은 KST ISO 8601로 기록한다.
- API 키는 환경변수에서만 읽고 URL·로그·예외 메시지에 넣지 않는다.
- 화면에서 같은 구간명이 중복되면 발생 순번을 포함한 안정 식별자를 사용하고 중복을 품질경고로 남긴다.

공모전 조건, 검증 상태와 주장 한계는 [plan.md](plan.md), [API 검증 기록](docs/api_validation.md), [출처 대장](docs/sources.md), [데이터 계약](docs/data_contract.md)을 따른다.
