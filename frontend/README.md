# 무주택자들 프론트엔드

공공 주거·창업지원 공고를 모아 지원 가능 여부를 알려주는 서비스의 PWA 프론트엔드예요.

## 스택

Next.js 16 (App Router) · React 19 · TypeScript · Tailwind CSS v4 · TanStack Query · pnpm

## 처음 실행

준비물: Node 24+, pnpm 11

```bash
pnpm install
cp .env.example .env.local   # 값 채우기
pnpm dev                     # http://localhost:3000
```

로컬 개발은 `.env.local`의 `NEXT_PUBLIC_API_BASE_URL=http://localhost:8080`으로 브라우저가 백엔드(api)를 바로 불러요.

## 명령

| 명령                                | 하는 일                                        |
| ----------------------------------- | ---------------------------------------------- |
| `pnpm dev`                          | 개발 서버                                      |
| `pnpm build && pnpm start`          | 프로덕션 빌드·실행 (서비스 워커 확인은 여기서) |
| `pnpm lint`                         | ESLint                                         |
| `pnpm typecheck`                    | 라우트 타입 생성 + `tsc`                       |
| `pnpm format` / `pnpm format:check` | Prettier                                       |

PR마다 GitHub Actions가 format·lint·typecheck·build를 돌려요.

## 구조

```
src/app/manifest.ts             웹 앱 매니페스트
src/app/offline/                오프라인 폴백 페이지
src/app/providers.tsx           QueryClient + 서비스 워커 등록
src/components/pwa/             서비스 워커 등록, 오프라인 배너
src/lib/api/                    fetch 래퍼, 엔드포인트
src/lib/push.ts                 웹 푸시 구독/해지
public/sw.js                    서비스 워커 (오프라인 폴백, 정적 자산 캐시, 푸시)
```

## UI

- 디자인 원본은 `.design/`에 두고 로컬에서만 봐요 (git에 안 올라가요). 기준은 `.design/DESIGN.md`와 화면 파일의 인라인 스타일이에요.
- 색·둥글기·자간은 `src/app/globals.css`의 토큰만 써요 (`bg-brand`, `text-text-sub`, `rounded-card` 등).
- 라우트마다 PC(`Web*`)와 모바일(`M*`) 화면을 따로 만들고 `Responsive`로 1024px 기준 하나만 보여줘요 (`src/screens/`).
- 예시 데이터는 `src/mocks/`, 화면은 `src/features/*/queries.ts`의 쿼리로 받아요. API가 생기면 쿼리의 `queryFn`만 바꾸면 돼요.
- 공통 부품: `src/components/ui/`(배지·버튼·칩·세그먼트·토글·입력칸), `src/components/layout/`(헤더·하단 탭).
- `/states`는 빈 상태·오류 미리보기예요 (개발 서버에서만).

## PWA

- 서비스 워커는 `public/sw.js`를 직접 작성해서 써요 (`next.config.ts`에서 `/sw.js` 캐시 끔).
- 확인: `pnpm build && pnpm start` → Chrome DevTools > Application에서 Manifest·Service Workers 확인, Network를 Offline으로 바꾸고 새로고침하면 `/offline`이 떠요.
- 페이지 이동 중 연결이 끊기면 `experimental.useOffline`이 요청을 보류했다가 다시 시도하고, 상단에 오프라인 배너를 보여줘요.

## 웹 푸시

1. VAPID 키 만들기: `pnpm dlx web-push generate-vapid-keys`
2. 공개 키는 `.env.local`의 `NEXT_PUBLIC_VAPID_PUBLIC_KEY`에, 비공개 키는 백엔드에만 둬요.
3. 구독 정보는 `POST /api/v1/notifications/subscriptions`로 보내요 (백엔드 notification 모듈 확정 전 임시 경로, `src/lib/api/endpoints.ts`).
4. 테스트: DevTools > Application > Service Workers의 Push 버튼으로 알림을 띄워볼 수 있어요.

iOS는 16.4 이상에서 홈 화면에 설치한 경우에만 푸시가 와요.

## 배포 (Vercel)

백엔드는 AWS EC2에 HTTP(80)로만 떠 있어요(도메인·HTTPS 인증서 없음). 브라우저는 Vercel 주소 하나만 부르고,
Vercel이 `/api/**`·`/oauth2/**`·`/login/oauth2/**`를 백엔드로 대신 넘겨요(`next.config.ts` rewrites, `API_ORIGIN`이 있을 때만).
그래서 HTTPS가 필요 없고 refresh 토큰 쿠키(SameSite=Lax)도 같은 사이트 쿠키로 쓰여요. `/login` 화면은 넘기지 않아요.

| 이름                           | Production           | Preview              |
| ------------------------------ | -------------------- | -------------------- |
| `API_ORIGIN`                   | http://3.37.131.73   | http://52.79.106.144 |
| `NEXT_PUBLIC_USE_MOCKS`        | false                | false                |
| `NEXT_PUBLIC_VAPID_PUBLIC_KEY` | prod 공개키          | dev 공개키           |
| `NEXT_PUBLIC_KAKAO_MAP_KEY`    | 카카오 JavaScript 키 | 같은 값              |

- `NEXT_PUBLIC_API_BASE_URL`은 Vercel에 넣지 않아요 (같은 주소로 불러요). 로컬 개발 전용이에요
- `API_ORIGIN`은 서버 전용이라 브라우저로 나가지 않아요. 바꾸면 다시 배포해야 반영돼요
- 백엔드 서버는 자동 중지로 매일 일정 시간만 켜져 있어요. 응답이 없으면 화면 위에 「서비스 운영 시간: 10:00~19:00」 안내가 떠요 (`src/lib/api/availability.ts`)

사람이 할 일

- `main`에서 `dev` 브랜치 만들기 (Vercel Preview 고정 주소용)
- Vercel → Settings → Deployment Protection에서 Preview 보호 설정 확인
- 카카오 개발자 콘솔 → 플랫폼 → Web에 두 Vercel 주소(Production·dev Preview) 등록 (지도)
- 소셜 로그인 콘솔 3곳(카카오·네이버·구글)에 리다이렉트 URI 등록: `https://mujuthaek-fe.vercel.app/login/oauth2/code/{kakao,naver,google}`, dev Preview 주소의 같은 경로
