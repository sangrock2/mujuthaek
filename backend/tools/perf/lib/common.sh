# perf 스크립트들이 같이 쓰는 설정과 서버 접속. source 해서 써요
set -euo pipefail

PERF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -f "$PERF_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PERF_DIR/.env"
  set +a
fi

# 서버 주소는 저장소에 기본값으로 두지 않고 tools/perf/.env에서만 읽어요(2026-11-16 보안 감사 4장)
BASE_URL="${BASE_URL:-}"
EC2_HOST="${EC2_HOST:-}"
[ -n "$BASE_URL" ] || { echo "tools/perf/.env에 BASE_URL을 적어요 (.env.example 참고)" >&2; exit 1; }
[ -n "$EC2_HOST" ] || { echo "tools/perf/.env에 EC2_HOST를 적어요 (.env.example 참고)" >&2; exit 1; }
SSH_USER="${SSH_USER:-ubuntu}"
SSH_KEY="${SSH_KEY:-}"
SSH_KEY="${SSH_KEY/#\~/$HOME}"
if [ -z "${AWS_PROFILE:-}" ]; then unset AWS_PROFILE; fi
PROM=http://localhost:9090
GRAFANA=http://localhost:3300
REMOTE_DIR=/opt/mujuthaek

warn() { echo "  ! $*" >&2; }

# JWT를 직접 만들어도 되는 주소인지: 로컬·테스트 이름만이에요. k6/lib/token.js의 mintAllowed와 같은 규칙이에요
token_host_allowed() {
  local rest="${1#*://}" host
  if [ "${rest#\[}" != "$rest" ]; then host="${rest#\[}" && host="${host%%]*}"; else host="${rest%%[:/?#]*}"; fi
  host="$(printf '%s' "$host" | tr 'A-Z' 'a-z')"
  case "$host" in
    localhost | 127.0.0.1 | ::1 | *.localhost | *.test) return 0 ;;
    staging.* | dev.* | test.* | qa.*) return 0 ;;
    *) return 1 ;;
  esac
}

remote() {
  local key=()
  [ -n "$SSH_KEY" ] && key=(-i "$SSH_KEY")
  ssh ${key[@]+"${key[@]}"} -o BatchMode=yes -o ConnectTimeout=10 "$SSH_USER@$EC2_HOST" "$@"
}

# 표준 입력의 SQL을 운영 api DB에 돌려 CSV로 내요. 서버 .env의 API_DB_* 값으로 서버 안에서 psql을 띄워요(RDS는 밖에서 안 열려요)
remote_sql() {
  remote "cd $REMOTE_DIR && docker run --rm -i --env-file .env postgres:16-alpine sh -c '
    url=\"\${API_DB_URL#jdbc:}\"
    PGPASSWORD=\"\$API_DB_PASSWORD\" psql \"\$url\" -U \"\${API_DB_USER:-api_app}\" -X -q --csv -v ON_ERROR_STOP=1 -f -'"
}

remote_versions() {
  remote "cat $REMOTE_DIR/versions.env"
}
