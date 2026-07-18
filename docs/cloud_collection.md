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

2026-07-18 13:20 KST 수동 검증 실행에서 1공구 9행·12공구 32행을 추가하고 Release 자산 교체까지 성공했다. 업로드된 최신 자산을 별도 폴더에 다시 내려받아 5스냅숏·205행, SQLite 조회, 수집·품질 JSON, GitHub 자산 SHA-256 일치를 확인했다.

## 상태 확인

~~~powershell
gh run list --repo ukaysir/taekbae --workflow collect-djtram.yml --limit 10
gh release download cloud-collector-state --repo ukaysir/taekbae --pattern "collector-state.tar.gz" --dir .tmp\cloud-collector
~~~

내려받은 자료를 현재 작업본에 복원할 때는 먼저 로컬 수집기를 중지하고 기존 `data/raw`와 `data/processed/traffic.sqlite`를 별도 백업한다. 그다음 압축을 작업 루트에 해제하고 `scripts/finalize_submission.ps1`로 준비상태를 재검증한다.

수집을 조기 중단하려면 다음 명령을 사용한다.

~~~powershell
gh workflow disable collect-djtram.yml --repo ukaysir/taekbae
~~~

초안 Release는 공개 저장소의 일반 Release 목록에 게시하지 않지만 저장소 쓰기 권한이 있는 계정과 워크플로가 접근할 수 있다. 최종 동결 후에는 필요한 산출물을 별도로 보관하고 임시 수집 Release를 삭제할 수 있다.
