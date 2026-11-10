import {
  type InfiniteData,
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useAdminMe } from "@/components/admin/AdminGuard";
import { useCallback } from "react";
import { mockQuery } from "@/features/mock-query";
import {
  adminCounts,
  adminCriteria,
  adminOverview,
  adminReports,
  adminSources,
  reviewQueue,
  type AdminCounts,
  type ReportItem,
  type ReportStatus,
  type ReviewReason,
} from "@/mocks/admin";
import {
  EMPTY_REVIEW,
  liveCounts,
  liveCriteria,
  liveOverview,
  liveChatReportPage,
  liveReportCounts,
  liveReportDetail,
  liveReportQueuePage,
  liveReports,
  liveReviewDetail,
  liveReviewQueuePage,
  liveSources,
  liveBotTraffic,
  liveActivity,
  liveNotificationStats,
  livePolicyDuplicates,
  liveRealtime,
  liveAdminChanges,
  liveUsers,
  liveUserNames,
  liveTraffic,
  noticeTitles,
  groupChatReports,
  liveChatReports,
} from "./api";
import { USE_MOCKS } from "@/lib/api/config";
import { botTrafficMock, noticeTitlesMock, realtimeMock, trafficMock } from "@/mocks/admin-traffic";
import { chatReportTitlesMock, chatReportsMock, type ChatReviewStatus } from "@/mocks/admin-chat";
import { adminChangesMock, adminUsersMock, type AdminUserFilter } from "@/mocks/admin-users";
import { activityMock } from "@/mocks/admin-activity";
import { notificationStatsMock } from "@/mocks/admin-notifications";
import { duplicatesMock, type DuplicateStatus } from "@/mocks/admin-duplicates";

export const adminKeys = {
  counts: ["admin", "counts"] as const,
  overview: ["admin", "overview"] as const,
  review: ["admin", "review"] as const,
  reviewDetail: ["admin", "reviewDetail"] as const,
  sources: ["admin", "sources"] as const,
  criteria: ["admin", "criteria"] as const,
  reports: ["admin", "reports"] as const,
};

/**
 * 실제 API(NEXT_PUBLIC_USE_MOCKS=false)면 관리자 화면 값을 백엔드에서 받아요(./api). 받기 전에는 빈 값(불러오는 중)을 보여 줘요.
 * USE_MOCKS는 빌드 때 정해지는 상수라 아래 훅에서 갈라 불러도 훅 순서가 바뀌지 않아요.
 */
const LIVE = !USE_MOCKS;
const live = (key: readonly string[]) => ["admin", "live", ...key.slice(1)] as const;
const ZERO: AdminCounts = {
  reviewPending: 0,
  sourceIssues: 0,
  newReports: 0,
  chatReports: 0,
  policyDuplicates: 0,
};

/** 사이드바 메뉴 옆 숫자 */
export function useAdminCounts() {
  if (LIVE) {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const q = useQuery({ queryKey: live(adminKeys.counts), queryFn: liveCounts, staleTime: 0 });
    return { ...q, data: q.data ?? ZERO };
  }
  // eslint-disable-next-line react-hooks/rules-of-hooks
  return useQuery(mockQuery(adminKeys.counts, adminCounts));
}

/** 화면에서 처리한 결과를 사이드바 숫자에 반영해요 (실제 연결이면 다시 받아요) */
export function useSetAdminCounts() {
  const queryClient = useQueryClient();
  return useCallback(
    (patch: Partial<AdminCounts>) => {
      if (LIVE) {
        void queryClient.invalidateQueries({ queryKey: ["admin", "live"] });
        return;
      }
      queryClient.setQueryData<AdminCounts>(adminKeys.counts, (prev) => ({
        ...(prev ?? adminCounts),
        ...patch,
      }));
    },
    [queryClient],
  );
}

export function useAdminOverview() {
  if (LIVE) {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const q = useQuery({
      queryKey: live(adminKeys.overview),
      queryFn: () => liveOverview(adminOverview),
      staleTime: 0,
    });
    const wait = q.isError ? "불러오지 못했어요" : "불러오는 중";
    const empty = {
      ...adminOverview,
      asOf: wait,
      // 받기 전에는 0이 아니라 「-」로 보여요
      review: { count: null, oldest: wait },
      collected: { count: null, note: wait },
      issues: { count: null, note: wait },
      reports: { count: null, note: wait },
      todos: [],
      quality: { asIs: "-", edited: "-", rejected: "-", medianTime: "-", fixedByReport: "-" },
      today: { approved: null, editedApproved: null, rejected: null, replied: null },
    };
    return { ...q, data: q.data ?? empty };
  }
  // eslint-disable-next-line react-hooks/rules-of-hooks
  return useQuery(mockQuery(adminKeys.overview, adminOverview));
}

type QueuePage = Awaited<ReturnType<typeof liveReviewQueuePage>>;

/**
 * 검수 대기열 (무한 스크롤): 사유(reason)로 거른 대기열을 20건씩 이어 받아요. 내 권한으로 볼 수 있는 종류(공고 검수·혜택 검수)만 물어요.
 * 화면을 떠나면 받아 둔 페이지를 버려요(돌아왔을 때 수천 건을 페이지마다 다시 받지 않게 첫 페이지부터).
 */
export function useReviewQueue(reason: ReviewReason | null) {
  const permissions = useAdminMe().data?.permissions;
  const kinds = [
    ...(permissions?.includes("NOTICE_REVIEW") ? ["NOTICE"] : []),
    ...(permissions?.includes("BENEFIT_REVIEW") ? ["BENEFIT"] : []),
  ];
  const q = useInfiniteQuery({
    queryKey: [...live(adminKeys.review), kinds.join(","), reason ?? "all"],
    queryFn: ({ pageParam }) => liveReviewQueuePage(kinds, reason, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last: QueuePage) => last.nextCursor,
    enabled: LIVE && kinds.length > 0,
    staleTime: 60 * 1000,
    gcTime: 0,
    refetchOnWindowFocus: false,
  });
  if (!LIVE) {
    const items = reviewQueue.items.filter((i) => !reason || i.reason === reason);
    return { total: reviewQueue.total, items, more: false, loadingMore: false, loadMore: () => {} };
  }
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return {
    total: q.data?.pages[0]?.total ?? 0,
    items: items.length
      ? items
      : [{ ...EMPTY_REVIEW, title: q.isPending ? "불러오는 중…" : EMPTY_REVIEW.title }],
    more: q.hasNextPage,
    loadingMore: q.isFetchingNextPage,
    /** 대기열 아래 끝이 보이면 다음 20건 */
    loadMore: () => {
      if (q.hasNextPage && !q.isFetchingNextPage) void q.fetchNextPage();
    },
  };
}

/** 고른 검수 건의 원문·추출 결과. 목업이면 대기열 항목에 이미 들어 있어 받지 않아요 */
export function useReviewDetail(id: string) {
  return useQuery({
    queryKey: [...live(adminKeys.reviewDetail), id],
    queryFn: () => liveReviewDetail(id),
    enabled: LIVE && id !== "empty",
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

/**
 * 승인·반려 뒤: 대기열은 다시 받지 않고(받아 둔 페이지가 많으면 페이지마다 다시 불러요) 건수만 하나 줄이고, 사이드바 숫자만 다시 받아요.
 * 처리한 건은 「승인함·반려함」으로 남았다가 화면을 다시 열면 빠져요. 관리자 화면 전체({@link useSetAdminCounts})는 다시 받지 않아요
 */
export function useReviewDecided() {
  const queryClient = useQueryClient();
  const setCounts = useSetAdminCounts();
  return useCallback(
    (pending: number) => {
      if (!LIVE) {
        setCounts({ reviewPending: pending });
        return;
      }
      queryClient.setQueriesData<InfiniteData<QueuePage>>(
        { queryKey: live(adminKeys.review) },
        (data) =>
          data && {
            ...data,
            pages: data.pages.map((p, i) =>
              i === 0 ? { ...p, total: Math.max(0, p.total - 1) } : p,
            ),
          },
      );
      void queryClient.invalidateQueries({ queryKey: live(adminKeys.counts), exact: true });
    },
    [queryClient, setCounts],
  );
}

export function useAdminSources() {
  if (LIVE) {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const q = useQuery({
      queryKey: live(adminKeys.sources),
      queryFn: liveSources,
      staleTime: 0,
      // 수집기가 꺼져 있으면(503) 바로 다시 묻지 않고 1분 뒤에 다시 봐요 (서버 오류 기록이 쌓이지 않게)
      retry: false,
      refetchInterval: (query) => (query.state.status === "error" ? 60_000 : 15_000),
    });
    return {
      ...q,
      data: q.data ?? {
        ...adminSources,
        asOf: "불러오는 중",
        summary: { ok: 0, late: 0, fail: 0 },
        rows: adminSources.rows.slice(0, 0),
        enabled: {} as Record<string, boolean>,
      },
    };
  }
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const q = useQuery(mockQuery(adminKeys.sources, adminSources));
  return { ...q, data: { ...q.data, enabled: {} as Record<string, boolean> } };
}

export function useAdminCriteria() {
  if (LIVE) {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const q = useQuery({
      queryKey: live(adminKeys.criteria),
      queryFn: () => liveCriteria(adminCriteria),
      staleTime: 0,
    });
    return {
      ...q,
      data: q.data ?? {
        ...adminCriteria,
        incomeBase: [],
        rules: [],
        history: [],
        regions: [],
        rulesCount: 0,
      },
    };
  }
  // eslint-disable-next-line react-hooks/rules-of-hooks
  return useQuery(mockQuery(adminKeys.criteria, adminCriteria));
}

export function useAdminReports() {
  if (LIVE) {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const q = useQuery({ queryKey: live(adminKeys.reports), queryFn: liveReports, staleTime: 0 });
    return { ...q, data: q.data ?? { doneBefore: 0, newBefore: 0, items: [] } };
  }
  // eslint-disable-next-line react-hooks/rules-of-hooks
  return useQuery(mockQuery(adminKeys.reports, adminReports));
}

type ReportQueuePage = Awaited<ReturnType<typeof liveReportQueuePage>>;

/**
 * 제보 대기열 (무한 스크롤): 고른 상태의 제보를 최신순으로 20건씩 이어 받아요(공고·혜택·사업 제보와 생활권 제보를 서버가 섞어요).
 * 화면을 떠나면 받아 둔 페이지를 버려요.
 */
export function useReportQueue(status: ReportStatus) {
  const q = useInfiniteQuery({
    queryKey: [...live(adminKeys.reports), "queue", status],
    queryFn: ({ pageParam }) => liveReportQueuePage(status, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last: ReportQueuePage) => last.nextCursor,
    enabled: LIVE,
    staleTime: 0,
    gcTime: 0,
    refetchOnWindowFocus: false,
  });
  if (!LIVE) {
    const items = adminReports.items.filter((i) => i.st === status);
    return { items, loading: false, more: false, loadingMore: false, loadMore: () => {} };
  }
  return {
    items: q.data?.pages.flatMap((p) => p.items) ?? [],
    loading: q.isPending,
    more: q.hasNextPage,
    loadingMore: q.isFetchingNextPage,
    /** 목록 아래 끝이 보이면 다음 20건 */
    loadMore: () => {
      if (q.hasNextPage && !q.isFetchingNextPage) void q.fetchNextPage();
    },
  };
}

/** 제보 상태별 건수 (탭 숫자). 목업이면 목업 목록에서 세요 */
export function useReportCounts() {
  const q = useQuery({
    queryKey: [...live(adminKeys.reports), "counts"],
    queryFn: liveReportCounts,
    enabled: LIVE,
    staleTime: 0,
  });
  if (!LIVE) {
    const n = (st: ReportStatus) => adminReports.items.filter((i) => i.st === st).length;
    return { new: n("new"), doing: n("doing"), done: n("done") + adminReports.doneBefore };
  }
  return q.data ?? null;
}

/** 제보 상세 받기 설정 (화면이 고른 제보, 처리 직전 답장 확인에 같이 써요) */
export const reportDetailQuery = (id: string, summary: string) => ({
  queryKey: [...live(adminKeys.reports), "detail", id] as const,
  queryFn: () => liveReportDetail(id, summary),
  staleTime: 0,
});

/**
 * 고른 제보 하나의 설명·같은 묶음 설명·답장. 목록은 이 값 없이 받아요(제보마다 상세를 받지 않게). 목업이면 목록에 이미 있어 받지 않아요.
 * 받기 전에는 목록 값(요약)을 그대로 보여 줘요.
 */
export function useAdminReportDetail(item: ReportItem | undefined) {
  return useQuery({
    ...reportDetailQuery(item?.id ?? "", item?.summary ?? ""),
    enabled: LIVE && !!item,
  });
}

/** 트래픽(GA·서버 숫자). 기간이 바뀌면 다시 받아요. GA 숫자는 백엔드가 한 시간쯤 다시 써요 */
export function useAdminTraffic(days: number) {
  return useQuery({
    queryKey: ["admin", LIVE ? "live" : "mock", "traffic", days],
    queryFn: () => (LIVE ? liveTraffic(days) : Promise.resolve(trafficMock)),
    staleTime: 60_000,
  });
}

/** 봇·보안(서버 요청 기록) */
export function useAdminBotTraffic(days: number) {
  return useQuery({
    queryKey: ["admin", LIVE ? "live" : "mock", "traffic-bots", days],
    queryFn: () => (LIVE ? liveBotTraffic(days) : Promise.resolve(botTrafficMock)),
    staleTime: 60_000,
  });
}

/** 채팅 신고(메시지별로 묶음). 상태가 바뀌면 다시 받아요 */
export function useAdminChatReports(status: ChatReviewStatus) {
  return useQuery({
    queryKey: ["admin", LIVE ? "live" : "mock", "chat-reports", status],
    queryFn: () =>
      LIVE
        ? liveChatReports(status)
        : Promise.resolve(
            groupChatReports(
              chatReportsMock.filter((r) => r.reviewStatus === status),
              chatReportTitlesMock,
            ),
          ),
    staleTime: 0,
  });
}

type ChatReportQueuePage = Awaited<ReturnType<typeof liveChatReportPage>>;

/** 채팅 신고 (무한 스크롤): 고른 상태의 신고를 20건씩 이어 받아 글마다 묶어요. 화면을 떠나면 받아 둔 페이지를 버려요 */
export function useChatReportQueue(status: ChatReviewStatus) {
  const q = useInfiniteQuery({
    queryKey: ["admin", "live", "chat-reports", status, "queue"],
    queryFn: ({ pageParam }) => liveChatReportPage(status, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last: ChatReportQueuePage) => last.nextCursor,
    enabled: LIVE,
    staleTime: 0,
    gcTime: 0,
    refetchOnWindowFocus: false,
  });
  if (!LIVE) {
    const groups = groupChatReports(
      chatReportsMock.filter((r) => r.reviewStatus === status),
      chatReportTitlesMock,
    );
    return {
      groups,
      loading: false,
      failed: false,
      more: false,
      loadingMore: false,
      loadMore: () => {},
    };
  }
  const pages = q.data?.pages ?? [];
  const groups = groupChatReports(
    pages.flatMap((p) => p.reports),
    Object.assign({}, ...pages.map((p) => p.titles)),
  );
  return {
    groups,
    loading: q.isPending,
    failed: q.isError,
    more: q.hasNextPage,
    loadingMore: q.isFetchingNextPage,
    /** 목록 아래 끝이 보이면 다음 20건 */
    loadMore: () => {
      if (q.hasNextPage && !q.isFetchingNextPage) void q.fetchNextPage();
    },
  };
}

/** 지금 접속자. 화면을 열어 둔 동안 30초마다 다시 받아요(백엔드도 30초 다시 써요) */
export function useAdminRealtime() {
  return useQuery({
    queryKey: ["admin", LIVE ? "live" : "mock", "traffic-realtime"],
    queryFn: () => (LIVE ? liveRealtime() : Promise.resolve(realtimeMock)),
    refetchInterval: 30_000,
    staleTime: 30_000,
  });
}

/** 공고 ID → 제목 (많이 본 공고·채팅 신고 등). 못 찾은 공고는 빠져요 */
export function useNoticeTitles(ids: string[]) {
  return useQuery({
    queryKey: ["admin", LIVE ? "live" : "mock", "notice-titles", ...ids],
    queryFn: () => (LIVE ? noticeTitles(ids) : Promise.resolve(noticeTitlesMock)),
    enabled: ids.length > 0,
    staleTime: 10 * 60_000,
  });
}

/** 회원 찾기 (한 쪽 30명) */
export function useAdminUsers(query: string, filter: AdminUserFilter, page: number) {
  return useQuery({
    queryKey: ["admin", LIVE ? "live" : "mock", "users", query, filter, page],
    queryFn: () => {
      if (LIVE) return liveUsers(query, filter, page);
      const items = adminUsersMock.filter(
        (u) =>
          (!filter ||
            (filter === "ADMIN" && u.role !== "USER") ||
            (filter === "USER" && u.role === "USER") ||
            (filter === "SUSPENDED" && u.suspension)) &&
          (!query.trim() || (u.nickname ?? "").includes(query.trim()) || u.id === query.trim()),
      );
      return Promise.resolve({ items, total: items.length });
    },
    staleTime: 0,
  });
}

/** 회원 ID → 이름 (처리 기록의 관리자 이름) */
export function useAdminUserNames(ids: string[]) {
  return useQuery({
    queryKey: ["admin", LIVE ? "live" : "mock", "user-names", ...ids],
    queryFn: () =>
      LIVE ? liveUserNames(ids) : Promise.resolve(adminUsersMock.filter((u) => ids.includes(u.id))),
    enabled: ids.length > 0,
    staleTime: 5 * 60_000,
  });
}

/** 관리자 변경 기록 (지정·해제·권한·정지·넘기기·긴급 정지) */
export function useAdminChanges(days: number, enabled = true) {
  return useQuery({
    queryKey: ["admin", LIVE ? "live" : "mock", "admin-changes", days],
    queryFn: () => (LIVE ? liveAdminChanges(days) : Promise.resolve(adminChangesMock)),
    enabled,
    staleTime: 0,
  });
}

/** 제보·신고 「중복 의심」: 출처에 두 번 올라온 것 같은 사업 쌍 */
export function useAdminPolicyDuplicates(status: DuplicateStatus) {
  return useQuery({
    queryKey: ["admin", LIVE ? "live" : "mock", "policy-duplicates", status],
    queryFn: () =>
      LIVE
        ? livePolicyDuplicates(status)
        : Promise.resolve({
            ...duplicatesMock,
            items: duplicatesMock.items.filter((d) => d.status === status),
          }),
    staleTime: 0,
  });
}

/** 알림: 발송 결과와 봤는지·눌렀는지 */
export function useAdminNotificationStats(days: number) {
  return useQuery({
    queryKey: ["admin", LIVE ? "live" : "mock", "notifications", days],
    queryFn: () => (LIVE ? liveNotificationStats(days) : Promise.resolve(notificationStatsMock)),
    staleTime: 0,
  });
}

/** 처리 기록 (검수·제보·기준값·권한) */
export function useAdminActivity(days: number) {
  return useQuery({
    queryKey: ["admin", LIVE ? "live" : "mock", "activity", days],
    queryFn: () => (LIVE ? liveActivity(days) : Promise.resolve(activityMock)),
    staleTime: 0,
  });
}
