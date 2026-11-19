# picomatch 한시 예외 비활성화

2026-11-19 공식 GitHub Advisory Database의 GHSA-fc5q-39xc-vjpf 기록이 11월 18일 철회된 것을 확인했다. 현재 잠금 파일에 대한 운영 전용 및 전체 pnpm 의존성 감사는 모두 경보 0건이며, 저장소의 열린 Dependabot 경보도 0건이다.

기존 `frontend/scripts/audit-policy.json`의 `enabled`를 false로 바꿔 승인받았던 11월 25일까지의 한시 예외를 조기 비활성화한다. 이는 picomatch 코드가 패치되었다는 뜻이 아니다. 이 경보가 다시 보고돼도 예외를 사용하지 못하며, 운영 의존성 및 새 경보를 차단하는 기존 검사는 유지한다. 기존 감사 정책 단위 검사 9건을 통과했다.

공식 기록: https://github.com/advisories/GHSA-fc5q-39xc-vjpf
