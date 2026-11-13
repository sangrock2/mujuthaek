# 프론트엔드

[문서 목차](../docs/README.md) · [프론트 구조](../docs/05-frontend.md) · [실행·환경 설정](../docs/04-local-development.md)

Next.js 16·React 19·TypeScript·Tailwind CSS v4·TanStack Query 기반 PWA입니다. `src/app`은 라우트입니다. `src/features/<기능>/`에 화면·전용 부품·시연 데이터·상태·요청을 모으고, `src/shared/`에 공통 UI·레이아웃·기반 코드를 둡니다.

Node.js 24+와 package.json에 지정된 pnpm을 준비합니다. 이 폴더에서:

```bash
pnpm install --frozen-lockfile
# .env.example을 .env.local로 복사하고 설정 확인(기존 파일은 덮어쓰지 않음)
pnpm dev
```

기본은 실제 API 모드입니다. 디자인 시연이 필요할 때만 `NEXT_PUBLIC_USE_MOCKS=true`를 명시합니다. `pnpm test:ui`, `pnpm typecheck`, `pnpm lint`, `pnpm build`로 확인합니다.

신청 준비함은 실제 API 모드에서 공고 상세·관심 공고·내 정보에서 사용합니다. 주거 공고의 서류·일정과 준비 상태를 관리하고 정정 시 재확인을 안내합니다. 별도 격리 환경의 실제 API 브라우저 검사는 `pnpm exec playwright install chromium` 후 `pnpm test:e2e`로 실행합니다(JDK 25·Docker 필요). 환경 생성·빌드·실행·정리는 자동이며 [실행 안내](../backend/infra/e2e/README.md)를 참고합니다.

[UI/UX 수정 기록](../docs/changes/2026-11-11-ui-ux.md) · [기존 상세 안내](../docs/reference/frontend-operations.md) · [테스트 범위](../docs/10-testing-and-quality.md)
