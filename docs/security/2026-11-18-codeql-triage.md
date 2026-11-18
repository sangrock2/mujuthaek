# CodeQL 19건의 개별 검토

범위: main의 열린 경보 19건. 경보를 줄이기 위해 분석 언어·규칙·검사 경로를 제외하지 않는다. 코드 수정과 근거가 있는 오탐 분류를 구분한다. 사용자는 서비스에 문제가 없는 범위의 조치를 승인했다.

## 코드 보완 대상

| 경보 | 판단과 변경 |
| --- | --- |
| #25 | NoticeQueries의 날짜 대체값은 서버 상수이며 외부 문자열 삽입은 확인되지 않았다. 그래도 SQL에 날짜 문자열을 연결하지 않고 NamedParameterJdbcTemplate의 날짜 바인딩으로 바꾼다. 정렬 방향과 커서 의미는 유지한다. |
| #26 | 테스트가 만든 UUID지만 PreparedStatement로 위치 ID를 바인딩해 경보 지점의 문자열 결합을 없앤다. |
| #9 | CSP의 script-src 토큰 배열에 Array.includes로 정확히 일치하는 항목을 검사하는 코드다. 부분 문자열 검사가 아니지만 분석기의 혼동을 줄이기 위해 Set.has로 명시한다. |

## 근거를 남겨 분류할 대상

| 경보 | 분류 | 실제 입력·사용 경로와 근거 |
| --- | --- | --- |
| #1–8 | used in tests | 대전 기관 원본 HTML을 보존한 collector/tests/fixtures/dcco 자료다. test_dcco_fixtures.py가 read_text 후 서버 측 HTML 파서로 분류·첨부 선택에 사용한다. 브라우저에서 스크립트를 실행하거나 public 정적 자산으로 배포하는 경로가 없다. 원본을 수정하면 파서 회귀 자료의 충실도가 낮아져 그대로 보존한다. 이 판정은 해당 8개 fixture에만 적용한다. |
| #16 | false positive | 서비스 격리 도구는 RabbitMQ가 지정한 salt 4바이트 + SHA-256 포맷을 구현한다. 사람이 정한 로그인 비밀번호의 저장 기능이 아니며 prepare는 secrets.token_hex(32)로 서비스별 256비트 무작위 자격증명을 생성한다. readiness는 64자리 hex 및 서로 다른 값을 요구한다. 해시를 bcrypt로 독자 변경하면 RabbitMQ 인증이 깨진다. |
| #15 | false positive | secret_errors는 비밀값을 발견하지만 값 대신 PRIVATE_URL과 정제한 JSON 위치만 반환한다. diagnostic_path는 자유 형식 키도 숨긴다. jsonschema의 원본 error.message도 출력하지 않는다. 합성 비밀값·잘못된 타입·자유 키를 이용한 관련 회귀 검사를 확인한다. |
| #20 | false positive | 조건에 따라 생략되는 WithdrawalSession.clear는 인증/인가 검사가 아니라 일반 로그인에서 이전 탈퇴 세션 표시를 지우는 처리다. 유효한 탈퇴 티켓에서는 start가 표시를 교체하고 재인증 매개변수를 추가한다. 제공자 등록 검사·43자 티켓 검사·OAuth 기본 resolver의 state·콜백 검증은 우회하지 않는다. |
| #17 | false positive | 일반 API 인증은 Authorization Bearer이며 세션으로 회원 요청을 인증하지 않는다. 쿠키를 쓰는 refresh/logout만 POST, HttpOnly·Secure(운영)·SameSite=Lax·Path=/api/auth다. Spring CORS 필터는 정확한 허용 Origin 밖의 요청을 실행 전 거절한다. SecurityIntegrationTest의 untrustedOriginsCannotRefreshOrLogOutEvenFromASiblingSite가 악성·형제 도메인·null Origin 거절과 정상 Origin 성공을 검사한다. OAuth state 보호는 별도 기본 resolver로 유지한다. CSRF disable만 보고 동등한 보호가 없는 것으로 분류된 경보이며, 쿠키 인증 API 추가·SameSite/Origin 변경 시 반드시 재검토한다. |
| #10·13 | false positive | run-e2e.mjs의 spawn은 shell:false이고 실행 파일은 저장소 코드의 상수 또는 process.execPath다. 추가 argv는 개발자가 지정하는 로컬 Playwright 옵션이며 HTTP·PR 본문·workflow_dispatch 입력을 실행 명령으로 전달하지 않는다. Windows의 cmd.exe 호출은 고정 gradlew 명령이다. E2E_PROJECT도 제한된 패턴으로 검증하며 provider 비밀은 isolatedEnvironment가 제거한다. |
| #11 | false positive | 파일에서 읽는 이전 preview 정보가 호출 대상을 정하지 않는다. fetch 대상은 코드에 고정된 127.0.0.1:18080이며 준비 ID는 검증하고 재개 토큰도 48자리 hex만 허용한다. 외부 네트워크로 파일을 유출하는 경로가 아니다. |
| #12 | false positive | 출력 경로는 저장소 아래 고정 test-results/servers/preview.json이며 서버 응답이 경로를 정하지 않는다. 저장값은 로컬 합성 테스트의 PID·프로젝트·검증된 준비 ID·무작위 진입 URL이다. 응답 본문·실제 토큰·프로바이더 자격증명을 파일로 저장하지 않는다. 로컬 Docker만 허용하고 기존 포트가 사용 중이면 중단한다. |

오탐 처리는 각 경보에 개별 이유를 기록하고 다시 조회해 상태를 확인한다. 이후 코드 분석의 새 경보는 계속 검사한다. 현재 도구의 신뢰 모델이 달라지거나 fixture를 브라우저에서 실행하게 되면 해당 판정을 재검토한다.

## 공식 근거

- [RabbitMQ 비밀번호 해시 규격](https://www.rabbitmq.com/docs/passwords): 기본 SHA-256 및 salted hashing 형식. 운영자 도구의 포맷 호환성이 필요하다.
- [Spring Security CSRF 설명](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): 인증 전달 방식과 쿠키 사용에 따른 보호를 함께 평가한다. STATELESS라는 이유만으로 안전하다고 판단하지 않는다.

검사 결과·PR·main 분석 완료 상태는 적용 후 아래에 추가한다. 코드 보완 3건은 수정 PR이 main에서 분석되기 전까지 해결 완료로 세지 않는다.
