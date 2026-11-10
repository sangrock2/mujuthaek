"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { formatWon } from "@/features/notice/format";
import type { NoticeJudgment } from "@/features/notice/judgment";
import { api } from "@/lib/api/client";
import { endpoints } from "@/lib/api/endpoints";
import type { NoticeSite, NoticeUnit } from "@/mocks/notice";

/** GET /api/v1/notices/{id}/units 한 줄 (백엔드 NoticeUnitResponse) */
type ApiUnit = {
  id: string;
  siteId: string | null;
  siteName: string | null;
  address: string | null;
  unitLabel: string | null;
  floor: string | null;
  houseType: string | null;
  exclusiveM2: number | null;
  depositWon: number | null;
  rentWon: number | null;
  /** 가격 대상별 (예: 「수급자 등」·「그 외」) */
  prices: { targets: string[]; depositWon: number | null; rentWon: number | null }[];
};

type ApiUnitPage = { items: ApiUnit[]; nextCursor: string | null; hasNext: boolean };

/** 백엔드가 한 번에 주는 최대 개수 */
const PAGE_SIZE = 100;

/** 주택목록 (호별). 공개 정보라 조금 길게 둬요 */
export function useNoticeUnits(id: string, enabled: boolean) {
  return useInfiniteQuery({
    queryKey: ["notice", "units", id] as const,
    queryFn: ({ pageParam }) => {
      const q = new URLSearchParams({ size: String(PAGE_SIZE) });
      if (pageParam) q.set("cursor", pageParam);
      return api.get<ApiUnitPage>(`${endpoints.noticeUnits(id)}?${q}`);
    },
    initialPageParam: null as string | null,
    getNextPageParam: (last) => (last.hasNext ? last.nextCursor : null),
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}

/** 응답 한 줄 → 화면 집 하나. 신청 가능 · 준비할 돈은 내 판정의 주택형별 값으로 */
export function toUnit(
  u: ApiUnit,
  sites: NoticeSite[],
  judgment: NoticeJudgment | null,
): NoticeUnit {
  const site = sites.find((s) => s.id === u.siteId);
  const type = u.houseType ?? "";
  const siteName = u.siteName ?? site?.name ?? undefined;
  return {
    id: u.id,
    name: [siteName, u.unitLabel].filter(Boolean).join(" ") || "공급 주택",
    label: u.unitLabel ?? undefined,
    siteName,
    addr: u.address ?? undefined,
    type: type || "주택형 확인",
    area: u.exclusiveM2 === null ? "면적 확인" : `${u.exclusiveM2}㎡`,
    floor: u.floor ?? "층 확인",
    deposit: u.depositWon === null ? "원문 확인" : formatWon(u.depositWon),
    rent: u.rentWon === null ? "월세 원문 확인" : `월 ${formatWon(u.rentWon)}`,
    // 가격 대상이 둘 이상일 때만 (하나면 deposit·rent와 같아요)
    prices:
      u.prices.length > 1
        ? u.prices.map((p) => ({
            target: p.targets.join("·") || "모든 신청자",
            deposit: p.depositWon === null ? "원문 확인" : formatWon(p.depositWon),
            rent: p.rentWon === null ? "월세 원문 확인" : `월 ${formatWon(p.rentWon)}`,
          }))
        : undefined,
    station: "",
    ok: Boolean(judgment?.mineTypes.includes(type)),
    otherTarget: judgment ? "다른 대상" : "판정 전",
    prep: judgment?.prepByType[type] ?? "확인 필요",
    siteId: u.siteId ?? undefined,
    lifeScore: site?.lifeScore,
    // 호마다 좌표가 없어서 그림 지도 위치는 쓰지 않아요 (단지 위치는 카카오맵으로)
    x: 0,
    y: 0,
  };
}

/** 단지별로 묶어요 (백엔드가 단지 순서로 줘요). count는 all에서 센 그 단지 호수 (목록을 일부만 보여줘도 전체 수) */
export function bySite<T extends { siteId?: string; siteName?: string; lifeScore?: number }>(
  units: T[],
  all = units,
) {
  const groups: {
    key: string;
    name: string | undefined;
    count: number;
    lifeScore: number | undefined;
    units: T[];
  }[] = [];
  for (const u of units) {
    const key = u.siteId ?? "";
    const last = groups.at(-1);
    if (last?.key === key) last.units.push(u);
    else
      groups.push({
        key,
        name: u.siteName,
        lifeScore: u.lifeScore,
        count: all.filter((a) => (a.siteId ?? "") === key).length,
        units: [u],
      });
  }
  return groups;
}

/** 단지 길찾기 (카카오맵). 좌표가 없으면 null */
export function directionsUrl(
  site: { name: string; lat: number | null; lng: number | null } | undefined,
) {
  if (!site || site.lat === null || site.lng === null) return null;
  return `https://map.kakao.com/link/to/${encodeURIComponent(site.name)},${site.lat},${site.lng}`;
}

/** 웹·모바일 화면이 같이 그려져서 같은 id가 둘이에요. 보이는 쪽으로 스크롤해요 */
export function scrollToVisible(id: string) {
  const target = Array.from(document.querySelectorAll<HTMLElement>(`#${id}`)).find(
    (el) => el.offsetParent !== null,
  );
  target?.scrollIntoView({ behavior: "smooth" });
}
