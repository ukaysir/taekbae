# GitHub Actions 클라우드 수집

로컬 PC를 계속 켜두지 않아도 `.github/workflows/collect-djtram.yml`이 GitHub macOS 호스팅 실행기에서 1·12공구를 수집한다.

## 운영 계약

- 실행 간격: 매시 7·17·27·37·47·57분(UTC 기준, 약 10분 간격)
- 실행 환경: `macos-latest`(Ubuntu·Windows 호스팅 풀에서는 대전시 공식 호스트 연결이 타임아웃됨)
- 수집 종료: 2026-07-21 04:00 UTC(2026-07-21 13:00 KST) 이후 워크플로 자동 비활성화
- 상태 저장: `cloud-collector-state` 초안 Release의 `collector-state.tar.gz`
- 복구본: 직전 성공 상태를 `collector-state.previous.tar.gz`로 함께 보존
- 포함 자료: 공식 트램 페이지 원문 gzip·메타데이터, `traffic.sqlite`, 최근 수집·품질 JSON
- 제외 자료: API 키, `.env`, `.private`, 참가자 개인정보, 대형 외부 데이터

GitHub 예약 실행은 정확한 시각을 보장하지 않으므로 최소 48시간보다 긴 약 72시간 창을 사용한다. 각 실행은 이전 성공 자산을 복원하고 한 스냅숏을 추가한 뒤 새 자산을 업로드한다. 한 실행이 실패하면 Release의 최신본 또는 직전 백업본에서 다음 실행을 재개한다.

2026-07-18 13:20 KST 수동 검증 실행에서 1공구 9행·12공구 32행을 추가하고 Release 자산 교체까지 성공했다. 15:25 KST 예약 실행까지 원격 자산은 8스냅숏·328행으로 늘었다. 이후 예약 실행이 지연돼 16:24 KST부터 로컬 10분 수집기를 보조 경로로 다시 가동했다.

16:23 KST 최신 Release 자산을 별도 폴더에 복원해 SHA-256 `748af28a845aaad24dbc8b0952583da0d1aa8145fdc826cda896b90b9d258d67`을 확인했다. 원격 8스냅숏·328행과 로컬 2스냅숏·82행의 스키마·기본키 비중복을 검증하고 복원 직후 DB를 별도 보존한 뒤 한 트랜잭션으로 병합했다. 로컬 재시작 첫 수집까지 포함한 16:25 KST 현재 상태는 11스냅숏·451행이며 SQLite 무결성 검사를 통과했다.

## 상태 확인

~~~powershell
gh run list --repo ukaysir/taekbae --workflow collect-djtram.yml --limit 10
gh release download cloud-collector-state --repo ukaysir/taekbae --pattern "collector-state.tar.gz" --dir .tmp\cloud-collector
~~~

## 새 작업환경에서 이어가기

GitHub CLI 인증이 된 Windows 환경에서 다음 순서로 코드와 최신 수집상태를 복원한다. 복원 스크립트는 로컬 수집기·대시보드가 실행 중이면 중단하고, Release 자산의 SHA-256을 검증하며, 기존 원문·DB가 있으면 `.tmp/cloud-restore/` 아래에 먼저 백업한다. 압축을 저장소 루트에 직접 풀지 않는다.

~~~powershell
git clone https://github.com/ukaysir/taekbae.git
Set-Location taekbae
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[analysis,pdf]"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\restore_cloud_state.ps1
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m taekbae quality
~~~

수집 원문과 SQLite는 이 절차로 복원되지만, 대용량 표준 노드·링크와 상가정보 원본은 Git과 Release에서 의도적으로 제외한다. 최종화를 다시 실행하려면 `data/external/README.md`의 공식 출처에서 같은 판본을 내려받고 기록된 SHA-256을 확인해야 한다.

수집을 조기 중단하려면 다음 명령을 사용한다.

~~~powershell
gh workflow disable collect-djtram.yml --repo ukaysir/taekbae
~~~

초안 Release는 공개 저장소의 일반 Release 목록에 게시하지 않지만 저장소 쓰기 권한이 있는 계정과 워크플로가 접근할 수 있다. 최종 동결 후에는 필요한 산출물을 별도로 보관하고 임시 수집 Release를 삭제할 수 있다.
