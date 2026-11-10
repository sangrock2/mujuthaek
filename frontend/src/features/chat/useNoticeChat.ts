"use client";

// 공고 채팅 화면 데이터: 방 정보 + 메시지(최신순 30개씩) + 실시간(SSE).
// SSE가 계속 끊기면(프록시가 오래 열린 연결을 끊는 등) 20초마다 목록을 다시 받아요
import { useEffect, useMemo, useState } from "react";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
  type InfiniteData,
  type QueryClient,
} from "@tanstack/react-query";
import { useSession } from "@/features/auth/session";
import { API_BASE_URL } from "@/lib/api/client";
import { USE_MOCKS } from "@/lib/api/config";
import { endpoints } from "@/lib/api/endpoints";
import {
  chatKeys,
  deleteMessage,
  fetchMessages,
  fetchRoom,
  reportMessage,
  sendMessage,
  setLike,
  type ChatMessage,
  type ChatMessageStatus,
  type ChatPage,
  type ChatReportReason,
  type ChatRoom,
} from "./api";
import { mockChatPage, mockChatRoom, mockMessage } from "./mock";

type Data = InfiniteData<ChatPage, string | null>;

/** 이 브라우저에서 내가 보낸 메시지 ID. SSE로 온 메시지에는 mine이 없어서 이걸로 내 글을 알아봐요 */
const sentIds = new Set<string>();

/** 이만큼 연달아 끊기면 SSE를 접고 목록을 주기적으로 다시 받아요 */
const MAX_FAILURES = 3;
const POLL_MS = 20 * 1000;

/** 같은 메시지가 다시 오면(보내기 응답 · SSE · 가림 해제) 바꿔 끼우고, 처음이면 맨 앞(최신)에 넣어요 */
function upsert(d: Data | undefined, m: ChatMessage): Data | undefined {
  if (!d || d.pages.length === 0) return d;
  const found = d.pages.some((p) => p.items.some((x) => x.id === m.id));
  if (found) {
    return mapItems(d, (x) =>
      x.id === m.id ? { ...m, likedByMe: x.likedByMe || m.likedByMe, mine: x.mine || m.mine } : x,
    );
  }
  const [first, ...rest] = d.pages;
  return { ...d, pages: [{ ...first, items: [m, ...first.items] }, ...rest] };
}

function mapItems(d: Data | undefined, fn: (m: ChatMessage) => ChatMessage): Data | undefined {
  return d && { ...d, pages: d.pages.map((p) => ({ ...p, items: p.items.map(fn) })) };
}

/** 지워지거나 가려진 메시지: 본문을 비우고, 그 메시지에 단 답장의 원문 미리보기도 같이 */
function hide(d: Data | undefined, id: string, status: ChatMessageStatus): Data | undefined {
  return mapItems(d, (x) =>
    x.id === id
      ? { ...x, status, content: null }
      : x.parent?.id === id
        ? { ...x, parent: { ...x.parent, status, content: null } }
        : x,
  );
}

type Key = readonly unknown[];
type Stream = {
  users: number;
  polling: boolean;
  listeners: Set<(polling: boolean) => void>;
  stop: () => void;
};

/** 같은 방을 여러 곳(웹·모바일 화면이 같이 그려져요)에서 보여도 연결은 하나만 열어요 */
const streams = new Map<string, Stream>();

function joinStream(
  client: QueryClient,
  key: Key,
  noticeId: string,
  onPolling: (polling: boolean) => void,
) {
  const id = JSON.stringify(key);
  let s = streams.get(id);
  if (!s) {
    const stream: Stream = {
      users: 0,
      polling: false,
      listeners: new Set(),
      stop: () => undefined,
    };
    stream.stop = openStream(client, key, noticeId, (polling) => {
      stream.polling = polling;
      stream.listeners.forEach((l) => l(polling));
    });
    streams.set(id, stream);
    s = stream;
  }
  const joined = s;
  joined.users += 1;
  joined.listeners.add(onPolling);
  onPolling(joined.polling);
  return () => {
    joined.listeners.delete(onPolling);
    joined.users -= 1;
    if (joined.users === 0) {
      joined.stop();
      streams.delete(id);
    }
  };
}

/** 실시간: 로그인 없이 EventSource로 붙어요. 탭이 숨으면 닫고, 돌아오면 다시 붙으면서 목록을 새로 받아요 */
function openStream(
  client: QueryClient,
  key: Key,
  noticeId: string,
  notify: (polling: boolean) => void,
): () => void {
  let es: EventSource | null = null;
  let failures = 0;
  let missed = false; // 끊긴 동안 삭제·좋아요는 다시 오지 않아서, 다시 붙으면 목록을 새로 받아요
  let retry: ReturnType<typeof setTimeout> | undefined;
  const refetch = () => void client.invalidateQueries({ queryKey: key });
  const read = <T>(e: Event) => JSON.parse((e as MessageEvent<string>).data) as T;

  const close = () => {
    clearTimeout(retry);
    es?.close();
    es = null;
  };
  const open = () => {
    if (es || document.hidden) return;
    const source = new EventSource(`${API_BASE_URL}${endpoints.noticeChatStream(noticeId)}`);
    es = source;
    source.onopen = () => {
      failures = 0;
      notify(false);
      if (missed) refetch();
      missed = false;
    };
    source.onerror = () => {
      missed = true;
      failures += 1;
      if (failures >= MAX_FAILURES) {
        close();
        notify(true);
      } else if (source.readyState === EventSource.CLOSED) {
        // 브라우저가 다시 붙지 않는 끊김(오류 응답 등)이면 조금 있다 직접 다시 붙어요
        close();
        retry = setTimeout(open, failures * 3000);
      }
    };
    source.addEventListener("message.created", (e) =>
      client.setQueryData<Data>(key, (d) => upsert(d, read<ChatMessage>(e))),
    );
    source.addEventListener("message.restored", (e) =>
      client.setQueryData<Data>(key, (d) => upsert(d, read<ChatMessage>(e))),
    );
    source.addEventListener("message.deleted", (e) =>
      client.setQueryData<Data>(key, (d) => hide(d, read<{ id: string }>(e).id, "DELETED")),
    );
    source.addEventListener("message.hidden", (e) =>
      client.setQueryData<Data>(key, (d) => hide(d, read<{ id: string }>(e).id, "HIDDEN_REPORTED")),
    );
    source.addEventListener("like.updated", (e) => {
      const { id, likeCount } = read<{ id: string; likeCount: number }>(e);
      client.setQueryData<Data>(key, (d) =>
        mapItems(d, (x) => (x.id === id ? { ...x, likeCount } : x)),
      );
    });
  };
  const onVisibility = () => {
    if (document.hidden) {
      close();
      missed = true;
    } else {
      failures = 0;
      open();
      refetch();
    }
  };

  open();
  document.addEventListener("visibilitychange", onVisibility);
  return () => {
    document.removeEventListener("visibilitychange", onVisibility);
    close();
  };
}

/**
 * 공고 채팅. live면 실시간(SSE)으로 붙어요: 채팅 창을 열었을 때만 붙여서, 공고만 보는 사람은 연결을 쥐지 않아요.
 * 닫혀 있을 때는 방 정보와 첫 쪽만 받아요 (「이야기」 단추의 이야기 수 · 말풍선의 최근 이야기 미리보기)
 */
export function useNoticeChat(noticeId: string, { live = true }: { live?: boolean } = {}) {
  const client = useQueryClient();
  const session = useSession();
  const loggedIn = USE_MOCKS || !!session.data;
  // 로그인 여부에 따라 내 좋아요·내 글 표시가 달라서 키를 나눠요
  const key = useMemo(
    () => [...chatKeys.messages(noticeId), loggedIn ? "member" : "guest"] as const,
    [noticeId, loggedIn],
  );
  const [polling, setPolling] = useState(false);

  const room = useQuery<ChatRoom>({
    queryKey: chatKeys.room(noticeId),
    queryFn: USE_MOCKS ? async () => mockChatRoom(noticeId) : () => fetchRoom(noticeId),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  const list = useInfiniteQuery({
    queryKey: key,
    queryFn: ({ pageParam }) =>
      USE_MOCKS ? Promise.resolve(mockChatPage(noticeId)) : fetchMessages(noticeId, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => (last.hasNext ? last.nextCursor : undefined),
    // 로그인 확인이 끝난 뒤에 받아야 내 좋아요·내 글이 채워져요
    enabled: USE_MOCKS || !session.isPending,
    retry: false,
    refetchInterval: polling ? POLL_MS : false,
  });

  useEffect(() => {
    if (!live || USE_MOCKS || typeof EventSource === "undefined") return;
    // 채팅 창을 열면 닫혀 있던 동안 쌓인 메시지부터 새로 받고 실시간으로 붙어요
    void client.invalidateQueries({ queryKey: key });
    const leave = joinStream(client, key, noticeId, setPolling);
    return () => {
      leave();
      setPolling(false); // 닫으면 실시간 대신 받던 주기적 새로고침도 멈춰요
    };
  }, [client, key, noticeId, live]);

  /** 오래된 것 → 최신(아래) 순서 */
  const messages = useMemo(
    () => (list.data?.pages ?? []).flatMap((p) => p.items).reverse(),
    [list.data],
  );

  const send = async (content: string, parentId?: string) => {
    const parent = parentId ? messages.find((m) => m.id === parentId) : undefined;
    const message = USE_MOCKS
      ? mockMessage(noticeId, content, parent)
      : await sendMessage(noticeId, content, parentId);
    sentIds.add(message.id);
    client.setQueryData<Data>(key, (d) => upsert(d, { ...message, mine: true }));
  };

  const remove = async (id: string) => {
    if (!USE_MOCKS) await deleteMessage(id);
    client.setQueryData<Data>(key, (d) => hide(d, id, "DELETED"));
  };

  /** 누르면 바로 바뀌어 보이고, 서버 값으로 맞추거나 실패하면 되돌려요 */
  const toggleLike = async (m: ChatMessage) => {
    const on = !m.likedByMe;
    const set = (likedByMe: boolean, likeCount: number) =>
      client.setQueryData<Data>(key, (d) =>
        mapItems(d, (x) => (x.id === m.id ? { ...x, likedByMe, likeCount } : x)),
      );
    set(on, Math.max(0, m.likeCount + (on ? 1 : -1)));
    if (USE_MOCKS) return;
    try {
      const r = await setLike(m.id, on);
      set(r.liked, r.likeCount);
    } catch (error) {
      set(m.likedByMe, m.likeCount);
      throw error;
    }
  };

  const report = async (id: string, reason: ChatReportReason, detail?: string) => {
    if (!USE_MOCKS) await reportMessage(id, reason, detail);
  };

  return {
    room: room.data,
    roomError: room.isError,
    messages,
    loading: list.isPending,
    error: list.isError,
    hasOlder: !!list.hasNextPage,
    loadingOlder: list.isFetchingNextPage,
    loadOlder: () => void list.fetchNextPage(),
    loggedIn,
    sessionPending: !USE_MOCKS && session.isPending,
    isMine: (m: ChatMessage) => m.mine || sentIds.has(m.id),
    send,
    remove,
    toggleLike,
    report,
  };
}
