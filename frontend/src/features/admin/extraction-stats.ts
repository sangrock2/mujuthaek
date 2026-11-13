// 관리자 「추출 비용·품질」: GET /api/admin/reviews/extraction-stats?days= (추출 서비스 extraction_stats.py 집계를 api가 그대로 넘겨요)
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api/client";
import { USE_MOCKS } from "@/shared/lib/api/config";

/** 상태 묶음: 자동 게시 COMPLETED · 부분 게시 PARTIAL · 검수로 감 IN_REVIEW·INTAKE_REVIEW·APPROVED · 실패 FAILED·WAITING_SOURCE·INTERRUPTED · 그 밖 */
export type StatusGroup = "AUTO" | "PARTIAL" | "REVIEW" | "FAILED" | "OTHER";
export type StopKind = "CALL_LIMIT" | "BUDGET" | "OUTPUT_LIMIT" | "ERROR";

export type ExtractionStats = {
  days: number;
  /** 기간 첫날·마지막 날(한국 시간, YYYY-MM-DD) */
  since: string;
  until: string;
  /** 처리 작업 수(다시 처리 포함) */
  jobs: number;
  /** 처리 공고 수(원본·버전 하나) */
  notices: number;
  /** 기간 비용(작업 cost_usd 합, 예산 기준 추정 달러) */
  costUsd: number;
  costPerNotice: { avgUsd: number | null; maxUsd: number | null };
  statuses: {
    groups: {
      group: StatusGroup;
      label: string;
      notices: number;
      costUsd: number;
      ratio: number | null;
    }[];
    /** 원래 상태(마지막 작업)별 공고 수 */
    byStatus: Record<string, number>;
    publishedWithoutReview: number;
    publishedWithoutReviewRatio: number | null;
  };
  daily: { date: string; jobs: number; notices: number; costUsd: number }[];
  topJobs: {
    jobId: string;
    status: string;
    statusGroup: StatusGroup;
    costUsd: number;
    createdAt: string;
    title: string | null;
    sourceCode: string | null;
    rawPostId: string | null;
    rawVersion: number | null;
  }[];
  usage: {
    /** 작업 기록을 본 작업 수(최근 limit개까지) */
    jobs: number;
    v2Jobs: number;
    costUsd: number;
    inputTokens: number;
    cachedTokens: number;
    outputTokens: number;
    /** 캐시로 읽은 입력 비율(캐시 읽기 ÷ 입력 토큰) */
    cachedRatio: number | null;
    byAgent: {
      agent: string;
      label: string;
      calls: number;
      costUsd: number;
      share: number | null;
    }[];
    stops: {
      total: number;
      /** 멈춤이 하나라도 있는 작업 수 */
      jobs: number;
      byKind: { kind: StopKind; label: string; count: number }[];
      byAgent: { agent: string | null; label: string; count: number }[];
    };
    /** 넣기(add_…) 결과가 거절·오류인 횟수 */
    addRejections: number;
    /** 끝까지 넣지 못한 항목 수 */
    rejectedLeft: number;
    resolver: { agents: number; adopted: number; conversations: number };
    limit: number;
    truncated: boolean;
  };
};

export function useExtractionStats(days: number) {
  return useQuery({
    queryKey: ["admin", "extractionStats", USE_MOCKS ? "mock" : "live", days],
    queryFn: () =>
      USE_MOCKS
        ? Promise.resolve(mockExtractionStats(days))
        : api.get<ExtractionStats>(`/api/admin/reviews/extraction-stats?days=${days}`),
    placeholderData: keepPreviousData,
    staleTime: 60 * 1000,
    retry: false,
  });
}

/** 목업: 기간 길이에 맞춘 그럴듯한 예(금액은 실제 측정 범위, 공고당 $0.01~0.06) */
export function mockExtractionStats(days: number): ExtractionStats {
  const until = new Date("2026-11-11T00:00:00Z");
  const daily = Array.from({ length: days }, (_, i) => {
    const d = new Date(until);
    d.setUTCDate(d.getUTCDate() - (days - 1 - i));
    const notices = [3, 5, 0, 7, 4, 2, 6, 8, 1, 4][i % 10]!;
    const jobs = notices + (i % 4 === 0 && notices > 0 ? 1 : 0);
    return {
      date: d.toISOString().slice(0, 10),
      jobs,
      notices,
      costUsd: Math.round(notices * (0.021 + (i % 3) * 0.006) * 10000) / 10000,
    };
  });
  const notices = daily.reduce((a, d) => a + d.notices, 0);
  const jobs = daily.reduce((a, d) => a + d.jobs, 0);
  const costUsd = Math.round(daily.reduce((a, d) => a + d.costUsd, 0) * 10000) / 10000;
  const split = (r: number) => Math.round(notices * r);
  const counts = {
    AUTO: split(0.52),
    PARTIAL: split(0.27),
    REVIEW: split(0.14),
    FAILED: split(0.04),
  };
  const other = Math.max(0, notices - counts.AUTO - counts.PARTIAL - counts.REVIEW - counts.FAILED);
  const group = (g: StatusGroup, label: string, n: number) => ({
    group: g,
    label,
    notices: n,
    costUsd: Math.round((notices ? (costUsd * n) / notices : 0) * 10000) / 10000,
    ratio: notices ? Math.round((n / notices) * 10000) / 10000 : null,
  });
  const agents: [string, string, number, number][] = [
    ["eligibility", "자격 담당", 0.31, 4],
    ["prime", "캐시 데우기", 0.19, 1],
    ["resolver", "해결 담당", 0.14, 2],
    ["documents", "서류 담당", 0.11, 3],
    ["structure", "구조 (공고·위치·공급)", 0.09, 1],
    ["schedules", "일정 담당", 0.07, 2],
    ["selection", "선정 담당", 0.05, 2],
    ["v1", "V1 방식 호출(그림 판독·재확인 등)", 0.04, 1],
  ];
  return {
    days,
    since: daily[0]!.date,
    until: daily.at(-1)!.date,
    jobs,
    notices,
    costUsd,
    costPerNotice: {
      avgUsd: notices ? Math.round((costUsd / notices) * 10000) / 10000 : null,
      maxUsd: notices ? 0.0912 : null,
    },
    statuses: {
      groups: [
        group("AUTO", "자동 게시", counts.AUTO),
        group("PARTIAL", "부분 게시", counts.PARTIAL),
        group("REVIEW", "검수로 감", counts.REVIEW),
        group("FAILED", "실패", counts.FAILED),
        group("OTHER", "그 밖", other),
      ],
      byStatus: {
        COMPLETED: counts.AUTO,
        PARTIAL: counts.PARTIAL,
        IN_REVIEW: Math.max(0, counts.REVIEW - 1),
        APPROVED: Math.min(1, counts.REVIEW),
        FAILED: counts.FAILED,
        UNSUPPORTED: other,
      },
      publishedWithoutReview: counts.AUTO + counts.PARTIAL,
      publishedWithoutReviewRatio: notices
        ? Math.round(((counts.AUTO + counts.PARTIAL) / notices) * 10000) / 10000
        : null,
    },
    daily,
    topJobs: [
      // 첫 작업은 검수 대기열 r2 · 「추출 과정」 목업(mockTrace)과 같은 공고예요
      ["○○지구 행복주택 입주자 모집", "PARTIAL", "PARTIAL", 0.0912],
      ["서울 청년 매입임대주택 예비입주자 모집", "COMPLETED", "AUTO", 0.0745],
      ["부산 창업지원주택 입주자 모집", "IN_REVIEW", "REVIEW", 0.0633],
      ["인천 국민임대 추가 모집 공고", "COMPLETED", "AUTO", 0.0581],
      ["대전 신혼희망타운 잔여 세대 모집", "FAILED", "FAILED", 0.0402],
    ].map(([title, status, statusGroup, cost], i) => ({
      jobId: `00000000-0000-7000-8000-00000000000${i + 1}`,
      status: status as string,
      statusGroup: statusGroup as StatusGroup,
      costUsd: cost as number,
      createdAt: `2026-11-${String(10 - i).padStart(2, "0")}T0${i + 1}:20:00+09:00`,
      title: title as string,
      sourceCode: ["LH", "SH", "BMC", "IH", "LH"][i]!,
      rawPostId: null,
      rawVersion: 1,
    })),
    usage: {
      jobs,
      v2Jobs: Math.max(0, jobs - 2),
      costUsd,
      inputTokens: jobs * 520000,
      cachedTokens: jobs * 401000,
      outputTokens: jobs * 9800,
      cachedRatio: jobs ? 0.7712 : null,
      byAgent: agents.map(([agent, label, share, perJob]) => ({
        agent,
        label,
        calls: jobs * perJob,
        costUsd: Math.round(costUsd * share * 10000) / 10000,
        share,
      })),
      stops: {
        total: Math.round(jobs * 0.12),
        jobs: Math.round(jobs * 0.09),
        byKind: [
          { kind: "CALL_LIMIT", label: "호출 상한", count: Math.round(jobs * 0.06) },
          { kind: "BUDGET", label: "예산 상한", count: Math.round(jobs * 0.01) },
          { kind: "OUTPUT_LIMIT", label: "출력 한도", count: Math.round(jobs * 0.02) },
          { kind: "ERROR", label: "오류", count: Math.round(jobs * 0.03) },
        ],
        byAgent: [
          { agent: "eligibility", label: "자격 담당", count: Math.round(jobs * 0.07) },
          { agent: "documents", label: "서류 담당", count: Math.round(jobs * 0.03) },
          { agent: "structure", label: "구조 (공고·위치·공급)", count: Math.round(jobs * 0.02) },
        ],
      },
      addRejections: jobs * 3,
      rejectedLeft: Math.round(jobs * 0.4),
      resolver: {
        agents: Math.round(jobs * 0.35),
        adopted: Math.round(jobs * 0.22),
        conversations: Math.round(jobs * 0.5),
      },
      limit: 3000,
      truncated: false,
    },
  };
}
