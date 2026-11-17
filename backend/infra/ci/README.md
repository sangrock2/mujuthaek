# 변경 범위별 CI

`plan.py`가 PR의 merge-base부터 head까지 실제 변경 경로를 계산한다. 파일 이동은 삭제/추가 양쪽을 포함한다. PR 전체에 무거운 서비스 검사를 무조건 실행하지 않는다.

| 변경 | 검사 |
|---|---|
| API | API; 런타임 변경이면 실제 API 브라우저 E2E도 실행 |
| 알림 | 알림 서비스 |
| 프론트 | 프론트; 런타임 변경이면 브라우저 E2E도 실행 |
| 수집기 | Docker 없는 네이티브 PostgreSQL 수집기 검사 |
| 추출기 | 추출기; 법정동 코드 원본은 API도 검사 |
| Python 공통 | 공통 라이브러리와 수집기·추출기 |
| Java 공통 | API·알림 및 연결 E2E |
| 계약 | 스키마와 소비하는 Java/Python 서비스·연결 경계 |
| 배포/운영 도구 | 인프라 검사; 게이트웨이/MQ 설정은 해당 통합 검사 추가 |
| CI 선택/gate 설정 | 선택 규칙 테스트·워크플로 정적 검사·인프라 검사 |
| README/docs | 서비스 검사 없음; 커밋 범위 비밀 검사는 유지 |

런타임 Markdown 프롬프트/콘텐츠는 문서로 제외하지 않는다. 알려지지 않은 공통 빌드 입력과 최초 배포처럼 기준 변경 목록이 없는 경우는 보수적으로 전체 관련 검사를 선택한다. 명시적 수동 CI 실행도 전체 검사를 지원한다.

`CI ready`와 `Backend ready`는 계획에 선택된 작업의 성공을 요구한다. 필요한 작업이 skip/failure/cancelled이면 실패한다. 선택하지 않은 작업만 skip을 허용한다. 검사 실패를 success로 바꾸거나 병합 보호를 우회하지 않는다.

Production은 직전 완료 배포부터의 변경 목록과 실제 배포 대상에 같은 선택 규칙을 적용한다. CI/선택 제어 파일만 바뀐 경우 앱을 불필요하게 재배포하지 않는다. 실제 release 실행/호스트 프로토콜 변경은 기존 보수적 배포 경로를 유지한다.

일반 PR 비밀 검사는 PR 커밋 범위만 검사한다. 전체 이력은 예약/수동 실행과 비밀 검사 설정 변경 시 검사하며 예외 canary도 유지한다. GitHub 관리형 CodeQL/병합 보안 규칙은 별도 보호로 유지한다.

선택 규칙과 gate를 변경했을 때의 로컬 검사:

```powershell
python -m unittest discover -s backend/infra/ci -p 'test_*.py' -v
python -m unittest discover -s backend/infra/deploy/personal/tests -p test_selective_release.py -v
```

워크플로 변경은 checksum 고정 actionlint 1.7.12로 구문·표현식을 검사한다. 관련 없는 서비스 전체 검사는 로컬 검증에 추가하지 않는다.
