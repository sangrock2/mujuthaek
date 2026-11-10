#!/usr/bin/env bash
# 서버에서 서비스 하나(또는 전부)를 그 버전 이미지로 바꿔요. GitHub Actions(deploy-dev.yml·release.yml)가 ssh로 불러요.
#   사용: deploy.sh <prod|dev> <api|notification|collector|extraction|all> <버전>
#   예:   deploy.sh prod api api-v1.2.0        deploy.sh dev all dev-1a2b3c4
# 하는 일: versions.env의 <서비스>_TAG만 바꿈(.env는 그대로) → 이미지 받기 → (collector·extraction) 그 이미지의 migrations로 Flyway
#          → up -d → 헬스체크(최대 3분). 실패하면 이전 태그로 되돌리고 exit 1. 마이그레이션은 되돌리지 않아요.
set -euo pipefail

BASE="${MUJUTHAEK_DIR:-/opt/mujuthaek}"
HEALTH_TIMEOUT=180

usage() {
  echo "사용: $0 <prod|dev> <api|notification|collector|extraction|all> <버전>" >&2
  exit 2
}

[ $# -eq 3 ] || usage
ENVIRONMENT="$1"
TARGET="$2"
VERSION="$3"

case "$ENVIRONMENT" in
  prod) SERVICES=(api notification collector extraction) ;;
  dev) SERVICES=(api notification extraction) ;;
  *) usage ;;
esac

if [ "$TARGET" = all ]; then
  TARGETS=("${SERVICES[@]}")
else
  found=no
  for s in "${SERVICES[@]}"; do [ "$s" = "$TARGET" ] && found=yes; done
  [ "$found" = yes ] || { echo "${ENVIRONMENT}에는 $TARGET 서비스가 없어요 (${SERVICES[*]})" >&2; exit 2; }
  TARGETS=("$TARGET")
fi

cd "$BASE"
[ -f .env ] || { echo "$BASE/.env가 없어요" >&2; exit 1; }
touch versions.env

# 빠지면 화면 일부가 안 되는 키를 이름만 확인해요(값은 출력하지 않아요). 배포는 막지 않고 경고만 해요.
#   EXTRACTION_REVIEW_TOKEN: api ↔ 검수 API(extraction:8092). 없으면 다른 컨테이너 요청이 401 → 관리자 검수 503
#   COLLECTOR_ADMIN_TOKEN:   api ↔ 수집기 관리자 API(collector:8093, 운영만). 없으면 수집 현황 503
#   SLACK_WEBHOOK_URL:       운영 오류 알림(api·수집기·추출기). 없으면 알림 없이 로그만
#   NOTIFICATION_INTERNAL_TOKEN: api ↔ 알림 서버 내부 통계(notification:8081). 없으면 다른 컨테이너 요청이 403 → 관리자 알림 통계가 안 됨
check_keys() {
  local key missing=()
  for key in "$@"; do
    grep -qE "^${key}=.+" .env || missing+=("$key")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "경고: .env(ENV_FILE)에 값이 없는 키: ${missing[*]} (README 「서비스 사이 연결」)" >&2
  fi
}
case "$ENVIRONMENT" in
  prod) check_keys EXTRACTION_REVIEW_TOKEN COLLECTOR_ADMIN_TOKEN SLACK_WEBHOOK_URL NOTIFICATION_INTERNAL_TOKEN ;;
  dev) check_keys EXTRACTION_REVIEW_TOKEN SLACK_WEBHOOK_URL NOTIFICATION_INTERNAL_TOKEN ;;
esac

compose() {
  docker compose -f "compose.$ENVIRONMENT.yml" --env-file .env --env-file versions.env "$@"
}

tag_key() {
  echo "$(echo "$1" | tr '[:lower:]' '[:upper:]')_TAG"
}

get_tag() {
  local line
  line="$(grep -E "^$(tag_key "$1")=" versions.env || true)"
  echo "${line#*=}"
}

set_tag() {
  local key value
  key="$(tag_key "$1")"
  value="$2"
  if grep -qE "^$key=" versions.env; then
    sed -i.bak "s|^$key=.*|$key=$value|" versions.env && rm -f versions.env.bak
  else
    echo "$key=$value" >> versions.env
  fi
}

# 다른 서비스 태그가 아직 없으면(첫 배포 중) compose가 멈추지 않게 지금 버전으로 채워 둬요
for s in "${SERVICES[@]}"; do
  [ -n "$(get_tag "$s")" ] || set_tag "$s" "$VERSION"
done

# compose 파일의 image와 같은 규칙 (IMAGE_PREFIX를 versions.env에 두면 바꿀 수 있어요)
image_of() {
  local prefix line
  line="$(grep -E '^IMAGE_PREFIX=' versions.env || true)"
  prefix="${line#*=}"
  echo "${prefix:-ghcr.io/prgrms-be-devcourse/nbe11-13-final-team02}/$1:$(get_tag "$1")"
}

# 그 버전 이미지 안의 migrations를 꺼내 ./migrations/<서비스>에 두고 Flyway 적용
migrate() {
  local svc="$1" image
  image="$(image_of "$svc")"
  rm -rf "migrations/$svc"
  mkdir -p "migrations/$svc"
  docker run --rm --entrypoint tar "$image" -C "/app/services/$svc/migrations" -cf - . | tar -xf - -C "migrations/$svc"
  echo "[$svc] Flyway 적용 ($image)"
  compose --profile migrate run --rm "migrate-$svc"
}

wait_healthy() {
  local svc="$1" deadline status container
  deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    case "$svc" in
      api) curl -fsS -o /dev/null http://127.0.0.1:8080/actuator/health && return 0 ;;
      notification) curl -fsS -o /dev/null http://127.0.0.1:8081/actuator/health && return 0 ;;
      *)
        container="$(compose ps -q "$svc")"
        if [ -n "$container" ]; then
          status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container")"
          [ "$status" = healthy ] && return 0
        fi
        ;;
    esac
    sleep 5
  done
  return 1
}

declare -A PREVIOUS
for s in "${TARGETS[@]}"; do
  PREVIOUS[$s]="$(get_tag "$s")"
done

rollback() {
  echo "실패: 이전 태그로 되돌려요" >&2
  for s in "${TARGETS[@]}"; do
    if [ -n "${PREVIOUS[$s]}" ] && [ "${PREVIOUS[$s]}" != "$VERSION" ]; then
      set_tag "$s" "${PREVIOUS[$s]}"
      echo "  $s → ${PREVIOUS[$s]}" >&2
      compose up -d "$s" || true
    fi
  done
  exit 1
}

for s in "${TARGETS[@]}"; do
  set_tag "$s" "$VERSION"
done

echo "== $ENVIRONMENT: ${TARGETS[*]} → $VERSION"
compose pull "${TARGETS[@]}" || rollback

compose up -d rabbitmq
wait_rabbitmq() {
  local deadline container
  deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
  container="$(compose ps -q rabbitmq)"
  while [ "$(date +%s)" -lt "$deadline" ]; do
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$container")" = healthy ] && return 0
    sleep 5
  done
  return 1
}
wait_rabbitmq || { echo "RabbitMQ가 준비되지 않았어요" >&2; rollback; }

for s in "${TARGETS[@]}"; do
  case "$s" in
    collector | extraction) migrate "$s" || rollback ;;
  esac
done

for s in "${TARGETS[@]}"; do
  echo "[$s] 시작"
  compose up -d "$s" || rollback
  if ! wait_healthy "$s"; then
    echo "[$s] ${HEALTH_TIMEOUT}초 안에 정상 응답이 없어요" >&2
    compose logs --tail 50 "$s" >&2 || true
    rollback
  fi
  echo "[$s] 정상"
done

compose up -d nginx
docker image prune -f > /dev/null
echo "== 끝: $(tr '\n' ' ' < versions.env)"
