"use client";

import { ChevronRight, ExternalLink, Users } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { AdminTitle, AdminTitleRow } from "@/components/admin/AdminShell";
import { Badge } from "@/components/ui/Badge";
import { decideReview, reviewMeta } from "@/features/admin/api";
import { useReviewDecided, useReviewDetail, useReviewQueue } from "@/features/admin/queries";
import { cn } from "@/lib/cn";
import type { ReviewReason, SourcePartKind } from "@/mocks/admin";
import { USE_MOCKS } from "@/lib/api/config";

const REASON: Record<ReviewReason, { label: string; tone: "ok" | "check" | "danger" }> = {
  must: { label: "필수 검수", tone: "ok" },
  low: { label: "검수 필요", tone: "check" },
  format: { label: "형식 오류", tone: "danger" },
};

const FILTERS: { key: "all" | ReviewReason; label: string }[] = [
  { key: "all", label: "전체" },
  { key: "must", label: "필수 검수" },
  { key: "low", label: "검수 필요" },
  { key: "format", label: "형식 오류" },
];

const partStyle: Record<SourcePartKind, string> = {
  ok: "bg-ok-bg text-ok-text font-bold",
  low: "bg-check-bg text-check-text font-bold",
  plain: "text-text-body-long font-normal",
};

const REJECT_REASONS = ["중복 공고", "원문과 다름", "서비스 대상 아님", "마감된 공고"];

type Done = "ok" | "no";

export function AdminWebReview() {
  const [filter, setFilter] = useState<"all" | ReviewReason>("all");
  // 사유로 거르기는 서버가 해요(대기열을 20건씩 이어 받아서, 받은 것만 거르면 뒤 페이지의 건이 빠져요)
  const queue = useReviewQueue(filter === "all" ? null : filter);
  const decided = useReviewDecided();
  const items = queue.items;

  const [sel, setSel] = useState(items[0].id);
  const [done, setDone] = useState<Record<string, Done>>({});
  const [edits, setEdits] = useState<Record<string, Record<string, string>>>({});
  const [rejectReason, setRejectReason] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const shown = items;
  const selId = shown.some((i) => i.id === sel) ? sel : items[0].id;
  const row = items.find((i) => i.id === selId) ?? items[0];
  // 대기열 아래 끝이 보이면 다음 20건을 받아요
  const listRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const { more, loadMore } = queue;
  useEffect(() => {
    const end = endRef.current;
    if (!end || !more) return;
    const seen = new IntersectionObserver((e) => e[0]?.isIntersecting && loadMore(), {
      root: listRef.current,
      rootMargin: "200px",
    });
    seen.observe(end);
    return () => seen.disconnect();
  }, [more, loadMore, items.length]);
  // 대기열 줄에는 원문·추출 결과가 없어요. 고른 건만 상세를 받아 채워요(목업은 줄에 다 있어요)
  const detail = useReviewDetail(row.id);
  const cur = detail.data ?? row;
  /** 상세(승인·반려에 쓰는 칸 정보)를 받기 전에는 처리하지 않아요 */
  const ready = USE_MOCKS || !!detail.data;
  const curEdits = edits[cur.id] ?? {};
  const edited = Object.keys(curEdits).length > 0;
  const curDone = done[cur.id];
  // 실제 연결은 처리할 때마다 받아 둔 건수를 하나씩 줄여요(useReviewDecided). 처리한 수를 또 빼지 않아요
  const pending = !USE_MOCKS ? queue.total : queue.total - Object.keys(done).length;
  const meta = reviewMeta.get(cur.id);
  /** 건을 바꾸면 반려 사유·오류도 그 건 것이 아니므로 비워요 */
  const select = (id: string) => {
    setSel(id);
    setRejectReason(null);
    setError(null);
  };

  const statusText = (id: string) =>
    done[id] === "ok" ? "승인함" : done[id] === "no" ? "반려함" : "대기 중";

  /** 승인·반려는 되돌릴 수 없어 한 번 더 물어요 */
  const confirmText = (kind: Done) => {
    const changed = Object.keys(curEdits);
    return kind === "ok"
      ? `「${cur.title}」을(를) ${changed.length ? `고친 ${changed.length}칸(${changed.join(", ")})으로 ` : ""}승인할까요? 승인하면 사용자 화면에 반영돼요.`
      : `「${cur.title}」을(를) ${rejectReason ? `「${rejectReason}」 사유로 ` : "사유 없이 "}반려할까요?`;
  };

  const finish = async (kind: Done) => {
    if (!window.confirm(confirmText(kind))) return;
    // 실제 백엔드에 승인·반려를 보내요(고친 칸은 칸별 수정으로). 목업이면 화면만 바꿔요
    if (reviewMeta.has(cur.id)) {
      setBusy(true);
      setError(null);
      try {
        await decideReview(cur.id, kind === "ok", curEdits, rejectReason);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setBusy(false);
        return;
      }
      setBusy(false);
    }
    const next = { ...done, [cur.id]: kind };
    setDone(next);
    decided(queue.total - Object.keys(next).length);
  };

  /** 다음 건. 받은 마지막 건이면 다음 20건을 받고(받으면 그때 다시 눌러요), 다 받았으면 처음으로 */
  const goNext = () => {
    const idx = items.findIndex((i) => i.id === cur.id);
    if (idx === items.length - 1 && more) {
      loadMore();
      return;
    }
    select(items[(idx + 1) % items.length].id);
  };

  const reason = REASON[cur.reason];

  return (
    <>
      <AdminTitleRow>
        <AdminTitle
          title="검수"
          desc="AI가 원문에서 뽑은 조건을 확인하고 서비스에 내보내요 · 필수 검수·형식 오류는 승인 전까지 안 보이고, 검수 필요는 이미 공개 중이며 보류 칸만 승인 전까지 안 보여요"
        />
      </AdminTitleRow>

      <div className="flex flex-wrap items-start gap-[20px]">
        {/* 대기열·원문·추출 결과는 칸마다 따로 휠로 내려요(아래 건을 골라도 페이지를 다시 올리지 않게).
            대기열과 「검수 대상+원문·추출 결과」는 같은 높이라 아래 끝이 맞아요 */}
        <section
          aria-label="검수 대기열"
          className="rounded-card bg-surface flex h-[max(560px,calc(100dvh-150px))] min-w-0 flex-col overflow-hidden"
          style={{ flex: "1 1 290px" }}
        >
          <div className="flex flex-col gap-[12px] px-[18px] pt-[18px] pb-[12px]">
            <div className="flex items-center justify-between">
              <span className="text-[16px] font-extrabold">대기열 {pending}건</span>
              <span className="text-text-sub text-[13px]">오래된 순</span>
            </div>
            <div role="group" aria-label="검수 사유" className="flex flex-wrap gap-[6px]">
              {FILTERS.map((f) => {
                const on = f.key === filter;
                return (
                  <button
                    key={f.key}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setFilter(f.key)}
                    className={cn(
                      "rounded-pill min-h-[36px] cursor-pointer border-0 px-[12px] text-[13px] font-bold",
                      on ? "bg-text text-white" : "bg-fill text-text-sub",
                    )}
                  >
                    {f.label}
                  </button>
                );
              })}
            </div>
          </div>
          <div
            ref={listRef}
            className="flex min-h-0 flex-col overflow-x-hidden overflow-y-auto overscroll-contain [overflow-wrap:anywhere]"
          >
            {shown.map((q) => {
              const on = q.id === selId;
              const r = REASON[q.reason];
              return (
                <button
                  key={q.id}
                  type="button"
                  aria-pressed={on}
                  onClick={() => select(q.id)}
                  className={cn(
                    "border-t-line-soft text-text flex cursor-pointer flex-col gap-[6px] border-0 border-t border-l-4 border-solid py-[14px] pr-[18px] pl-[14px] text-left",
                    on ? "bg-row-selected border-l-brand" : "bg-surface border-l-transparent",
                  )}
                >
                  <span className="flex w-full items-center justify-between gap-[8px]">
                    <Badge tone={r.tone} size="xs">
                      {r.label}
                    </Badge>
                    <span className="text-text-sub text-[12px]">{q.age}</span>
                  </span>
                  <span className="text-[15px] font-bold">{q.title}</span>
                  <span className="text-text-sub text-[13px]">
                    {q.source} · {statusText(q.id)}
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

        {/* 검수 건을 바꾸면 상세 영역을 통째로 새로 그려요(이전 건의 문단·칸이 남아 보이지 않게) */}
        <div
          key={cur.id}
          className="flex min-w-0 flex-col gap-[16px]"
          style={{ flex: "999 1 600px" }}
        >
          <div className="flex h-[max(560px,calc(100dvh-150px))] flex-col gap-[16px]">
            <section
              aria-label="검수 대상"
              className="rounded-card bg-surface flex shrink-0 flex-wrap items-center justify-between gap-[12px] px-[26px] py-[22px]"
            >
              <div className="flex flex-col gap-[6px]">
                <div className="flex flex-wrap gap-[6px]">
                  <Badge tone={reason.tone} size="md">
                    {reason.label}
                  </Badge>
                  <Badge tone="neutral" size="md" className="font-semibold">
                    {cur.kind}
                  </Badge>
                </div>
                <h2 className="tracking-title m-0 text-[22px] font-extrabold">{cur.title}</h2>
                <span className="text-text-sub text-[14px]">
                  출처 {cur.source} · {cur.version} · 들어온 시각 {cur.received}
                </span>
              </div>
              <a
                href={reviewMeta.get(cur.id)?.detailUrl ?? "#"}
                target="_blank"
                rel="noreferrer"
                className="bg-fill text-text hover:text-text inline-flex min-h-[44px] items-center gap-[6px] rounded-sm px-[14px] text-[14px] font-bold no-underline"
              >
                원문 사이트
                <ExternalLink size={16} aria-hidden />
              </a>
            </section>

            <div className="grid min-h-0 flex-1 auto-rows-[minmax(0,1fr)] grid-cols-[repeat(auto-fit,minmax(320px,1fr))] gap-[16px]">
              <section
                aria-labelledby="src-h"
                className="rounded-card bg-surface box-border flex min-h-0 min-w-0 flex-col gap-[12px] px-[24px] py-[22px]"
              >
                <div className="flex items-center justify-between">
                  <h3 id="src-h" className="m-0 text-[17px] font-extrabold">
                    원문
                  </h3>
                  <span className="text-text-sub inline-flex gap-[10px] text-[12px]">
                    <span className="inline-flex items-center gap-[4px]">
                      <span className="bg-ok-bg size-[10px] rounded-[3px]" aria-hidden />
                      추출
                    </span>
                    <span className="inline-flex items-center gap-[4px]">
                      <span className="bg-check-bg size-[10px] rounded-[3px]" aria-hidden />
                      검수 필요
                    </span>
                  </span>
                </div>
                <div className="-mr-[12px] flex min-h-0 flex-col gap-[12px] overflow-x-hidden overflow-y-auto overscroll-contain pr-[12px] [overflow-wrap:anywhere]">
                  {!ready && cur.id !== "empty" && (
                    <p className="text-text-sub m-0 text-[15px]">
                      {detail.isError
                        ? "원문을 불러오지 못했어요 · 이미 처리된 건일 수 있어요. 새로고침해 주세요"
                        : "원문을 불러오는 중이에요"}
                    </p>
                  )}
                  {cur.paras.map((p) => (
                    <p key={p.head} className="text-text-body-long m-0 text-[15px] leading-[1.85]">
                      <strong className="text-text">{p.head}</strong>{" "}
                      {p.parts.map((s, i) => (
                        <span key={i} className={cn("rounded-[4px]", partStyle[s.kind])}>
                          {s.t}
                        </span>
                      ))}
                    </p>
                  ))}
                </div>
              </section>

              <section
                aria-labelledby="ex-h"
                className="rounded-card bg-surface box-border flex min-h-0 min-w-0 flex-col gap-[12px] px-[24px] py-[22px]"
              >
                <div className="flex items-center justify-between">
                  <h3 id="ex-h" className="m-0 text-[17px] font-extrabold">
                    AI 추출 결과
                  </h3>
                  <span className="text-text-sub text-[13px]">상태</span>
                </div>
                <div className="-mr-[12px] flex min-h-0 flex-col gap-[12px] overflow-x-hidden overflow-y-auto overscroll-contain py-[2px] pr-[12px] [overflow-wrap:anywhere]">
                  {cur.fields.map((f) => {
                    // 신뢰도 숫자 대신 백엔드 칸 상태(보류·확인 필요)로 표시해요
                    const low = f.status ? true : f.conf < 0.7;
                    const value = curEdits[f.label] ?? f.value;
                    // 백엔드가 칸별 수정을 받지 않는 칸(목록·묶음 등)은 읽기만
                    const readOnly = meta ? meta.fields[f.label]?.editable === false : false;
                    return (
                      <label
                        key={f.label}
                        className="grid items-center gap-[10px] text-[14px] font-bold"
                        style={{ gridTemplateColumns: "92px minmax(0, 1fr) 54px" }}
                      >
                        {f.label}
                        <input
                          type="text"
                          value={value}
                          readOnly={readOnly}
                          title={
                            readOnly
                              ? "여기서 고칠 수 없는 칸이에요. 다르면 반려해 주세요"
                              : undefined
                          }
                          onChange={(e) =>
                            setEdits({
                              ...edits,
                              [cur.id]: { ...curEdits, [f.label]: e.target.value },
                            })
                          }
                          className={cn(
                            "text-text box-border min-h-[44px] min-w-0 rounded-sm border-solid px-[12px] text-[15px] font-medium",
                            low
                              ? "border-lowconf-line bg-lowconf-bg border-2"
                              : "border-line bg-surface border",
                          )}
                        />
                        <span
                          className={cn(
                            "text-right text-[13px] font-extrabold",
                            low ? "text-check-text" : "text-text-sub",
                          )}
                        >
                          {f.status === "HELD"
                            ? "보류"
                            : f.status === "CHECK"
                              ? "확인"
                              : f.status === "EMPTY"
                                ? "값 없음"
                                : ""}
                        </span>
                        {f.why && (
                          <span className="text-check-text col-start-2 col-end-4 text-[12px] font-medium">
                            {f.why}
                          </span>
                        )}
                      </label>
                    );
                  })}
                </div>
                <span className="text-text-sub border-line-soft border-t border-solid pt-[10px] text-[13px]">
                  보류: 확인 전까지 회원 화면·판정에 안 보이는 칸 · 확인: 확인이 필요한 칸 · 고친
                  칸은 &apos;수정 후 승인&apos;으로 저장돼요
                </span>
              </section>
            </div>
          </div>

          <section
            aria-label="승인 영향"
            className="bg-brand-soft flex flex-wrap items-center gap-x-[16px] gap-y-[10px] rounded-[20px] px-[20px] py-[16px]"
          >
            <Users size={20} className="text-brand-strong" aria-hidden />
            <span className="text-brand-strong text-[15px]" style={{ flex: "1 1 300px" }}>
              <strong>승인하면</strong> {cur.impact}
            </span>
          </section>

          <section
            aria-label="처리"
            className="rounded-card bg-surface flex flex-col gap-[14px] px-[24px] py-[20px]"
          >
            {error && (
              <div
                role="alert"
                className="rounded-control bg-fill text-text px-[16px] py-[12px] text-[14px] font-bold"
              >
                처리하지 못했어요 · {error}
              </div>
            )}
            {curDone && (
              <div
                role="status"
                className={cn(
                  "rounded-control px-[16px] py-[12px] text-[15px] font-bold",
                  curDone === "ok" ? "bg-ok-bg text-ok-text" : "bg-fill text-text-sub",
                )}
              >
                {curDone === "ok"
                  ? edited
                    ? "수정 후 승인했어요 · 사용자 화면에 반영됐어요"
                    : "승인했어요 · 사용자 화면에 반영됐어요"
                  : "반려했어요 · 다시 수집되면 대기열에 돌아와요"}
              </div>
            )}
            <div className="flex flex-wrap items-center gap-[8px]">
              <button
                type="button"
                onClick={() => finish("ok")}
                disabled={busy || !ready || cur.id === "empty"}
                className="rounded-control bg-brand min-h-[52px] cursor-pointer border-0 px-[22px] text-[16px] font-extrabold text-white"
              >
                {edited ? "수정 후 승인" : "승인"}
              </button>
              <button
                type="button"
                onClick={() => finish("no")}
                disabled={busy || !ready || cur.id === "empty"}
                className="rounded-control bg-fill text-text min-h-[52px] cursor-pointer border-0 px-[20px] text-[15px] font-bold"
              >
                반려
              </button>
              <select
                aria-label="반려 사유"
                value={rejectReason ?? "반려 사유 선택"}
                onChange={(e) => setRejectReason(e.target.selectedIndex ? e.target.value : null)}
                className="rounded-control border-line bg-surface text-text min-h-[52px] border border-solid px-[14px] text-[15px]"
              >
                <option>반려 사유 선택</option>
                {REJECT_REASONS.map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
              <span className="flex-1" />
              <button
                type="button"
                onClick={goNext}
                className="rounded-control text-text-sub inline-flex min-h-[52px] cursor-pointer items-center gap-[4px] border-0 bg-transparent px-[12px] text-[15px] font-bold"
              >
                다음 건
                <ChevronRight size={18} aria-hidden />
              </button>
            </div>
          </section>

          <section
            aria-labelledby="log-h"
            className="rounded-card bg-surface flex flex-col gap-[6px] px-[24px] py-[20px]"
          >
            <h3 id="log-h" className="m-0 mb-[6px] text-[17px] font-extrabold">
              처리 기록
            </h3>
            {cur.log.map((l, i) => (
              <div
                key={`${i}-${l.at}`}
                className="border-line-soft grid gap-[12px] border-t border-solid py-[10px] text-[14px]"
                style={{ gridTemplateColumns: "120px 80px minmax(0, 1fr)" }}
              >
                <span className="text-text-sub">{l.at}</span>
                <span className="font-bold">{l.who}</span>
                <span>{l.text}</span>
              </div>
            ))}
          </section>
        </div>
      </div>
    </>
  );
}
