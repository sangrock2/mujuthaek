# Repository guidance

- Follow applicable repository instructions and the existing service boundaries. Frontend is in `frontend/`; API, notification, collector and extraction services are in `backend/services/`.
- Use synthetic fixtures. Never read or copy `.env`, runtime credentials, private recovery keys, production database contents, or cloud credentials into code, logs, issues, prompts, or artifacts.
- Preserve authentication, authorization, OAuth state, token redaction, strict dependency verification, and existing security checks. Do not dismiss security alerts or disable a gate just to make checks pass.
- Pin GitHub Actions to complete commit SHAs and keep job permissions minimal. Untrusted pull requests must not receive deployment credentials or cloud access. Production changes follow a pull request into `dev`, then `dev` into `main`.
- Keep E2E runs local and disposable. Do not inherit provider secrets, use a remote Docker daemon, send real email/push notifications, or operate on production data during tests.
- Explain the security impact of changes and run checks appropriate to the affected code. Fix suggestions require review; do not automatically deploy or merge security changes.
