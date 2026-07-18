# 출처 대장

- 최종 확인일: 2026-07-15 KST
- 원칙: 공식 공고·제공기관·제품문서를 우선한다. 생성형 AI 답변과 검색결과 요약은 근거로 쓰지 않는다.
- 상태: `사용`은 실제 산출물에 투입, `비교`는 차별성 검토, `후보`는 접근·호환 검증 전이다.

## 공모전 공식자료

| ID | 자료 | 상태 | 직접 뒷받침하는 내용 |
|---|---|---|---|
| C01 | `[붙임1] 공고문_2026년 물류데이터·AI 활용 및 분석 아이디어 공모전.pdf` 및 `붙임1.txt` | 사용 | 지정공모 3, 가점 3점, 평가항목, 자격, 일정, 제출물, 선행사업·수상작 |
| C02 | `[붙임2] 신청양식_2026년 물류데이터·AI 활용 및 분석 아이디어 공모전.hwp` 및 `붙임2.txt` | 사용 | 서식 1~5, 제안서 10쪽 이내, 보고서 권장 3~5쪽, AI 기록 필드 |
| C03 | `[붙임3] 신청 가이드_2026년 물류데이터·AI 활용 및 분석 아이디어 공모전.pdf` 및 `붙임3.txt` | 사용 | 참가·제출 절차 요약 |
| C04 | `[붙임4] 매뉴얼_2026년 물류데이터·AI 활용 및 분석 아이디어 공모전 사업관리시스템(PMS) 신청.pdf` 및 `붙임4.txt` | 사용 | PMS 입력·파일 업로드·임시저장·접수 절차 |
| C05 | https://pms.dicia.or.kr/mgmt/mjgg/mjggMgmtView.do?MJGGSBBEONHO=260605091929LJ016CFD&SBSESBBEONHO=260605091220JALKP6UY&menuId=73 | 사용 | 접수 중인 PMS 공식 공고, 2026-08-04 14:00 마감, 2026-06-19 갱신 첨부 1~5 |

2026-07-15에 PMS 공식 공고의 2026-06-19 갱신 첨부를 다시 내려받아 로컬 첨부 1~4와 SHA-256을 대조했고 모두 일치했다. 첨부 3·4는 이미지형 PDF를 직접 확인해 수동 전사했으며, 전사본은 원본보다 우선하지 않는다. 최신 원본 HWP에서도 공고문과 참가서약서의 저작재산권 문구가 충돌함을 확인했으므로 주최기관 답변 전에는 어느 한쪽을 임의로 우선하지 않는다.

## 핵심 공공데이터

| ID | 자료·URL | 상태 | 사용 필드·역할 | 한계·검증 |
|---|---|---|---|---|
| D01 | 대전 트램 공구별 공사·교통상황: https://www.daejeon.go.kr/djTram/getConstInfo.do?menuSeq=7699&zone=1 및 `zone=12` | 사용 | 공사명·기간·통제내용, 현재 구간 라벨·상태·속도 | 링크 ID·좌표·통행시간 없음; 동일 라벨 중복 있음 |
| D02 | 대전 트램 사업현황: https://www.daejeon.go.kr/djTram/contentView.do?menuSeq=7701 | 사용 | 38.8km, 정거장 45개소, 14개 공구와 추진현황 | 계획 일정은 변경 가능; 완료 사실로 표현 금지 |
| D03 | 대전 트램 추진현황: https://www.daejeon.go.kr/djTram/contentView.do?menuSeq=7698 | 사용 | 공사·시험운행·개통 전환의 계획 근거 | 확인일을 함께 표기 |
| D04 | 대전광역시 대전교통정보 API: https://www.data.go.kr/data/15157924/openapi.do | 후보 | 링크 ID·속도·통행시간·혼잡·방향 | 2026-07-15 HTTP 403; 현재 분석에는 미사용 |
| D05 | 기상청 ASOS 시간자료: https://www.data.go.kr/data/15057210/openapi.do | 후보 | 대전 133 기온·강수·풍속·습도 | 2026-07-15 HTTP 403; 현재 분석에는 미사용 |
| D06 | ITS 표준 노드·링크 조회: https://www.its.go.kr/nodelink/nodelinkStatus?service=inquiryNodelink | 사용 | 노드·방향성 링크·도로명·길이·제한속도 | 2024-11-29 배포본; 실시간값 아님 |
| D07 | ITS 노드·링크 자료실: https://www.its.go.kr/nodelink/nodelinkRef | 사용 | 공식 배포파일 출처 | 대용량 원본은 Git 제외, 해시 기록 |
| D08 | 국가교통 데이터 오픈마켓 이용안내: https://docs.bigdata-transportation.kr/open/open_2.html 및 https://docs.bigdata-transportation.kr/open/open_6.html | 후보 | 과거 대전 소통정보 다운로드 절차 | 로그인/구매 후 파일 확인 필요 |
| D09 | 대전 트램 공사 알림: https://www.daejeon.go.kr/djTram/notify/normalBoardDetail.do?boardId=djTram_0001&menuSeq=6724&ntatcSeq=1495771010 | 사용 | 계족로 동부여성가족원~읍내동 보도육교 통제범위 | 2025-08-22 게시문구를 자동 대조; 현재 상태는 D01에서 별도 확인 |
| D10 | 소상공인시장진흥공단 상가(상권)정보: https://www.data.go.kr/data/15083033/fileData.do | 사용 | 2026-03-31 영업 중 상가 ID·주소·경도·위도 | 공식 ZIP과 대전 CSV 해시 검증; 상가 수는 실제 택배 물량이 아닌 노출 대리값 |

## 실제 산출물과 원자료 계보

| 산출물 | 직접 입력 | 처리 |
|---|---|---|
| `data/manual/urban_events.csv` | D01 | 공사 이벤트를 사람이 전사하고 확인시각·상태를 기록 |
| `data/processed/traffic.sqlite` | D01의 1·12공구 교통표 | 10분 수집, 원응답 gzip·SHA-256 보존, 구간 정규화 |
| `data/manual/standard_corridor_evidence.csv` | D06·D07 | EPSG:5186 영역 필터 후 공식 링크 길이 방향성 최단경로 |
| `data/manual/event_scope_evidence.csv` | D01의 공식 이미지 2건·D09의 공지문 | URL·기대문구·이미지 SHA-256과 공사범위 신뢰도를 기록 |
| `outputs/tables/mapping_evidence_validation.json` | `event_scope_evidence.csv`의 공식 URL·자산 | HTTP 상태·문구·PNG 규격·해시를 실시간 검증 |
| `data/manual/event_segment_mapping.csv` | 공사 이벤트·현재 교통라벨·표준 링크·공식 범위근거 | 사람이 포함/후보/제외와 범위/개별라벨 신뢰도를 구분해 판정 |
| `data/manual/event_exposure_geometry.csv` | D01·D06·D07의 공식 공사범위와 표준 링크/노드 | 이벤트별 점·링크 참조, 250m 반경, 공간근거 신뢰도를 고정 |
| `outputs/tables/exposure_validation.json` | D10 대전 CSV + `event_exposure_geometry.csv` | WGS84→EPSG:5186 변환, 점–이벤트 거리, 원본 품질·해시·이벤트별 상가 수 기록 |
| `outputs/tables/segment_exposure.csv` | 이벤트별 상가 수 + `event_segment_mapping.csv` | 시범 관측구간 10개에 노출값·단위·기준일·공간/매핑 신뢰도를 연결 |
| `outputs/api/current_risk.*` | 최신 관측 + 검증된 시범구간 노출값 | 현재 속도 기반 관측등급과 노출 대리값을 별도 필드로 제공; 예측필드는 null |
| `outputs/api/route_risk.*` | `examples/route_sample.csv` + 최신 관측 + 노출값 | 계획경로의 구간 ID와 관측위험·노출 대리값을 결합 |
| `outputs/tables/model_evaluation.json` | SQLite 관측패널 | 최소 데이터 미달 시 평가·학습을 중단하고 주장 잠금 |
| `outputs/tables/finalization_status.json` | 품질·모델준비·데이터원·매핑 검증 | 부족조건과 허용/금지 주장을 기계 판독 형태로 기록 |
| `outputs/tables/finalization_manifest.json` | 게이트 통과 후 동결 DB·모델·결과·근거 파일 | 상대경로·바이트·SHA-256과 SQLite 무결성 결과를 기록; 현재 미달이면 생성하지 않음 |

## 경쟁·대체재 공식자료

| ID | 자료·URL | 상태 | 확인 범위 |
|---|---|---|---|
| K01 | 카카오모빌리티 TMS: https://developers.kakaomobility.com/product/tms.html | 비교 | 대량배송 경로최적화, 배차 자동화, 실시간 도로와 미래 교통량 반영, ETA |
| K02 | 카카오 미래 운행정보 길찾기: https://developers.kakaomobility.com/guide/navi-api/future.html | 비교 | 미래 출발시각, 대안경로, 도로공사 등 전체차선 통제 반영 |
| K03 | CJ대한통운 로이스 파슬: https://www.cjlogistics.com/ko/newsroom/news/NR_00001138 | 비교 | 예약·분류·배차·정산 코어, 기사앱, 고객접수, 실시간 운영분석 |
| K04 | 공모전 붙임1의 2024·2025 수상작 | 비교 | 트램 심야 공동물류, 동적 경로 최적화 등 동일성 배제 |
| K05 | 공모전 붙임1의 스마트물류 실증화 7개 서비스 | 비교 | 개발 중 플랫폼·신서비스와 동일내용 배제 |

공개 문서에서 특정 기능을 찾지 못했다는 사실은 “그 기능이 없다”는 증거가 아니다. 비교표에는 확인된 공개기능과 미확인 영역을 분리한다.

## 버전·무결성 기록

- 표준 노드·링크 ZIP: 2024-11-29, 125,973,128바이트
- 표준 노드·링크 SHA-256: `4ddd6632756204c7fc8a429bfc57a91215f38138f1e78e65d65778e4b9187e90`
- 상가정보 전국 ZIP: 2026-03-31 기준, 341,856,617바이트, SHA-256 `a3b37ae5a5856407374e041b5cf8714b3090036a15e90d879d30f652b698b304`(2026-07-18 공식 다운로드 재검증; 대전 CSV는 이전 검증본과 동일)
- 상가정보 대전 CSV: 78,607행, 41,866,930바이트, SHA-256 `ad252b91748ca35889370fe664326fa6acc145457252f77c031b13e92201c470`
- 1공구 동부여성가족원~영진로얄아파트 공식 이미지 SHA-256: `cc53de219ef78da31113ffff93ee7e0241452c4c51466dd40218f4c3937bb413`
- 1공구 읍내삼거리 공식 이미지 SHA-256: `d7d5b0ec42725da5a752b0acfc6b9994a39bcd3925b60b334c76afc833c06d12`
- 공모전 붙임1 공고문 SHA-256: `fbfc83d0fadee584c7d2b0329ddf05572ce9b6fd0eaca05ddd1626e19e483a29`
- 공모전 붙임2 신청양식 SHA-256: `87a7ba89598f68545da6b47ab65137535c98c19574f7c08f9e1db7898b213b9c`
- 공모전 붙임3 신청 가이드 SHA-256: `6622ffea79dfaad9a7d6aa4713205e0d82f6f71f8bd65018933d99d9d20577a3`
- 공모전 붙임4 PMS 매뉴얼 SHA-256: `044fcc2a3de2635c1a52e09445255e4a3f4508ceb1e99723da1e6a550c6ff60b`
- 공모전 첨부 1~4: PMS 공식 공고의 2026-06-19 갱신 첨부와 로컬 해시 일치 확인(2026-07-15)
- 수집 원응답: `data/raw/<source>/<date>/`에 gzip과 메타데이터로 보존, Git 제외
- 실시간·공사계획 자료: 제출 직전 다시 확인하고 확인일을 갱신
