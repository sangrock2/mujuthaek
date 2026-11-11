"use client";

// GET /api/v1/areas/sites/{siteId} (백엔드 SiteDetail) → 단지 하나의 생활권 항목 점수·지표
import { useQuery } from "@tanstack/react-query";
import { mockQuery } from "@/features/mock-query";
import { api } from "@/lib/api/client";
import { USE_MOCKS } from "@/lib/api/config";
import { endpoints } from "@/lib/api/endpoints";

type LifeCategory = "TRANSIT" | "SCHOOL" | "PARK" | "CONVENIENCE" | "HOSPITAL";

export type ApiSiteDetail = {
  siteId: string;
  lat: number;
  lng: number;
  /** 법정동 대표점(대략 위치)이면 true */
  approximate: boolean;
  metrics: {
    nearestStation: { name: string; meters: number; walkMinutes: number } | null;
    stationCount1km: number;
    busStopNearestM: number | null;
    busStops300m: number;
    elementaryNearestM: number | null;
    middleSchools1km: number;
    highSchools1km: number;
    parkNearestM: number | null;
    parkArea1kmM2: number;
    hospitalNearestM: number | null;
    clinics500m: number;
    convenienceStores300m: number;
    martNearestM: number | null;
    stores300m: number;
  } | null;
  categoryScores: Partial<Record<LifeCategory | "WORK", number>>;
  tags: string[];
  calculatedAt: string | null;
};

/** 단지 하나의 생활권 화면 값 */
export type SiteLife = {
  approximate: boolean;
  /** 항목별 점수 0~100 (총점과 같은 5개 항목) */
  categories: { key: LifeCategory; label: string; score: number }[];
  /** 가까운 시설 (있는 것만) */
  facts: { label: string; value: string }[];
};

const categoryLabel: Record<LifeCategory, string> = {
  TRANSIT: "교통",
  SCHOOL: "학교",
  PARK: "공원",
  CONVENIENCE: "편의시설",
  HOSPITAL: "병원",
};

/** 120m → "120m", 1,450m → "1.5km" */
const distance = (m: number) => (m < 1000 ? `${m}m` : `${(m / 1000).toFixed(1)}km`);

export function toSiteLife(d: ApiSiteDetail): SiteLife {
  const m = d.metrics;
  const facts: SiteLife["facts"] = [];
  if (m?.nearestStation) {
    facts.push({
      label: `${m.nearestStation.name}역까지`,
      value: `도보 ${m.nearestStation.walkMinutes}분`,
    });
  } else if (m?.busStopNearestM != null) {
    facts.push({ label: "버스 정류장까지", value: distance(m.busStopNearestM) });
  }
  if (m?.elementaryNearestM != null)
    facts.push({ label: "초등학교까지", value: distance(m.elementaryNearestM) });
  if (m?.parkNearestM != null) facts.push({ label: "공원까지", value: distance(m.parkNearestM) });
  if (m && m.convenienceStores300m > 0)
    facts.push({ label: "300m 안 편의점", value: `${m.convenienceStores300m}곳` });
  if (m?.hospitalNearestM != null)
    facts.push({ label: "병원까지", value: distance(m.hospitalNearestM) });
  return {
    approximate: d.approximate,
    categories: (Object.keys(categoryLabel) as LifeCategory[])
      .filter((k) => d.categoryScores[k] != null)
      .map((k) => ({ key: k, label: categoryLabel[k], score: d.categoryScores[k]! })),
    facts,
  };
}

const siteLifeKey = (areaId: string) => ["area", "site", areaId] as const;

/** 실제 API: 지표는 하루 한 번 꼴로 바뀌어서 길게 둬요 */
function useApiSiteLife(areaId: string | null) {
  const q = useQuery({
    queryKey: siteLifeKey(areaId ?? ""),
    queryFn: async () => toSiteLife(await api.get<ApiSiteDetail>(endpoints.areaSite(areaId!))),
    enabled: Boolean(areaId),
    staleTime: 30 * 60 * 1000,
  });
  return { data: q.data, loading: Boolean(areaId) && q.isPending, error: q.isError };
}

/** 목업 단지의 항목 점수 (총점 = 다섯 항목 평균, mocks/notice의 life.sites와 맞춰요) */
const mockLife = (scores: number[], facts: SiteLife["facts"]): SiteLife => ({
  approximate: false,
  categories: (Object.keys(categoryLabel) as LifeCategory[]).map((key, i) => ({
    key,
    label: categoryLabel[key],
    score: scores[i]!,
  })),
  facts,
});

const mockSiteLives: Record<string, SiteLife> = {
  // ○○지구 행복주택 A블록 (82점)
  "mock-area-1": mockLife(
    [90, 72, 81, 88, 79],
    [
      { label: "○○역까지", value: "도보 6분" },
      { label: "초등학교까지", value: "320m" },
      { label: "공원까지", value: "450m" },
      { label: "300m 안 편의점", value: "5곳" },
    ],
  ),
  // 양산 삼성파크빌 (58점): 가까운 역이 없어 버스 정류장 거리를 보여 줘요
  "mock-area-2": mockLife(
    [41, 66, 74, 52, 57],
    [
      { label: "버스 정류장까지", value: "90m" },
      { label: "초등학교까지", value: "540m" },
      { label: "공원까지", value: "380m" },
      { label: "300m 안 편의점", value: "2곳" },
      { label: "병원까지", value: "1.4km" },
    ],
  ),
  // ○○지구 행복주택 B블록 (74점)
  "mock-area-3": mockLife(
    [70, 80, 76, 72, 72],
    [
      { label: "○○역까지", value: "도보 9분" },
      { label: "초등학교까지", value: "260m" },
      { label: "공원까지", value: "520m" },
      { label: "300m 안 편의점", value: "3곳" },
    ],
  ),
};

function useMockSiteLife(areaId: string | null) {
  const q = useQuery(
    mockQuery(
      siteLifeKey(areaId ?? ""),
      mockSiteLives[areaId ?? ""] ?? mockSiteLives["mock-area-1"]!,
    ),
  );
  return { data: areaId ? q.data : undefined, loading: false, error: false };
}

// USE_MOCKS는 빌드 때 정해지는 값이라 훅 순서가 바뀌지 않아요
export const useSiteLife = USE_MOCKS ? useMockSiteLife : useApiSiteLife;

// GET /api/v1/areas/criteria (백엔드 AreaCriteria): 생활권 점수 기준표와 데이터 출처

type ApiAreaCriteria = {
  scoreVersion: string;
  /** 지표별 구간: xs(거리 m · 개수 · 면적) → ys(점수), 사이는 직선, 양끝 밖은 끝 값 */
  rules: { metric: string; xs: number[]; ys: number[] }[];
  /** 생활권 항목을 이루는 지표와 비중 */
  weights: { category: string; metric: string; weight: number }[];
  sources: {
    data: string;
    provider: string | null;
    license: string | null;
    licenseUrl: string | null;
  }[];
};

/** 생활권 점수 기준 화면 값 */
export type AreaCriteria = {
  /** 항목마다 지표 기준 줄 ("가장 가까운 역 (70%): 500m 안 100점 → …") */
  categories: { key: LifeCategory; label: string; lines: string[] }[];
  sources: { text: string; license?: string; licenseUrl?: string }[];
};

type MetricKind = "distance" | "count" | "area";

/** 지표 이름 (백엔드 area.score_rules.metric) → 화면 이름 · 단위 */
const metricInfo: Record<string, { label: string; kind: MetricKind }> = {
  station_nearest_m: { label: "가장 가까운 역", kind: "distance" },
  bus_stop_count_300m: { label: "300m 안 버스 정류장", kind: "count" },
  elementary_nearest_m: { label: "가장 가까운 초등학교", kind: "distance" },
  middle_count_1km: { label: "1km 안 중학교", kind: "count" },
  high_count_1km: { label: "1km 안 고등학교", kind: "count" },
  park_nearest_m: { label: "가장 가까운 공원", kind: "distance" },
  park_area_1km_m2: { label: "1km 안 공원 넓이", kind: "area" },
  convenience_store_count_300m: { label: "300m 안 편의점", kind: "count" },
  mart_nearest_m: { label: "가장 가까운 마트", kind: "distance" },
  hospital_nearest_m: { label: "가장 가까운 병원", kind: "distance" },
  clinic_count_500m: { label: "500m 안 동네 의원", kind: "count" },
};

/** 100000㎡ → "10만㎡" */
const areaText = (m2: number) =>
  m2 >= 10_000 ? `${(m2 / 10_000).toLocaleString("ko-KR")}만㎡` : `${m2.toLocaleString("ko-KR")}㎡`;

/** 1000m → "1km" (기준표 경계는 딱 떨어지는 값이라 소수점을 빼요) */
const boundText = (m: number) => (m >= 1000 && m % 1000 === 0 ? `${m / 1000}km` : distance(m));

const valueText = (kind: MetricKind, x: number) =>
  kind === "distance" ? boundText(x) : kind === "area" ? areaText(x) : `${x}곳`;

/**
 * 구간 → 한 줄. 거리: "500m 안 100점 → 1km 70점 → 3km부터 0점", 개수: "없으면 0점 → 5곳부터 100점".
 * 구간 사이는 직선으로 바뀌어요 (화면에 한 번 적어요)
 */
export function ruleText(kind: MetricKind, xs: number[], ys: number[]) {
  if (!xs.length || xs.length !== ys.length) return "";
  const last = xs.length - 1;
  const parts = xs.map((x, i) => {
    const v = valueText(kind, x);
    if (i === 0 && kind === "distance") return `${v} 안 ${ys[i]}점`;
    if (i === 0 && x === 0) return `없으면 ${ys[i]}점`;
    if (i === last) return `${v}부터 ${ys[i]}점`;
    return `${v} ${ys[i]}점`;
  });
  return parts.join(" → ");
}

export function toAreaCriteria(c: ApiAreaCriteria): AreaCriteria {
  const rules = new Map(c.rules.map((r) => [r.metric.toLowerCase(), r] as const));
  const categories = (Object.keys(categoryLabel) as LifeCategory[])
    .map((key) => {
      const lines = c.weights
        .filter((w) => w.category === key)
        .map((w) => {
          const metric = w.metric.toLowerCase();
          const info = metricInfo[metric];
          const rule = rules.get(metric);
          if (!info || !rule) return null;
          const share = Math.round(Number(w.weight) * 100);
          return `${info.label} (${share}%): ${ruleText(info.kind, rule.xs.map(Number), rule.ys.map(Number))}`;
        })
        .filter((l): l is string => Boolean(l));
      return { key, label: categoryLabel[key], lines };
    })
    .filter((g) => g.lines.length > 0);
  return {
    categories,
    sources: c.sources.map((s) => ({
      text: [s.data, s.provider].filter(Boolean).join(" · "),
      license: s.license ?? undefined,
      licenseUrl: s.licenseUrl ?? undefined,
    })),
  };
}

const criteriaKey = ["area", "criteria"] as const;

/** 실제 API: 하루 캐시라 길게 둬요. 못 불러오면 기준 칸을 숨겨요 */
function useApiAreaCriteria() {
  const q = useQuery({
    queryKey: criteriaKey,
    queryFn: async () => toAreaCriteria(await api.get<ApiAreaCriteria>(endpoints.areaCriteria)),
    staleTime: 24 * 60 * 60 * 1000,
    retry: false,
  });
  return q.data;
}

/** 목업: 백엔드 규칙 2026.1 (V202610241852__area_life_scores.sql)과 출처 목록 그대로 */
const mockAreaCriteria = toAreaCriteria({
  scoreVersion: "2026.1",
  rules: [
    { metric: "station_nearest_m", xs: [500, 1000, 2000, 3000], ys: [100, 70, 40, 0] },
    { metric: "bus_stop_count_300m", xs: [0, 5], ys: [0, 100] },
    { metric: "elementary_nearest_m", xs: [300, 600, 1000, 2000], ys: [100, 80, 60, 0] },
    { metric: "middle_count_1km", xs: [0, 2], ys: [0, 100] },
    { metric: "high_count_1km", xs: [0, 2], ys: [0, 100] },
    { metric: "park_nearest_m", xs: [300, 500, 1000, 2000], ys: [100, 80, 60, 0] },
    { metric: "park_area_1km_m2", xs: [0, 100000], ys: [0, 100] },
    { metric: "convenience_store_count_300m", xs: [0, 5], ys: [0, 100] },
    { metric: "mart_nearest_m", xs: [500, 1000, 3000], ys: [100, 70, 0] },
    { metric: "hospital_nearest_m", xs: [1000, 3000, 6000], ys: [100, 60, 0] },
    { metric: "clinic_count_500m", xs: [0, 5], ys: [0, 100] },
  ],
  weights: [
    { category: "TRANSIT", metric: "station_nearest_m", weight: 0.7 },
    { category: "TRANSIT", metric: "bus_stop_count_300m", weight: 0.3 },
    { category: "SCHOOL", metric: "elementary_nearest_m", weight: 0.6 },
    { category: "SCHOOL", metric: "middle_count_1km", weight: 0.2 },
    { category: "SCHOOL", metric: "high_count_1km", weight: 0.2 },
    { category: "PARK", metric: "park_nearest_m", weight: 0.7 },
    { category: "PARK", metric: "park_area_1km_m2", weight: 0.3 },
    { category: "CONVENIENCE", metric: "convenience_store_count_300m", weight: 0.6 },
    { category: "CONVENIENCE", metric: "mart_nearest_m", weight: 0.4 },
    { category: "HOSPITAL", metric: "hospital_nearest_m", weight: 0.6 },
    { category: "HOSPITAL", metric: "clinic_count_500m", weight: 0.4 },
  ],
  sources: [
    { data: "전국 도시철도역", provider: null, license: null, licenseUrl: null },
    { data: "전국 버스정류장 위치정보", provider: "국토교통부", license: null, licenseUrl: null },
    {
      data: "전국초중등학교위치표준데이터",
      provider: "공공데이터포털",
      license: null,
      licenseUrl: null,
    },
    {
      data: "전국도시공원정보표준데이터",
      provider: "공공데이터포털",
      license: null,
      licenseUrl: null,
    },
    {
      data: "병원정보서비스",
      provider: "건강보험심사평가원",
      license: "공공누리 제1유형 (출처표시)",
      licenseUrl: "https://www.kogl.or.kr/info/licenseType1.do",
    },
    { data: "상가(상권)정보", provider: "소상공인시장진흥공단", license: null, licenseUrl: null },
    {
      data: "도로명주소 출입구 정보·구역의 도형",
      provider: "행정안전부 주소기반산업지원서비스",
      license: null,
      licenseUrl: null,
    },
  ],
});

function useMockAreaCriteria() {
  return useQuery(mockQuery(criteriaKey, mockAreaCriteria)).data;
}

// USE_MOCKS는 빌드 때 정해지는 값이라 훅 순서가 바뀌지 않아요
export const useAreaCriteria: () => AreaCriteria | undefined = USE_MOCKS
  ? useMockAreaCriteria
  : useApiAreaCriteria;
