"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { ListingVerdict } from "@/components/ui/Badge";
import { noticeTypeLabel } from "@/features/notice/labels";
import { api } from "@/lib/api/client";
import { endpoints } from "@/lib/api/endpoints";

/** GET /api/v1/notices/map 응답 (백엔드 NoticeMapResponse) */
export type MapCluster = {
  regionCode: string | null;
  regionName: string | null;
  count: number;
  lat: number;
  lng: number;
};
export type MapPinItem = {
  id: string;
  title: string;
  noticeType: string | null;
  applyEnd: string | null;
  lat: number;
  lng: number;
};
export type NoticeMapResponse = { clusters: MapCluster[]; pins: MapPinItem[] };

export type MapView = {
  swLat: number;
  swLng: number;
  neLat: number;
  neLng: number;
  /** 카카오맵 확대 단계 (1이 가장 가까워요) */
  level: number;
};

/**
 * 카카오맵 단계 → 백엔드 zoom (웹 지도 확대 단계, 클수록 가까워요).
 * 백엔드는 zoom 10 미만이면 시·도, 아니면 시·군·구로 묶어요
 */
export const zoomOf = (level: number) => 20 - level;

/** 좌표를 조금 뭉개서 지도를 살짝 움직일 때마다 다시 받지 않게 해요 */
const round = (v: number) => Math.round(v * 100) / 100;

export function useNoticeMap(view: MapView | null, tenure: "RENT" | "BUY") {
  return useQuery({
    queryKey: [
      "notices",
      "map",
      view && [round(view.swLat), round(view.swLng), round(view.neLat), round(view.neLng)],
      view?.level,
      tenure,
    ] as const,
    queryFn: () => {
      const v = view!;
      const q = new URLSearchParams({
        swLat: String(v.swLat),
        swLng: String(v.swLng),
        neLat: String(v.neLat),
        neLng: String(v.neLng),
        zoom: String(zoomOf(v.level)),
        tenure,
      });
      return api.get<NoticeMapResponse>(`${endpoints.noticesMap}?${q}`);
    },
    enabled: view !== null,
    // 공개 정보라 조금 길게 둬요
    staleTime: 5 * 60 * 1000,
    placeholderData: keepPreviousData,
  });
}

/** "2026-11-02" → 오늘부터 며칠 (한국 날짜) */
function ddayOf(applyEnd: string, now: Date) {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(now);
  return Math.round((Date.parse(applyEnd) - Date.parse(today)) / 86_400_000);
}

/** 핀 둘째 줄: "행복주택 · D-12" */
export function pinLabel(pin: MapPinItem, now = new Date()) {
  const type = (pin.noticeType && noticeTypeLabel[pin.noticeType]) || "공고";
  if (!pin.applyEnd) return type;
  const d = ddayOf(pin.applyEnd, now);
  return d < 0 ? type : d === 0 ? `${type} · 오늘 마감` : `${type} · D-${d}`;
}

/** 시·도 대표 좌표 (지도를 처음 열 때 찾아볼 지역 쪽으로) */
const sidoCenter: Record<string, [number, number]> = {
  "11": [37.5665, 126.978],
  "26": [35.1796, 129.0756],
  "27": [35.8714, 128.6014],
  "28": [37.4563, 126.7052],
  "29": [35.1595, 126.8526],
  "30": [36.3504, 127.3845],
  "31": [35.5384, 129.3114],
  "36": [36.48, 127.289],
  "41": [37.2752, 127.0095],
  "42": [37.8854, 127.7298],
  "43": [36.6357, 127.4917],
  "44": [36.6588, 126.6728],
  "45": [35.8203, 127.1088],
  "46": [34.8161, 126.4629],
  "47": [36.576, 128.5056],
  "48": [35.2383, 128.6922],
  "50": [33.4996, 126.5312],
  "51": [37.8854, 127.7298],
  "52": [35.8203, 127.1088],
};

/** 처음 보여줄 곳과 확대 단계. 시·군·구를 골랐으면 더 가까이 */
export function initialCenter(regionCodes: string[]): { lat: number; lng: number; level: number } {
  // 전체 지역이면 남한 전체가 보이게
  if (regionCodes.length === 0) return { lat: 36.3, lng: 127.8, level: 13 };
  const code = regionCodes[0];
  const [lat, lng] = sidoCenter[code.slice(0, 2)] ?? sidoCenter["11"];
  return { lat, lng, level: code.length > 2 ? 8 : 10 };
}

/** 핀 색: 맞춤 목록에서 받은 판정. 목록에 없는 공고는 판정 전(회색) */
export type PinTone = ListingVerdict | "unknown";
