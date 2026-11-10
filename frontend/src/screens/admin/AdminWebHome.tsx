"use client";

import Link from "next/link";
import { Calendar, ChevronRight, Clock4, Flag, TriangleAlert, type LucideIcon } from "lucide-react";
import { AdminTitle, AdminTitleRow } from "@/components/admin/AdminShell";
import { useAdminMe } from "@/components/admin/AdminGuard";
import { canOpen } from "@/features/admin/permissions";
import { useAdminOverview } from "@/features/admin/queries";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import type { AdminTodoKind } from "@/mocks/admin";

const todoStyle: Record<AdminTodoKind, { icon: LucideIcon; tone: string; href: string }> = {
  deadline: { icon: Clock4, tone: "bg-check-bg text-check-text", href: routes.adminReview },
  source: { icon: TriangleAlert, tone: "bg-danger-bg text-danger-text", href: routes.adminSources },
  report: { icon: Flag, tone: "bg-fill text-text-sub", href: routes.adminReports },
  criteria: { icon: Calendar, tone: "bg-brand-soft text-brand", href: routes.adminCriteria },
};

function StatCard({
  href,
  label,
  value,
  note,
  valueClassName,
  noteClassName,
}: {
  href: string;
  label: string;
  value: string;
  note: string;
  valueClassName?: string;
  noteClassName?: string;
}) {
  return (
    <Link
      href={href}
      className="rounded-card bg-surface text-text hover:text-text flex flex-col gap-[8px] px-[24px] py-[22px] no-underline"
    >
      <span className="text-text-sub text-[14px] font-semibold">{label}</span>
      <span className={cn("tracking-h1 text-[34px] font-extrabold", valueClassName)}>{value}</span>
      <span className={cn("text-text-sub text-[13px]", noteClassName)}>{note}</span>
    </Link>
  );
}

function QualityRow({
  label,
  value,
  divided,
}: {
  label: string;
  value: string;
  divided?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-baseline justify-between",
        divided && "border-line-soft border-t border-solid pt-[12px]",
      )}
    >
      <span className="text-text-sub text-[15px]">{label}</span>
      <span className="text-[22px] font-extrabold">{value}</span>
    </div>
  );
}

export function AdminWebHome() {
  const { data } = useAdminOverview();
  // 받은 권한의 화면 숫자만 보여 줘요 (권한이 없는 숫자는 서버가 막아서 0처럼 보이면 안 돼요)
  const permissions = useAdminMe().data?.permissions ?? [];
  const can = (href: string) => canOpen(permissions, href);
  const cards = [
    {
      href: routes.adminReview,
      label: "검수 대기",
      value: data.review.count == null ? "-" : `${data.review.count}건`,
      note:
        data.review.count == null ? data.review.oldest : `가장 오래된 건 ${data.review.oldest} 째`,
      noteClassName: "text-check-text font-bold",
    },
    {
      href: routes.adminSources,
      label: "오늘 수집",
      value: data.collected.count == null ? "-" : `${data.collected.count}건`,
      note: data.collected.note,
    },
    {
      href: routes.adminSources,
      label: "수집 이상",
      value: data.issues.count == null ? "-" : `${data.issues.count}곳`,
      note: data.issues.note,
      valueClassName: "text-danger-text",
    },
    {
      href: routes.adminReports,
      label: "새 제보",
      value: data.reports.count == null ? "-" : `${data.reports.count}건`,
      note: data.reports.note,
    },
  ].filter((c) => can(c.href));
  const todos = data.todos.filter((t) => can(todoStyle[t.kind].href));
  const seesReview = can(routes.adminReview);

  return (
    <>
      <AdminTitleRow>
        <AdminTitle title="오늘 운영 현황" desc={`${data.asOf} 기준`} />
      </AdminTitleRow>

      <section
        aria-label="요약"
        className="grid gap-[14px]"
        style={{ gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))" }}
      >
        {cards.map((c) => (
          <StatCard key={c.label} {...c} />
        ))}
      </section>

      {cards.length === 0 && todos.length === 0 && !seesReview && (
        <section className="rounded-card bg-surface flex flex-col gap-[6px] px-[24px] py-[22px]">
          <h2 className="m-0 text-[18px] font-extrabold">개요에서 볼 숫자가 없어요</h2>
          <span className="text-text-sub text-[15px]">
            개요는 검수·수집 출처·제보 권한이 있어야 보여요. 받은 권한의 메뉴는 왼쪽에 있어요.
          </span>
        </section>
      )}

      <div className="flex flex-wrap items-start gap-[20px]">
        {todos.length > 0 && (
          <section
            aria-labelledby="todo-h"
            className="rounded-card-lg bg-surface box-content flex min-w-0 flex-col gap-[6px] px-[28px] py-[26px]"
            style={{ flex: "999 1 480px" }}
          >
            <h2 id="todo-h" className="tracking-title m-0 mb-[8px] text-[20px] font-extrabold">
              지금 처리할 일
            </h2>
            {todos.map((todo, i) => {
              const { icon: Icon, tone, href } = todoStyle[todo.kind];
              const last = i === todos.length - 1;
              return (
                <Link
                  key={todo.id}
                  href={href}
                  className={cn(
                    "text-text hover:text-text flex items-center gap-[14px] no-underline",
                    last ? "pt-[14px]" : "border-line-soft border-b border-solid py-[14px]",
                  )}
                >
                  <span
                    className={cn(
                      "flex size-[40px] flex-none items-center justify-center rounded-sm",
                      tone,
                    )}
                  >
                    <Icon size={20} aria-hidden />
                  </span>
                  <span className="flex flex-1 flex-col gap-[3px]">
                    <span className="text-[16px] font-bold">{todo.title}</span>
                    <span className="text-text-sub text-[14px]">{todo.desc}</span>
                  </span>
                  <ChevronRight size={18} className="text-text-tertiary" aria-hidden />
                </Link>
              );
            })}
          </section>
        )}

        {seesReview && (
          <div className="flex min-w-0 flex-col gap-[16px]" style={{ flex: "1 1 300px" }}>
            <section
              aria-labelledby="q-h"
              className="rounded-card-lg bg-surface flex flex-col gap-[14px] p-[24px]"
            >
              <h2 id="q-h" className="m-0 text-[18px] font-extrabold tracking-[-0.02em]">
                판정 품질 · 최근 7일
              </h2>
              <QualityRow label="AI 추출 그대로 승인" value={data.quality.asIs} />
              <QualityRow label="수정 후 승인" value={data.quality.edited} />
              <QualityRow label="반려" value={data.quality.rejected} />
              <QualityRow
                label="검수까지 걸린 시간 (중간값)"
                value={data.quality.medianTime}
                divided
              />
              <QualityRow label="제보로 고친 값" value={data.quality.fixedByReport} />
            </section>
            <section
              aria-labelledby="t-h"
              className="rounded-card-lg bg-surface flex flex-col gap-[10px] p-[24px]"
            >
              <h2 id="t-h" className="m-0 text-[18px] font-extrabold tracking-[-0.02em]">
                오늘 처리
              </h2>
              <span className="text-text-sub text-[15px]">
                승인 <strong className="text-text">{data.today.approved ?? "-"}</strong> · 수정 후
                승인 <strong className="text-text">{data.today.editedApproved ?? "-"}</strong> ·
                반려 <strong className="text-text">{data.today.rejected ?? "-"}</strong> · 제보 답변{" "}
                <strong className="text-text">{data.today.replied ?? "-"}</strong>
              </span>
            </section>
          </div>
        )}
      </div>
    </>
  );
}
