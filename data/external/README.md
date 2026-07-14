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
- `sbiz_stores_20260331.zip`
  - 출처: 공공데이터포털 `소상공인시장진흥공단_상가(상권)정보_20260331`
  - 공식 상세: `https://www.data.go.kr/data/15083033/fileData.do`
  - 크기: 341,021,001바이트
  - SHA-256: `1cf968e5b3e428bd46ad8f64f6e7c39da52c9b60d023a473b46163577484c6e9`
  - 이용허락범위: 제한 없음, 분기 갱신
- `sbiz_stores_daejeon_202603.csv`
  - 위 ZIP의 대전광역시 CSV만 추출한 로컬 작업본
  - 78,607행, 41,866,930바이트
  - SHA-256: `ad252b91748ca35889370fe664326fa6acc145457252f77c031b13e92201c470`
  - 상가업소번호·경도·위도를 250m 배송노출 대리값 계산에 사용

해시와 통행축 근거 재생성:

~~~powershell
.\.venv\Scripts\python.exe -m taekbae build-corridor-evidence
.\.venv\Scripts\python.exe -m taekbae build-exposure
~~~

원본이 없으면 명령은 실패해야 하며, 다른 파일의 해시가 나오면 분석을 중단한다.
