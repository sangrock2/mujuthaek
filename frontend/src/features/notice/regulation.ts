"use client";

// GET /api/v1/eligibility/notices/{id}/regulation (백엔드 NoticeRegulationResponse): 공고 지역의 규제지역 안내.
// 판정 값은 바꾸지 않고 판정 화면에 함께 보여 줄 안내예요
import { useQuery } from "@tanstack/react-query";
import { mockQuery } from "@/features/mock-query";
import { api } from "@/shared/lib/api/client";
import { USE_MOCKS } from "@/shared/lib/api/config";
import { endpoints } from "@/shared/lib/api/endpoints";
import { snapshotRegions } from "@/shared/lib/regions";

type ApiRegulation = {
  noticeId: string;
  referenceDate: string;
  regulated: boolean;
  areas: {
    /** 시군구 5자리 (시도 전체면 xx000) */
    regionCode: string;
    kind: "SPECULATION_OVERHEATED" | "ADJUSTMENT_TARGET" | "SPECULATION" | string;
    kindLabel: string;
    /** 공고는 시도 전체인데 그 안의 일부 시군구만 규제지역이면 true */
    partial: boolean;
    scopeNote: string | null;
    validFrom: string | null;
    validUntil: string | null;
  }[];
  /** 규제 종류마다 안내 문장 (공고문 확인 권유 포함) */
  guidance: string[];
};

/** 화면 값: 규제지역이 아니면 null */
export type NoticeRegulation = {
  /** 걸린 규제 종류 이름 (투기과열지구 · 조정대상지역 · 투기지역) */
  kinds: string[];
  /** 걸린 지역 줄 ("서울 마포구 · 투기과열지구") */
  areas: string[];
  /** 공고 지역 중 일부만 규제지역 */
  partial: boolean;
  guidance: string[];
};

/** "11440" → "서울 마포구", "11000" → "서울" */
const regionName = (code: string) =>
  snapshotRegions.label(code.endsWith("000") ? code.slice(0, 2) : code) || code;

export function toRegulation(r: ApiRegulation): NoticeRegulation | null {
  if (!r.regulated || !r.areas.length) return null;
  return {
    kinds: [...new Set(r.areas.map((a) => a.kindLabel))],
    areas: r.areas.map((a) =>
      [`${regionName(a.regionCode)} · ${a.kindLabel}`, a.scopeNote].filter(Boolean).join(" · "),
    ),
    partial: r.areas.some((a) => a.partial),
    guidance: r.guidance,
  };
}

const regulationKey = (id: string) => ["notice", "regulation", id] as const;

/** 실제 API: 공개 정보이고 하루에 거의 안 바뀌어서 길게 둬요. 못 불러오면 안내를 숨겨요 */
function useApiRegulation(id: string | undefined) {
  const q = useQuery({
    queryKey: regulationKey(id ?? ""),
    queryFn: async () =>
      toRegulation(await api.get<ApiRegulation>(endpoints.noticeRegulation(id!))),
    enabled: Boolean(id),
    staleTime: 30 * 60 * 1000,
    retry: false,
  });
  return q.data ?? null;
}

/** 목업: 첫 공고(서울 마포구)만 예시로 보여 줘요 */
const mockRegulation: NoticeRegulation = {
  kinds: ["투기과열지구", "조정대상지역"],
  areas: ["서울 · 투기과열지구", "서울 · 조정대상지역"],
  partial: false,
  guidance: [
    "투기과열지구예요. 민영주택 1순위는 보통 세대주여야 하고, 청약통장 가입 2년(국민주택은 24회 납입) 이상이어야 해요. 당첨되면 재당첨 제한이 있어요. 정확한 자격은 공고문을 확인하세요.",
    "조정대상지역이에요. 민영주택 1순위는 보통 세대주여야 하고, 청약통장 가입 2년(국민주택은 24회 납입) 이상이어야 해요. 정확한 자격은 공고문을 확인하세요.",
  ],
};

function useMockRegulation(id: string | undefined) {
  const q = useQuery(mockQuery(regulationKey(id ?? ""), { value: mockRegulation }));
  return id === "n1" ? q.data.value : null;
}

// USE_MOCKS는 빌드 때 정해지는 값이라 훅 순서가 바뀌지 않아요
export const useNoticeRegulation: (id: string | undefined) => NoticeRegulation | null = USE_MOCKS
  ? useMockRegulation
  : useApiRegulation;
