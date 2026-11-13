# API 서버

[백엔드 구조](../../../docs/06-backend.md) · [로컬 실행](../../../docs/04-local-development.md) · [인증·관심·알림 상세](../../../docs/reference/api-operations.md)

Java 25·Spring Boot 4.1.1의 모듈러 모놀리스입니다. 업무 모듈은 notice·benefit·eligibility·area·user·notification·chat·traffic 8개이며 common은 기술 공통 코드입니다.

DB·RabbitMQ를 준비한 뒤 이 폴더에서 `./gradlew bootRun`을 실행합니다. PowerShell은 `.\gradlew.bat bootRun`을 사용합니다. 기본 API 포트는 8080입니다.

검사는 `./gradlew check`, 경계 검사만 실행하려면 `./gradlew test --tests '*ModuleStructureTest'`입니다. JDK 25·테스트용 Docker 등 전제는 [테스트 문서](../../../docs/10-testing-and-quality.md)를 확인합니다.

이 프로젝트의 빌드는 `../../contracts`와 `../extraction/data/legal-dong-codes`를 읽으므로 api 폴더만 떼어 빌드하지 않습니다. 업무 모듈 간 규칙은 [루트 개발 원칙](../../../CLAUDE.md)을 따릅니다.
