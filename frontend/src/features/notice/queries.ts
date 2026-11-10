import { useQuery } from "@tanstack/react-query";
import { mockQuery } from "@/features/mock-query";
import { toNotice, type ApiNoticeDetail } from "@/features/notice/detail";
import { api } from "@/lib/api/client";
import { USE_MOCKS } from "@/lib/api/config";
import { endpoints } from "@/lib/api/endpoints";
import { notices, type Notice } from "@/mocks/notice";

export const noticeKeys = {
  detail: (id: string) => ["notice", "detail", id] as const,
};

/** 목업 단계: 없는 id는 첫 공고를 보여줘요 */
export function findNotice(id: string): Notice {
  return notices.find((n) => n.id === id) ?? notices[0];
}

type NoticeState = { data: Notice | undefined; loading: boolean; error: boolean };

/** 실제 API: 공개 정보라 조금 길게 둬요. enabled가 false면 부르지 않아요 (사업공간 모집 정책은 공고 상세가 없어요) */
function useApiNotice(id: string, enabled = true): NoticeState {
  const q = useQuery({
    queryKey: noticeKeys.detail(id),
    queryFn: async () => toNotice(await api.get<ApiNoticeDetail>(endpoints.noticeDetail(id))),
    staleTime: 5 * 60 * 1000,
    enabled,
  });
  return { data: q.data, loading: enabled && q.isPending, error: q.isError };
}

function useMockNotice(id: string): NoticeState {
  const q = useQuery(mockQuery(noticeKeys.detail(id), findNotice(id)));
  return { data: q.data, loading: false, error: false };
}

// USE_MOCKS는 빌드 때 정해지는 값이라 훅 순서가 바뀌지 않아요
export const useNotice: (id: string, enabled?: boolean) => NoticeState = USE_MOCKS
  ? useMockNotice
  : useApiNotice;
