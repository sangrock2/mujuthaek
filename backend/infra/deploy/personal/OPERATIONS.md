# 운영 비용과 인증 점검

`Operations monitor`는 main의 GitHub Actions에서 매일 09:15 KST에 실행됩니다. 예약 실행은 GitHub 상황에 따라 늦어질 수 있습니다. Actions에서 수동 실행할 때 `send_report`를 선택하면 현재 점검 결과를 소유자 이메일로 보냅니다.

- AWS 월 예산: 비공개 설정에 지정한 크레딧 차감 전 기준. 기존 AWS Budgets의 실제 비용 50%·80%·100%, 예상 비용 100% 알림을 유지합니다. 기존 예산 이름의 문자열은 과거 식별자일 수 있으며 실제 한도는 AWS 설정으로 확인합니다.
- 크레딧: 잔액이 비공개 설정의 각 기준 이하가 되면 이메일로 알립니다. 동일 상태의 일일 중복 발송은 방지하고, 충전 후 다시 낮아지면 알립니다.
- 크레딧 만료: 사용자가 비공개 설정에 제공한 날짜를 기준으로 30·7·1일 전 및 만료 시 알립니다. Paid 계정 API는 개별 크레딧 만료일을 제공하지 않으므로 Billing → Credits에서 각 만료일을 별도로 확인해야 합니다.
- Vercel: 실제 GitHub `VERCEL_TOKEN`으로 프로젝트 접근과 현재 토큰 메타데이터를 확인합니다. 계정·해당 팀 범위 중 빠른 만료일을 사용합니다. API가 만료일을 반환하지 않으면 날짜를 추정하지 않습니다. 만료 30·7·1일 전 및 만료 시 알리며, 폐기·인증 실패·조회 장애도 점검 실패로 알립니다.
- 운영 IAM 키: 지정된 개인 프로젝트 사용자 3개의 생성일·활성 상태만 읽습니다. 생성 75·90일이 지나면 순차 교체를 권고합니다. IAM 키 자체에는 자동 만료가 없으며, 현재 키를 자동으로 폐기하지 않습니다.

금융 정보와 키 메타데이터는 공개 저장소의 Actions 로그·artifact·summary에 출력하지 않습니다. 전체 결과는 기존 비공개 S3 버킷의 `operations/monitor/latest.json`, 중복 방지 상태는 `state.json`에 덮어씁니다. 최초 실행, 새로운 경고, 수동 보고 요청 시에만 설정된 소유자 Gmail로 발송합니다. 이메일 성공 후 중복 방지 상태를 기록합니다. 재시도 경계에서 이메일이 중복될 가능성은 있으나 발송 실패를 성공으로 기록하지 않습니다.

모니터 역할은 main 브랜치 OIDC 단기 인증을 사용합니다. 비용·자격 메타데이터 읽기, 위 S3 파일 두 개의 읽기·쓰기, 지정 발신 주소에서 소유자 한 명에게 이메일 발송만 허용합니다. 배포용 역할·런타임 키의 권한을 확대하지 않습니다. 예산과 잔액 알림은 서버를 자동 중지하거나 삭제하는 기능이 아닙니다. AWS 집계에는 지연이 있으며 OpenAI 분석 예산은 별도입니다. 일일 점검은 유료 Cost Explorer 쿼리를 호출하지 않습니다.

## GA4 관리자 통계 연결

운영과 개발 속성은 분리한다. Vercel 프로젝트의 production 환경에 웹 스트림의 `NEXT_PUBLIC_GA_ID=G-…`를 설정하고 프론트를 다시 빌드한다. 기존 방문 통계 동의 흐름은 유지하며, 동의 전·거부 후·관리자 화면에서는 GA를 실행하지 않는다.

서버가 보고서를 읽으려면 Google Analytics Data API를 활성화하고 서비스 계정에 해당 운영 GA4 속성의 뷰어 권한을 부여한다. 속성 ID는 측정 ID와 다르며, 운영 서버의 `.env`에 숫자 `GA_PROPERTY_ID`와 `GA_CREDENTIALS_FILE=/run/mujuthaek-analytics/service-account.json`을 지정한다. 설정을 비워 두면 기존처럼 서버 통계만 제공한다.

서비스 계정 JSON은 Git·Vercel 환경변수·GitHub secrets·로그에 넣지 않는다. 서버 전용 `runtime/analytics/service-account.json`에 보관하고 API에만 디렉터리를 읽기 전용으로 마운트한다. 서버 디렉터리는 root 소유·그룹 10001·0750, 파일은 root 소유·그룹 10001·0440으로 만들어 UID 10001의 API 프로세스가 읽게 한다. PC 원본 파일과 상위 폴더의 권한은 변경하지 않는다.

반영 전 서비스 계정의 일반·실시간 보고서 접근을 확인하고, Compose 해석 결과에서 API 외 서비스에 GA 자격증명이 전달되지 않는지 확인한다. 기존 MQ/S3 분리·이미지 버전·DB를 유지하며 API 설정만 갱신한다. 실패 시 이전 환경·인증 파일로 복원한다. 일반 보고서에는 처리 지연과 서버의 1시간 캐시가 있으므로 실시간 보고서도 별도로 확인한다.

## 설치와 확인

개인 AWS 관리 로그인 후 `python backend/infra/deploy/personal/setup_operations.py --config <owner-only-json-path>`를 실행합니다. 계정과 기존 예산 구독을 확인한 뒤 소유 프로젝트 역할을 생성하고 `OPERATIONS_CONFIG`, `AWS_OPERATIONS_ROLE_ARN`, `AWS_OPERATIONS_ACCOUNT_ID`를 GitHub Actions secrets로 설정합니다. 실제 계정·버킷·이메일·비용 기준은 소스에 넣지 않습니다. 코드가 dev → main으로 병합된 뒤 Actions → Operations monitor → Run workflow(main)에서 실행합니다. 첫 보고 메일 수신과 워크플로 성공을 확인합니다.

GitHub Actions의 실패 알림도 계정 Notifications → Actions에서 활성화하세요. OIDC 인증·GitHub 자체 장애처럼 모니터가 시작되지 못한 경우에는 SES 알림도 보낼 수 없습니다. 공개 저장소에서 60일간 활동이 없으면 GitHub가 예약 워크플로를 비활성화할 수 있으므로 Actions에서 다시 활성화해야 합니다.

## 토큰·키 교체

Vercel 알림이 오면 Account → Tokens에서 새 배포 토큰을 만들고 GitHub 저장소 Settings → Secrets and variables → Actions → `VERCEL_TOKEN`을 교체합니다. 값은 채팅·커밋·로그에 남기지 않습니다. 수동 모니터와 프론트 배포를 확인한 다음 기존 토큰을 폐기합니다. 자동 교체를 위한 별도의 광범위 GitHub 쓰기 토큰을 만들지 않습니다.

IAM 키는 새 키 생성 → 해당 서버의 비공개 설정에 적용 → SES 발송·S3 백업·릴리스 수신 등 사용자별 실제 기능 확인 → 기존 키 비활성화 → 오류가 없으면 삭제 순서로 교체합니다. 사용자마다 권한과 적용 위치가 달라 일괄 자동 교체하지 않습니다. 기존 승인된 범위를 벗어난 키 생성·삭제는 별도로 검토합니다.

개인 `aws login --profile mujuthaek --region ap-northeast-2` 세션 만료는 관리 작업에만 영향을 줍니다. GitHub OIDC 배포·점검, 실행 중 서버와는 독립적입니다. VAPID·OAuth·JWT 키를 주기적으로 무조건 바꾸면 구독·로그인에 영향을 줄 수 있으므로 이 모니터에서는 자동 교체하지 않습니다.

근거: [Vercel 현재 토큰 메타데이터](https://github.com/vercel/sdk/blob/main/src/models/getauthtokenop.ts), [Vercel 만료일 필드](https://github.com/vercel/sdk/blob/main/src/models/authtoken.ts), [AWS 임시 자격 증명](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp.html), [GitHub 예약 워크플로](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

비공개 JSON 필드: `account`, `bucket`, `budget`, `recipient`, `sender`, `vercel_team`, `vercel_project`, `iam_users`(배열), `credit_levels`(숫자 배열), `budget_limit`(USD), `credit_expiry`(YYYY-MM-DD). 실제 파일은 Git 제외 경로에 저장하고 소유자만 읽도록 파일 권한을 제한합니다. 검사 코드의 주소·계정·금액은 모두 가상 데이터입니다.
