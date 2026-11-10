"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { WebHeader } from "@/components/layout/WebHeader";
import { WebMain, WebPage } from "@/components/layout/Responsive";
import { Badge } from "@/components/ui/Badge";
import { ringStyle, SCORE_MAX, type ScoreItemKey } from "@/features/score/score";
import { useScoreCalculator } from "@/features/score/useScoreCalculator";
import { routes } from "@/lib/routes";

const titles: Record<ScoreItemKey, string> = {
  homeless: "무주택 기간",
  dependents: "부양가족 수",
  account: "청약통장 가입 기간",
};

const help: Record<ScoreItemKey, string> = {
  homeless: "만 30세부터 세요. 그 전에 혼인했다면 혼인신고일부터 세요.",
  dependents: "나를 뺀 세대원 수예요. 직계존속은 3년 이상 같은 등본에 있어야 인정돼요.",
  account: "주택청약종합저축에 처음 가입한 날부터 세요.",
};

function AltLink({ title, desc }: { title: string; desc: string }) {
  return (
    <Link
      href={routes.homes}
      className="rounded-control bg-surface text-text hover:text-text flex items-center justify-between gap-[8px] px-[14px] py-[12px] no-underline"
    >
      <span className="flex flex-col gap-[2px]">
        <span className="text-[15px] font-bold">{title}</span>
        <span className="text-text-sub text-[13px]">{desc}</span>
      </span>
      <ChevronRight size={18} className="text-text-sub flex-none" aria-hidden />
    </Link>
  );
}

export function WebScore() {
  const { profile, items, total, diff, set } = useScoreCalculator();

  return (
    <WebPage>
      <WebHeader mode="home" current={routes.homes} />
      <WebMain className="gap-[20px] pt-[24px]">
        <nav
          aria-label="위치"
          className="text-text-tertiary flex items-center gap-[4px] text-[14px]"
        >
          <Link
            href={routes.homes}
            className="text-text-sub hover:text-text-sub inline-flex min-h-[36px] items-center font-semibold no-underline"
          >
            내 집
          </Link>
          <ChevronRight size={16} aria-hidden />
          <span aria-current="page">청약 가점 계산</span>
        </nav>
        <div className="flex flex-col gap-[6px]">
          <h1 className="tracking-h1 m-0 text-[32px] font-extrabold">청약 가점 계산</h1>
          <span className="text-text-sub text-[16px]">
            내 조건으로 미리 채웠어요. 바꿔 보면 점수가 바로 바뀌어요
          </span>
        </div>

        <div className="flex flex-wrap items-start gap-[20px]">
          <section
            aria-label="가점 항목"
            className="flex min-w-0 flex-col gap-[12px]"
            style={{ flex: "999 1 560px" }}
          >
            {items.map((it) => (
              <div
                key={it.key}
                className="rounded-card bg-surface flex flex-col gap-[14px] px-[26px] py-[24px]"
              >
                <div className="flex items-baseline justify-between gap-[12px]">
                  <span className="flex flex-col gap-[2px]">
                    <span className="tracking-title text-[19px] font-extrabold">
                      {titles[it.key]}
                    </span>
                    <span className="text-text-sub text-[14px]">최대 {it.max}점</span>
                  </span>
                  <span className="tracking-h1 text-brand text-[30px] font-extrabold">
                    {it.points}
                    <span className="text-text text-[16px]">점</span>
                  </span>
                </div>
                <select
                  aria-label={titles[it.key]}
                  value={it.index}
                  onChange={(e) => set(it.key, Number(e.target.value))}
                  className="rounded-control border-line bg-surface text-text min-h-[54px] border border-solid px-[14px] text-[16px] font-semibold"
                >
                  {it.options.map((o, i) => (
                    <option key={o.label} value={i}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <span className="bg-fill h-[8px] overflow-hidden rounded-[4px]">
                  <span
                    className="bg-brand block h-full rounded-[4px]"
                    style={{ width: it.width }}
                  />
                </span>
                <span className="text-text-sub text-[14px] leading-[1.6]">
                  {help[it.key]}
                  {it.key === "homeless" && ` ${profile.homelessNote}`}
                </span>
              </div>
            ))}
          </section>

          <aside className="flex min-w-0 flex-col gap-[16px]" style={{ flex: "1 1 340px" }}>
            <section
              aria-label="총점"
              aria-live="polite"
              className="rounded-card-lg bg-surface flex flex-col items-center gap-[16px] p-[28px]"
            >
              <div
                className="rounded-pill flex size-[180px] items-center justify-center"
                style={ringStyle(total)}
              >
                <div className="rounded-pill bg-surface flex size-[146px] flex-col items-center justify-center">
                  <span className="text-[48px] leading-none font-extrabold tracking-[-0.05em]">
                    {total}
                  </span>
                  <span className="text-text-sub text-[15px]">{SCORE_MAX}점 만점</span>
                </div>
              </div>
              <div className="rounded-tile bg-bg box-content flex w-full flex-col gap-[6px] px-[16px] py-[14px]">
                <span className="text-text-sub flex justify-between text-[14px]">
                  <span>{profile.cutoff.label}</span>
                  <span>예시</span>
                </span>
                <span className="flex items-center justify-between">
                  <span className="text-[20px] font-extrabold">{profile.cutoff.score}점</span>
                  <Badge
                    tone={diff >= 0 ? "ok" : "check"}
                    className="px-[10px] py-[4px] text-[14px] font-extrabold"
                  >
                    {diff >= 0 ? `${diff}점 넘어요` : `${-diff}점 부족해요`}
                  </Badge>
                </span>
              </div>
            </section>

            <section
              aria-label="가점이 낮다면"
              className="rounded-card bg-brand-soft flex flex-col gap-[10px] px-[24px] py-[22px]"
            >
              <span className="text-brand-strong text-[17px] font-extrabold">
                가점이 낮다면 이쪽도 보세요
              </span>
              <AltLink title="공공분양 · 공공임대" desc="가점이 아니라 납입 횟수·소득으로 정해요" />
              <AltLink
                title="추첨제 물량 · 특별공급"
                desc="청년·신혼부부 특별공급은 가점과 따로예요"
              />
            </section>

            <span className="text-text-sub px-[4px] text-[13px] leading-[1.6]">
              가점제는 주로 <strong className="text-text">민영주택</strong> 청약에 쓰여요. 최종
              점수는 청약홈의 확인 결과를 기준으로 해요.
            </span>
          </aside>
        </div>
      </WebMain>
    </WebPage>
  );
}
