# 배포 설정

[현재 배포 구조](../../../docs/09-deployment-and-operations.md) · [상세 운영 기록](../../../docs/reference/deployment-runbook.md)

이 폴더에는 compose.dev.yml·compose.prod.yml·nginx·deploy.sh와 복사·shovel 도구가 있습니다. 운영 서버의 대상 폴더에서 `.env`, `versions.env`와 함께 사용하는 Bash/Docker 설정입니다.

현재 저장소에는 기존 기록에 등장하는 deploy-dev.yml·release.yml 워크플로가 없습니다. 설정 파일이 있다는 이유로 자동 배포가 활성화됐다고 가정하지 않습니다. 실제 서버 주소·외부 콘솔·운영 시간은 배포 환경에서 확인합니다.

DB·큐·원천 파일 복구 명령과 과거 대응 사례는 상세 기록으로 이관했습니다. 구조 정리를 위해 이 명령이나 볼륨 삭제·운영 재처리를 실행하지 않습니다.

## HTTPS 적용과 갱신

현재 프로젝트는 아직 새 서버에 배포하지 않았습니다. 기존 AWS 프로필·EC2·고정 IP는 이전 팀 자원이므로 재사용하지 않습니다. 아래 명령은 새로 준비한 본인 소유의 Linux/Docker 배포 호스트에서만 실행합니다. 이 저장소가 AWS 자원을 자동 선택하거나 생성하지는 않습니다.

nginx는 API를 443 TLS에서만 제공합니다. 80 포트는 `/.well-known/acme-challenge/`의 GET·HEAD만 처리하며 API·OAuth 요청은 404입니다. `API_ORIGIN`, `NEXT_PUBLIC_API_BASE_URL`, `TRAFFIC_INGEST_URL`에 공개 HTTP 주소를 넣으면 프론트 설정 검증이 실패합니다. HTTP는 로컬 loopback 개발·E2E에만 허용하고, Vercel에서는 loopback도 거부합니다.

적용 전 준비:

1. 새 서버와 이미지 저장소·DB·객체 저장소 등 배포 환경을 먼저 준비합니다. 인증 대상은 본인 소유 API 도메인 또는 고정 공인 IP입니다. IP 인증서는 Let's Encrypt shortlived 프로필을 사용하므로 약 6일마다 만료하며 자동 갱신이 필수입니다.
2. 서버의 전용 디렉터리(예: `/opt/mujuthaek/tls`)에 `fullchain.pem`, `privkey.pem`을 준비합니다. 디렉터리는 root 소유 700, 개인키는 600을 권장합니다. Certbot live 디렉터리의 링크만 단독 마운트하면 archive 경로가 끊길 수 있으므로 실제 파일을 복사하거나 갱신 훅으로 배치합니다. 인증서는 Git·Docker 이미지·로그에 넣지 않습니다.
3. 서버 `.env`에 `API_TLS_CERT_DIR=/opt/mujuthaek/tls`를 설정합니다. Compose는 이를 read-only로 마운트합니다. 값이 없으면 구성 검증이 실패하며 인증서가 없거나 키가 불일치하면 nginx가 시작되지 않습니다. `deploy.sh`는 앱 교체 전과 프록시 시작 전에 `nginx -t`를 수행합니다.
4. 새 서버의 보안 그룹에서 ACME용 80과 HTTPS용 443을 허용합니다. 백엔드 API 포트 8080은 loopback에만 둡니다. 80을 사용하는 앱 프록시는 두지 않습니다.
5. Vercel Production·Preview 각각 `API_ORIGIN=https://<해당 API 도메인>`으로 바꿔 재배포합니다. 트래픽 수집을 사용하면 `TRAFFIC_INGEST_URL`도 HTTPS로 바꾸고, Vercel의 `NEXT_PUBLIC_API_BASE_URL`은 비웁니다. `FRONTEND_URL`, `OAUTH_REDIRECT_BASE_URL`, 제공자 콘솔 콜백은 실제 프론트 주소를 유지합니다.
6. 인증서 검증을 끄지 않은 `curl -fsS https://<API 도메인>/actuator/health`와 프론트의 로그인·refresh·로그아웃을 확인합니다. Production·Preview 양쪽 모두 확인합니다. HTTPS가 실패할 때 HTTP로 되돌리지 않습니다.

갱신 훅은 새 인증서·개인키를 위 디렉터리에 배치한 뒤 서버 작업 폴더에서 아래를 실행합니다. prod 대신 dev를 사용하는 환경은 파일 이름을 바꿉니다. 인증서 만료 모니터링도 함께 설정합니다.

```bash
docker compose -f compose.prod.yml --env-file .env --env-file versions.env exec -T nginx nginx -t
docker compose -f compose.prod.yml --env-file .env --env-file versions.env exec -T nginx nginx -s reload
```

검증용 `tests/verify_https.py`는 임시 자체 서명 인증서와 격리된 nginx만 사용합니다. Docker·OpenSSL이 있는 환경에서 `python3 backend/infra/deploy/tests/verify_https.py`로 실행하며 운영 인증서나 계정은 사용하지 않습니다.

### Certbot 자동화

`certificates.py`는 새 Linux 배포 호스트의 Python 3·Docker·OpenSSL·systemd를 사용합니다. Certbot은 고정된 공식 `certbot/certbot:v5.10.0` 컨테이너로 실행하며 Docker 소켓을 그 컨테이너에 넘기지 않습니다. 프로젝트 파일·`.env`·`versions.env`가 준비된 배포 폴더에서 실행합니다.

```bash
# <새 서버 공인 IP 또는 API 도메인>은 실제 본인 소유 대상만 입력합니다.
sudo python3 certificates.py issue prod --base-dir /opt/mujuthaek \
  --identifier '<새 서버 공인 IP 또는 API 도메인>' --email '<연락용 이메일>'

# 실제 갱신 없이 ACME staging으로 갱신 검증
sudo python3 certificates.py test-renew prod --base-dir /opt/mujuthaek
systemctl status mujuthaek-certbot-prod.timer
journalctl -u mujuthaek-certbot-prod.service
```

`issue`는 현재 nginx를 중지하고 인증 파일만 제공하는 bootstrap을 연 뒤 staging 검증→실제 발급→인증서 체인·키·대상 검사→TLS 전환을 진행합니다. 검증·발급 실패 시 bootstrap은 인증 경로만 제공하며 HTTP API로 대체하지 않습니다. 잠시 중단이 있을 수 있으므로 새 서버의 첫 HTTPS 구성용으로 사용합니다. 기존 인증서 파일이 직접 배치돼 있으면 자동 덮어쓰지 않고 마이그레이션이 필요하다고 중단합니다.

발급 성공 후 systemd timer가 하루 4번 갱신 필요 여부를 검사하고, 필요한 경우 갱신한 인증서 쌍을 원자적으로 교체하고 nginx 검사·reload를 수행합니다. 서버가 꺼져 있으면 timer도 실행되지 않습니다. 새 배포에서 이전 팀의 서버 중지 스케줄을 그대로 적용하지 마세요. 갱신 실패는 systemd 로그·실패 상태로 남으며 별도 모니터링 연결이 필요합니다.

연락 이메일은 CLI 또는 Git에서 제외되는 `tls-contact.json`으로 설정할 수 있습니다. 이 이메일을 등록하는 것만으로 만료·실패 알림이 발송되는 것은 아닙니다. Let's Encrypt는 만료 안내 이메일을 종료했습니다. [Certbot IP 인증서 안내](https://letsencrypt.org/2026/03/11/shorter-certs-certbot), [이메일 종료 안내](https://letsencrypt.org/2025/01/22/ending-expiration-emails/).
