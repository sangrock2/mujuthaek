# 백엔드

[문서 목차](../docs/README.md) · [백엔드 구조](../docs/06-backend.md) · [실행 순서](../docs/04-local-development.md) · [파이프라인](../docs/07-data-pipeline-and-contracts.md)

| 서비스                                          | 스택                | 책임                                        |
| ----------------------------------------------- | ------------------- | ------------------------------------------- |
| [api](services/api/README.md)                   | Java 25·Spring Boot | 브라우저의 업무 API, 업무 모듈 8개와 common |
| [collector](services/collector/README.md)       | Python 3.12         | 기관 공고·정책·생활권 원천 수집             |
| [extraction](services/extraction/README.md)     | Python 3.12         | 원문 구조화·검증·검수·이벤트 발행           |
| [notification](services/notification/README.md) | Java 25·Spring Boot | 독립 이메일·웹 푸시 발송                    |

이 폴더에서 `make help`, `make infra`를 실행합니다(Bash·make 필요). PowerShell용 직접 Compose 명령은 [로컬 문서](../docs/04-local-development.md)를 참고합니다. 현재 로컬 `make up`은 collector와 마이그레이션만 포함하며 API·extraction·notification은 별도로 실행합니다.

[계약 원본](contracts/README.md) · [공통 Python 코드](libs/python-platform/README.md) · [배포](infra/deploy/README.md) · [성능 측정](tools/perf/README.md) · [초기 팀 구성 기록](../docs/reference/backend-history.md)
