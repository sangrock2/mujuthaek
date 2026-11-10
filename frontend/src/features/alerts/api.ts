// 알림함 API (백엔드 notification 모듈)를 화면 모양(AlertsData)으로 바꿔요
import { api } from "@/lib/api/client";
import { endpoints } from "@/lib/api/endpoints";
import type { AlertGroup, AlertIcon, AlertItem, AlertsData, AlertType } from "@/mocks/alerts";

/** GET /api/users/me/notifications 한 줄 */
type InboxItem = {
  id: string;
  /** NEW_NOTICE · NEW_SUPPORT · DEADLINE_D3 · DEADLINE_D1 · CORRECTED · FOLLOW_UP · REPORT_ANSWERED */
  type: string;
  /** NOTICE · BENEFIT · SPACE_RECRUITMENT */
  target: { type: string; id: string } | null;
  title: string;
  body: string | null;
  linkPath: string | null;
  createdAt: string;
  readAt: string | null;
};

type InboxPage = { items: InboxItem[]; nextCursor: string | null; hasNext: boolean };

type Settings = {
  newNotice: boolean;
  newSupport: boolean;
  deadline: boolean;
  correction: boolean;
  followUp: boolean;
  quietEnabled: boolean;
};

const KIND: Record<string, { kind: string; icon: AlertIcon }> = {
  NEW_NOTICE: { kind: "새 공고", icon: "home" },
  NEW_SUPPORT: { kind: "새 혜택", icon: "benefit" },
  DEADLINE_D3: { kind: "마감 3일 전", icon: "clock" },
  DEADLINE_D1: { kind: "마감 하루 전", icon: "clock" },
  CORRECTED: { kind: "정정 안내", icon: "notice" },
  FOLLOW_UP: { kind: "후속 안내", icon: "notice" },
  // 내 제보에 관리자가 답함 (처리 결과)
  REPORT_ANSWERED: { kind: "제보 답변", icon: "notice" },
};

const KST = "Asia/Seoul";
const day = (d: Date) => d.toLocaleDateString("en-CA", { timeZone: KST });

function groupOf(at: Date, now: Date): AlertGroup {
  const d = Math.round((Date.parse(day(now)) - Date.parse(day(at))) / 86_400_000);
  return d <= 0 ? "오늘" : d === 1 ? "어제" : d < 7 ? "이번 주" : "이전";
}

function timeOf(at: Date, now: Date) {
  const min = Math.floor((now.getTime() - at.getTime()) / 60_000);
  if (min < 1) return "방금";
  if (min < 60) return `${min}분 전`;
  if (min < 24 * 60) return `${Math.floor(min / 60)}시간 전`;
  const days = Math.floor(min / (24 * 60));
  if (days < 7) return `${days}일 전`;
  return at.toLocaleDateString("ko-KR", { timeZone: KST, month: "long", day: "numeric" });
}

/** 혜택이면 「혜택」, 나머지(공고·사업공간)는 「공고」 */
const typeOf = (i: InboxItem): AlertType => (i.target?.type === "BENEFIT" ? "혜택" : "공고");

export function toAlert(i: InboxItem, now: Date): AlertItem & { linkPath: string | null } {
  const at = new Date(i.createdAt);
  const k = KIND[i.type] ?? { kind: "알림", icon: "notice" as const };
  return {
    id: i.id,
    group: groupOf(at, now),
    type: typeOf(i),
    icon: k.icon,
    kind: k.kind,
    title: i.title,
    body: i.body ?? "",
    time: timeOf(at, now),
    read: i.readAt != null,
    linkPath: i.linkPath,
  };
}

/** 최근 알림 100개 + 받는 알림 설정 */
export async function liveAlerts(): Promise<AlertsData> {
  const [page, settings] = await Promise.all([
    api.get<InboxPage>(`${endpoints.notifications}?size=100`),
    api.get<Settings>(endpoints.notificationSettings).catch(() => null),
  ]);
  const now = new Date();
  return {
    items: page.items.map((i) => toAlert(i, now)),
    settings: settings
      ? [
          { label: "새 공고", on: settings.newNotice },
          { label: "새 혜택", on: settings.newSupport },
          { label: "마감 D-3 · D-1", on: settings.deadline },
          { label: "정정 안내", on: settings.correction },
          { label: "후속 안내", on: settings.followUp },
        ]
      : [],
    quietHours: settings?.quietEnabled === false ? "꺼짐" : "밤 10시 ~ 아침 8시",
  };
}

export const markAlertRead = (id: string) => api.post(`${endpoints.notifications}/${id}/read`);
/** 눌러서 그 화면으로 감 (읽음도 함께, 관리자 알림 지표). 바로 화면을 옮겨도 요청이 끊기지 않게 keepalive */
export const markAlertClicked = (id: string) =>
  api.post(`${endpoints.notificationEvents}/${id}/clicked`, undefined, { keepalive: true });

export const markAllAlertsRead = () => api.post(`${endpoints.notifications}/read-all`);
