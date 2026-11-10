// 목업 모드의 공고 채팅 (보내기·삭제·좋아요는 이 화면에서만 바뀌어요)
import type { ChatMessage, ChatPage, ChatRoom } from "./api";

const GUIDE =
  "채팅은 사용자 의견이에요. 판정 결과가 아니니 지원 자격은 공고문과 판정 결과로 확인해 주세요.";

export const mockChatRoom = (noticeId: string): ChatRoom => ({
  noticeId,
  readOnly: false,
  readOnlyFrom: null,
  guide: GUIDE,
});

const base = { likedByMe: false, mine: false, parent: null, status: "VISIBLE" } as const;

/** 최신순 (백엔드와 같은 순서) */
export const mockChatPage = (noticeId: string): ChatPage => ({
  items: [
    {
      ...base,
      id: "mock-m4",
      noticeId,
      authorNickname: "새내기세입자",
      content: "저도 같은 단지 넣으려고요. 서류는 주민센터에서 한 번에 뗐어요",
      likeCount: 2,
      parent: {
        id: "mock-m2",
        authorNickname: "청약3년차",
        content: "소득 서류 언제까지 내야 하는지 아시는 분?",
        status: "VISIBLE",
      },
      createdAt: "2026-10-28T09:12:00Z",
    },
    {
      ...base,
      id: "mock-m3",
      noticeId,
      authorNickname: null,
      content: null,
      status: "HIDDEN_REPORTED",
      likeCount: 0,
      createdAt: "2026-10-28T08:40:00Z",
    },
    {
      ...base,
      id: "mock-m2",
      noticeId,
      authorNickname: "청약3년차",
      content:
        "소득 서류 언제까지 내야 하는지 아시는 분? 공고문 9쪽에는 서류 제출 기간이 따로 있네요",
      likeCount: 5,
      createdAt: "2026-10-28T07:05:00Z",
    },
    {
      ...base,
      id: "mock-m1",
      noticeId,
      authorNickname: "무주택5년",
      content: "작년 같은 공고는 경쟁률이 꽤 높았어요. 1순위 조건 꼭 확인하세요",
      likeCount: 8,
      createdAt: "2026-10-27T12:30:00Z",
    },
  ],
  nextCursor: null,
  hasNext: false,
});

let seq = 0;

export const mockMessage = (
  noticeId: string,
  content: string,
  parent?: ChatMessage,
): ChatMessage => ({
  ...base,
  id: `mock-new-${++seq}`,
  noticeId,
  authorNickname: "준",
  content,
  likeCount: 0,
  mine: true,
  parent: parent
    ? {
        id: parent.id,
        authorNickname: parent.authorNickname,
        content: parent.content?.slice(0, 50) ?? null,
        status: parent.status,
      }
    : null,
  createdAt: new Date().toISOString(),
});
