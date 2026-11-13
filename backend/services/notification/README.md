# notification 발송 서버

[백엔드 구조](../../../docs/06-backend.md) · [발송 상세·샘플](../../../docs/reference/notification-delivery.md) · [로컬 실행](../../../docs/04-local-development.md)

API 내부 notification 모듈과 구분되는 독립 Java 25·Spring Boot 서버입니다. RabbitMQ로 받은 발송 요청을 notification DB에 기록하고 채널별 묶음·시각·재시도를 처리합니다. 사용자 대상·설정·문구는 API가 결정합니다.

인프라를 준비한 뒤 이 폴더에서 `./gradlew bootRun` 또는 `.\gradlew.bat bootRun`으로 시작합니다. 기본 포트는 8081입니다. 검사는 `./gradlew check`이며 테스트용 Docker가 필요합니다.

로컬 기본 메일·푸시 provider는 log입니다. SES·webpush와 `samples/publish.sh`는 실제 외부 발송을 수행할 수 있습니다. 키·주소·구독 정보는 문서나 로그에 복사하지 않습니다.
