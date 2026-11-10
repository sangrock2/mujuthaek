"use client";

import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { AdminTitleRow } from "@/components/admin/AdminShell";
import { isAreaReport, reopenFromReport, resolveReport } from "@/features/admin/api";
import {
  reportDetailQuery,
  useAdminReportDetail,
  useReportCounts,
  useReportQueue,
  useSetAdminCounts,
} from "@/features/admin/queries";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import type { ReportStatus } from "@/mocks/admin";
import { USE_MOCKS } from "@/lib/api/config";

const TABS: { key: ReportStatus; label: string }[] = [
  { key: "new", label: "새 제보" },
  { key: "doing", label: "확인 중" },
  { key: "done", label: "처리 완료" },
];

type Finish = "fix" | "same";

const secondary =
  "rounded-control bg-fill text-text hover:text-text min-h-[52px] px-[18px] text-[15px] font-bold";

/** 목록·상세 칸 높이: 화면에 고정하고 칸 안에서 스크롤해요(검수 화면과 같은 방식) */
const PANEL_HEIGHT = "h-[max(560px,calc(100dvh-210px))]";

/** 정보 제보 (제보·신고 화면의 한 갈래). head: 제목 줄 왼쪽 */
export function AdminWebReports({ head }: { head: React.ReactNode }) {
  const setCounts = useSetAdminCounts();
  const queryClient = useQueryClient();
  const counts = useReportCounts();

  const [tab, setTab] = useState<ReportStatus>("new");
  // 고른 상태의 제보를 서버가 최신순으로 20건씩 줘요(공고·혜택·사업 제보와 생활권 제보를 섞어서)
  const queue = useReportQueue(tab);
  const list = queue.items;
  const [sel, setSel] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<Record<string, Finish>>({});
  const [replies, setReplies] = useState<Record<string, string>>({});

  const selId = list.some((d) => d.id === sel) ? sel : (list[0]?.id ?? null);
  const picked = list.find((d) => d.id === selId);

  // 목록 아래 끝이 보이면 다음 20건을 받아요. loadMore는 그릴 때마다 새로 만들어지니 ref로 들고 있어 감시를 다시 걸지 않아요
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
  // 설명·같은 묶음 설명·답장은 고른 제보만 받아요. 받기 전에는 목록 값(요약)
  const detail = useAdminReportDetail(picked);
  const cur = picked && detail.data ? { ...picked, ...detail.data } : picked;

  const finish = async (kind: Finish) => {
    if (!cur) return;
    // 처리 끝과 답장을 실제 백엔드로 보내요(답은 알림 쪽 이벤트로 나가요)
    if (!USE_MOCKS) {
      try {
        setError(null);
        // 상세를 아직 못 받았으면 저장된 답장을 먼저 받아요(빈 답장으로 덮어쓰지 않게)
        const saved =
          replies[cur.id] ??
          (await queryClient.ensureQueryData(reportDetailQuery(cur.id, cur.summary))).reply;
        await resolveReport(cur.id, kind === "fix", saved);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        return;
      }
    }
    // 처리한 건은 목록에 「처리함」으로 남았다가 탭을 다시 열면 빠져요. 상태별 건수·사이드바 숫자는 다시 받아요
    setDone({ ...done, [cur.id]: kind });
    void queryClient.invalidateQueries({ queryKey: ["admin", "live", "reports", "counts"] });
    setCounts({});
  };

  return (
    <>
      <AdminTitleRow>
        {head}
        <div role="group" aria-label="처리 상태" className="flex flex-wrap gap-[6px]">
          {TABS.map((t) => {
            const on = t.key === tab;
            const count = counts?.[t.key];
            return (
              <button
                key={t.key}
                type="button"
                aria-pressed={on}
                onClick={() => setTab(t.key)}
                className={cn(
                  "rounded-pill min-h-[40px] cursor-pointer border-0 px-[16px] text-[14px] font-bold",
                  on ? "bg-text text-white" : "bg-surface text-text-sub",
                )}
              >
                {t.label} {count ?? ""}
              </button>
            );
          })}
        </div>
      </AdminTitleRow>

      <div className="flex flex-wrap items-start gap-[20px]">
        <section
          aria-label="제보 목록"
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
            {list.length === 0 && (
              <div className="text-text-sub px-[24px] py-[40px] text-center text-[15px]">
                {queue.loading ? "불러오는 중…" : "이 상태의 제보가 없어요"}
              </div>
            )}
            {list.map((r) => {
              const on = r.id === selId;
              return (
                <button
                  key={r.id}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setSel(r.id)}
                  className={cn(
                    "border-b-line-soft text-text flex cursor-pointer flex-col gap-[6px] border-0 border-b border-l-4 border-solid py-[16px] pr-[18px] pl-[14px] text-left",
                    on ? "bg-row-selected border-l-brand" : "bg-surface border-l-transparent",
                  )}
                >
                  <span className="flex w-full justify-between gap-[8px]">
                    <span className="text-text-sub text-[12px] font-bold">{r.where}</span>
                    <span className="text-text-sub text-[12px]">{r.age}</span>
                  </span>
                  <span className="text-[15px] font-bold">{r.target}</span>
                  <span className="text-text-body-long text-[14px]">{r.summary}</span>
                  {r.groupCount > 1 && (
                    <span className="rounded-tag bg-check-bg text-check-text self-start px-[8px] py-[2px] text-[12px] font-extrabold">
                      같은 제보 {r.groupCount}건
                    </span>
                  )}
                  {done[r.id] && <span className="text-ok-text text-[12px] font-bold">처리함</span>}
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
              aria-label="제보 내용"
              className="rounded-card bg-surface flex flex-col gap-[16px] px-[26px] py-[24px]"
            >
              <div className="flex flex-wrap items-start justify-between gap-[12px]">
                <div className="flex flex-col gap-[6px]">
                  <span className="text-text-sub text-[13px] font-bold">{cur.where}</span>
                  <h2 className="tracking-title m-0 text-[22px] font-extrabold">{cur.target}</h2>
                </div>
                {cur.link && (
                  <Link
                    href={cur.link}
                    className="bg-fill text-text hover:text-text inline-flex min-h-[44px] items-center gap-[6px] rounded-sm px-[14px] text-[14px] font-bold no-underline"
                  >
                    사용자 화면에서 보기
                  </Link>
                )}
              </div>
              <div
                className="grid gap-[12px]"
                style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}
              >
                <div className="bg-bg flex flex-col gap-[6px] rounded-[18px] px-[18px] py-[16px]">
                  <span className="text-text-sub text-[13px] font-bold">
                    지금 서비스 값 · {cur.field}
                  </span>
                  <span className="text-[20px] font-extrabold">{cur.current}</span>
                </div>
                <div className="bg-lowconf-bg flex flex-col gap-[6px] rounded-[18px] px-[18px] py-[16px] shadow-[inset_0_0_0_1px_var(--color-lowconf-line)]">
                  <span className="text-check-text text-[13px] font-bold">사용자가 말한 값</span>
                  <span className="text-[20px] font-extrabold">{cur.reported}</span>
                </div>
                <div className="bg-bg flex flex-col gap-[6px] rounded-[18px] px-[18px] py-[16px]">
                  <span className="text-text-sub text-[13px] font-bold">제보 설명</span>
                  <span className="text-[15px] leading-[1.5] font-semibold">{cur.source}</span>
                </div>
              </div>
              <div className="flex flex-col gap-[8px]">
                <span className="text-[15px] font-extrabold">사용자 메모</span>
                {cur.notes.map((n, i) => (
                  <div
                    key={`${i}-${n.meta}`}
                    className="rounded-control bg-bg flex flex-col gap-[4px] px-[14px] py-[12px]"
                  >
                    <span className="text-[15px] leading-[1.6]">{n.text}</span>
                    <span className="text-text-sub text-[12px]">{n.meta}</span>
                  </div>
                ))}
              </div>
            </section>

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
              {done[cur.id] && (
                <div
                  role="status"
                  className="rounded-control bg-ok-bg text-ok-text px-[16px] py-[12px] text-[15px] font-bold"
                >
                  {done[cur.id] === "fix"
                    ? "고쳤다고 답변을 보냈어요 · 값은 「다시 검수로 보내기」로 검수에서 고쳐요"
                    : "원문과 같다고 답변을 보냈어요"}
                </div>
              )}
              <label className="flex flex-col gap-[8px] text-[15px] font-extrabold">
                사용자에게 보낼 답변
                <textarea
                  rows={3}
                  value={replies[cur.id] ?? cur.reply}
                  onChange={(e) => setReplies({ ...replies, [cur.id]: e.target.value })}
                  className="rounded-control border-line text-text resize-y border border-solid px-[14px] py-[12px] text-[15px] leading-[1.6] font-medium"
                />
                <span className="text-text-sub text-[13px] font-medium">
                  {/* 제보한 회원에게 처리 결과(고침·그대로 둠) 알림이 가요. 답변 원문은 개인정보가 들어갈 수 있어 알림에 넣지 않아요 */}
                  같은 제보를 보낸 {cur.groupCount}명 모두에게 처리 결과 알림이 가요 · 답변 내용은
                  알림에 담기지 않아요
                </span>
              </label>
              <div className="flex flex-wrap gap-[8px]">
                <button
                  type="button"
                  onClick={() => finish("fix")}
                  className="rounded-control bg-brand min-h-[52px] cursor-pointer border-0 px-[20px] text-[16px] font-extrabold text-white"
                >
                  {/* 이 버튼은 값을 고치지 않고 「고침」 답장만 보내요. 값은 검수에서 고쳐요 */}
                  고쳤다고 답변 보내기
                </button>
                <button
                  type="button"
                  onClick={() => finish("same")}
                  className={cn(secondary, "cursor-pointer border-0")}
                >
                  원문과 같아요 · 답변만
                </button>
                {/* 생활권 제보는 AI 추출 값이 아니라, 일반 제보는 대상이 없어 검수로 보내지 않아요 */}
                {!isAreaReport(cur.id) && !cur.general && (
                  <Link
                    href={routes.adminReview}
                    onClick={async (e) => {
                      // 이 제보로 검수를 다시 연 뒤 검수 화면으로 가요
                      if (USE_MOCKS || !cur) return;
                      e.preventDefault();
                      try {
                        await reopenFromReport(cur.id);
                        setCounts({});
                        window.location.href = routes.adminReview;
                      } catch (err) {
                        setError(err instanceof Error ? err.message : String(err));
                      }
                    }}
                    className={cn(secondary, "inline-flex items-center no-underline")}
                  >
                    다시 검수로 보내기
                  </Link>
                )}
              </div>
            </section>
          </div>
        )}
      </div>
    </>
  );
}
