"use client";

import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { AdminTitleRow } from "@/components/admin/AdminShell";
import { decidePolicyDuplicate } from "@/features/admin/api";
import { useAdminPolicyDuplicates, useSetAdminCounts } from "@/features/admin/queries";
import { USE_MOCKS } from "@/lib/api/config";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import type { DuplicateItem, DuplicateSide, DuplicateStatus } from "@/mocks/admin-duplicates";

const TABS: { key: DuplicateStatus; label: string; count: "pending" | "keptBoth" | "hidden" }[] = [
  { key: "PENDING", label: "확인 전", count: "pending" },
  { key: "KEPT_BOTH", label: "둘 다 둠", count: "keptBoth" },
  { key: "HIDDEN", label: "나중 것 숨김", count: "hidden" },
];

const FIELD: Record<DuplicateSide["field"], string> = {
  STARTUP_SUPPORT: "사업 지원",
  SPACE_RECRUITMENT: "입주 모집",
};

const when = (iso: string) =>
  new Date(iso).toLocaleString("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

const day = (iso: string | null) => (iso ? iso.slice(5).replace("-", ".") : null);

/** 우리 서비스 상세 주소 (사업 지원 · 입주 모집) */
const hrefOf = (s: DuplicateSide) =>
  s.field === "STARTUP_SUPPORT" ? `${routes.bizSupport}/${s.id}` : routes.space(s.id);

const keyOf = (d: DuplicateItem) => `${d.later.id}:${d.earlier.id}`;

/** 제보·신고의 「중복 의심」 갈래. head: 제목 줄 왼쪽 */
export function AdminWebPolicyDuplicates({ head }: { head: React.ReactNode }) {
  const [tab, setTab] = useState<DuplicateStatus>("PENDING");
  const { data, isPending, isError } = useAdminPolicyDuplicates(tab);
  const [done, setDone] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const setCounts = useSetAdminCounts();
  const items = (data?.items ?? []).filter((d) => !done[keyOf(d)]);

  const decide = async (d: DuplicateItem, action: "KEEP_BOTH" | "HIDE_LATER") => {
    setBusy(keyOf(d));
    setError(null);
    try {
      if (!USE_MOCKS) await decidePolicyDuplicate(d.later.id, d.earlier.id, action);
      setDone({ ...done, [keyOf(d)]: action });
      setCounts({ policyDuplicates: Math.max(0, items.length - 1) });
      if (!USE_MOCKS) {
        void queryClient.invalidateQueries({ queryKey: ["admin", "live", "policy-duplicates"] });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <AdminTitleRow>
        {head}
        <div role="group" aria-label="처리 상태" className="flex flex-wrap gap-[6px]">
          {TABS.map((t) => {
            const on = t.key === tab;
            return (
              <button
                key={t.key}
                type="button"
                aria-pressed={on}
                onClick={() => {
                  setTab(t.key);
                  setDone({});
                }}
                className={cn(
                  "rounded-pill min-h-[40px] cursor-pointer border-0 px-[16px] text-[14px] font-bold",
                  on ? "bg-text text-white" : "bg-surface text-text-sub",
                )}
              >
                {t.label} {data?.counts[t.count] ?? ""}
              </button>
            );
          })}
        </div>
      </AdminTitleRow>

      {error && (
        <div
          role="alert"
          className="rounded-control bg-danger-bg text-danger-text px-[16px] py-[12px] text-[14px] font-bold"
        >
          처리하지 못했어요 · {error}
        </div>
      )}
      {isPending && <span className="text-text-sub text-[15px]">불러오는 중이에요</span>}
      {isError && (
        <span className="text-text-sub text-[15px]">중복 의심 목록을 불러오지 못했어요</span>
      )}
      {data && items.length === 0 && (
        <div className="rounded-card bg-surface text-text-sub px-[24px] py-[48px] text-center text-[15px]">
          이 상태의 중복 의심이 없어요
        </div>
      )}

      {/* 화면 높이에 고정하고 칸 안에서 스크롤해요(검수·정보 제보와 같은 방식). 건수가 적어 한 번에 받아요 */}
      <div className="flex h-[max(560px,calc(100dvh-210px))] flex-col gap-[16px] overflow-y-auto overscroll-contain">
        {items.map((d) => (
          <section
            key={keyOf(d)}
            aria-label={`중복 의심: ${d.later.title}`}
            className="rounded-card bg-surface flex flex-col gap-[14px] px-[24px] py-[20px]"
          >
            <div className="text-text-sub flex flex-wrap items-center gap-x-[10px] text-[13px]">
              <span className="rounded-tag bg-check-bg text-check-text px-[8px] py-[2px] font-extrabold">
                {FIELD[d.later.field]}
              </span>
              <span>같은 분야 · 같은 이름 · 같은 지역</span>
              <span>· 올라온 때 {when(d.createdAt)}</span>
              {d.decidedAt && <span>· 처리 {when(d.decidedAt)}</span>}
            </div>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-[12px]">
              <SideCard label="먼저 있던 사업" side={d.earlier} />
              <SideCard label="나중에 들어온 사업" side={d.later} strong />
            </div>
            {d.status === "PENDING" && (
              <div className="border-line-soft flex flex-wrap items-center gap-[10px] border-t border-solid pt-[14px]">
                <span className="text-text-sub flex-1 text-[13px]">
                  같은 사업이면 나중 것을 숨겨요 (사업 목록·판정·알림에서 빠지고 먼저 있던 사업만
                  보여요). 다른 사업이면 둘 다 둬요
                </span>
                <button
                  type="button"
                  disabled={busy === keyOf(d)}
                  onClick={() => decide(d, "KEEP_BOTH")}
                  className="rounded-control bg-fill text-text min-h-[48px] cursor-pointer border-0 px-[18px] text-[15px] font-bold"
                >
                  다른 사업이라 둘 다 둠
                </button>
                <button
                  type="button"
                  disabled={busy === keyOf(d)}
                  onClick={() => decide(d, "HIDE_LATER")}
                  className="rounded-control bg-brand min-h-[48px] cursor-pointer border-0 px-[18px] text-[15px] font-extrabold text-white"
                >
                  같은 사업이라 나중 것 숨김
                </button>
              </div>
            )}
          </section>
        ))}
      </div>
    </>
  );
}

function SideCard({
  label,
  side,
  strong,
}: {
  label: string;
  side: DuplicateSide;
  strong?: boolean;
}) {
  const period = [day(side.applyStart), day(side.applyEnd)].filter(Boolean).join(" ~ ");
  return (
    <div
      className={cn(
        "rounded-control flex min-w-0 flex-col gap-[6px] border border-solid px-[16px] py-[14px]",
        strong ? "border-check-text" : "border-line",
      )}
    >
      <span className="text-text-sub text-[12px] font-bold">
        {label} · 받은 때 {when(side.createdAt)}
        {side.hidden && " · 숨김"}
      </span>
      <span className="text-[16px] font-extrabold">{side.title}</span>
      <span className="text-text-sub text-[13px]">
        {[
          side.organization,
          period ? `접수 ${period}` : null,
          side.regionCodes.length ? `지역 ${side.regionCodes.length}곳` : "전국",
        ]
          .filter(Boolean)
          .join(" · ")}
      </span>
      <div className="flex flex-wrap gap-[12px] pt-[2px] text-[13px] font-bold">
        <a
          href={hrefOf(side)}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-[4px]"
        >
          서비스 화면 <ExternalLink size={13} aria-hidden />
        </a>
        {side.detailUrl && (
          <a
            href={side.detailUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-[4px]"
          >
            출처 원문 <ExternalLink size={13} aria-hidden />
          </a>
        )}
      </div>
    </div>
  );
}
