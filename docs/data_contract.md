# 데이터 계약서 v0.1.0

이 문서는 특정 TMS 제품과의 계약이 아니라, 계획경로에 트램 공사구간의 관측·예보 위험을 붙이기 위한 독립형 CSV/JSON 프로토타입 계약이다. 주문, 송장, 주소, 수취인, 기사 개인정보는 입력받지 않는다.

## 입력: 계획경로 CSV

필수 열은 네 개다.

| 필드 | 형식 | 의미 | 예시 |
|---|---|---|---|
| `route_id` | 문자열 | 배차 또는 경로의 비식별 ID | `demo-route-001` |
| `stop_order` | 정수형 문자열 | 경로 내 구간 순서 | `1` |
| `segment_id` | 문자열 | 본 프로토타입이 발급한 관측구간 ID | `djtram-z01-2475bde4126f` |
| `planned_at_kst` | ISO 8601 | 해당 구간 계획 통과시각 | `2026-07-15T09:00:00+09:00` |

샘플은 `examples/route_sample.csv`에 있다. 빈 파일, 필수 열 누락, 파싱할 수 없는 계획시각은 오류로 거부한다.

## 출력: 위험정보 CSV/JSON

JSON 최상위 필드:

| 필드 | 형식 | 의미 |
|---|---|---|
| `schema_version` | 문자열 | 현재 `0.1.0` |
| `generated_at_kst` | ISO 8601 | 파일 생성시각 |
| `records` | 배열 | 구간별 결과 |

구간별 필드:

| 필드 | 형식/허용값 | 의미 |
|---|---|---|
| `route_id`, `stop_order` | 문자열 또는 null | 입력 경로 식별자와 순서 |
| `segment_id` | 문자열 | 관측구간 ID |
| `segment_label` | 문자열 또는 null | 공식 화면 기반 구간 라벨 |
| `zone` | 1~14 또는 null | 트램 공구 번호 |
| `planned_at_kst` | ISO 8601 또는 null | 계획 통과시각 |
| `forecast_at_kst` | ISO 8601 또는 null | 예보 생성/관측 기준시각 |
| `target_at_kst` | ISO 8601 또는 null | 예보 대상시각. 현재 관측만 있으면 null |
| `predicted_travel_time_sec` | 0 이상 수 또는 null | 검증된 모델의 예측 통행시간. 현재 null |
| `baseline_travel_time_sec` | 0 이상 수 또는 null | 같은 시점의 기준모델 값. 현재 null |
| `expected_delay_sec` | 수 또는 null | 기준 대비 예상 지연. 현재 null |
| `observed_speed_kmh` | 0 이상 수 또는 null | 최신 공식 화면의 현재 속도 |
| `observed_traffic_state` | `원활`, `지체`, `정체`, null | 최신 공식 화면의 현재 상태 |
| `risk_grade` | `low`, `medium`, `high`, `unknown` | 현재 상태 또는 향후 검증모델의 등급 |
| `risk_basis` | 문자열 | 등급의 근거 코드 |
| `exposure_proxy` | 수 또는 null | 향후 공사노출 대리변수. 현재 null |
| `model_status` | `ready_for_evaluation`, `insufficient_data`, `unavailable` 등 | 자료·평가 상태. `ready_for_evaluation`은 예측모델 사용 가능을 뜻하지 않음 |
| `confidence_or_warning` | 문자열 | 예측/관측 구분과 제한사항 |
| `source_updated_at_kst` | ISO 8601 또는 null | 원자료 갱신시각 |
| `matched` | 불리언 | 입력 구간 ID가 현재 관측과 결합됐는지 여부 |

## 현재 등급 규칙

현재는 AI 예측등급이 아니라 공식 화면 상태의 직역이다.

| 공식 상태 | `risk_grade` | `risk_basis` |
|---|---|---|
| 원활 | `low` | `official_current_traffic_state` |
| 지체 | `medium` | `official_current_traffic_state` |
| 정체 | `high` | `official_current_traffic_state` |
| 없음/알 수 없음 | `unknown` | `insufficient_observation` |

따라서 `forecast_at_kst`라는 필드명이 있어도 현재 레코드는 예측이 아니다. `target_at_kst`, `predicted_travel_time_sec`, `expected_delay_sec`가 null이고 경고문에 “예측 아님”이 들어간다.

## 향후 예측 활성화 조건

예측 필드는 다음을 모두 통과한 버전에서만 채운다.

1. 최소 48시간·3개 날짜·288스냅숏·5,000예제
2. 30분 뒤 실제 관측과 시간순 평가
3. 지속성·동시간 기준모델 대비 성능 공개
4. 데이터 누수 검사 통과
5. 매핑 신뢰도와 예측 불확실성 표시

모델이 기준모델을 이기지 못하면 현재 관측 계약을 유지하고 AI 예측 필드는 계속 null로 둔다.

## 실행 예

~~~powershell
.\.venv\Scripts\python.exe -m taekbae export-risk
.\.venv\Scripts\python.exe -m taekbae enrich-route --input examples\route_sample.csv
~~~

48시간 이후 최종 자료를 고정할 때는 개별 명령 대신 다음 통합 명령을 사용한다.

~~~powershell
.\scripts\finalize_submission.ps1
~~~

자료량·기간·날짜·예제 수 또는 공식 근거 검증이 부족하면 `outputs/tables/finalization_status.json`만 `pending`/`blocked`로 갱신한다. 모든 게이트가 통과해야 일관된 SQLite 복제본, 모델평가, 위험·경로 파일과 `finalization_manifest.json`이 생성된다. 모델평가 성공과 위험계약의 예측필드 활성화는 별도다. 추론출력과 링크 길이/통행시간 계약을 연결하기 전에는 `predicted_*`를 계속 null로 둔다.

생성 파일:

- `outputs/api/current_risk.csv`
- `outputs/api/current_risk.json`
- `outputs/api/route_risk.csv`
- `outputs/api/route_risk.json`

## 생산 연동 전에 남은 일

- 특정 TMS의 링크 ID 체계와 본 구간 ID 간 변환
- 인증·권한·호출한도·재시도·감사로그
- 개인정보·영업정보 최소화와 보유기간 합의
- 서비스 수준, 장애시 기본행동, 모델 버전 고정
- 실제 업체와 샌드박스 상호운용 시험

현재 파일 교환 성공은 생산 TMS 연동 성공을 뜻하지 않는다.
