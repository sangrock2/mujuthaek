# collector (지방 공사 공고·정책 API 수집 워커)

지방 공사 9곳의 주거 공고 게시판에서 새 모집공고를 모아요. 공고문·주택목록 원본을 S3에 저장하고 공고문 글자를 뽑아, `raw.notice.collected` 이벤트를 RabbitMQ로 보내요.
정책·혜택 공공 API 4곳(보조금24, 복지로 중앙·지자체, 온통청년)과 창업지원 공고 API 2곳(K-Startup, 기업마당)도 모아서 `raw.policy.collected` 이벤트로 보내요 ([정책 API 수집](#정책-api-수집)).

## 처음 실행
```bash
# 저장소 루트
make infra               # PostgreSQL·RabbitMQ·MinIO
make migrate-collector   # collector 테이블

# 여기 (services/collector)
uv sync
uv run pytest
uv run python -m mujuthaek_collector run-once dcco   # 대전 한 번 수집 (환경 변수 없이 로컬 값 사용)
```

## 명령
`uv run python -m mujuthaek_collector <명령>`

| 명령 | 하는 일 |
| --- | --- |
| `run` | 스케줄러로 계속 실행 + `:8091/health` (Docker 기본) |
| `run-once <출처> [--recheck]` | 출처 하나를 지금 수집하고 이벤트까지 발행. `--recheck`면 마감 전 공고를 다시 열어 정정 확인 |
| `run-all [--recheck]` | `sources.enabled`인 출처를 순서대로 |
| `run-policies` | `sources.enabled`인 정책 출처를 순서대로 (`run-once gov24`처럼 하나만도 돼요) |
| `relay` | 아웃박스 이벤트를 한 번 보내기 |
| `cleanup` | 보관 기한이 지난 원본 파일만 S3에서 지우기 |
| `save-fixtures <출처> [--details 3]` | 실제 목록·상세 화면을 `tests/fixtures/<출처>/`에 저장 (실제 사이트에 요청해요) |
| `status` | 최근 수집 회차 20개 |
| `intake [--decide]` | 처음 수집 개수 제한: 묶음마다 고른 결과·기다리는(HELD) 글. `--decide`면 지금 고르기 ([처음 수집 개수 제한](#처음-수집-개수-제한)) |
| `area-upload --source <원천> --data-date <기준일> --file <파일> [--scope <시도>]` | 생활권·상권 원천 파일을 S3 `area/{원천}/{기준일}/{영문 이름}.csv`로 올리고 `area.source.ready` 발행 (api가 받아 적재). 지하철 엑셀은 UTF-8 CSV로 바꿔 올려요. 같은 파일은 다시 올리거나 보내지 않아요 |
| `area-upload --manifest area/area_manifest.csv --skip-upload` | 이미 S3에 올린 파일 목록으로 적재 요청만 보내기 (S3 sha256 메타데이터를 확인해요). 2026-10-22에 올린 21개가 `area/area_manifest.csv`예요 |

출처: `sh`, `gh`, `bmc`, `ih`, `dcco`, `dudc`, `umca`, `gbdc`, `gndc`, `soco`, `lh` (LH는 API로 받고 `LH_API_KEY`가 필요해요 — `sources/lh/README.md`) / 정책: `gov24`, `bokjiro_central`, `bokjiro_local`, `youth`, `kstartup`, `bizinfo`

대구(`dudc`)는 robots.txt가 사이트 전체 수집을 막아서 꺼 두었어요(`sources.enabled = false`). 기관 허락을 받으면 다시 켜요.

## 처음 수집 개수 제한
배포 뒤 처음 한 번은 묶음마다 **최신 N개만** AI 추출로 보내고, 그 이전 글은 쓰지 않아요 (2026-10-27 결정, `core/intake.py`). 그 뒤로는 새로 올라온 글만 보내요.

| 묶음 | 무엇 | 개수 (환경 변수) |
| --- | --- | --- |
| `HOUSING_LH` | LH 주거 공고 | 10 (`COLLECTOR_INTAKE_HOUSING_LH`) |
| `HOUSING_OTHER` | LH 말고 다른 게시판 주거 공고 (합쳐서) | 10 (`COLLECTOR_INTAKE_HOUSING_OTHER`) |
| `SPACE` | 사업공간 모집 (`SPACE_RECRUITMENT`) | 10 (`COLLECTOR_INTAKE_SPACE`) |
| `POLICY` | 지원 정책 (혜택·창업 지원, 출처 합쳐서) | 500 (`COLLECTOR_INTAKE_POLICY`) |

- 고르기 전(`intake_decisions`에 그 묶음 줄이 없음): 새로 본 열 글은 상세를 열지 않고 `HELD`로 둬요
- 고르기: `run`이 뜰 때 모든 출처 목록을 읽고 `HELD` 중 날짜(게시판 게시일, 정책은 목록의 등록일)가 최신인 N개를 `PENDING`으로, 나머지를 `IGNORED`로 바꾼 뒤 고른 글을 바로 수집해요. 고른 글 중 가장 오래된 날짜가 기준일이에요. 그때 읽은 글이 없던 묶음은 매일 12시 30분에 다시 골라요
- 고른 뒤: 새 글은 바로 `PENDING`, 기준일보다 오래된 글과 쓰지 않는 공고의 정정·후속 안내는 `IGNORED`. `IGNORED`는 목록이 바뀌어도 다시 큐에 넣지 않아요
- 이미 수집해 발행한 데이터가 있던 DB(로컬·개발)는 마이그레이션이 고른 것으로 표시해서 지금처럼 동작해요 (`intake` → 「제한 없음」)

## 확인
| 무엇 | 어떻게 |
| --- | --- |
| 저장된 글 | `docker compose -f infra/docker-compose.yml --env-file infra/.env exec postgres psql -U collector_app -d collector -c "select source_code, post_key, status, title from raw_posts order by created_at desc limit 20"` |
| 저장된 정책 | `docker compose -f infra/docker-compose.yml --env-file infra/.env exec postgres psql -U collector_app -d collector -c "select source_code, policy_id, status, title from raw_policies order by updated_at desc limit 20"` |
| 원본 파일 | `docker compose -f infra/docker-compose.yml --env-file infra/.env exec minio mc ls --recursive local/mujuthaek-raw/raw/` |
| 보낸 이벤트 | RabbitMQ 관리 화면 http://localhost:15672 → Exchanges `mujuthaek.events` |
| 안 보낸 이벤트 | `select count(*) from outbox where published_at is null` |

## 테스트
```bash
uv run pytest                                  # 기관 사이트·S3·RabbitMQ에 요청하지 않아요
uv run pytest tests/test_sources.py -k dcco    # 한 출처만
```
- 실제 DB 테스트(`test_storage_postgres.py`)는 `COLLECTOR_TEST_DB_URL`이 있을 때만 돌아요. 테스트용 DB는 처음 한 번만 만들어요.

  ```bash
  # 저장소 루트
  docker compose -f infra/docker-compose.yml --env-file infra/.env exec postgres psql -U postgres -c "create database collector_test owner collector_app"
  docker compose -f infra/docker-compose.yml --env-file infra/.env --profile apps run --rm migrate-collector \
    -url=jdbc:postgresql://postgres:5432/collector_test -user=collector_app -password=collector-pass -locations=filesystem:/flyway/sql migrate
  # services/collector
  COLLECTOR_TEST_DB_URL=postgresql://collector_app:collector-pass@localhost:5432/collector_test uv run pytest tests/test_storage_postgres.py
  ```

- 저장 화면 테스트(`test_fixtures.py`)는 `save-fixtures`로 저장한 출처만 돌아요.

## 새 기관 붙이기
1. `sources/local/`에 `Source`를 상속한 파일을 추가해요. `list_request`, `parse_list`, `parse_detail` 세 가지만 구현하면 돼요.
2. `sources/registry.py`의 `build_sources`와 `ORDER`에 추가해요.
3. 새 마이그레이션으로 `sources` 테이블에 한 줄 넣어요. 기존 마이그레이션 파일은 고치지 않아요.
4. `save-fixtures <출처>`로 화면을 저장하고 테스트해요.

## Docker
```bash
docker build -f services/collector/Dockerfile -t mujuthaek-collector .   # 저장소 루트에서
make up                                                                   # 스케줄러까지 띄우기 (정해진 시간에 실제 사이트 수집)
```

## 정책 API 수집
코드: `src/mujuthaek_collector/sources/policy/`, 이벤트 계약: `contracts/events/raw.policy.collected.v1.json`

| 출처 | API | 첨부 |
| --- | --- | --- |
| `gov24` | 행안부 공공서비스(혜택) 목록·상세·지원조건 (`api.odcloud.kr/api/gov24/v3`) | API에 없음. 원문(www.gov.kr)은 robots.txt가 막아서 요청하지 않아요 (`attachments = NEVER`, 상태 `NOT_NEEDED`) |
| `bokjiro_central` | 복지로 중앙부처 복지서비스 목록·상세 (`B554287/NationalWelfareInformationsV001`) | 상세의 관련 서식(`basfrmList`) 중 안내문·지침만. 서식뿐이면 원문 화면에서 찾기 |
| `bokjiro_local` | 복지로 지자체 복지서비스 목록·상세 (`B554287/LocalGovernmentWelfareInformations`) | 관련 서식 중 안내문·지침만. 서식뿐이거나 없으면 관련 홈페이지(원문)에서 찾기 |
| `youth` | 온통청년 청년정책 (`youthcenter.go.kr/go/ythip/getPlcy`), 분류 조건 없이 전체 | API에 없음. 참고 주소(`refUrlAddr1·2`, 기관 원문 공고)에서 찾기 |
| `kstartup` | K-Startup 창업지원사업 공고 (`B552735/kisedKstartupService01/getAnnouncementInformation01`), 모집 중인 공고만 | API에 없음. **사업공간 모집만** 상세 화면(`detl_pg_url`) 본문을 읽어요 ('입주공간 및 이용료', 2026-10-22 결정). 첨부(`/afile/`)는 robots.txt 금지라 받지 않아요 (`origin_files = False`) |
| `bizinfo` | 기업마당 지원사업 공고 (`bizinfo.go.kr/uss/rss/bizinfoApi.do`), 게시 중인 공고 전체 | 본문 출력 파일(`printFlpthNm`, 모든 공고에 있어요)과 첨부(`flpthNm`). API 항목만으로는 부족해서 본문 파일 글자를 꼭 뽑아요 |

흐름
1. 목록을 끝까지 읽어요. 처음 본 정책과, 수정일(수정일이 없으면 목록 항목 해시)이 바뀐 정책만 PENDING이 돼요.
   1차 거름에 걸리지 않은 정책은 상세를 열지 않고 SKIPPED로 남겨요. API의 분류(복지로 관심주제, 보조금24 서비스분야, 온통청년 대분류)는 실제 내용과 맞지 않아서 요청 조건에 쓰지 않고, 목록 전체를 받은 뒤 골라요. 최종 판단은 AI 추출 단계가 해요. 회차마다 다시 판단하니까 기준을 넓히면 다음 회차에 PENDING으로 돌아와요.
   | 출처 | 통과 기준 | 통과 수 (2026-10-15) |
   | --- | --- | --- |
   | `gov24` | 서비스명·서비스목적요약에 이주 혜택(주거·전입·정착) 단어 (`base.SETTLE_WORDS`) | 10,968건 중 약 880 |
   | `bokjiro_central`·`bokjiro_local` | 이름·요약에 이주 혜택 단어 | 461건 중 약 45 / 4,822건 중 약 480 |
   | `youth` | 대분류 `주거` 또는 이주 혜택 단어 → `BENEFIT`, 중분류 `창업` 중 창업 공간·지원금·정책자금 → `STARTUP_SUPPORT`. 신청 기간(`aplyYmd`)이 끝난 정책은 빼요 (상시·기간 없음은 넣어요) | 3,255건 중 827 (창업 388 중 276), 마감 빼면 478 (2026-10-19) |
   | `kstartup` | 모집 중(`rcrt_prgs_yn=Y`)만 요청하고, 그중 창업 공간·지원금·정책자금 → `STARTUP_SUPPORT` | 모집 중 228건 중 82 (2026-10-18) |
   | `bizinfo` | 분야 대분류 `창업` 또는 공고명·해시태그에 창업 단어, 그중 창업 공간·지원금·정책자금 → `STARTUP_SUPPORT` | 1,436건 중 90 (2026-10-18) |

   신청이 끝난 정책(`source.closed`, 지금은 온통청년만)도 AI 추출 비용을 아끼려고 SKIPPED로 남겨요. 기관이 새 신청 기간으로 고치면 다음 회차에 PENDING으로 돌아와요.

   창업지원 범위는 **창업 공간 + 지원금·정책자금**이에요 (`base.startup_in_scope`). 출처 분류가 공간·자금이거나 이름(온통청년은 지원 내용도)에 공간·자금 단어가 있으면 넣고, 이름에 교육·멘토링·컨설팅·행사·경진대회·홍보 단어가 있으면 빼요(공간 단어가 같이 있으면 넣어요).
   **분류(`raw_policies.field`, 이벤트 `field`)**: 지원 정책(`BENEFIT`·`STARTUP_SUPPORT`)과 사업공간 모집(`SPACE_RECRUITMENT`)으로 나눠요 (2026-10-22 결정, `source.classify`).
   창업지원 중 이름이 입주·입점 모집, 임대 공급이면 `SPACE_RECRUITMENT`예요 (`base.SPACE_RECRUIT`, 창업보육센터·공유오피스 입주기업 모집, LH 업무시설 임대공급). 임대료를 대신 내주는 사업은 `STARTUP_SUPPORT`예요.
   **상가 모집은 수집하지 않아요** (2026-10-22 결정, `base.SHOP_RECRUIT`): 전통시장 청년몰 입점, 상가 임대공급, 청년상인·점포운영자 모집은 거름을 통과해도 SKIPPED. 점포 임차료 지원·상가 임대료 감면은 그대로 수집해요.
   원본은 `raw_policies` 한 테이블에 두고 이 칸으로 나눠요. 목록 단계에서 정해 저장하고, 추출 결과는 지원 정책은 `benefits`, 사업공간 모집은 `space_recruitments`에 저장해요 (`contracts/schemas/*-extracted.draft.md`).
   보조금24는 열 정책이 20건 이상이면 상세·지원조건을 1000건씩 한꺼번에 받아요(정책마다 2번 대신 모두 합쳐 22번).
2. PENDING 정책을 회차마다 `POLICY_DETAIL_LIMIT`건까지 처리해요. 상세 API → 첨부(API 첨부, 없으면 원문 화면의 첨부 링크) → 공고·안내 문서 글자 뽑기 → 버전 비교 → 저장 + 이벤트.
3. 수정일만 바뀌고 내용·첨부가 같으면 새 버전을 만들지 않아요. 조회수도 비교에서 빼요.

저장 위치: 정책 전용 테이블이에요 (`V202610220910__collector_policy_tables.sql`). 수집 회차(`crawl_runs`)와 `outbox`만 게시판 수집과 같이 써요.

| 테이블 | 내용 |
| --- | --- |
| `raw_policies` | 정책 한 건. 6개 API의 칸을 통일한 값(제목·요약·기관·지역·field·분야·상세/신청 주소·출처 수정일) + 목록 응답 원본 `list_raw` + 상태(SKIPPED·PENDING·DONE·FAILED) |
| `raw_policy_versions` | 내용이 바뀔 때마다 한 줄. 통일한 내용 칸(지원대상·선정기준·지원내용·신청방법·신청기간·제출서류·나이) + 응답 원본 `api_raw` + `document_status`·`origin_status` + AI에 넘긴 `full_text` |
| `raw_policy_files` | 첨부 (role `POLICY_DOC` 글자를 뽑은 문서·`ATTACHMENT` 글자를 못 뽑은 설명 문서, found_on `API`·`ORIGIN_PAGE`, S3 `raw/<출처>/<정책 ID>/v<버전>/`) |
| `raw_policy_texts` | 첨부에서 뽑은 글자 |

첨부·원문 상태: `OK` 있음, `NONE` 확인했지만 없음(서식·포스터만 있음, 정책과 무관한 화면 포함), `NO_SOURCE` 볼 곳이 없음, `BLOCKED` robots.txt 등으로 확인 못 함, `FAILED` 받기·글자 뽑기 실패, `NOT_OPENED`(원문만) API가 첨부를 줘서 열지 않음

원칙
- 원문 화면·첨부는 기관 사이트라 `PoliteClient`로 robots.txt를 지키고 4초 간격으로 요청해요. 막힌 도메인은 그 회차에 다시 묻지 않아요.
- **AI 비용을 줄이려고 출처마다 첨부를 다르게 봐요** (`PolicySource.attachments`, 2026-10-19 기준 AI 입력 662만 자 → 약 300만 자).

  | 출처 | 첨부·원문 화면 | 이유 |
  | --- | --- | --- |
  | `bizinfo` | 항상 (공고문 1개) | API 개요의 약 60%가 '공고문 참조'뿐 |
  | `youth` | 항상 (참고 주소의 공고문 1개) | API에 첨부가 없고 원문이 공고 화면 |
  | `bokjiro_local` | API 설명 칸이 700자 미만이거나 '공고문 참조'일 때만 (`WHEN_THIN`) | 설명 칸이 충분한 정책이 많아요 |
  | `bokjiro_central` | 보지 않음 (`NEVER`) | 설명 칸이 길고(중앙값 약 3,400자), 첨부는 수백 쪽 지침서 |
  | `gov24` | 보지 않음 (`NEVER`) | API에 첨부가 없고, 원문(www.gov.kr)은 robots.txt가 막아요 |
  | `kstartup` | 사업공간 모집만 상세 화면 본문 | API에 첨부가 없어요. 첨부 파일은 robots.txt 금지라 받지 않아요 |

  첨부를 보지 않은 정책은 `document_status = NOT_NEEDED`예요. 글자를 뽑은 문서가 1개 생기면 더 받지 않아요 (`MAX_TEXT_DOCS`).
- AI 입력(`full_text`)에는 API 항목 중 **설명 칸만** 넣어요 (`PolicySource.ai_keys`: 대상·선정기준·지원내용·신청방법·기간·요약·분류). 주소·파일 경로·연락처·서식 목록·근거 법령, 규칙으로 옮기는 코드 칸(온통청년 `zipCd`·직업·학력 코드, 보조금24 `지원조건`)은 빼요. 원본은 `api_raw`와 이벤트 `record`에 그대로 있어요. 버전 비교(`content_hash`)는 전체 항목(`body_text`)으로 해서, 빠진 칸이 바뀌어도 새 버전이 돼요.
- 첨부는 AI 추출에 쓸 **설명 문서(공고문·안내문·지침·사업 계획, 지자체 조례·시행규칙, pdf·hwp·hwpx)만** 받아요 (`attachments.explains`). 신청서·서식·동의서·수령증, 포스터·홍보물, 명단·현황, 국가 법령·시행령·훈령·고시·예규·업무 편람, `첨부파일없음.hwp` 같은 빈 파일, 그림·압축·엑셀 파일은 받지 않아요. API 첨부가 서식뿐이면 원문 화면에서 공고문을 찾아요.
- 원문 화면의 첨부 링크는 게시판 다운로드 주소이거나 한글 이름인 파일만 써요 (`attachments.origin_file_ok`). 사이트 하단 공통 파일(웹 접근성 인증서, 전화번호부, 외국인 이용 안내 …)은 영문·숫자 이름의 정적 파일이에요. 화면이 정책과 관련 없으면(사이트 첫 화면) 이름에 정책 핵심 단어가 있는 파일만 써요.
- 첨부 문서 하나가 1만 자를 넘으면(사업 안내 지침서 한 권 등) AI 입력(`full_text`)에는 정책 이름의 핵심 단어가 나오는 부분만 골라 넣어요 (`attachments.focus`, 빠진 곳은 `[… 생략 …]`). 핵심 단어가 한 번도 안 나오면 넣지 않아요. 뽑은 글자 전체는 `raw_policy_texts`에 그대로 둬요. PDF 글꼴 문제로 `(cid:12)…`만 나오면 글자 뽑기 실패로 봐요.
- 인증키는 주소에 들어가서, 오류 메시지·DB 기록에서는 `***`로 가려요.

환경 변수 (`infra/.env.example`)

| 이름 | 기본 | 설명 |
| --- | --- | --- |
| `DATA_GO_KR_SERVICE_KEY` | 없음 | 공공데이터포털 인증키 (보조금24·복지로·K-Startup). 인코딩·디코딩 키 둘 다 돼요 |
| `YOUTHCENTER_API_KEY` | 없음 | 온통청년 인증키 |
| `BIZINFO_API_KEY` | 없음 | 기업마당 인증키 (K-Startup은 `DATA_GO_KR_SERVICE_KEY`를 같이 써요) |
| `POLICY_YOUTH_CATEGORIES` | 빈 값 | 온통청년을 정책 대분류로 좁혀 받기, 쉼표로. 빈 값이면 전체를 받고 수집기가 골라요 |
| `POLICY_DETAIL_LIMIT` | `300` | 한 회차에 상세·첨부를 처리하는 정책 수 |
| `POLICY_API_DELAY_SECONDS` | `1.0` | 같은 API 도메인 요청 간격 |
| `POLICY_MAX_FILES` | `5` | 정책 하나에서 받는 첨부 수 |

스케줄: 매일 11시 전체, 금요일 13시 다시 확인(목록에 수정일이 없는 `bokjiro_central`만 전부 다시 열어요).
처음에는 보조금24가 1만 건이 넘어서 하루 300건씩 채워져요. 빨리 채우려면 `POLICY_DETAIL_LIMIT`를 올리거나 `run-once gov24`를 여러 번 실행해요 (공공데이터포털 하루 호출 한도 확인).

로컬에서 실제 API로 실행 (Docker 밖, `services/collector`에서)
```bash
make -C ../.. infra migrate-collector   # 인프라와 테이블 (새 마이그레이션이 있으면 적용)
set -a; . ../../infra/.env; set +a       # 인증키(DATA_GO_KR_SERVICE_KEY, YOUTHCENTER_API_KEY, BIZINFO_API_KEY)
export AWS_ACCESS_KEY_ID="$MINIO_ROOT_USER" AWS_SECRET_ACCESS_KEY="$MINIO_ROOT_PASSWORD"   # MinIO 키
uv run python -m mujuthaek_collector run-once kstartup
uv run python -m mujuthaek_collector run-policies   # 정책 출처 전체
```
- MinIO 키를 넘기지 않으면 수집기 기본값(`minio` / `minio-pass`)을 써요. `infra/.env`의 `MINIO_ROOT_USER`·`MINIO_ROOT_PASSWORD`를 바꿨다면 첨부 저장이 `InvalidAccessKeyId`로 실패하고 그 정책은 FAILED가 돼요. Docker로 띄우면(`make up`) compose가 넘겨줘요.
- 실행이 끝나면 이벤트 발행(relay)도 해요. 이벤트를 받는 서비스(extraction)가 아직 큐를 만들지 않았으면 `UnroutableError`가 나요. 이벤트는 `outbox`에 남아 있다가 큐가 생기면 보내져요.
- 기업마당 첫 실행은 첨부 약 200개를 4초 간격으로 받아서 15분쯤 걸려요. 다음부터는 바뀐 공고만 받아요.

```bash
uv run pytest tests/test_policy_sources.py tests/test_policy_pipeline.py
```

새 정책 출처 붙이기 (게시판 `새 기관 붙이기`와 같은 모양)
1. `sources/policy/`에 `PolicySource`를 상속한 파일을 추가해요. `list_request`, `parse_list`, `parse_detail` 세 가지를 구현하고, 필요하면 `detail_requests`(상세 API), `wanted`(1차 거름), `segments`(나눠 받기), `prefetch`(한꺼번에 받기)를 바꿔요.
2. `sources/policy/registry.py`의 `build_policy_sources`와 `POLICY_ORDER`에 추가해요.
3. 새 마이그레이션으로 `sources` 테이블에 한 줄 넣어요.
4. 응답 예시를 `tests/policy_samples.py`에 넣고 테스트해요. 메모리 저장소는 `tests/policy_fakes.py`에 있어요.
