"use client";

import Link from "next/link";
import { MBackHeader } from "@/components/layout/MBackHeader";
import { MPage } from "@/components/layout/Responsive";
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
      className="text-text hover:text-text flex min-h-[44px] flex-col justify-center text-[15px] leading-[1.5] no-underline"
    >
      <strong>{title}</strong>
      <span className="text-brand-strong text-[13px]">{desc}</span>
    </Link>
  );
}

export function MScore() {
  const { profile, items, total, diff, set } = useScoreCalculator();

  return (
    <MPage>
      <MBackHeader title="청약 가점 계산" backHref={routes.homes} />
      <main className="flex flex-1 flex-col gap-[12px] px-[16px] pt-[16px] pb-[28px]">
        <section
          aria-live="polite"
          className="rounded-card bg-surface flex items-center gap-[18px] px-[20px] py-[22px]"
        >
          <span
            className="rounded-pill flex size-[108px] flex-none items-center justify-center"
            style={ringStyle(total)}
          >
            <span className="rounded-pill bg-surface flex size-[84px] flex-col items-center justify-center">
              <span className="tracking-h1 text-[30px] font-extrabold">{total}</span>
              <span className="text-text-sub text-[12px]">{SCORE_MAX}점 만점</span>
            </span>
          </span>
          <span className="flex flex-col gap-[8px]">
            <span className="text-text-sub text-[14px]">
              {profile.cutoff.label} 예시 {profile.cutoff.score}점
            </span>
            <Badge
              tone={diff >= 0 ? "ok" : "check"}
              className="self-start px-[10px] py-[4px] text-[14px] font-extrabold"
            >
              {diff >= 0 ? `${diff}점 넘어요` : `${-diff}점 부족해요`}
            </Badge>
          </span>
        </section>
        <span className="text-text-sub px-[4px] text-[14px]">
          내 조건으로 미리 채웠어요. 바꿔 보면 점수가 바로 바뀌어요
        </span>
        {items.map((it) => (
          <section
            key={it.key}
            className="rounded-card bg-surface flex flex-col gap-[10px] px-[20px] py-[18px]"
          >
            <div className="flex items-baseline justify-between">
              <span className="text-[17px] font-extrabold">{titles[it.key]}</span>
              <span className="text-text-sub text-[14px]">
                <strong className="text-text text-[20px]">{it.points}</strong> / {it.max}점
              </span>
            </div>
            <span className="bg-brand-soft h-[8px] overflow-hidden rounded-[4px]">
              <span className="bg-brand block h-full rounded-[4px]" style={{ width: it.width }} />
            </span>
            <select
              aria-label={titles[it.key]}
              value={it.index}
              onChange={(e) => set(it.key, Number(e.target.value))}
              className="rounded-control border-line bg-surface text-text min-h-[52px] border border-solid px-[12px] text-[16px]"
            >
              {it.options.map((o, i) => (
                <option key={o.label} value={i}>
                  {o.label}
                </option>
              ))}
            </select>
            <span className="text-text-sub text-[13px] leading-[1.6]">
              {help[it.key]}
              {it.key === "homeless" && ` ${profile.homelessNote}`}
            </span>
          </section>
        ))}
        <section className="rounded-card bg-brand-soft flex flex-col gap-[10px] px-[20px] py-[18px]">
          <span className="text-brand-strong text-[16px] font-extrabold">
            가점이 낮다면 이쪽도 보세요
          </span>
          <AltLink title="공공분양 · 공공임대" desc="납입 횟수·소득으로 정해요" />
          <AltLink title="추첨제 물량 · 특별공급" desc="청년·신혼부부 특별공급은 가점과 따로예요" />
        </section>
        <span className="text-text-sub px-[4px] text-[13px] leading-[1.6]">
          가점제는 주로 <strong className="text-text">민영주택</strong> 청약에 쓰여요. 최종 점수는
          청약홈의 확인 결과를 기준으로 해요.
        </span>
      </main>
    </MPage>
  );
}
