# 의존성 PR 통합 검토

17개의 Dependabot PR을 파일별로 병합하는 대신 변경이 겹치는 묶음으로 검토한다. 기존 검증·권한·캐시 신뢰 경계를 유지한다.

| 원래 PR | 처리 |
| --- | --- |
| #142·144·145·146·148·150·151·152 | #185에 Python 잠금 파일 3개로 통합. pytest 9.2.0·ruff 0.17.4·boto3 1.44.1·botocore 1.44.5. 관련 CI 및 98개 버전 취약점 조회 0건 확인 후 병합·중복 종료. |
| #143·149 | #184에 프론트 잠금 변경 통합. React Query/devtools 5.107.2·lucide 1.74.0. TypeScript·브라우저·프론트 CI 통과 후 병합·중복 종료. |
| #147 | Node 26 타입 제안을 그대로 적용하지 않았다. 실제 Node24 런타임에 맞는 @types/node 24.19.2로 대체해 #184에서 검증·병합. |
| #137·140·141 | API 의존성 통합 검증. networknt 3.0.9·springdoc 3.2.0·Modulith 2.1.2. Modulith는 테스트 모듈만 바꾸지 않고 runtime core·test·docs를 함께 정렬. |
| #136·138·139 | 공식 태그 커밋과 action.yml을 대조한 전체 SHA 교체안. checkout 7.0.1·setup-java 6.3.0·setup-gradle 6.4.1. Node24 실행 및 사용 중인 입력 지원 확인. |

## API 검증

Spring Boot 4.1에 맞는 [Modulith 공식 호환성 표](https://docs.spring.io/spring-modulith/reference/appendix.html)와 [springdoc 공식 표](https://springdoc.org/faq.html)를 확인했다. 새 버전으로 Java·테스트 소스 컴파일이 통과했다.

기존 Gradle SHA-256 검증값이 모두 유지되고 검증 정책이 바뀌지 않았음을 XML 항목 단위로 확인했다. 새 아티팩트 37개는 [Maven Central 공식 저장소](https://repo.maven.apache.org/maven2/)에서 독립적으로 받아 해시가 일치함을 확인했다. 생성 도구의 결과만 보고 임의로 신뢰 목록을 추가하지 않았다.

## Actions 검증

| Action | 공식 태그의 고정 커밋 |
| --- | --- |
| actions/checkout 7.0.1 | 3d3c42e5aac5ba805825da76410c181273ba90b1 |
| actions/setup-java 6.3.0 | d1374f8ac74474200d16ef8ecee22c7ae7a51880 |
| gradle/actions/setup-gradle 6.4.1 | 8da46b539cd8fe6ab27ca75128919a18d757604c |

12개 워크플로 YAML을 비교해 action SHA 및 setup-java의 명시적 problem-matcher 이외의 구조가 동일함을 검사했다. 권한·환경 비밀·실행 조건·명령·체크아웃 persist-credentials:false·PR 캐시 읽기 전용 경계는 유지된다. setup-java 6.3에서 기본값이 바뀐 컴파일러 주석은 problem-matcher:true로 기존 동작을 보존한다.

공식 변경 기록: [checkout 7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1), [setup-java 6.3.0](https://github.com/actions/setup-java/releases/tag/v6.3.0), [setup-gradle 6.4.1](https://github.com/gradle/actions/releases/tag/v6.4.1). 현재 의존성 그래프 제출은 Gradle의 dependency-submission action 대신 기존 분리된 inventory/submit 경로를 사용한다.

공통 Actions 교체는 여러 CI 작업에 영향을 주므로 해당 워크플로의 관련 검사를 확인한다. 무관한 전체 프로젝트 검사를 수동으로 다시 시작하지 않는다. 최종 병합·운영 반영·원래 PR 종료 결과는 후속 작업 기록에 별도로 남긴다.

## picomatch

이번 업데이트 뒤에도 [GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf)의 정식 수정 버전은 없다. 최신 공개 4.0.7과 공식 수정 PR 상태를 확인했다. 미완성 upstream 변경을 임의로 배포하거나 예외 만료를 연장하지 않는다. 개발 ESLint의 지정 경로·버전만 기존 승인에 따라 2026-11-25 00:00 KST까지 허용하며 운영 경보·새 경보·만료 후에는 계속 차단한다.
