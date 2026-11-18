"use client";

// GET /api/v1/notices/{id}/versions (백엔드 NoticeVersionResponse 목록): 공개한 버전을 첫 버전부터 순서대로
import { useQuery } from "@tanstack/react-query";
import { mockQuery } from "@/features/mock-query";
import { formatDay } from "@/features/notice/format";
import { api } from "@/shared/lib/api/client";
import { USE_MOCKS } from "@/shared/lib/api/config";
import { endpoints } from "@/shared/lib/api/endpoints";

type ApiVersion = {
  version: number;
  /** NOTICE 모집공고 · CORRECTION 정정 */
  kind: string;
  reviewStatus: string;
  /** 앞 버전과 비교해 바뀐 목록 값 (첫 버전은 빈 목록) */
  changedFields: string[];
  receivedAt: string;
};

/** 정정 이력 한 줄 */
export type NoticeVersion = {
  version: number;
  label: string;
  /** "11월 3일" */
  day: string;
  /** 바뀐 목록 값 이름 (모르는 값은 빼요) */
  changed: string[];
};

/** 백엔드 CompletedNotice.changedFrom의 이름 → 화면 이름 */
const fieldLabel: Record<string, string> = {
  title: "공고 이름",
  provider: "공고 기관",
  noticeType: "공고 종류",
  regionCode: "지역",
  applyStart: "접수 시작일",
  applyEnd: "접수 마감일",
  summaryText: "요약",
};

/**
 * 첫 반영·정정·목록 값 변경과 가장 최근 반영을 보여줘요.
 * 한 버전뿐이어도 원문 발표일과 서비스 반영일을 구분해 확인할 수 있어요.
 */
export function toVersions(list: ApiVersion[]): NoticeVersion[] {
  const rows = list
    .filter(
      (v, i) =>
        i === 0 || i === list.length - 1 || v.kind === "CORRECTION" || v.changedFields.length > 0,
    )
    .map((v, i) => ({
      version: v.version,
      label:
        i === 0
          ? "서비스 첫 반영"
          : v.kind === "CORRECTION"
            ? "정정 공고 반영"
            : v.changedFields.length
              ? "공고 내용 변경 반영"
              : "정보 다시 반영",
      day: `${v.receivedAt.slice(0, 4)}년 ${formatDay(v.receivedAt.slice(0, 10))}`,
      changed: v.changedFields.map((f) => fieldLabel[f]).filter(Boolean),
    }));
  return rows;
}

const versionsKey = (id: string) => ["notice", "versions", id] as const;

/** 실제 API: 공개 정보라 조금 길게 둬요. 못 불러오면 카드를 숨겨요 */
function useApiVersions(id: string | undefined) {
  const q = useQuery({
    queryKey: versionsKey(id ?? ""),
    queryFn: async () => toVersions(await api.get<ApiVersion[]>(endpoints.noticeVersions(id!))),
    enabled: Boolean(id),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  return q.data ?? [];
}

/** 목업: 정정 공고가 있는 공고(n7 양산)만 예시로 보여 줘요 */
const mockVersions: NoticeVersion[] = [
  { version: 1, label: "처음 올라온 공고", day: "9월 30일 (수)", changed: [] },
  { version: 2, label: "정정 공고", day: "10월 14일 (수)", changed: ["접수 마감일"] },
];

function useMockVersions(id: string | undefined) {
  const q = useQuery(mockQuery(versionsKey(id ?? ""), mockVersions));
  return id === "n7" ? q.data : [];
}

// USE_MOCKS는 빌드 때 정해지는 값이라 훅 순서가 바뀌지 않아요
export const useNoticeVersions: (id: string | undefined) => NoticeVersion[] = USE_MOCKS
  ? useMockVersions
  : useApiVersions;
