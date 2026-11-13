# 개인 AWS 배포

이 디렉터리는 기존 팀 배포와 분리되어 있다. 현재 리소스·검증 결과는 `docs/reviews/2026-11-13-lightsail-4gb-migration.md`에 기록한다. 최초 8GB 배포 이력은 `docs/reviews/2026-11-13-aws-personal-deployment-status.md`를 참고한다.

- 현재 운영은 서울 Lightsail Linux IPv4 번들 `medium_3_0`: 4GB / 2 vCPU / SSD 80GB / 월 $24다. 서버 이름은 `mujuthaek-personal-20261113-4gb`, API 주소는 `https://3.34.67.209`, 사용자 화면은 `https://mujuthaek.vercel.app`이다. IP의 화면 경로는 Vercel로 이동한다.
- `aws_personal.py`는 명시한 프로필과 12자리 계정 ID를 검증한다. 기존 팀 프로필·default는 거부하고, 생성 전 크레딧·사양·가격을 재검증한다. 플랜 전환은 하지 않는다.
- 임시 SSH 키와 호스트키는 TLS 인증된 AWS API로 얻는다. `ssh-keyscan`만 믿거나 host key 검사를 끄지 않는다. 임시 키를 갱신한 Windows 환경에서는 키 파일의 상속 권한을 제거하고 현재 사용자만 읽도록 제한해야 한다.
- `package_release.py`는 Git에 보이는 소스만 포함하고 환경 파일·키·빌드 산출물·runtime을 제외한다. 원격 빌드로 배포하므로 원본 소스도 서버에 남는다.
- `.env`는 `runtime/`에 생성한 새 비밀값을 서버에 안전하게 옮겨 사용한다. 기존 팀 환경 파일·OAuth 키·레지스트리는 가져오지 않는다. `.env`, 인증서·임시 키를 커밋하거나 로그로 출력하지 않는다.
- TLS는 `../certificates.py`를 이 디렉터리로 복사해 `--base-dir`를 현재 디렉터리로 지정한다. prod Compose와 versions.env를 읽는다. 도메인 없는 IP 인증서는 짧은 수명이라 설치되는 갱신 timer의 실제 성공 여부를 확인해야 한다.
- API·프론트·DB·MQ·notification만 기본 실행한다. 수집/분석은 `workers` profile로 분리하고 유료 AI 예산은 0으로 시작한다. 소셜 로그인 자격 증명, VAPID, SES는 별도 설정 전까지 완료 기능으로 간주하지 않는다.
- 4GB 기본 메모리 한도는 API 1024MiB, notification 384MiB, PostgreSQL 768MiB, RabbitMQ 320MiB, Next 384MiB, nginx 96MiB로 총 2976MiB다. 나머지는 OS·캐시·순간 증가에 남긴다. 수집·OCR을 같은 서버에서 활성화하려면 별도 부하 검증과 자원 조정이 필요하다. 서버에서는 앱 이미지를 빌드하지 않는다.
- DB/MQ/내부 API는 외부에 공개하지 않는다. 프록시는 외부 요청의 전달 헤더를 덮어쓴다. 관리 경로·Actuator 상세는 공개하지 않는다.
- `backup.sh`는 DB 4개를 논리 백업하고 S3에 업로드한다. 로컬 복사본은 자동 삭제하지 않으며 디스크 사용량을 확인해 별도 정리한다. bucket의 `backups/` lifecycle은 사용자가 승인한 30일로 제한한다. 백업이 실제 복구 가능한지 임시 DB로 검증한다.
- AWS Budgets 알림은 지출 강제 차단 장치가 아니다. 크레딧 소진 후 Paid 플랜 과금이 이어지므로 잔액 $30 전후에서 이전 여부를 결정한다. Lightsail은 정지해도 요금이 나가므로 종료할 때 인스턴스·남은 IP·스냅샷 등의 비용을 확인한다.
- 4GB 전환 후 기존 비용 알림의 월 한도는 $30로 조정한다. `migrate_4gb.py`, `migration_data.py`, `switch_4gb.py`는 8GB에서 4GB로 옮긴 일회성 이전 도구다. 삭제된 원본 서버를 대상으로 다시 실행하는 운영 배포 도구로 사용하지 않는다.

검증은 `python -m unittest discover -s backend/infra/deploy/personal/tests`로 실행한다.
