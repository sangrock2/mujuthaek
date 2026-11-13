# 개발·배포·롤백

## 브랜치

작업 브랜치는 dev에서 만들고 PR의 대상은 dev로 지정한다. 운영 반영은 같은 저장소의 dev → main PR로만 진행한다. main과 dev에 직접 push·force push·삭제를 금지하고 PR direction, CI ready 검사를 필수로 둔다. 병합 방식(merge/squash/rebase)은 기존 설정을 유지한다.

PR Direction은 pull_request_target 이벤트에서 PR 메타데이터만 검사한다. PR 코드를 checkout하거나 실행하지 않는다. Checks는 PR 코드의 포맷·테스트·계약·실제 API E2E를 실행한다. main 병합 후 Production이 다시 검증하고 배포한다. main에 직접 push하거나 다른 브랜치에서 병합한 커밋은 Production의 별도 검사에서도 거절한다.

## 운영 배포

프론트는 Vercel 후보 빌드를 먼저 만들고, 백엔드는 GitHub runner에서 linux/amd64 이미지를 빌드한다. 운영 4GB 서버에서 이미지를 빌드하지 않는다. 이미지 두 개(api, notification)와 SHA256·이미지 ID·Git SHA·Vercel 버전을 비공개 S3 deployments/releases/<release>/에 기록한다. 릴리스 ID는 <Git SHA>-<GitHub run ID>다.

AWS 인증은 개인 저장소 main에 한정한 OIDC 역할을 사용하며 S3 deployments/에만 읽기·쓰기 권한이 있다. 장기 AWS 키나 운영 SSH 키를 GitHub에 등록하지 않는다. Lightsail은 systemd 타이머로 1분마다 요청을 읽어 체크섬 검증·백업·컨테이너 교체·상태 검사를 수행한다. 이미지에는 앱 비밀값을 넣지 않고 서버 기존 .env를 사용한다.

백엔드 적용 성공 후 Vercel 후보를 공개 주소로 승격하고 공개 API를 확인한다. 배포는 순차 실행하며 진행 중인 배포를 자동 취소하지 않는다. api·notification 교체 중 짧은 응답 중단이 있을 수 있으며 두 플랫폼의 원자적 동시 전환이나 무중단을 보장하는 구성은 아니다.

필수 GitHub 설정:

- Secret: VERCEL_TOKEN — mujuthaek 팀 범위의 배포 토큰, 만료 시 교체
- Variable: AWS_DEPLOY_ROLE_ARN — main 전용 역할
- Variable: PRODUCTION_DEPLOY_ENABLED=true — 초기 소스 정렬과 검증 완료 뒤 활성화
- Vercel Git 자동 배포는 비활성으로 두어 검사를 거치는 Actions 배포와 중복되지 않게 한다.

## 과거 버전으로 복구

GitHub → Actions → Production → Run workflow → Branch main을 선택하고 release에 과거의 성공한 릴리스 ID를 입력한다. 바로 이전 버전뿐 아니라 S3에 보관된 더 오래된 버전도 지정할 수 있다. 성공한 배포의 release 값은 Actions 산출물 deployment-result.json과 S3 deployments/states/에서 확인한다. 재실행 입력은 저장된 릴리스만 허용하며 임의 파일 경로나 Docker 태그를 받지 않는다.

백엔드는 보관한 이미지를 그대로 다시 사용한다. 프론트는 해당 릴리스의 Git SHA로부터 새 후보를 빌드해 승격한다. Vercel Hobby의 Instant Rollback은 바로 이전 운영 배포만 지원하므로 더 오래된 버전은 이 재빌드 경로를 사용한다. 소스와 lockfile이 같아도 플랫폼 빌드 환경·환경 변수는 과거와 달라질 수 있다.

첫 보관 버전 20261113-1은 기존 로컬 배포 이미지다. Git SHA가 없어서 프론트는 저장된 Vercel 배포를 승격하는 방식이며 플랜·보관 상태에 따라 제한될 수 있다. 이후 Git 기반 릴리스부터 과거 SHA 재빌드를 지원한다. Git을 reset하거나 main을 과거로 force push할 필요는 없다.

컨테이너 health 검사 실패 시 DB 마이그레이션 이력이 그대로일 때만 이전 앱 이미지를 자동 복구한다. API·notification의 현재 Flyway 이력과 대상 릴리스의 이력이 다르면 수동 롤백도 차단한다. DB 백업 복구는 별도 작업이며 자동 수행하지 않는다. 앱 롤백은 배포 이후 추가된 사용자 데이터를 지우지 않는다.

## 운영 확인

서버: systemctl status mujuthaek-personal-release.timer / journalctl -u mujuthaek-personal-release.service

요청이 시간 초과하면 동일 버전을 무작정 재배포하지 말고 S3 deployments/results/<request>.json과 서버 journal을 확인한다. 실패 요청을 타이머가 무한 재시도하지 않으므로 원인을 고친 뒤 새 workflow 실행으로 요청한다. 기존 DB 백업 30일 보관 정책은 변경하지 않으며 배포 이미지·메타데이터에는 자동 삭제 정책을 추가하지 않았다. 릴리스가 쌓이면 S3 사용량을 확인한다.

공식 문서: [GitHub Rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets), [AWS OIDC](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws), [Vercel Instant Rollback](https://vercel.com/docs/instant-rollback).
