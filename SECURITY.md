# Security policy

Security fixes target the current `main` release. Versioned maintenance branches are not supported.

Please report vulnerabilities through [GitHub private vulnerability reporting](https://github.com/sangrock2/mujuthaek/security/advisories/new). Include the affected commit, reproduction steps using synthetic data, expected behavior, and impact. Do not publish credentials, personal information, or exploit details in a public issue or pull request.

Use an isolated local environment when reproducing issues. Testing must not interrupt the production service, send real notifications, or access other users' data.

If a credential is exposed, revoke or rotate it before removing it from Git history. Deleting the text alone does not invalidate the credential.

Dependency updates follow the same `dev` → `main` review path. If Dependabot opens a security update against `main`, retarget it to `dev` before merging; the branch-direction check intentionally prevents direct merges into `main`.
