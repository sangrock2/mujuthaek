// 관리자 「알림」 화면: 발송 결과와 알림을 봤는지·눌렀는지 (GET /api/admin/notifications/stats)

/** 알림 서버 발송 결과 (종류·채널별) */
export type DeliveryRow = {
  type: string;
  channel: "PUSH" | "EMAIL";
  sent: number;
  failed: number;
  pending: number;
};

/** 실패 사유 (채널이 남긴 코드) */
export type DeliveryFailure = { channel: "PUSH" | "EMAIL"; error: string; count: number };

/** 알림함 지표 (종류별). 회원별 값은 없어요 */
export type EngagementRow = {
  type: string;
  /** 알림함에 남긴 수 (받은 회원 수) */
  created: number;
  /** 웹 푸시가 기기에 뜬 수 */
  shown: number;
  /** 읽은 수 */
  read: number;
  /** 눌러서 그 화면으로 간 수 */
  clicked: number;
};

export type NotificationStats = {
  days: number;
  /** 알림 서버에 닿지 못하면 null */
  delivery: { byType: DeliveryRow[]; failures: DeliveryFailure[] } | null;
  engagement: EngagementRow[];
};

export const notificationStatsMock: NotificationStats = {
  days: 7,
  delivery: {
    byType: [
      { type: "NEW_NOTICE", channel: "PUSH", sent: 120, failed: 4, pending: 2 },
      { type: "DEADLINE_D3", channel: "PUSH", sent: 64, failed: 1, pending: 0 },
      { type: "DEADLINE_D1", channel: "PUSH", sent: 58, failed: 0, pending: 0 },
      { type: "CORRECTED", channel: "PUSH", sent: 12, failed: 0, pending: 0 },
      { type: "REPORT_ANSWERED", channel: "PUSH", sent: 5, failed: 0, pending: 0 },
    ],
    failures: [
      { channel: "PUSH", error: "PUSH_410", count: 4 },
      { channel: "PUSH", error: "PUSH_IO", count: 1 },
    ],
  },
  engagement: [
    { type: "NEW_NOTICE", created: 180, shown: 118, read: 74, clicked: 51 },
    { type: "DEADLINE_D3", created: 90, shown: 63, read: 40, clicked: 33 },
    { type: "DEADLINE_D1", created: 81, shown: 57, read: 45, clicked: 39 },
    { type: "CORRECTED", created: 15, shown: 12, read: 9, clicked: 7 },
    { type: "REPORT_ANSWERED", created: 6, shown: 5, read: 6, clicked: 4 },
  ],
};
