// 관리자 「제보·신고」의 「중복 의심」: 출처에 두 번 올라온 것 같은 창업 지원·입주 모집 사업 (GET /api/admin/policy-duplicates)

export type DuplicateStatus = "PENDING" | "KEPT_BOTH" | "HIDDEN";

/** 비교할 사업 하나 */
export type DuplicateSide = {
  id: string;
  field: "STARTUP_SUPPORT" | "SPACE_RECRUITMENT";
  title: string;
  /** 출처 안내의 운영 기관 */
  organization: string | null;
  applyStart: string | null;
  applyEnd: string | null;
  /** 시군구 5자리, 빈 목록은 전국 */
  regionCodes: string[];
  detailUrl: string | null;
  /** 처음 받은 때 */
  createdAt: string;
  hidden: boolean;
};

/** 후보 한 쌍: later가 나중에 들어온 사업, earlier가 먼저 있던 사업 */
export type DuplicateItem = {
  later: DuplicateSide;
  earlier: DuplicateSide;
  reason: string;
  status: DuplicateStatus;
  createdAt: string;
  decidedAt: string | null;
  decidedBy: string | null;
};

export type DuplicateList = {
  items: DuplicateItem[];
  counts: { pending: number; keptBoth: number; hidden: number };
};

const side = (id: string, at: string, url: string): DuplicateSide => ({
  id,
  field: "SPACE_RECRUITMENT",
  title: "청년창업 거주지원시설(창업하여家) 입주자 1차 모집",
  organization: null,
  applyStart: null,
  applyEnd: null,
  regionCodes: ["12210", "12240", "12270", "12300", "12330"],
  detailUrl: url,
  createdAt: at,
  hidden: false,
});

export const duplicatesMock: DuplicateList = {
  items: [
    {
      later: side("d2", "2026-10-28T02:24:00Z", "https://example.test/policy/212618"),
      earlier: side("d1", "2026-10-28T02:23:00Z", "https://example.test/policy/212601"),
      reason: "SAME_TITLE_REGION",
      status: "PENDING",
      createdAt: "2026-10-28T02:24:00Z",
      decidedAt: null,
      decidedBy: null,
    },
  ],
  counts: { pending: 1, keptBoth: 0, hidden: 0 },
};
