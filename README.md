# 무주택자들

공공 주거·창업지원 공고를 자동으로 모으고, AI로 자격 조건을 뽑아, 사용자가 지원할 수 있는지 알려주는 서비스예요.

## 구성
| 폴더 | 스택 | 하는 일 | 실행법 |
| --- | --- | --- | --- |
| `backend/` | 자바 25 + 스프링 부트, 파이썬 3.12 | api(프론트의 단일 입구)·collector(수집)·extraction(AI 추출)·notification(푸시), 서비스 사이 계약(`contracts/`), 인프라(`infra/`) | [`backend/README.md`](backend/README.md) |
| `frontend/` | Next.js 16 + React 19 + TypeScript (pnpm) | PWA 사용자 화면과 관리자 페이지 | [`frontend/README.md`](frontend/README.md) |

- 프론트는 2026-11-11 팀 프론트 저장소(kjungit/mujuthaek-fe)의 dev 브랜치를 커밋 이력째 가져왔어요.

## CI
| 워크플로 | 검사 | 도는 때 |
| --- | --- | --- |
| `ci.yml` | 추출·python-platform ruff·pytest | `backend/` 변경 |
| `contracts.yml` | 계약 스키마·경계 사례, 추출 입력 해석 | `backend/contracts/`·`backend/services/extraction/` 변경 |
| `web.yml` | 프론트 format·lint·typecheck·build | `frontend/` 변경 |
