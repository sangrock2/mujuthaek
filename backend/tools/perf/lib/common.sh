# perf 스크립트들이 같이 쓰는 설정과 서버 접속. source 해서 써요
set -euo pipefail

PERF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -f "$PERF_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PERF_DIR/.env"
  set +a
fi

BASE_URL="${BASE_URL:-http://3.37.131.73}"
EC2_HOST="${EC2_HOST:-3.37.131.73}"
SSH_USER="${SSH_USER:-ubuntu}"
SSH_KEY="${SSH_KEY:-}"
SSH_KEY="${SSH_KEY/#\~/$HOME}"
if [ -z "${AWS_PROFILE:-}" ]; then unset AWS_PROFILE; fi
PROM=http://localhost:9090
GRAFANA=http://localhost:3300
REMOTE_DIR=/opt/mujuthaek

warn() { echo "  ! $*" >&2; }

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
