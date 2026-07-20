# 대전 트램 공사정보를 배송위험으로 전환하는 근거제약형 AI 모듈

이 폴더는 제품 개발 저장소가 아니라 **공모전 서류 작성과 근거 확인을 위한 작업공간**이다. 교통자료 추가 수집은 종료했으며, 이번 제출에서는 30분 AI 예측 성능을 주장하지 않는다.

## 폴더 안내

| 폴더 | 용도 |
|---|---|
| [`01_official`](01_official/README.md) | 공고문, 신청양식, 신청가이드, PMS 매뉴얼 원본과 텍스트 |
| [`02_submission`](02_submission/README.md) | 실행계획, 제안서·분석보고서 초안, 체크리스트, 검토용 PDF |
| [`03_analysis`](03_analysis/README.md) | 교통품질·공사구간 매핑·상가노출의 실제 분석근거와 출처 |
| [`04_records`](04_records/README.md) | 의사결정, 작업일지, 생성형 AI 활용기록 |
| `_workspace` | `humanize-korean` 윤문 검수본과 자체 점검표. 제출·Git 대상 아님 |

## 현재 제출 전략

- 공식 주제: **대전 트램 공사정보를 배송위험으로 전환하는 근거제약형 AI 모듈**
- 현재 검증결과: 11스냅숏·451행·41구간의 교통품질, 공사범위·도로구간 매핑, 250m 상가노출 분석
- 핵심 AI: 공사정보 구조화, 근거 연결, 판단 보류, 배송위험 브리핑 생성
- 이번 제출에서 제외: 30분 예측 성능, 배송시간·비용·탄소 절감, 실제 TMS 연동
- 제품·서비스 개발 의무: 없음. 보존된 프로토타입 화면 이미지는 실현 가능성 보조자료로만 사용

## 바로 볼 문서

1. [확정 제출서류](02_submission/required_documents.md)
2. [실행계획](02_submission/plan.md)
3. [제출 체크리스트](02_submission/submission_checklist.md)
4. [제안서 초안](02_submission/drafts/proposal_draft.md)
5. [분석 과정 보고서 초안](02_submission/drafts/analysis_report_draft.md)

## 문서 도구

검토용 PDF를 다시 만들 때만 `02_submission/tools`를 사용한다.

~~~powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r .\02_submission\tools\requirements.txt
.\.venv\Scripts\python .\02_submission\tools\render_submission.py --input .\02_submission\drafts\proposal_draft.md --output ".\02_submission\review_pdfs\[DRAFT]제안서.pdf" --type proposal
.\.venv\Scripts\python .\02_submission\tools\render_submission.py --input .\02_submission\drafts\analysis_report_draft.md --output ".\02_submission\review_pdfs\[DRAFT]분석과정보고서.pdf" --type report
~~~

개인정보·서명·최종 제출본은 `.private/`에 두고 저장소에 커밋하지 않는다.
