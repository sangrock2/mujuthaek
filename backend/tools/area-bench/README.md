# area 저장·조회 방식 비교 도구

문서 "area 저장·조회 방식 비교"의 측정을 그대로 다시 돌려요. 앱 코드가 아니라 CI에서는 돌지 않아요.

## 돌리기

```bash
cd tools/area-bench
export BENCH_PSQL="psql postgresql://<user>:<password>@localhost:5432/<db>"
export BENCH_DSN="host=localhost dbname=<db> user=<user> password=<password>"
uv run --with "psycopg[binary]" bash run.sh real        # 원천 21개를 실제로 적재한 DB
uv run --with "psycopg[binary]" bash run.sh synthetic   # area 마이그레이션만 된 빈 DB (가짜 자료 277만 줄을 만들어요)
```

결과는 `results-<모드>-<날짜>.txt`에 남아요. 전체 7~10분 걸려요.

## 무엇을 재나

| 비교 | 내용 |
| --- | --- |
| A. 세권 지표 계산 | 지표 14개 × 단지 3,000곳을 지표마다 따로 / 단지마다 한 쿼리 / 전체 한 쿼리로. 공간 인덱스 하나일 때와 종류별 부분 인덱스 8개를 더했을 때 |
| B. 목록 API 읽기 | 공고 20개·300개에 점수·지표 붙이기: 조인 한 번 / ID 묶음 두 번 / N+1 |
| C. 파티션 | 상가 시도별 파티션과 테이블 하나: 단지 하나 조회, 전체 한 쿼리, 서울 다시 넣기(테이블 하나는 시간만 재고 되돌림) |

`real` 모드는 공고 단지가 아직 없어서(3단계 전) 실제 버스정류장 3,000곳을 단지 위치로 써요(시드 고정).

## 주의

- `synthetic`은 `area.stores`·`area.facilities`를 비우고 가짜 자료를 넣어요. 실제 적재 기록(`load_runs` 성공)이 있는 DB에서는 멈춰요.
- `real`은 실제 자료를 바꾸지 않아요. `bench` 스키마, 부분 인덱스, `area.stores_part`를 만들었다가 끝에 지워요.
- "서울 다시 넣기"의 기준일 갱신(UPDATE) 시간은 v1 적재기 비교용이에요. 이미 같은 기준일이면 0줄로 나와요.
