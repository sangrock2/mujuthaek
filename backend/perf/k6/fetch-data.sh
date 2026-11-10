#!/usr/bin/env bash
# k6가 쓸 테스트 데이터(지역 코드, 공고 id, 지도 영역, 가짜 지원자 조건)를 운영에서 한 번 뽑아 data/data.json에 써요.
# 개선 전후를 같은 데이터로 비교해야 해서, baseline을 잰 뒤에는 다시 뽑지 않아요(파일을 커밋해 둬요).
#   perf/k6/fetch-data.sh [BASE_URL]
set -euo pipefail

BASE_URL="${1:-${BASE_URL:-http://3.37.131.73}}"
OUT="$(cd "$(dirname "$0")" && pwd)/data/data.json"

regions="$(curl -fsS "$BASE_URL/api/v1/regions")"
notices="$(curl -fsS -X POST -H 'Content-Type: application/json' -d '{"sort":"DEADLINE","size":100}' "$BASE_URL/api/v1/notices/search")"

jq -n --argjson regions "$regions" --argjson notices "$notices" '
{
  sidoCodes: [$regions.sidos[].code],
  # 시군구는 앞에서부터 고르게 40개(매번 같은 값이 나오게 무작위로 뽑지 않아요)
  sigunguCodes: ([$regions.sidos[].sigungus[].code] | . as $all | [range(0; length; ((length / 40) | ceil | if . < 1 then 1 else . end))] | map($all[.])),
  noticeIds: [$notices.items[].id],
  # [swLat, swLng, neLat, neLng, zoom]: 서울 전체·강남·수도권·부산
  mapBoxes: [
    [37.42, 126.76, 37.70, 127.18, 11],
    [37.47, 127.00, 37.53, 127.10, 14],
    [37.20, 126.60, 37.80, 127.40, 10],
    [35.05, 128.90, 35.25, 129.20, 12]
  ],
  # 화면이 보내는 판정 입력 모양. 실제 사람 값이 아니에요(regionCode는 k6가 시군구에서 골라 채워요)
  applicants: [
    { birthMonth: "1997-03", householdHead: true, householdSize: 1, marital: "SINGLE", homeOwner: false, homelessYears: "1_3",
      targetGroups: ["YOUTH"], subscription: { months: "12_24", payments: 18 },
      income: { MEDIAN_INCOME: { gtPct: 50, lePct: 100 } }, incomeYear: 2026,
      assets: { gtWon: 0, leWon: 100000000 }, car: { gtWon: 0, leWon: 10000000 } },
    { birthMonth: "1993-08", householdHead: true, householdSize: 2, marital: "MARRIED", marriedOn: "2024-05", children: 0,
      homeOwner: false, homelessYears: "3_5", targetGroups: ["NEWLYWED"], subscription: { months: "24_PLUS", payments: 40 },
      income: { URBAN_WORKER_INCOME: { gtPct: 70, lePct: 120 } }, householdIncome: { URBAN_WORKER_INCOME: { gtPct: 100, lePct: 140 } },
      incomeYear: 2026, assets: { gtWon: 100000000, leWon: 300000000 }, car: { gtWon: 0, leWon: 35000000 } },
    { birthMonth: "2003-11", householdHead: false, householdSize: 3, marital: "SINGLE", homeOwner: false, homelessYears: "LT_1",
      targetGroups: ["UNIVERSITY_STUDENT"], subscription: { months: "LT_6", payments: 2 },
      income: { MEDIAN_INCOME: { gtPct: 0, lePct: 50 } }, incomeYear: 2026, assets: { gtWon: 0, leWon: 20000000 } },
    { birthMonth: "1985-01", householdHead: true, householdSize: 4, marital: "MARRIED", marriedOn: "2012-10", children: 2,
      homeOwner: false, homelessYears: "5_PLUS", welfareStatuses: ["NEAR_POOR"], subscription: { months: "24_PLUS", payments: 120 },
      householdIncome: { MEDIAN_INCOME: { gtPct: 50, lePct: 100 } }, incomeYear: 2026,
      assets: { gtWon: 50000000, leWon: 200000000 }, car: { gtWon: 0, leWon: 20000000 } }
  ]
}' > "$OUT"

echo "$OUT: 시도 $(jq '.sidoCodes|length' "$OUT"), 시군구 $(jq '.sigunguCodes|length' "$OUT"), 공고 $(jq '.noticeIds|length' "$OUT")"
