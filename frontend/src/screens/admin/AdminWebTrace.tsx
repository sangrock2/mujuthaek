"use client";

import { ArrowLeft, Check, ChevronDown, CircleAlert, X } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AdminTitle, AdminTitleRow } from "@/components/admin/AdminShell";
import { Badge } from "@/components/ui/Badge";
import {
  type ExtractionTrace,
  type TraceAgent,
  type TraceTurn,
  useExtractionTrace,
} from "@/features/admin/trace";
import { cn } from "@/lib/cn";

const card = "rounded-card bg-surface flex flex-col gap-[14px] px-[26px] py-[22px]";
const num = (n: number) => n.toLocaleString("ko-KR");
const usd = (n: number) => `$${n < 0.01 ? n.toFixed(4) : n.toFixed(3)}`;
const pct = (part: number, whole: number) => (whole ? `${Math.round((part / whole) * 100)}%` : "–");
const secs = (n: number | null) =>
  n === null
    ? "–"
    : n >= 60
      ? `${Math.floor(n / 60)}분 ${Math.round(n % 60)}초`
      : `${n.toFixed(1)}초`;

/** 도구 이름 → 화면 이름 (넣기 도구는 섹션마다 add_<섹션>) */
function toolLabel(name: string | null) {
  if (!name) return "도구";
  if (name.startsWith("add_")) return `넣기 · ${name.slice(4)}`;
  return (
    {
      update_item: "고치기",
      remove_item: "빼기",
      set_coverage: "범위 적기",
      report_missing: "누락 알리기",
      finish: "끝내기",
    }[name] ?? name
  );
}

/** 관리자 「추출 과정 보기」: 담당 에이전트들이 무엇을 넣고, 무엇이 거절돼 어떻게 고쳤고, 얼마가 들었는지 */
export function AdminWebTrace() {
  const job = useSearchParams().get("job");
  const trace = useExtractionTrace(job);

  return (
    <div className="flex flex-col gap-[20px]">
      <AdminTitleRow>
        <AdminTitle
          title="추출 과정"
          desc="섹션 담당 에이전트가 원문을 읽고 항목을 넣고, 검증 결과를 받아 스스로 고친 기록이에요."
        />
        <Link
          href="/admin/review"
          className="bg-fill text-text hover:text-text inline-flex min-h-[44px] items-center gap-[6px] rounded-sm px-[14px] text-[14px] font-bold no-underline"
        >
          <ArrowLeft size={16} aria-hidden />
          검수로 돌아가기
        </Link>
      </AdminTitleRow>

      {trace.isPending ? (
        <p className="text-text-sub m-0 text-[15px]">불러오는 중이에요…</p>
      ) : trace.isError || !trace.data ? (
        <p className="text-text-sub m-0 text-[15px]">
          추출 과정을 불러오지 못했어요. 작업이 없거나 추출 서버에 연결하지 못했어요.
        </p>
      ) : (
        <TraceBody trace={trace.data} />
      )}
    </div>
  );
}

function TraceBody({ trace }: { trace: ExtractionTrace }) {
  const t = trace.totals;
  const tiles = [
    { label: "비용", value: usd(t.costUsd) },
    { label: "모델 호출", value: `${num(t.calls)}번` },
    { label: "캐시로 읽은 입력", value: pct(t.cachedTokens, t.inputTokens) },
    { label: "걸린 시간", value: secs(trace.totalSeconds) },
  ];
  return (
    <>
      <section aria-label="요약" className={card}>
        <div className="flex flex-wrap items-center gap-[8px]">
          <Badge tone={trace.engine === "V2" ? "ok" : "neutral"} size="md">
            {trace.engine === "V2" ? "V2 섹션 담당 에이전트" : "V1 예전 방식"}
          </Badge>
          <Badge tone="neutral" size="md" className="font-semibold">
            작업 {trace.jobStatus}
          </Badge>
          <span className="text-text-sub text-[13px]">
            작업 ID {trace.jobId}
            {trace.modelUsed && ` · ${trace.modelUsed}`}
          </span>
        </div>
        <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-[10px]">
          {tiles.map((x) => (
            <div
              key={x.label}
              className="bg-bg rounded-tile flex flex-col gap-[4px] px-[16px] py-[14px]"
            >
              <dt className="text-text-sub text-[13px]">{x.label}</dt>
              <dd className="m-0 text-[20px] font-extrabold">{x.value}</dd>
            </div>
          ))}
        </dl>
        {trace.engine === "V1" && (
          <p className="text-text-sub m-0 text-[14px]">
            V2 기록이 없는 작업이에요(예전 방식으로 처리했거나 채팅 모델 없이 처리). 합계만 보여요.
          </p>
        )}
        {trace.stopped.length > 0 && (
          <ul className="text-check-text m-0 flex list-none flex-col gap-[2px] p-0 text-[14px] font-semibold">
            {trace.stopped.map((s, i) => (
              <li key={`${s.agent}-${i}`}>
                멈춘 담당: {s.label} — {s.reason}
              </li>
            ))}
          </ul>
        )}
      </section>

      {trace.byAgent.length > 0 && (
        <section aria-labelledby="cost-h" className={card}>
          <h2 id="cost-h" className="m-0 text-[18px] font-extrabold">
            담당별 호출
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-[14px]">
              <thead>
                <tr className="text-text-sub text-left text-[13px]">
                  {["담당", "호출", "입력 토큰", "캐시 읽기", "출력 토큰", "비용", "시간"].map(
                    (h, i) => (
                      <th
                        key={h}
                        className={cn(
                          "border-line border-b border-solid px-[10px] py-[8px] font-semibold",
                          i > 0 && "text-right",
                        )}
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {trace.byAgent.map((a) => (
                  <tr key={a.agent} className="border-line-soft border-b border-solid">
                    <td className="px-[10px] py-[10px] font-bold">{a.label}</td>
                    <td className="px-[10px] py-[10px] text-right">{num(a.calls)}</td>
                    <td className="px-[10px] py-[10px] text-right">{num(a.inputTokens)}</td>
                    <td className="px-[10px] py-[10px] text-right">
                      {pct(a.cachedTokens, a.inputTokens)}
                    </td>
                    <td className="px-[10px] py-[10px] text-right">{num(a.outputTokens)}</td>
                    <td className="px-[10px] py-[10px] text-right">{usd(a.costUsd)}</td>
                    <td className="px-[10px] py-[10px] text-right">{secs(a.seconds)}</td>
                  </tr>
                ))}
                {trace.v1Calls.calls > 0 && (
                  <tr>
                    <td className="text-text-sub px-[10px] py-[10px]">
                      V1 방식 호출 (그림 판독·끝 단계 재확인)
                    </td>
                    <td className="px-[10px] py-[10px] text-right">{num(trace.v1Calls.calls)}</td>
                    <td colSpan={3} />
                    <td className="px-[10px] py-[10px] text-right">{usd(trace.v1Calls.costUsd)}</td>
                    <td />
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {trace.agents.map((a, i) => (
        <AgentCard key={`${a.agent}-${i}`} agent={a} />
      ))}
    </>
  );
}

function AgentCard({ agent: a }: { agent: TraceAgent }) {
  const partial = Object.entries(a.coverage).filter(([, c]) => c.status !== "EXTRACTED");
  const itemTotal = Object.values(a.items).reduce((s, n) => s + n, 0);
  return (
    <section aria-label={a.label} className={card}>
      <div className="flex flex-wrap items-center justify-between gap-[10px]">
        <h2 className="m-0 text-[18px] font-extrabold">{a.label}</h2>
        <div className="flex flex-wrap gap-[6px]">
          {a.stopped ? (
            <Badge tone="danger" size="sm">
              멈춤
            </Badge>
          ) : a.finished ? (
            <Badge tone="ok" size="sm">
              스스로 끝냄
            </Badge>
          ) : null}
          {itemTotal > 0 && (
            <Badge tone="neutral" size="sm">
              넣은 항목 {num(itemTotal)}
            </Badge>
          )}
          <Badge tone="neutral" size="sm">
            {a.turns.length}차례
          </Badge>
          {a.verifyRounds > 0 && (
            <Badge tone="neutral" size="sm">
              검증 {a.verifyRounds}번
            </Badge>
          )}
          {a.failedResults > 0 && (
            <Badge tone="check" size="sm">
              거절·오류 {a.failedResults}
            </Badge>
          )}
        </div>
      </div>

      {a.stopped && <p className="text-danger-text m-0 text-[14px]">멈춘 이유: {a.stopped}</p>}
      {a.summary && <p className="m-0 text-[15px] leading-[1.6]">{a.summary}</p>}

      {Object.keys(a.tools).length > 0 && (
        <div className="flex flex-wrap gap-[6px] text-[13px]">
          {Object.entries(a.tools).map(([name, n]) => (
            <span key={name} className="bg-bg rounded-tag px-[8px] py-[3px]">
              {toolLabel(name)} {n}
            </span>
          ))}
        </div>
      )}

      {partial.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-[4px] p-0 text-[14px]">
          {partial.map(([section, c]) => (
            <li key={section} className="text-check-text">
              {section}: {c.status}
              {c.reason && ` — ${c.reason}`}
            </li>
          ))}
        </ul>
      )}

      {a.rejected.length > 0 && (
        <details className="rounded-tile border-line-soft border border-solid px-[14px] py-[10px]">
          <summary className="cursor-pointer text-[14px] font-bold">
            넣지 못한 항목 {a.rejected.length}개
          </summary>
          <ul className="m-0 mt-[8px] flex list-none flex-col gap-[6px] p-0 text-[13px]">
            {a.rejected.map((r) => (
              <li key={r.item}>
                <span className="font-bold">{r.item}</span>
                <span className="text-text-sub"> — {r.reasons.join(" · ")}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {a.resolver && (
        <p className="text-text-sub m-0 text-[14px]">
          해결 담당: 경고 {a.resolver.targets ?? 0}개를 대화 {a.resolver.conversations.length}개로
          다시 봄 → 남은 경고 {a.resolver.after ?? 0}개, 채택 {String(a.resolver.adopted ?? 0)}
        </p>
      )}
      {a.tables && a.tables.length > 0 && (
        <p className="text-text-sub m-0 text-[14px]">
          기준표 담당: 묶음 {a.tables.length}개
          {a.tables.some((t) => t.stopped) && " (멈춘 묶음 있음)"}
        </p>
      )}

      {a.turns.length > 0 && <Timeline turns={a.turns} />}
    </section>
  );
}

function Timeline({ turns }: { turns: TraceTurn[] }) {
  return (
    <details className="group">
      <summary className="text-brand-strong inline-flex cursor-pointer list-none items-center gap-[4px] text-[14px] font-bold [&::-webkit-details-marker]:hidden">
        차례별 대화 보기
        <ChevronDown size={16} aria-hidden className="transition-transform group-open:rotate-180" />
      </summary>
      <ol className="m-0 mt-[10px] flex list-none flex-col gap-[10px] p-0">
        {turns.map((turn, i) => (
          <li key={i} className="bg-bg rounded-tile flex flex-col gap-[8px] px-[14px] py-[12px]">
            <span className="text-text-sub text-[12px] font-bold">{i + 1}차례</span>
            {turn.text && <p className="m-0 text-[14px]">{turn.text}</p>}
            {turn.calls.map((c, j) => {
              const r = turn.results[j];
              return (
                <div key={j} className="flex flex-col gap-[4px]">
                  <span className="inline-flex items-center gap-[6px] text-[14px] font-bold">
                    {r ? (
                      r.failed ? (
                        <X size={15} className="text-danger-text" aria-label="거절·오류" />
                      ) : (
                        <Check size={15} className="text-ok-text" aria-label="받아들임" />
                      )
                    ) : null}
                    {toolLabel(c.name)}
                  </span>
                  {c.args && (
                    <code className="bg-surface block overflow-x-auto rounded-sm px-[8px] py-[6px] text-[12px] break-all whitespace-pre-wrap">
                      {c.args}
                    </code>
                  )}
                  {r?.result && (
                    <code
                      className={cn(
                        "block overflow-x-auto rounded-sm px-[8px] py-[6px] text-[12px] break-all whitespace-pre-wrap",
                        r.failed ? "bg-danger-bg" : "bg-surface",
                      )}
                    >
                      {r.result}
                    </code>
                  )}
                </div>
              );
            })}
            {turn.verify && (
              <details>
                <summary className="text-check-text inline-flex cursor-pointer items-center gap-[4px] text-[13px] font-bold">
                  <CircleAlert size={14} aria-hidden />
                  검증 결과 (다음 차례에 고칠 것)
                </summary>
                <pre className="bg-surface m-0 mt-[6px] max-h-[320px] overflow-auto rounded-sm px-[10px] py-[8px] text-[12px] whitespace-pre-wrap">
                  {turn.verify}
                </pre>
              </details>
            )}
          </li>
        ))}
      </ol>
    </details>
  );
}
