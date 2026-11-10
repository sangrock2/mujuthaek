// 관리자 「처리 기록」 타입과 예시 데이터. 실제 값은 GET /api/admin/activity + 기준값·권한 변경 기록
export type ActivityKind =
  | "NOTICE_REVIEW"
  | "BENEFIT_REVIEW"
  | "NOTICE_REPORT"
  | "BENEFIT_REPORT"
  | "PROGRAM_REPORT"
  | "AREA_REPORT"
  | "CHAT_REPORT"
  | "CRITERIA"
  | "ROLE";

/** 화면에 보여 줄 기록 한 줄 (세 API를 합친 모양) */
export type ActivityItem = {
  at: string;
  kind: ActivityKind;
  /** 검수 APPROVED·EDITED_APPROVED·REJECTED·REOPENED, 제보 FIXED·KEPT, 기준값 REPLACED, 관리자 APPOINT·DISMISS·GRANT·REVOKE·SUSPEND·UNSUSPEND·TRANSFER·FREEZE·UNFREEZE */
  action: string;
  title: string | null;
  detail: string | null;
  /** 처리한 관리자 (회원 ID 또는 이름) */
  by: string | null;
};

export type ActivityData = { items: ActivityItem[]; reviewsError: string | null };

export const activityMock: ActivityData = {
  reviewsError: null,
  items: [
    {
      at: "2026-10-27T02:10:00Z",
      kind: "NOTICE_REVIEW",
      action: "EDITED_APPROVED",
      title: "○○ 행복주택 입주자 모집",
      detail: null,
      by: "01a17000-0000-7000-8000-00000000ad01",
    },
    {
      at: "2026-10-27T01:30:00Z",
      kind: "NOTICE_REPORT",
      action: "FIXED",
      title: "○○ 국민임대 예비입주자 모집",
      detail: "보증금",
      by: "01a17000-0000-7000-8000-00000000ad01",
    },
    {
      at: "2026-10-26T09:00:00Z",
      kind: "CRITERIA",
      action: "REPLACED",
      title: "기준중위소득 2026년",
      detail: "보건복지부 고시 제2025-135호",
      by: "01a17000-0000-7000-8000-00000000ad01",
    },
    {
      at: "2026-10-25T05:00:00Z",
      kind: "ROLE",
      action: "DISMISS",
      title: "최운영",
      detail: null,
      by: "김○○",
    },
  ],
};
