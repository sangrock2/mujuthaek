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

const mockSiteLife: SiteLife = {
  approximate: false,
  categories: [
    { key: "TRANSIT", label: "교통", score: 90 },
    { key: "SCHOOL", label: "학교", score: 72 },
    { key: "PARK", label: "공원", score: 81 },
    { key: "CONVENIENCE", label: "편의시설", score: 88 },
    { key: "HOSPITAL", label: "병원", score: 79 },
  ],
  facts: [
    { label: "망원역까지", value: "도보 6분" },
    { label: "초등학교까지", value: "320m" },
    { label: "공원까지", value: "450m" },
    { label: "300m 안 편의점", value: "5곳" },
  ],
};

function useMockSiteLife(areaId: string | null) {
  const q = useQuery(mockQuery(siteLifeKey(areaId ?? ""), mockSiteLife));
  return { data: areaId ? q.data : undefined, loading: false, error: false };
}

// USE_MOCKS는 빌드 때 정해지는 값이라 훅 순서가 바뀌지 않아요
export const useSiteLife = USE_MOCKS ? useMockSiteLife : useApiSiteLife;
