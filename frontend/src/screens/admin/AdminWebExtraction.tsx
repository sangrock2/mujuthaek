"use client";

import Link from "next/link";
import { useState } from "react";
import { AdminTitle, AdminTitleRow } from "@/components/admin/AdminShell";
import {
  type ExtractionStats,
  type StatusGroup,
  useExtractionStats,
} from "@/features/admin/extraction-stats";
import { cn } from "@/lib/cn";

const PERIODS = [7, 30, 90];

const num = (n: number) => n.toLocaleString("ko-KR");
// 관리자 「추출 과정」 화면과 같은 달러 표기
const usd = (n: number | null) =>
  n === null ? "–" : `$${n !== 0 && n < 0.01 ? n.toFixed(4) : n.toFixed(3)}`;
const pct = (r: number | null) => (r === null ? "–" : `${Math.round(r * 1000) / 10}%`);
const shortDay = (iso: string) => `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}`;
const when = (iso: string) =>
  new Date(iso).toLocaleString("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

/** 상태 묶음 색: 상태를 나타내는 색이라 이름표와 함께만 써요 */
const GROUP_STYLE: Record<StatusGroup, { bar: string; tag: string }> = {
  AUTO: { bar: "bg-brand", tag: "bg-ok-bg text-ok-text" },
  PARTIAL: { bar: "bg-brand-deep-text-2", tag: "bg-brand-soft text-brand-strong" },
  REVIEW: { bar: "bg-warn-dot", tag: "bg-check-bg text-check-text" },
  FAILED: { bar: "bg-danger-text", tag: "bg-danger-bg text-danger-text" },
  OTHER: { bar: "bg-off", tag: "bg-fill text-text-sub" },
};

/** 관리자 「추출 비용·품질」: 기간별 처리 공고·검수 없이 게시된 비율·공고당 비용·담당별 비용 비중·멈춤·하루 추이 */
export function AdminWebExtraction() {
  const [days, setDays] = useState(30);
  const { data, isPending, isError, isFetching } = useExtractionStats(days);

  return (
    <>
      <AdminTitleRow>
        <AdminTitle
          title="추출 비용·품질"
          desc="공고 추출에 든 비용과, 검수 없이 게시된 비율·담당 에이전트가 멈춘 횟수를 기간별로 봐요"
        />
        <div role="group" aria-label="기간" className="flex flex-wrap gap-[6px]">
          {PERIODS.map((p) => (
            <button
              key={p}
              type="button"
              aria-pressed={days === p}
              onClick={() => setDays(p)}
              className={cn(
                "rounded-pill min-h-[40px] cursor-pointer border-0 px-[16px] text-[14px] font-bold",
                days === p ? "bg-text text-white" : "bg-surface text-text-sub",
              )}
            >
              최근 {p}일
            </button>
          ))}
        </div>
      </AdminTitleRow>

      {isPending && <Empty text="불러오는 중이에요" />}
      {isError && !data && (
        <Empty text="추출 집계를 불러오지 못했어요 · 추출 서비스를 확인해 주세요" />
      )}
      {data && (
        <div className={cn("flex flex-col gap-[20px]", isFetching && "opacity-70")}>
          <Dashboard data={data} />
        </div>
      )}
    </>
  );
}

function Dashboard({ data }: { data: ExtractionStats }) {
  const { statuses, usage } = data;
  const groups = statuses.groups;
  const auto = groups.find((g) => g.group === "AUTO");
  const partial = groups.find((g) => g.group === "PARTIAL");
  const resolverRate = usage.resolver.agents
    ? usage.resolver.adopted / usage.resolver.agents
    : null;

  return (
    <>
      <span className="text-text-sub text-[13px]">
        {data.since} ~ {data.until} (한국 시간) · 처리 작업 {num(data.jobs)}건
      </span>

      <section
        aria-label="요약"
        className="grid gap-[14px]"
        style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}
      >
        <Stat
          label="처리 공고"
          value={`${num(data.notices)}건`}
          note={`다시 처리 포함 작업 ${num(data.jobs)}건`}
        />
        <Stat
          label="검수 없이 게시"
          value={pct(statuses.publishedWithoutReviewRatio)}
          note={`자동 ${num(auto?.notices ?? 0)} · 부분 ${num(partial?.notices ?? 0)}건`}
        />
        <Stat
          label="기간 비용"
          value={usd(data.costUsd)}
          note={`공고당 평균 ${usd(data.costPerNotice.avgUsd)} · 최대 ${usd(data.costPerNotice.maxUsd)}`}
        />
        <Stat
          label="캐시로 읽은 입력"
          value={pct(usage.cachedRatio)}
          note={`입력 ${num(usage.inputTokens)}토큰 중 ${num(usage.cachedTokens)}`}
        />
      </section>

      <Card
        title="상태별 공고"
        desc="공고(원본·버전)마다 기간의 마지막 작업 상태예요. 자동·부분 게시가 검수 없이 게시된 공고예요"
      >
        {data.notices === 0 ? (
          <span className="text-text-sub text-[14px]">이 기간에 처리한 공고가 없어요</span>
        ) : (
          <>
            <div
              className="flex h-[18px] gap-[2px] overflow-hidden rounded-[4px]"
              role="img"
              aria-label={groups.map((g) => `${g.label} ${g.notices}건`).join(", ")}
            >
              {groups
                .filter((g) => g.notices > 0)
                .map((g) => (
                  <div
                    key={g.group}
                    className={cn("h-full", GROUP_STYLE[g.group].bar)}
                    style={{ flexGrow: g.notices, flexBasis: 0 }}
                    title={`${g.label} ${num(g.notices)}건 (${pct(g.ratio)})`}
                  />
                ))}
            </div>
            <ul className="m-0 flex list-none flex-wrap gap-x-[20px] gap-y-[8px] p-0 text-[14px]">
              {groups.map((g) => (
                <li key={g.group} className="flex items-center gap-[8px]">
                  <span
                    aria-hidden
                    className={cn("h-[10px] w-[10px] rounded-[3px]", GROUP_STYLE[g.group].bar)}
                  />
                  <span className="font-semibold">{g.label}</span>
                  <span className="text-text-sub">
                    {num(g.notices)}건 · {pct(g.ratio)} · {usd(g.costUsd)}
                  </span>
                </li>
              ))}
            </ul>
            <span className="text-text-sub text-[13px]">
              상태별:{" "}
              {Object.entries(statuses.byStatus)
                .map(([s, n]) => `${s} ${num(n)}`)
                .join(" · ")}
              . 승인한 공고(APPROVED)는 처음 상태가 남지 않아 「검수로 감」으로 세요.
            </span>
          </>
        )}
      </Card>

      <Grid>
        <Card title="하루 비용" desc="그날 처리한 작업의 비용(달러) 합이에요">
          <DailyBars
            data={data.daily}
            value={(d) => d.costUsd}
            label={(d) => `${d.date} ${usd(d.costUsd)} · 작업 ${num(d.jobs)}건`}
          />
        </Card>
        <Card title="하루 처리 공고" desc="그날 작업이 있었던 공고 수예요">
          <DailyBars
            data={data.daily}
            value={(d) => d.notices}
            label={(d) => `${d.date} 공고 ${num(d.notices)}건 · 작업 ${num(d.jobs)}건`}
          />
        </Card>
      </Grid>

      <Grid>
        <Card
          title="담당별 비용 비중"
          desc="작업 기록의 호출 비용을 담당 에이전트별로 더했어요(받은 응답의 사용량으로 계산)"
        >
          {usage.byAgent.length === 0 ? (
            <span className="text-text-sub text-[14px]">작업 기록이 없어요</span>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-[10px] p-0">
              {usage.byAgent.map((a) => (
                <li key={a.agent} className="flex flex-col gap-[4px]">
                  <div className="flex items-baseline justify-between gap-[12px] text-[14px]">
                    <span className="min-w-0 truncate font-semibold" title={a.label}>
                      {a.label}
                    </span>
                    <span className="text-text-sub flex-none">
                      {pct(a.share)} · {usd(a.costUsd)} · 호출 {num(a.calls)}
                    </span>
                  </div>
                  <Bar share={(a.share ?? 0) * 100} />
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title="멈춤·거절·해결"
          desc="담당이 끝내기 전에 멈춘 횟수와, 넣기가 거절된 횟수, 해결 담당이 고친 결과를 채택한 수예요"
        >
          <div className="flex flex-col gap-[12px]">
            <Row
              label="끝내기 전에 멈춤"
              value={`${num(usage.stops.total)}번`}
              note={`작업 ${num(usage.stops.jobs)}건`}
            />
            <ul className="m-0 flex list-none flex-wrap gap-[6px] p-0">
              {usage.stops.byKind.map((s) => (
                <li
                  key={s.kind}
                  className={cn(
                    "rounded-tag px-[8px] py-[3px] text-[13px] font-bold",
                    s.count > 0 ? "bg-check-bg text-check-text" : "bg-fill text-text-sub",
                  )}
                >
                  {s.label} {num(s.count)}
                </li>
              ))}
            </ul>
            {usage.stops.byAgent.length > 0 && (
              <span className="text-text-sub text-[13px]">
                많이 멈춘 담당:{" "}
                {usage.stops.byAgent
                  .slice(0, 4)
                  .map((s) => `${s.label} ${num(s.count)}`)
                  .join(" · ")}
              </span>
            )}
            <Row
              label="넣기 거절"
              value={`${num(usage.addRejections)}번`}
              note={`끝까지 못 넣은 항목 ${num(usage.rejectedLeft)}개`}
              divided
            />
            <Row
              label="해결 담당 채택"
              value={`${num(usage.resolver.adopted)} / ${num(usage.resolver.agents)}`}
              note={`채택률 ${pct(resolverRate)} · 대화 ${num(usage.resolver.conversations)}번`}
              divided
            />
          </div>
        </Card>
      </Grid>

      <Card
        title="비용이 큰 작업"
        desc="작업 하나의 비용 순이에요. 「추출 과정 보기」에서 담당별 호출·거절을 볼 수 있어요"
      >
        {data.topJobs.length === 0 ? (
          <span className="text-text-sub text-[14px]">유료 호출이 있었던 작업이 없어요</span>
        ) : (
          <ol className="m-0 flex list-none flex-col p-0">
            {data.topJobs.map((j) => (
              <li
                key={j.jobId}
                className="border-b-line-soft flex flex-wrap items-center gap-x-[12px] gap-y-[6px] border-b border-solid py-[12px] text-[14px]"
              >
                <span className="w-[72px] flex-none text-right font-extrabold">
                  {usd(j.costUsd)}
                </span>
                <span
                  className={cn(
                    "rounded-tag flex-none px-[8px] py-[2px] text-[12px] font-extrabold",
                    GROUP_STYLE[j.statusGroup]?.tag ?? GROUP_STYLE.OTHER.tag,
                  )}
                >
                  {j.status}
                </span>
                <span className="min-w-0 flex-1 truncate font-semibold" title={j.title ?? ""}>
                  {j.title ?? "제목 없음"}
                  {j.sourceCode && (
                    <span className="text-text-sub font-medium"> · {j.sourceCode}</span>
                  )}
                </span>
                <span className="text-text-sub flex-none text-[13px]">{when(j.createdAt)}</span>
                <Link
                  href={`/admin/review/trace?job=${encodeURIComponent(j.jobId)}`}
                  className="bg-fill text-text hover:text-text inline-flex min-h-[36px] flex-none items-center rounded-sm px-[12px] text-[13px] font-bold no-underline"
                >
                  추출 과정 보기
                </Link>
              </li>
            ))}
          </ol>
        )}
      </Card>

      <p className="text-text-sub m-0 text-[13px]">
        비용은 예산 기준 추정 달러(응답을 받지 못한 호출은 최악 비용)이고 청구 금액과 다를 수
        있어요. 담당별 비중·캐시·멈춤은 작업 기록 {num(usage.jobs)}건(V2 {num(usage.v2Jobs)}건)에서
        모았어요
        {usage.truncated && ` · 작업이 많아 최근 ${num(usage.limit)}건만 봤어요`}.
      </p>
    </>
  );
}

function DailyBars({
  data,
  value,
  label,
}: {
  data: ExtractionStats["daily"];
  value: (d: ExtractionStats["daily"][number]) => number;
  label: (d: ExtractionStats["daily"][number]) => string;
}) {
  const max = Math.max(...data.map(value), 0);
  if (max === 0) return <span className="text-text-sub text-[14px]">이 기간에는 없어요</span>;
  // 날짜 표시는 처음·가운데·끝만 (90일이면 막대가 가늘어요)
  const marks = new Set([0, Math.floor((data.length - 1) / 2), data.length - 1]);
  return (
    <div className="flex flex-col gap-[6px]">
      <div className="flex h-[120px] items-end gap-[2px]" role="img" aria-label="하루별 막대">
        {data.map((d) => (
          <div key={d.date} className="group flex h-full min-w-0 flex-1 items-end" title={label(d)}>
            <div
              className="bg-brand group-hover:bg-brand-strong w-full rounded-t-[4px]"
              style={{ height: value(d) > 0 ? `${Math.max(3, (value(d) / max) * 100)}%` : 0 }}
            />
          </div>
        ))}
      </div>
      <div className="text-text-sub flex text-[11px]">
        {data.map((d, i) => (
          <span key={d.date} className="min-w-0 flex-1 text-center whitespace-nowrap">
            {marks.has(i) ? shortDay(d.date) : ""}
          </span>
        ))}
      </div>
    </div>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="rounded-card bg-surface flex flex-col gap-[8px] px-[24px] py-[22px]">
      <span className="text-text-sub text-[14px] font-semibold">{label}</span>
      <span className="tracking-h1 text-[32px] font-extrabold">{value}</span>
      <span className="text-text-sub text-[13px]">{note}</span>
    </div>
  );
}

function Row({
  label,
  value,
  note,
  divided,
}: {
  label: string;
  value: string;
  note: string;
  divided?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-baseline justify-between gap-x-[12px]",
        divided && "border-line-soft border-t border-solid pt-[12px]",
      )}
    >
      <span className="text-text-sub text-[15px]">{label}</span>
      <span className="flex items-baseline gap-[8px]">
        <span className="text-text-sub text-[13px]">{note}</span>
        <span className="text-[22px] font-extrabold">{value}</span>
      </span>
    </div>
  );
}

function Card({
  title,
  desc,
  children,
}: {
  title: string;
  desc?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-card bg-surface flex min-w-0 flex-col gap-[14px] px-[24px] py-[22px]">
      <div className="flex flex-col gap-[2px]">
        <h2 className="m-0 text-[17px] font-extrabold">{title}</h2>
        {desc && <span className="text-text-sub text-[13px]">{desc}</span>}
      </div>
      {children}
    </section>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="grid gap-[14px]"
      style={{ gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))" }}
    >
      {children}
    </div>
  );
}

function Bar({ share }: { share: number }) {
  return (
    <div className="bg-fill h-[10px] overflow-hidden rounded-[4px]">
      <div
        className="bg-brand h-full rounded-[4px]"
        style={{ width: `${Math.min(100, share)}%` }}
      />
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="rounded-card bg-surface text-text-sub px-[24px] py-[40px] text-center text-[15px]">
      {text}
    </div>
  );
}
