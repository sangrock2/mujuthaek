#!/usr/bin/env bash
# 개선 전후 결과 폴더 두 개를 표로 비교해요(마크다운). 같은 테스트끼리 비교해요.
#   perf/compare.sh perf/results/<전> perf/results/<후> [> 비교.md]
source "$(dirname "$0")/lib/common.sh"
[ $# -eq 2 ] || { sed -n '2,3p' "$0"; exit 1; }
[ "$(jq -r .test "$1/meta.json")" = "$(jq -r .test "$2/meta.json")" ] || warn "테스트 종류가 달라요"
[ "$(jq -r .data_json_sha256 "$1/meta.json")" = "$(jq -r .data_json_sha256 "$2/meta.json")" ] || warn "테스트 데이터(data.json)가 달라요"
python3 "$PERF_DIR/lib/tools.py" compare "$1" "$2"
