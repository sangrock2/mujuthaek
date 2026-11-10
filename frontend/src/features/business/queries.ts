import { useQuery } from "@tanstack/react-query";
import {
  useApiBusinessPreview,
  useApiBusinessSummary,
  useApiSpaceDetail,
  useApiSupportDetail,
  useApiSupportList,
  type RegionScope,
} from "@/features/business/api";
import { mockQuery } from "@/features/mock-query";
import {
  profileChips,
  useBizProfileInput,
  type BizProfileInput,
  type BizSession,
} from "@/features/business/profile";
import { USE_MOCKS } from "@/lib/api/config";
import {
  bizOnboarding,
  bizProfile,
  businessSummary,
  spaceDetails,
  supportList,
  type SpaceType,
} from "@/mocks/business";

export { useRegionScope, type RegionScope } from "@/features/business/api";

/** 사업 정보의 필요한 공간 → 사업공간 홈 종류 필터 처음 값 (하나만 골랐을 때만) */
export function useInitialSpaceType(): "all" | SpaceType {
  const stored = useBizProfileInput();
  const needs = stored.status === "ready" ? (stored.profile?.needs ?? []) : [];
  const byNeed: Record<string, SpaceType> = {
    STARTUP_SPACE: "startup",
    SHOP_RENTAL: "shop",
    MEETING_ROOM: "room",
  };
  return needs.length === 1 ? (byNeed[needs[0]] ?? "all") : "all";
}

export const businessKeys = {
  profile: ["business", "profile"] as const,
  summary: ["business", "summary"] as const,
  support: ["business", "support"] as const,
  space: (id: string) => ["business", "space", id] as const,
  onboarding: ["business", "onboarding"] as const,
};

/** "내 사업 정보" 칩: 저장한 사업 정보로. 목업 모드에서 아직 없으면 예시를 보여줘요 */
export function useBizProfileChips(): string[] {
  const stored = useBizProfileInput();
  const { data: example } = useQuery(mockQuery(businessKeys.profile, bizProfile));
  const profile = stored.status === "ready" ? stored.profile : null;
  if (profile) return profileChips(profile);
  return USE_MOCKS
    ? [example.stageLabel, example.industry, example.staff, `희망 지역 ${example.region}`]
    : [];
}

function useMockBusinessSummary() {
  const { data } = useQuery(mockQuery(businessKeys.summary, businessSummary));
  return { data, loading: false, error: false };
}

// USE_MOCKS는 빌드 때 정해지는 값이라 훅 순서가 바뀌지 않아요
export const useBusinessSummary: (
  scope?: RegionScope,
) => ReturnType<typeof useMockBusinessSummary> = USE_MOCKS
  ? useMockBusinessSummary
  : useApiBusinessSummary;

function useMockSupportList() {
  const { data } = useQuery(mockQuery(businessKeys.support, supportList));
  return { data, loading: false, error: false };
}

export const useSupportList: (scope?: RegionScope) => ReturnType<typeof useMockSupportList> =
  USE_MOCKS ? useMockSupportList : useApiSupportList;

/** 목업 단계: 사업 지원 상세는 공간 예시를 보여줘요 */
function useMockSupportDetail(id: string) {
  return useMockSpaceDetail(id);
}

export const useSupportDetail = USE_MOCKS ? useMockSupportDetail : useApiSupportDetail;

/** 목업 단계: 없는 id면 첫 공간을 보여줘요 */
function useMockSpaceDetail(id: string) {
  const detail = spaceDetails.find((s) => s.id === id) ?? spaceDetails[0];
  const { data } = useQuery(mockQuery(businessKeys.space(id), detail));
  return { data, loading: false, error: false };
}

export const useSpaceDetail = USE_MOCKS ? useMockSpaceDetail : useApiSpaceDetail;

/** 목업 단계: 창업 상태별 예시 개수 */
function useMockBusinessPreview(draft: BizProfileInput) {
  return bizOnboarding.preview[draft.stage];
}

export const useBusinessPreview: (
  draft: BizProfileInput,
  session: BizSession,
) => { spaces: number; support: number; check: number } = USE_MOCKS
  ? useMockBusinessPreview
  : useApiBusinessPreview;

export function useBizOnboarding() {
  return useQuery(mockQuery(businessKeys.onboarding, bizOnboarding));
}
