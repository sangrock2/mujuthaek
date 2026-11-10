"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AdminTitleRow } from "@/components/admin/AdminShell";
import { reviewChatMessage } from "@/features/admin/api";
import { useChatReportQueue, useSetAdminCounts } from "@/features/admin/queries";
import { USE_MOCKS } from "@/lib/api/config";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import type {
  ChatMessageStatus,
  ChatReportGroup,
  ChatReportReason,
  ChatReviewAction,
  ChatReviewStatus,
} from "@/mocks/admin-chat";

const TABS: { key: ChatReviewStatus; label: string }[] = [
  { key: "PENDING", label: "검토 전" },
  { key: "KEPT_HIDDEN", label: "가림 유지" },
  { key: "RESTORED", label: "다시 보임" },
];

const REASON: Record<ChatReportReason, string> = {
  AD: "광고",
  ABUSE: "욕설",
  PRIVACY: "개인정보 노출",
  FALSE_INFO: "허위 정보",
  ETC: "기타",
};

const MESSAGE: Record<ChatMessageStatus, { label: string; cls: string }> = {
  VISIBLE: { label: "지금 보이는 글", cls: "bg-ok-bg text-ok-text" },
  HIDDEN_REPORTED: { label: "신고 3건으로 자동 가림", cls: "bg-check-bg text-check-text" },
  HIDDEN_ADMIN: { label: "관리자가 가림", cls: "bg-fill text-text" },
  DELETED: { label: "작성자가 지운 글", cls: "bg-fill text-text-sub" },
};

const when = (iso: string) =>
  new Date(iso).toLocaleString("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

/** 신고 사유별 건수 (예: 광고 2 · 기타 1) */
function reasonSummary(g: ChatReportGroup) {
  const n = new Map<ChatReportReason, number>();
  g.reports.forEach((r) => n.set(r.reason, (n.get(r.reason) ?? 0) + 1));
  return [...n.entries()].map(([k, v]) => `${REASON[k]} ${v}`).join(" · ");
}

/** 목록·상세 칸 높이: 화면에 고정하고 칸 안에서 스크롤해요(검수·정보 제보와 같은 방식) */
const PANEL_HEIGHT = "h-[max(560px,calc(100dvh-210px))]";

/** 채팅 신고 (제보·신고 화면의 한 갈래). head: 제목 줄 왼쪽 */
export function AdminWebChatReports({ head }: { head: React.ReactNode }) {
  const [tab, setTab] = useState<ChatReviewStatus>("PENDING");
  // 신고를 20건씩 이어 받아 글마다 묶어요(무한 스크롤)
  const queue = useChatReportQueue(tab);
  const groups = queue.groups;
  const isPending = queue.loading;
  const isError = queue.failed;
  const [sel, setSel] = useState<string | null>(null);
  const [done, setDone] = useState<Record<string, ChatReviewAction>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const setCounts = useSetAdminCounts();

  // 방금 처리한 글은 목록에서 빼요(다시 받으면 다른 탭으로 옮겨 가 있어요)
  const list = groups.filter((g) => !done[g.messageId]);
  const cur = list.find((g) => g.messageId === sel) ?? list[0];

  // 목록 아래 끝이 보이면 다음 20건을 받아요(검수·정보 제보와 같은 방식)
  const listRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const loadMore = useRef(queue.loadMore);
  useEffect(() => {
    loadMore.current = queue.loadMore;
  });
  const { more } = queue;
  useEffect(() => {
    const end = endRef.current;
    if (!end || !more) return;
    const seen = new IntersectionObserver((e) => e[0]?.isIntersecting && loadMore.current(), {
      root: listRef.current,
      rootMargin: "200px",
    });
    seen.observe(end);
    return () => seen.disconnect();
  }, [more, list.length]);

  const review = async (action: ChatReviewAction) => {
    if (!cur) return;
    setBusy(true);
    setError(null);
    try {
      if (!USE_MOCKS) await reviewChatMessage(cur.messageId, action);
      setDone({ ...done, [cur.messageId]: action });
      setSel(null);
      if (tab === "PENDING") setCounts({ chatReports: Math.max(0, list.length - 1) });
      if (!USE_MOCKS) {
        void queryClient.invalidateQueries({ queryKey: ["admin", "live", "chat-reports"] });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <AdminTitleRow>
        {head}
        <div role="group" aria-label="검토 상태" className="flex flex-wrap gap-[6px]">
          {TABS.map((t) => {
            const on = t.key === tab;
            return (
              <button
                key={t.key}
                type="button"
                aria-pressed={on}
                onClick={() => {
                  setTab(t.key);
                  setSel(null);
                  setDone({});
                }}
                className={cn(
                  "rounded-pill min-h-[40px] cursor-pointer border-0 px-[16px] text-[14px] font-bold",
                  on ? "bg-text text-white" : "bg-surface text-text-sub",
                )}
              >
                {t.label}
                {on && !isPending ? ` ${list.length}${more ? "+" : ""}` : ""}
              </button>
            );
          })}
        </div>
      </AdminTitleRow>

      <div className="flex flex-wrap items-start gap-[20px]">
        <section
          aria-label="신고된 글 목록"
          className={cn(
            "rounded-card bg-surface flex min-w-0 flex-col overflow-hidden",
            PANEL_HEIGHT,
          )}
          style={{ flex: "1 1 300px" }}
        >
          <div
            ref={listRef}
            className="flex min-h-0 flex-1 flex-col overflow-x-hidden overflow-y-auto overscroll-contain [overflow-wrap:anywhere]"
          >
            {isPending && (
              <div className="text-text-sub px-[24px] py-[40px] text-center text-[15px]">
                불러오는 중이에요
              </div>
            )}
            {isError && (
              <div className="text-text-sub px-[24px] py-[40px] text-center text-[15px]">
                신고 목록을 불러오지 못했어요
              </div>
            )}
            {!isPending && !isError && list.length === 0 && (
              <div className="text-text-sub px-[24px] py-[40px] text-center text-[15px]">
                이 상태의 신고가 없어요
              </div>
            )}
            {list.map((g) => {
              const on = g.messageId === cur?.messageId;
              return (
                <button
                  key={g.messageId}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setSel(g.messageId)}
                  className={cn(
                    "border-b-line-soft text-text flex cursor-pointer flex-col gap-[6px] border-0 border-b border-l-4 border-solid py-[16px] pr-[18px] pl-[14px] text-left",
                    on ? "bg-row-selected border-l-brand" : "bg-surface border-l-transparent",
                  )}
                >
                  <span className="flex w-full justify-between gap-[8px]">
                    <span className="text-text-sub truncate text-[12px] font-bold">
                      {g.noticeTitle ?? "공고 채팅"}
                    </span>
                    <span className="text-text-sub shrink-0 text-[12px]">
                      {when(g.lastReportedAt)}
                    </span>
                  </span>
                  <span className="text-[15px] leading-[1.5] font-bold">
                    {g.message.content ?? "(본문 없음)"}
                  </span>
                  <span className="flex flex-wrap gap-[6px]">
                    <span className="rounded-tag bg-check-bg text-check-text px-[8px] py-[2px] text-[12px] font-extrabold">
                      신고 {g.reports.length}건
                    </span>
                    <span className="text-text-sub text-[12px]">{reasonSummary(g)}</span>
                  </span>
                </button>
              );
            })}
            {more && (
              <div
                ref={endRef}
                className="border-t-line-soft text-text-sub border-0 border-t border-solid px-[18px] py-[14px] text-[13px]"
              >
                {queue.loadingMore ? "더 불러오는 중이에요" : "아래로 내리면 더 불러와요"}
              </div>
            )}
          </div>
        </section>

        {cur && (
          <div
            className={cn(
              "flex min-w-0 flex-col gap-[16px] overflow-y-auto overscroll-contain",
              PANEL_HEIGHT,
            )}
            style={{ flex: "999 1 560px" }}
          >
            <section
              aria-label="신고된 글"
              className="rounded-card bg-surface flex flex-col gap-[16px] px-[26px] py-[24px]"
            >
              <div className="flex flex-wrap items-start justify-between gap-[12px]">
                <div className="flex min-w-0 flex-col gap-[6px]">
                  <span className="text-text-sub text-[13px] font-bold">
                    {cur.noticeTitle ?? "공고 채팅"}
                  </span>
                  <span
                    className={cn(
                      "rounded-tag self-start px-[8px] py-[2px] text-[12px] font-extrabold",
                      MESSAGE[cur.message.status].cls,
                    )}
                  >
                    {MESSAGE[cur.message.status].label}
                  </span>
                </div>
                <Link
                  href={routes.notice(cur.noticeId)}
                  target="_blank"
                  className="bg-fill text-text hover:text-text inline-flex min-h-[44px] items-center gap-[6px] rounded-sm px-[14px] text-[14px] font-bold no-underline"
                >
                  공고에서 보기
                </Link>
              </div>
              <div className="bg-bg flex flex-col gap-[8px] rounded-[18px] px-[20px] py-[18px]">
                <span className="text-text-sub text-[13px] font-bold">
                  {cur.message.authorNickname ?? "알 수 없는 작성자"}
                </span>
                <p className="m-0 text-[17px] leading-[1.6] font-semibold whitespace-pre-wrap">
                  {cur.message.content ?? "(본문 없음)"}
                </p>
              </div>
              <div className="flex flex-col gap-[8px]">
                <span className="text-[15px] font-extrabold">
                  신고 {cur.reports.length}건 · {reasonSummary(cur)}
                </span>
                {cur.reports.map((r) => (
                  <div
                    key={r.reportId}
                    className="rounded-control bg-bg flex flex-wrap items-baseline justify-between gap-[8px] px-[14px] py-[12px]"
                  >
                    <span className="text-[15px] font-bold">
                      {REASON[r.reason]}
                      {r.detail && (
                        <span className="text-text-body-long font-medium"> · {r.detail}</span>
                      )}
                    </span>
                    <span className="text-text-sub text-[12px]">{when(r.reportedAt)}</span>
                  </div>
                ))}
                <span className="text-text-sub text-[13px]">신고한 회원은 보여 주지 않아요</span>
              </div>
            </section>

            {tab === "PENDING" && (
              <section
                aria-label="처리"
                className="rounded-card bg-surface flex flex-col gap-[14px] px-[26px] py-[22px]"
              >
                {error && (
                  <div
                    role="alert"
                    className="rounded-control bg-fill text-text px-[16px] py-[12px] text-[14px] font-bold"
                  >
                    처리하지 못했어요 · {error}
                  </div>
                )}
                <span className="text-text-sub text-[14px] leading-[1.6]">
                  계속 가리기: 채팅방에서 「신고로 가려진 메시지」로 보여요 · 다시 보이기: 원래 글로
                  돌아가고 검토 전 신고 수가 0이 돼요 (새 신고 3건이 쌓이면 다시 가려져요)
                </span>
                <div className="flex flex-wrap gap-[8px]">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => review("KEEP_HIDDEN")}
                    className="rounded-control bg-brand min-h-[52px] cursor-pointer border-0 px-[20px] text-[16px] font-extrabold text-white disabled:opacity-50"
                  >
                    계속 가리기
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => review("RESTORE")}
                    className="rounded-control bg-fill text-text min-h-[52px] cursor-pointer border-0 px-[18px] text-[15px] font-bold disabled:opacity-50"
                  >
                    문제없어요 · 다시 보이기
                  </button>
                </div>
              </section>
            )}
          </div>
        )}
      </div>
    </>
  );
}
