# 대전 트램 공사공지를 배송경로 판단정보로 전환하는 근거제약형 AI 모듈

이 폴더는 제품 개발 저장소가 아니라 **공모전 서류 작성과 근거 확인을 위한 작업공간**이다. 교통자료 추가 수집은 종료했으며, 이번 제출에서는 30분 AI 예측 성능을 주장하지 않는다.

## 폴더 안내

| 폴더 | 용도 |
|---|---|
| [`01_official`](01_official/README.md) | 공고문, 신청양식, 신청가이드, PMS 매뉴얼 원본과 텍스트 |
| [`02_submission`](02_submission/README.md) | 실행계획, 제출 원고, HWP·PDF, 제출용 시각자료, 체크리스트 |
| [`03_analysis`](03_analysis/README.md) | 교통품질·공사구간 매핑·상가노출의 실제 분석근거와 출처 |
| [`04_records`](04_records/README.md) | 의사결정, 작업일지, 생성형 AI 활용기록 |
| `_workspace` | `humanize-korean` 윤문 검수본과 자체 점검표. 제출·Git 대상 아님 |

## 현재 제출 전략

- 공식 주제: **대전 트램 공사공지를 배송경로 판단정보로 전환하는 근거제약형 AI 모듈**
- 현재 검증결과: 11스냅숏·451행·41구간의 교통품질, 공사범위·도로구간 매핑, 250m 상가노출 분석
- 핵심 AI: 공사정보 구조화, 근거 연결, 판단 보류, 배송위험 브리핑 생성
- 이번 제출에서 제외: 30분 예측 성능, 배송시간·비용·탄소 절감, 실제 TMS 연동
- 제품·서비스 개발 의무: 없음. 기존 대시보드 시안은 폐기했고, 제공된 디자인 레퍼런스를 반영한 서비스 흐름·검증 화면·분석 근거 이미지 3종을 제작

## 바로 볼 문서

1. [확정 제출서류](02_submission/required_documents.md)
2. [실행계획](02_submission/plan.md)
3. [제출 체크리스트](02_submission/submission_checklist.md)
4. [제안서 원고](02_submission/drafts/proposal_draft.md)
5. [분석 과정 보고서 원고](02_submission/drafts/analysis_report_draft.md)
6. [UI·UX 요소와 표시 데이터 확정본](02_submission/ui_ux_data_spec.md)
7. [HWP·PDF 제출 원고](02_submission/manuscripts/README.md)
8. [제출용 시각자료](02_submission/visuals/README.md)

## 문서 도구

HWP·PDF 원고를 다시 만들거나 검증할 때 `02_submission/tools`를 사용한다. HWP 생성에는 한컴오피스와 현재 사용자 범위의 자동화 보안모듈 등록이 필요하며 빌드 스크립트가 해당 등록을 수행한다.

~~~powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r .\02_submission\tools\requirements.txt
.\.venv\Scripts\python .\02_submission\tools\build_hwp_manuscript.py --input .\02_submission\drafts\proposal_draft.md --hwp ".\02_submission\manuscripts\2. 제안서.hwp" --pdf ".\02_submission\manuscripts\2. 제안서.pdf" --type proposal
.\.venv\Scripts\python .\02_submission\tools\build_hwp_manuscript.py --input .\02_submission\drafts\analysis_report_draft.md --hwp ".\02_submission\manuscripts\3. 분석 과정 보고서.hwp" --pdf ".\02_submission\manuscripts\3. 분석 과정 보고서.pdf" --type report
.\.venv\Scripts\python .\02_submission\tools\verify_submission.py --input ".\02_submission\manuscripts\2. 제안서.pdf" --type proposal --render-dir .\.tmp\verify\proposal
.\.venv\Scripts\python .\02_submission\tools\verify_submission.py --input ".\02_submission\manuscripts\3. 분석 과정 보고서.pdf" --type report --render-dir .\.tmp\verify\report
~~~

개인정보·서명·최종 제출본은 `.private/`에 두고 저장소에 커밋하지 않는다.
