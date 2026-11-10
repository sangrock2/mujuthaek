// 관리자 「채팅 신고」 화면 타입과 예시 데이터. 실제 값은 GET /api/admin/chat/reports (백엔드 chat 모듈)
export type ChatReportReason = "AD" | "ABUSE" | "PRIVACY" | "FALSE_INFO" | "ETC";
export type ChatReviewStatus = "PENDING" | "KEPT_HIDDEN" | "RESTORED";
export type ChatMessageStatus = "VISIBLE" | "DELETED" | "HIDDEN_REPORTED" | "HIDDEN_ADMIN";
export type ChatReviewAction = "KEEP_HIDDEN" | "RESTORE";

/** 백엔드 신고 한 건 (신고한 회원은 오지 않아요) */
export type ChatReport = {
  reportId: string;
  messageId: string;
  noticeId: string;
  reason: ChatReportReason;
  detail: string | null;
  reviewStatus: ChatReviewStatus;
  reportedAt: string;
  message: {
    authorNickname: string | null;
    content: string | null;
    status: ChatMessageStatus;
    /** 검토 전 신고 수 */
    reportCount: number;
  };
  /** 처리한 관리자 회원 ID (검토 전이면 없음) */
  reviewedBy?: string | null;
  /** 처리한 시각 */
  reviewedAt?: string | null;
};

/** 화면용: 신고된 메시지 하나와 그 메시지에 들어온 신고들 */
export type ChatReportGroup = {
  messageId: string;
  noticeId: string;
  noticeTitle: string | null;
  message: ChatReport["message"];
  reports: {
    reportId: string;
    reason: ChatReportReason;
    detail: string | null;
    reportedAt: string;
  }[];
  lastReportedAt: string;
};

const NOTICE = "n1"; // 목업 공고 (사용자 화면 /notices/n1)

export const chatReportsMock: ChatReport[] = [
  {
    reportId: "r1",
    messageId: "m1",
    noticeId: NOTICE,
    reason: "AD",
    detail: null,
    reviewStatus: "PENDING",
    reportedAt: "2026-10-27T01:20:00Z",
    message: {
      authorNickname: "청약도우미",
      content: "당첨 확률 올리는 방법 알려드려요. 오픈채팅으로 오세요",
      status: "HIDDEN_REPORTED",
      reportCount: 3,
    },
  },
  {
    reportId: "r2",
    messageId: "m1",
    noticeId: NOTICE,
    reason: "AD",
    detail: null,
    reviewStatus: "PENDING",
    reportedAt: "2026-10-27T01:12:00Z",
    message: {
      authorNickname: "청약도우미",
      content: "당첨 확률 올리는 방법 알려드려요. 오픈채팅으로 오세요",
      status: "HIDDEN_REPORTED",
      reportCount: 3,
    },
  },
  {
    reportId: "r3",
    messageId: "m1",
    noticeId: NOTICE,
    reason: "ETC",
    detail: "같은 글을 여러 방에 올려요",
    reviewStatus: "PENDING",
    reportedAt: "2026-10-27T01:05:00Z",
    message: {
      authorNickname: "청약도우미",
      content: "당첨 확률 올리는 방법 알려드려요. 오픈채팅으로 오세요",
      status: "HIDDEN_REPORTED",
      reportCount: 3,
    },
  },
  {
    reportId: "r4",
    messageId: "m2",
    noticeId: NOTICE,
    reason: "FALSE_INFO",
    detail: "마감일이 공고문과 달라요",
    reviewStatus: "PENDING",
    reportedAt: "2026-10-26T23:40:00Z",
    message: {
      authorNickname: "마포주민",
      content: "이거 신청 이번 주 금요일까지래요",
      status: "VISIBLE",
      reportCount: 1,
    },
  },
];

export const chatReportTitlesMock: Record<string, string> = {
  [NOTICE]: "서초구 서리풀 청년아트타운 잔여세대 입주자 모집공고",
};
