# Repository guidance

- 초기 PR 양식을 따른다. 제목은 `Fix(extraction): 한국어 설명`, `Feat(frontend): 한국어 설명`처럼 `종류(범위): 한국어 설명`으로 작성한다. 본문은 `## 무엇을` → 실제 변경 파일의 `| 파일 | 바뀐 점 |` 표 → `## 왜` 순서로 쓴다. 검증 결과와 운영 반영 범위·미완료 사항을 보존한다.

- PR 제목과 본문은 한국어로 작성한다. `Fix`, `Feat`, `CI`, `Release` 같은 관례적인 태그와 코드·API·패키지·파일 경로·버전 식별자는 영어 원문을 유지할 수 있다. 본문의 설명과 검증 결과는 한국어로 쓴다. 기존 PR을 갱신할 때도 이 기준을 적용하고, Dependabot이 본문을 재생성한 경우 한국어 안내를 다시 확인한다. PR 메타데이터 수정으로 병합 커밋 메시지나 Git 이력이 바뀌었다고 설명하지 않는다.

- Follow applicable repository instructions and the existing service boundaries. Frontend is in `frontend/`; API, notification, collector and extraction services are in `backend/services/`.
- Use synthetic fixtures. Never read or copy `.env`, runtime credentials, private recovery keys, production database contents, or cloud credentials into code, logs, issues, prompts, or artifacts.
- Preserve authentication, authorization, OAuth state, token redaction, strict dependency verification, and existing security checks. Do not dismiss security alerts or disable a gate just to make checks pass.
- Pin GitHub Actions to complete commit SHAs and keep job permissions minimal. Untrusted pull requests must not receive deployment credentials or cloud access. Production changes follow a pull request into `dev`, then `dev` into `main`.
- Keep E2E runs local and disposable. Do not inherit provider secrets, use a remote Docker daemon, send real email/push notifications, or operate on production data during tests.
- Explain the security impact of changes and run checks appropriate to the affected code. Fix suggestions require review; do not automatically deploy or merge security changes.
