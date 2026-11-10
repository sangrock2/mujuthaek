import { queryOptions, type QueryKey } from "@tanstack/react-query";

/**
 * API가 나오기 전까지 목업 데이터를 돌려주는 쿼리.
 * API가 생기면 queryFn을 api.get(...)으로 바꾸고 initialData를 지워요.
 */
export function mockQuery<T extends object>(queryKey: QueryKey, data: T) {
  return queryOptions({
    queryKey,
    queryFn: async () => data,
    initialData: data,
    // Cache Components 프리렌더 중 Date.now()를 부르지 않도록 고정값 + static을 써요
    initialDataUpdatedAt: 0,
    staleTime: "static",
  });
}
