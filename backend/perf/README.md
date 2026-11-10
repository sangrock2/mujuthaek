# 성능 테스트 (perf)

운영(prod) 서버에 k6로 부하를 주고, 그 구간의 숫자·그래프 이미지·느린 쿼리·버전·데이터 양을 **결과 폴더 하나**에 모아요. 개선 전에 잰 폴더와 개선 후 폴더를 `compare.sh`로 나란히 비교해요.

```
노트북                                         운영 EC2 (127.0.0.1에만 열림)
 k6 ──────── http://3.37.131.73 (nginx) ────▶ api
 Prometheus ◀─ SSH 터널(tunnel.sh) ─────────── api·notification /actuator/prometheus, node-exporter, cAdvisor
 Grafana(3300) + 이미지 렌더러                  RDS ◀─ server.sh가 서버 안에서 psql (pg_stat_statements)
```

## 처음 한 번 (사용자가 할 일)

| 언제 | 할 일 | 비고 |
|---|---|---|
| 지금 | AWS 보안 그룹: 내 IP에서 EC2 22·80 열려 있는지 | |
| 지금 | EC2 크레딧 모드(Standard·Unlimited) 확인 | Standard면 테스트 사이 30분 쉬기 |
| 지금 | `cp perf/.env.example perf/.env` 후 SSH 키·인스턴스 id 채우기 | `perf/.env`는 커밋되지 않아요 |
| 지금 | `perf/server.sh version` 으로 SSH·버전 확인 | |
| 지금(권장) | RDS **api DB**에 `CREATE EXTENSION IF NOT EXISTS pg_stat_statements;` (마스터 계정) | `shared_preload_libraries`에 없으면 파라미터 그룹 수정 + 재부팅. `perf/server.sh check`로 확인 |
| 지금(선택) | 테스트 계정: 소셜 로그인으로 가입 → 회원 id를 `TEST_USER_ID`에, 운영 `JWT_SECRET`을 `perf/.env`에 | 비우면 로그인 흐름(15%)을 판정 흐름으로 돌려요. **나중에 넣으면 baseline을 다시 재야 해요** |
| 배포 | 이 브랜치(지표 노출)가 prod에 배포돼 있어야 해요 | `/actuator/prometheus`가 있어야 서버 쪽 숫자가 나와요 |
| 테스트 날 | 운영 슬랙 알림 채널에 공지(스트레스·스파이크에서 5xx 알림이 몰려요), 팀에 시간 공지(RDS를 dev와 같이 써요) | |

## 테스트 날 순서

```bash
docker compose -f perf/docker-compose.yml up -d   # Prometheus·Grafana (http://localhost:3300)
perf/server.sh exporters-up                        # 서버에 node-exporter·cAdvisor
perf/tunnel.sh                                     # ← 다른 터미널에 켜 두기

perf/run.sh smoke                                  # 먼저 스모크로 결과 폴더가 다 차는지 확인
perf/run.sh load
perf/run.sh soak                                   # 1시간, 18시(11/7부터 19시) 자동 중지 전에
perf/run.sh stress                                 # 사이사이 30분 쉬기(크레딧)
perf/run.sh breakpoint
perf/run.sh spike

perf/server.sh exporters-down                      # 다 끝나면
```

- 11:00~11:45에는 돌리지 않아요. 일일 정리 작업(혜택 상태, 토큰·outbox·요청 로그 정리)이 이때 돌아요.
- k6 종료 코드 99는 합격 기준을 넘었다는 뜻이고, 결과는 그대로 모아요. 스트레스·한계 찾기는 기준을 넘고 1분 뒤 스스로 멈춰요.
- 끝나면 문서 「결과 기록」 표에 붙일 한 줄을 출력해요.

## 결과 폴더

`perf/results/<yyyyMMdd-HHmm>_<test>_<api 버전>/` (커밋되지 않아요. 지우지 말고 보관해요)

| 파일 | 내용 |
|---|---|
| `meta.json` | 시각, api·notification 버전, 부하, 메모, 로그인 흐름 포함 여부, k6 종료 코드, perf 스크립트 커밋, data.json 해시 |
| `summary.json` · `k6.log` · `k6-report.html` | k6 결과(API 종류별 p95·p99, RPS, 에러율). html은 브라우저로 여는 그래프 리포트 |
| `server_summary.json` | 서버 p95·p99, CPU 평균·최대, steal, 힙, GC, Hikari 사용·대기 최대, 컨테이너별 CPU·메모리 |
| `server_by_uri.csv` | API(경로)별 서버 p95·p99·평균·건수·5xx |
| `stages.csv` | 스트레스·한계 찾기만: 단계별 RPS·에러율·p95, 기준을 처음 넘은 단계(`over`) |
| `slow_queries.csv` | 테스트 동안 DB 시간을 많이 쓴 쿼리 50개 (pg_stat_statements 전후 차이) |
| `table_counts.csv` | 테이블별 행 수 — 전후에 데이터 양이 크게 다르면 비교가 틀어져요 |
| `images/00-dashboard.png`, `01~15.png` | Grafana 패널 이미지(응답 시간, RPS, 에러율, 서버 p95·p99, CPU·steal, 컨테이너, 힙, GC, Hikari …) |
| `images/cw-*.png` · `cloudwatch.json` | CloudWatch: EC2 CPU·크레딧, RDS CPU·커넥션·메모리·IO |
| `timeseries/NN.csv` | 패널과 같은 쿼리의 15초 간격 숫자 |
| `prometheus_snapshot.txt` | Prometheus 스냅숏 이름. 원본 시계열은 `perf-prometheus-data` 볼륨에 남아요 |

CloudWatch는 몇 분 늦게 채워져요. 비어 있으면 10분 뒤 `perf/collect.sh perf/results/<폴더>`로 다시 모아요(그래프·서버 지표도 다시 받아요).

## 고친 뒤

```bash
perf/run.sh load "Hikari 풀 10 → 20"                # 메모가 meta.json과 표의 「고친 것」에 들어가요
perf/compare.sh perf/results/<전 폴더> perf/results/<후 폴더> > 비교.md
```

비교가 맞으려면 같게 둬요: `k6/data/data.json`(다시 뽑지 않기), `k6/lib/config.js`·`flows.js`(바꾸면 meta.json의 perf 커밋이 달라져요), 테스트 시간대, 로그인 흐름 포함 여부. 한 번에 하나만 고쳐요.

## 시나리오

`k6/main.js`가 반복마다 흐름 하나를 골라요: 둘러보기 60% · 조건 넣고 판정 25% · 로그인 사용자 15%, 행동 사이 3~5초. 한계 찾기는 쉬는 시간 없이 반복 한 번에 요청 한 건이라 초당 반복 수가 곧 RPS예요.

| 종류(태그 `type`) | p95 / p99 기준 | API |
|---|---|---|
| 조회 `lookup` | 200ms / 500ms | regions, eligibility/criteria, push/public-key, users/me·favorites·notifications·notification-settings, 관심 등록·해제 |
| 목록·검색 `search` | 500ms / 1s | home/summary, notices/search, notices/map, notices/{id}, benefits·spaces·supports/search (조건 없이) |
| 판정 `judge` | 1s / 2s | benefits/search·notices/search·home/summary + 지원자 조건 |

- 모든 검색은 POST + JSON 바디예요. 지원자 조건은 `data.json`의 가짜 조합 4개(사람 값 아님)에 시군구만 바꿔 넣어요.
- `/api/auth/refresh`는 뺐어요: refresh 토큰이 HttpOnly 쿠키라 쓰면 테스트 계정 로그인이 돌아가며 바뀌어요.
- 관심 등록은 등록 직후 해제해서 운영 DB에 남지 않아요. 남았으면 테스트 계정 화면에서 지워요.
- 외부 API를 부르는 기능(주소 좌표, AI 추출)과 관리자 API는 부르지 않아요.

## 알아 둘 것

- 요청마다 `RequestLogFilter`가 요청 로그를 DB에 써요(5초마다 모아서). 운영과 같은 조건이라 그대로 두고 재요. 전후 비교도 같은 조건이에요.
- api DB 커넥션 풀(Hikari)은 기본값 10, 가상 스레드 켜짐이에요. 유력한 병목이지만 baseline을 재기 전엔 바꾸지 않아요.
- `k6/data/data.json`은 `k6/fetch-data.sh`로 운영에서 뽑은 값이에요. baseline 뒤에는 다시 뽑지 않아요.
- Grafana 대시보드를 고치려면 `lib/dashboard.py`를 고치고 `python3 perf/lib/dashboard.py`. 패널 순서(id)는 결과 이미지 이름이라 끝에만 더해요.
