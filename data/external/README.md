# 외부 데이터 위치

대용량 원자료는 이 폴더에 두되 Git에는 커밋하지 않는다. 각 데이터의 출처, 다운로드 시각, 해시와 이용조건은 `docs/sources.md`에 기록한다.

## 현재 로컬 원본

- `NODELINKDATA_2024-11-29.zip`
  - 출처: ITS 국가교통정보센터 노드·링크 자료실
  - 공식 첨부: `[2024-11-29]NODELINKDATA`
  - 크기: 125,973,128바이트
  - SHA-256: `4ddd6632756204c7fc8a429bfc57a91215f38138f1e78e65d65778e4b9187e90`
  - 다운로드 URL: `https://www.its.go.kr/opendata/nodelinkFileSDownload/DF_196/0`
- `nodelink_2024_11_29/`
  - 위 ZIP을 해제한 로컬 작업본
  - `MOCT_NODE`, `MOCT_LINK` shapefile 사용
  - 좌표계: ITRF2000 Central Belt 60, EPSG:5186

해시와 통행축 근거 재생성:

~~~powershell
.\.venv\Scripts\python.exe -m taekbae build-corridor-evidence
~~~

원본이 없으면 명령은 실패해야 하며, 다른 파일의 해시가 나오면 분석을 중단한다.
