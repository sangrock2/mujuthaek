#!/usr/bin/env bash
# 결과 폴더의 시간 구간(meta.json)으로 그래프 이미지·서버 지표·CloudWatch를 (다시) 모아요.
# CloudWatch는 몇 분 늦게 채워져서, run.sh 직후 비어 보이면 10분 뒤에 이걸 한 번 더 돌려요.
#   perf/collect.sh perf/results/<폴더>
source "$(dirname "$0")/lib/common.sh"

OUT="${1:?결과 폴더를 넘겨요}"
START=$(jq -r .start_epoch "$OUT/meta.json")
END=$(jq -r .end_epoch "$OUT/meta.json")
# 그래프는 앞뒤 1분씩 여유를 둬요(올라가기 전·내려온 뒤가 보이게)
FROM=$(( (START - 60) * 1000 ))
TO=$(( (END + 60) * 1000 ))

echo "  서버 지표 → server_by_uri.csv, server_summary.json, timeseries/"
python3 "$PERF_DIR/lib/tools.py" prom "$OUT" "$START" "$END" || warn "Prometheus 내보내기 실패"

echo "  Grafana 그래프 → images/"
mkdir -p "$OUT/images"
panels=$(jq '.panels | length' "$PERF_DIR/grafana/dashboards/perf.json")
for id in $(seq 1 "$panels"); do
  curl -sf -o "$OUT/images/$(printf %02d "$id").png" \
    "$GRAFANA/render/d-solo/mujuthaek-perf/x?orgId=1&panelId=$id&from=$FROM&to=$TO&width=1200&height=500&tz=Asia%2FSeoul" \
    || warn "패널 $id 이미지 실패"
done
curl -sf -o "$OUT/images/00-dashboard.png" \
  "$GRAFANA/render/d/mujuthaek-perf/x?orgId=1&from=$FROM&to=$TO&width=1600&height=$(( (panels + 1) / 2 * 330 + 120 ))&kiosk&tz=Asia%2FSeoul" \
  || warn "대시보드 전체 이미지 실패"

if command -v aws > /dev/null && [ -n "${EC2_INSTANCE_ID:-}${RDS_INSTANCE_ID:-}" ]; then
  echo "  CloudWatch → images/cw-*.png, cloudwatch.json"
  iso() { date -u -r "$1" +%Y-%m-%dT%H:%M:%SZ; }
  S=$(iso $((START - 60)))
  E=$(iso $((END + 60)))
  region=(--region "${AWS_REGION:-ap-northeast-2}")
  widget() { # 파일 제목 기간 지표JSON
    jq -n --arg t "$2" --arg s "$S" --arg e "$E" --argjson p "$3" --argjson m "$4" \
      '{title:$t, start:$s, end:$e, period:$p, stat:"Average", width:1200, height:500, timezone:"+0900", metrics:$m}' > "$OUT/.widget.json"
    aws cloudwatch get-metric-widget-image "${region[@]}" --metric-widget "file://$OUT/.widget.json" \
      --output-format png --query MetricWidgetImage --output text 2> /dev/null | base64 -d > "$OUT/images/$1.png" \
      && [ -s "$OUT/images/$1.png" ] || { rm -f "$OUT/images/$1.png"; warn "CloudWatch $1 실패(aws 로그인·권한)"; }
  }
  queries='[]'
  if [ -n "${EC2_INSTANCE_ID:-}" ]; then
    # EC2 기본 모니터링은 5분 단위예요
    widget cw-ec2 "EC2 CPU · 크레딧" 300 "$(jq -nc --arg i "$EC2_INSTANCE_ID" \
      '[["AWS/EC2","CPUUtilization","InstanceId",$i],[".","CPUCreditBalance",".",".",{"yAxis":"right"}],[".","CPUSurplusCreditsCharged",".",".",{"yAxis":"right"}]]')"
    queries=$(jq -c --arg i "$EC2_INSTANCE_ID" '. + [
      {Id:"ec2cpu", MetricStat:{Metric:{Namespace:"AWS/EC2",MetricName:"CPUUtilization",Dimensions:[{Name:"InstanceId",Value:$i}]},Period:300,Stat:"Average"}},
      {Id:"credit", MetricStat:{Metric:{Namespace:"AWS/EC2",MetricName:"CPUCreditBalance",Dimensions:[{Name:"InstanceId",Value:$i}]},Period:300,Stat:"Minimum"}}]' <<< "$queries")
  fi
  if [ -n "${RDS_INSTANCE_ID:-}" ]; then
    widget cw-rds "RDS CPU · 커넥션" 60 "$(jq -nc --arg i "$RDS_INSTANCE_ID" \
      '[["AWS/RDS","CPUUtilization","DBInstanceIdentifier",$i],[".","DatabaseConnections",".",".",{"yAxis":"right"}]]')"
    widget cw-rds-io "RDS 메모리 · IO" 60 "$(jq -nc --arg i "$RDS_INSTANCE_ID" \
      '[["AWS/RDS","FreeableMemory","DBInstanceIdentifier",$i],[".","ReadIOPS",".",".",{"yAxis":"right"}],[".","WriteIOPS",".",".",{"yAxis":"right"}]]')"
    queries=$(jq -c --arg i "$RDS_INSTANCE_ID" '. + [
      {Id:"rdscpu", MetricStat:{Metric:{Namespace:"AWS/RDS",MetricName:"CPUUtilization",Dimensions:[{Name:"DBInstanceIdentifier",Value:$i}]},Period:60,Stat:"Maximum"}},
      {Id:"rdsconn", MetricStat:{Metric:{Namespace:"AWS/RDS",MetricName:"DatabaseConnections",Dimensions:[{Name:"DBInstanceIdentifier",Value:$i}]},Period:60,Stat:"Maximum"}},
      {Id:"rdsmem", MetricStat:{Metric:{Namespace:"AWS/RDS",MetricName:"FreeableMemory",Dimensions:[{Name:"DBInstanceIdentifier",Value:$i}]},Period:60,Stat:"Minimum"}}]' <<< "$queries")
  fi
  rm -f "$OUT/.widget.json"
  aws cloudwatch get-metric-data "${region[@]}" --start-time "$S" --end-time "$E" \
    --metric-data-queries "$queries" --output json > "$OUT/cloudwatch.json" 2> /dev/null \
    || { rm -f "$OUT/cloudwatch.json"; warn "CloudWatch 숫자 실패"; }
else
  warn "CloudWatch는 건너뛰었어요(perf/.env의 EC2_INSTANCE_ID·RDS_INSTANCE_ID). 필요하면 AWS 콘솔에서 캡처해 images/에 넣어요"
fi

echo "  Prometheus 스냅숏"
snap=$(curl -sf -X POST "$PROM/api/v1/admin/tsdb/snapshot" | jq -r .data.name) && echo "$snap" > "$OUT/prometheus_snapshot.txt" || warn "스냅숏 실패"
