# Streamlit Cloud 배포용 안내

## 저장소 구조

```text
your_repository/
├── app.py
├── requirements.txt
└── data/
    ├── 고령자현황_내국인_구별_2024.csv
    ├── 2024_서울시_국민기초생활수급자_일반+생계+의료+구별_65세이상.csv
    ├── 독거노인_기초수급.csv
    ├── 독거노인_저소득.csv
    ├── 독거노인_총.csv
    └── seoul_municipalities_geo_simple.json
```

## 실행 방법

```bash
py -m streamlit run app.py
```

## 앱 기능

- 원천 데이터 5종을 자동으로 읽어 4개 지표 계산
- 4개 지표 지도 동시 비교
- 지표별 상세 지도와 자치구 순위표 제공
- 자치구 선택 시 기본지표 1, 2, 3에 대해
  - 선택 자치구 도넛차트
  - 서울시 전체(합계 기준) 도넛차트
  - 실제 인구수와 비중 동시 표시
- 계산 결과 CSV 다운로드

## Streamlit Community Cloud 배포

1. GitHub 저장소에 `app.py`, `requirements.txt`, `data/` 폴더 업로드
2. Streamlit Community Cloud에서 저장소 연결
3. Main file path를 `app.py`로 설정
4. Deploy 클릭

## 참고

- 앱은 `data/` 폴더를 우선 탐색합니다.
- `data/` 폴더가 없더라도 동일 경로에 파일이 있으면 로컬에서 동작하도록 fallback이 포함되어 있습니다.
- 서울시 비교용 도넛차트는 실제 인구수 표기를 위해 서울시 전체 합계 기준으로 계산합니다.
