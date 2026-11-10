# 무주택자들

공공 주거·창업지원 공고를 수집하고, AI로 자격 조건을 뽑아, 사용자의 지원 가능 여부를 판정하는 서비스.
`backend/`(api·collector·extraction·notification·contracts·infra)와 `frontend/`(Next.js) 두 폴더로 나뉘어요.

## Commands
```bash
cd backend && make infra                                                      # 로컬 인프라 (PostgreSQL·RabbitMQ·MinIO), make help
cd backend/services/api && ./gradlew bootRun                                  # api 실행
cd backend/services/api && ./gradlew spotlessApply check                      # 포맷 + 테스트 (커밋 전)
cd backend/services/api && ./gradlew test --tests '*ModuleStructureTest'      # 모듈 경계 검사만
cd backend/services/collector && uv run ruff check && uv run pytest           # 수집기 린트 + 테스트
cd frontend && pnpm lint && pnpm typecheck                                    # 프론트 린트 + 타입 검사
```

## Rules (backend)
- 다른 모듈 데이터는 **service 계층에서 그 모듈의 service 조회 메서드**로만 가져온다. 다른 모듈의 repository·엔티티·테이블은 쓰지 않는다
- 호출 방향은 notice → area·benefit / eligibility·user → notice·benefit / notification → user·notice·benefit / chat → notice·user 만 허용. area·benefit은 다른 모듈을 부르지 않는다
- 다른 모듈에 영향을 주는 변경은 직접 호출하지 말고 `common/event` 이벤트로 (`@TransactionalEventListener`)
- `eligibility/rule`은 스프링·JPA 없는 순수 자바로 유지한다
- 마이그레이션은 기존 파일을 고치지 말고 `V<yyyyMMddHHmm>__<module>_<desc>.sql`로 새로 만든다
- 사용자 소득·자산·나이는 저장하거나 로그에 남기지 않는다
- API 설명은 컨트롤러가 아니라 `.../spec/<이름>ApiSpec` 인터페이스(@Tag·@Operation·@ApiResponse)에 쓰고, 컨트롤러가 그걸 implements 한다. 로컬 문서는 http://localhost:8080/swagger-ui.html. spec·@Tag·@Operation(summary)을 빠뜨리거나 태그 이름이 겹치면 `ApiSpecConventionTest`가 실패한다(실제로 나는 오류의 @ApiResponse는 시험이 못 잡으니 리뷰에서 본다)
