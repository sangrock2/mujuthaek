// 공고 채팅 (백엔드 chat 모듈). 방 = 공고 ID라 방을 따로 만들지 않아요. 읽기는 로그인 없이, 쓰기는 로그인한 회원만
import { api, ApiError } from "@/lib/api/client";
import { endpoints } from "@/lib/api/endpoints";

export type ChatMessageStatus = "VISIBLE" | "DELETED" | "HIDDEN_REPORTED" | "HIDDEN_ADMIN";
export type ChatReportReason = "AD" | "ABUSE" | "PRIVACY" | "FALSE_INFO" | "ETC";

/** 채팅방 정보. readOnly면 보내기·답장·좋아요를 막아요(신고·내 글 삭제는 돼요) */
export type ChatRoom = {
  noticeId: string;
  readOnly: boolean;
  /** 읽기 전용이 되는 날 (접수 마감 + 31일). 상시 공고는 null */
  readOnlyFrom: string | null;
  /** 채팅방 위에 늘 보여 줄 안내 */
  guide: string;
};

/** 메시지 하나 (목록 · 보내기 응답 · SSE message.created·restored가 같은 모양) */
export type ChatMessage = {
  id: string;
  noticeId: string;
  authorNickname: string | null;
  /** 삭제·가림이면 null (status로 안내 문구를 골라요) */
  content: string | null;
  status: ChatMessageStatus;
  likeCount: number;
  /** 비로그인·SSE로 받은 메시지는 false */
  likedByMe: boolean;
  /** 비로그인·SSE로 받은 메시지는 false. 내가 보낸 ID를 따로 기억해 채워요 */
  mine: boolean;
  parent: {
    id: string;
    authorNickname: string | null;
    content: string | null;
    status: ChatMessageStatus;
  } | null;
  createdAt: string;
};

export type ChatPage = { items: ChatMessage[]; nextCursor: string | null; hasNext: boolean };
export type LikeResult = { messageId: string; likeCount: number; liked: boolean };

/** 한 번에 받는 메시지 수 (백엔드 기본 30, 최대 100) */
export const PAGE_SIZE = 30;
/** 메시지 최대 글자 수 (백엔드는 앞뒤 공백을 지운 뒤 1~500자) */
export const MAX_LENGTH = 500;

export const chatReasons: { key: ChatReportReason; label: string }[] = [
  { key: "AD", label: "광고" },
  { key: "ABUSE", label: "욕설" },
  { key: "PRIVACY", label: "개인정보 노출" },
  { key: "FALSE_INFO", label: "허위 정보" },
  { key: "ETC", label: "기타" },
];

export const chatKeys = {
  room: (noticeId: string) => ["chat", noticeId, "room"] as const,
  messages: (noticeId: string) => ["chat", noticeId, "messages"] as const,
};

export const fetchRoom = (noticeId: string) => api.get<ChatRoom>(endpoints.noticeChat(noticeId));

export const fetchMessages = (noticeId: string, cursor: string | null) =>
  api.get<ChatPage>(
    `${endpoints.noticeChatMessages(noticeId)}?size=${PAGE_SIZE}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
  );

export const sendMessage = (noticeId: string, content: string, parentId?: string) =>
  api.post<ChatMessage>(endpoints.noticeChatMessages(noticeId), { content, parentId });

export const deleteMessage = (id: string) => api.delete<null>(endpoints.chatMessage(id));

export const setLike = (id: string, on: boolean) =>
  on
    ? api.put<LikeResult>(endpoints.chatMessageLike(id))
    : api.delete<LikeResult>(endpoints.chatMessageLike(id));

export const reportMessage = (id: string, reason: ChatReportReason, detail?: string) =>
  api.post<null>(endpoints.chatMessageReports(id), { reason, detail: detail || undefined });

/** 삭제·가림 메시지 자리에 보일 문구 */
export const hiddenText: Record<ChatMessageStatus, string> = {
  VISIBLE: "",
  DELETED: "삭제된 메시지예요",
  HIDDEN_REPORTED: "신고가 많아 가려진 메시지예요",
  HIDDEN_ADMIN: "운영 정책에 따라 가려진 메시지예요",
};

/** 보내기·좋아요·신고 실패 문구 */
export function chatErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "연결이 끊겼어요. 잠시 뒤 다시 해 주세요";
  switch (error.code) {
    case "UNAUTHENTICATED":
      return "로그인이 풀렸어요. 다시 로그인해 주세요";
    case "ACCOUNT_SUSPENDED":
      return "이용이 정지된 계정이라 채팅을 쓸 수 없어요";
    case "CHAT_RATE_LIMITED":
      return `메시지는 1분에 5개까지 보낼 수 있어요. ${error.retryAfter ?? 60}초 뒤 다시 보내 주세요`;
    case "CHAT_PERSONAL_INFO":
      return "휴대폰 번호·주민등록번호는 올릴 수 없어요. 지우고 보내 주세요";
    case "CHAT_INVALID_CONTENT":
      return "메시지는 1~500자로 써 주세요";
    case "CHAT_REPLY_DEPTH":
      return "답장에는 답장할 수 없어요";
    case "CHAT_READ_ONLY":
      return "접수 마감 30일이 지나 읽기만 할 수 있어요";
    case "CHAT_ALREADY_REPORTED":
      return "이미 신고한 메시지예요";
    case "CHAT_NOT_OWNER":
      return "내가 쓴 메시지만 지울 수 있어요";
    case "CHAT_MESSAGE_NOT_FOUND":
      return "이미 지워진 메시지예요";
    default:
      return "처리하지 못했어요. 잠시 뒤 다시 해 주세요";
  }
}

/** 말풍선 옆 시각: 오전 9:04 · 오후 2:30 */
export function chatClock(iso: string): string {
  const d = new Date(iso);
  const h = d.getHours();
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${h < 12 ? "오전" : "오후"} ${h % 12 === 0 ? 12 : h % 12}:${mm}`;
}

/** 같은 날인지 가르는 키 (보는 사람 시간대 기준) */
export function chatDayKey(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

/** 날짜 구분선: 오늘 · 어제 · 10월 28일 (화). 올해가 아니면 2025년 12월 30일 (화) */
export function chatDay(iso: string, now: number): string {
  const d = new Date(iso);
  const today = new Date(now);
  const yesterday = new Date(now - 24 * 60 * 60 * 1000);
  if (chatDayKey(iso) === chatDayKey(today.toISOString())) return "오늘";
  if (chatDayKey(iso) === chatDayKey(yesterday.toISOString())) return "어제";
  const weekday = "일월화수목금토"[d.getDay()];
  const year = d.getFullYear() === today.getFullYear() ? "" : `${d.getFullYear()}년 `;
  return `${year}${d.getMonth() + 1}월 ${d.getDate()}일 (${weekday})`;
}
