import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api } from "@/lib/api/client";
import { USE_MOCKS } from "@/lib/api/config";
import { endpoints } from "@/lib/api/endpoints";
import { regionIndex, type RegionTree } from "@/lib/regions";
import { regionSnapshot } from "@/lib/regions-data";

export const regionKeys = {
  tree: ["regions"] as const,
};

// 목업: 저장해 둔 목록을 바로 써요 (프리렌더 중 Date.now()를 부르지 않게 static)
const mockOptions = {
  queryFn: () => regionSnapshot,
  initialData: regionSnapshot,
  initialDataUpdatedAt: 0,
  staleTime: "static" as const,
};

// 실제 API: 받기 전엔 저장해 둔 목록을 보여주고(placeholder), 하루에 한 번 새로 받아요.
// initialData를 쓰면 프리렌더 중 신선도 계산에 Date.now()가 불려서 placeholder로 둬요
const apiOptions = {
  queryFn: () => api.get<RegionTree>(endpoints.regions),
  placeholderData: regionSnapshot,
  staleTime: 24 * 60 * 60 * 1000,
};

/** 시·도와 시·군·구 */
export function useRegions() {
  const { data = regionSnapshot } = useQuery({
    queryKey: regionKeys.tree,
    ...(USE_MOCKS ? mockOptions : apiOptions),
  });
  return useMemo(() => regionIndex(data), [data]);
}
