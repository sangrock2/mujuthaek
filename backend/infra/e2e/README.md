# 실제 API 브라우저 검증

저장소 루트의 `frontend/`에서 실행합니다. JDK 25, Node.js 24+, 지정 pnpm, 실행 중인 Linux Docker 엔진이 필요합니다. Windows·Ubuntu를 지원합니다.

```bash
pnpm install --frozen-lockfile
pnpm exec playwright install chromium
pnpm test:e2e
# 한 기기만 확인
pnpm test:e2e --project=mobile
# 실제 브라우저에서 직접 조작 (로그에 표시되는 PREVIEW_URL을 연다)
pnpm preview:api
# 미리보기의 체크 상태·할 일을 유지하며 다시 시작
pnpm preview:resume
```

Linux CI의 브라우저 OS 의존성까지 설치하려면 `pnpm exec playwright install --with-deps chromium`을 사용합니다. GitHub의 `Real API E2E` 워크플로는 이를 포함합니다.

실행기는 전용 Compose project로 PostGIS·RabbitMQ·MinIO를 띄우고 API·notification의 `e2eRun`을 실행합니다. Next는 `NEXT_PUBLIC_USE_MOCKS=false`와 전용 API_ORIGIN으로 프로덕션 빌드한 뒤 실행합니다. `.env.local` 등 기존 파일을 수정하지 않습니다. `NEXT_PUBLIC_API_BASE_URL`도 실행기에서 비워 같은 출처 rewrite를 거칩니다.

| 포트(loopback) | 대상                             |
| -------------- | -------------------------------- |
| 13000          | Next                             |
| 18080 / 18081  | API / notification E2E 전용 서버 |
| 15439          | PostGIS                          |
| 15679          | RabbitMQ AMQP                    |
| 19009          | MinIO                            |

포트가 이미 사용 중이면 기존 서버를 재사용하지 않고 실패합니다. 앱 서버는 loopback에만 바인딩하고 제어 API에는 실행마다 생성하는 키를 요구합니다. 전용 데이터베이스 이름·계정은 E2E 설정에 고정하고 실제 계정·외부 OAuth·유료 모델·실발송은 사용하지 않습니다. 테스트 로그인은 실제 소셜 로그인 서비스와 토큰·HttpOnly refresh 쿠키 발급을 거치되 제공자 네트워크만 제외합니다.

공고는 계약 예제를 바탕으로 실제 `NoticeIngestionService`로 반영합니다. 한 고정 공고와 서로 다른 입력으로 충족·확인 필요·불충족을 확인합니다. 테스트 PDF는 한 쪽 ASCII 문서이며 API의 원문 경로와 실제 MinIO를 통해 읽고 근거 문장 강조까지 확인합니다. notification은 실제 outbox·RabbitMQ·DB·채널·워커를 사용하고 외부 전송 인터페이스만 기록기로 바꿉니다. 알림함뿐 아니라 그 기록도 확인합니다.

테스트마다 fixture를 초기화합니다. 초기화·로그인·정정·마감 작업 제어 코드는 `src/e2e`에만 있으며 운영 jar에는 포함되지 않습니다. 각 Java `check`의 `verifyE2eIsolation`이 운영 jar에 제어 코드와 e2e 설정이 없는지 확인합니다. 운영 앱에서 profile 이름만 바꿔 제어 기능을 켤 수 없습니다.

자동 테스트는 완료·실패·중단 시 자식 프로세스와 해당 Compose project의 컨테이너·볼륨·네트워크를 정리합니다. 미리보기는 자식 프로세스 종료와 컨테이너 중지만 수행해 준비 기록을 보존합니다. 기존 개발/운영 project에는 접근하지 않습니다. 강제 종료 후 잔여 자원을 완전히 지워야 하면 **해당 실행 로그의 `mujuthaek-e2e-...` 이름**을 확인해 그 project에만 `docker compose -p <이름> -f backend/infra/e2e/compose.yml down --volumes`를 실행합니다(저장소 루트 기준). 이 명령은 미리보기의 저장 기록도 삭제합니다.

실패 보고서는 `frontend/playwright-report/`, trace·스크린샷·서버 로그는 `frontend/test-results/`에 있습니다. 모두 Git·ESLint·Prettier 대상에서 제외합니다. CI에서는 합성 계정의 보고서를 7일 보관합니다. trace에는 테스트 쿠키·제어 키가 들어갈 수 있으나 전용 프로세스·DB가 종료되면 사용할 수 없고 운영 서명 키와도 분리돼 있습니다.

실제 제공자 OAuth, 배포 HTTPS·도메인 쿠키, 실제 단말 푸시 수신은 이 자동 검증 범위 밖이며 staging에서 별도로 확인합니다.

미리보기 모드는 13001 포트의 임의 진입 주소에서 테스트 계정으로 로그인시킨 뒤 준비함을 연 채 유지합니다. `preview:api`는 새 예시 데이터를 만들고, `preview:resume`는 `test-results/servers/preview.json`의 이전 project와 준비 기록을 재사용합니다. 미리보기 종료 시에는 컨테이너를 중지해 DB·원문 볼륨을 남기며, 브라우저 자동 테스트 모드만 자기 project를 볼륨까지 정리합니다. 실행 중인 미리보기를 재개하려면 기존 프로세스를 먼저 중지해야 합니다. 미리보기 제어 코드와 계정은 운영 jar에 포함되지 않습니다.

Playwright 참고: [실행 설정](https://playwright.dev/docs/test-configuration), [브라우저와 요청의 쿠키 공유](https://playwright.dev/docs/api/class-apirequestcontext).
