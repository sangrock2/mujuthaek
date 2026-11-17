# 지도 복구 배포를 막는 개발 의존성 경보 검토안

상태: 2026-11-18 소유자가 「제한된 한시 예외와 지도 배포 승인」을 명시했다. 승인 후 `frontend/scripts/audit-policy.json`의 `enabled`를 true로 변경했다.

## 확인한 사실

- 지도 PR #174를 최신 dev로 갱신한 뒤 프론트 CI의 npm 감사가 `GHSA-fc5q-39xc-vjpf` 한 건으로 실패했다. picomatch의 반복 extglob 정규식에 의한 ReDoS 고위험 경보다.
- 현재 잠금 파일의 관련 버전은 2.3.2·4.0.7이며, 모든 발견 경로가 `eslint-config-next` 아래이고 감사 결과의 `dev`가 true다. 운영 의존성만 감사한 결과는 모든 심각도 0건이다.
- npm 감사는 패치 범위를 `>=4.0.8`로 제시하지만, 공식 npm 배포 목록은 4.0.7까지다. 공식 GitHub 권고도 수정 배포 버전을 제시하지 않는다. 존재하지 않는 버전으로 갱신하거나 검증되지 않은 PR을 패치로 간주하지 않는다.
- 이 의존성은 빌드/린트 때 사용한다. CI 자원 고갈 위험이 사라졌다고 주장하지 않으며 경보를 숨기거나 해결 처리하지 않는다. 운영의 사용자 입력을 이 개발 의존성에 넘기는 경로로 확인된 것은 없다.

근거: [GitHub 권고](https://github.com/advisories/GHSA-fc5q-39xc-vjpf), [공식 배포 목록](https://github.com/micromatch/picomatch/releases), 실제 `pnpm audit --json`·`pnpm audit --prod --json` 결과.

## 검토 가능한 한시 승인안

- 한국 시간 2026-11-25 00:00까지 해당 GHSA·패키지·버전·ESLint 개발 의존 경로만 일시 허용한다. 승인 전에는 계속 실패한다.
- 운영 의존성의 moderate/high/critical 경보는 예외 없이 차단한다. 새 경보, 개발 전용 여부 누락, 경로·버전 변경, 불완전한 감사 응답, 조회 실패와 만료도 차단한다.
- 운영/전체 감사를 모두 실행하며 전체 심각도 집계·경보·한시 예외를 로그에 표시한다. Dependabot 경보를 닫거나 무시 처리하지 않는다.
- 기존 감사 단계 대신 이 정책을 검사하는 감사 실행기와 정책 회귀 검사를 연결하는 로컬 변경을 준비했다. 정책 경계 검사 9개를 통과했다. 다른 CI 검사와 배포 보호 조건은 유지한다.

검토 파일: `frontend/scripts/audit-dependencies.mjs`, `frontend/scripts/audit-dependencies.test.mjs`, `frontend/scripts/audit-policy.json`, `.github/workflows/web.yml`. 승인된 범위의 변경만 지도 PR에 포함하고 필수 검사 후 dev→main으로 반영한다.

한시 승인을 원하지 않으면 프론트 배포는 공식 패치가 제공되거나 별도 검증한 해결책이 준비될 때까지 보류한다. 공고 좌표 한 행은 이미 공식 건물 좌표로 복구했으며, 준비한 CSP를 격리 브라우저에만 적용하면 해당 공고 지도·실제 타일 9개가 모두 정상 응답하는 것을 확인했다.
