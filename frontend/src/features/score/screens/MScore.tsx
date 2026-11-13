"use client";

import Link from "next/link";
import { MBackHeader } from "@/shared/layout/MBackHeader";
import { MPage } from "@/shared/layout/Responsive";
import {
  ScoreFields,
  scoreHelp,
  scoreItemKeys,
  scoreMax,
  ScoreStatus,
  scoreTitles,
} from "@/features/score/components/ScoreFields";
import { ringStyle, SCORE_MAX } from "@/features/score/score";
import { useScoreCalculator } from "@/features/score/useScoreCalculator";
import { routes } from "@/shared/lib/routes";

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
  const calc = useScoreCalculator();
  const { pointsOf, total, score } = calc;

  return (
    <MPage>
      <MBackHeader title="청약 가점 계산" backHref={routes.homes} />
      <main
        id="main-content"
        tabIndex={-1}
        className="flex flex-1 flex-col gap-[12px] px-[16px] pt-[16px] pb-[28px]"
      >
        <section
          aria-live="polite"
          aria-busy={calc.updating}
          className="rounded-card bg-surface flex items-center gap-[18px] px-[20px] py-[22px]"
        >
          <span
            className="rounded-pill flex size-[108px] flex-none items-center justify-center"
            style={ringStyle(total)}
          >
            <span className="rounded-pill bg-surface flex size-[84px] flex-col items-center justify-center">
              <span className="tracking-h1 text-[30px] font-extrabold">{score ? total : "–"}</span>
              <span className="text-text-sub text-[12px]">{SCORE_MAX}점 만점</span>
            </span>
          </span>
          <span className="flex flex-col gap-[8px]">
            <ScoreStatus calc={calc} />
          </span>
        </section>
        <span className="text-text-sub px-[4px] text-[14px]">
          내 조건으로 채울 수 있는 칸은 미리 채웠어요. 날짜를 넣으면 점수를 계산해 드려요
        </span>
        {scoreItemKeys.map((key) => {
          const item = pointsOf(key);
          const max = scoreMax[key];
          const points = item?.points ?? null;
          return (
            <section
              key={key}
              className="rounded-card bg-surface flex flex-col gap-[10px] px-[20px] py-[18px]"
            >
              <div className="flex items-baseline justify-between">
                <span className="text-[17px] font-extrabold">{scoreTitles[key]}</span>
                <span className="text-text-sub text-[14px]">
                  <strong className="text-text text-[20px]">{points ?? "–"}</strong>
                  {` / ${max}점`}
                </span>
              </div>
              <span className="bg-brand-soft h-[8px] overflow-hidden rounded-[4px]">
                <span
                  className="bg-brand block h-full rounded-[4px]"
                  style={{ width: `${Math.round(((points ?? 0) / max) * 100)}%` }}
                />
              </span>
              <ScoreFields item={key} calc={calc} variant="mobile" />
              <span className="flex flex-col gap-[2px] text-[13px] leading-[1.6]">
                {item && <strong className="text-[14px]">{item.reason}</strong>}
                <span className="text-text-sub">{scoreHelp[key]}</span>
              </span>
            </section>
          );
        })}
        <section className="rounded-card bg-brand-soft flex flex-col gap-[10px] px-[20px] py-[18px]">
          <span className="text-brand-strong text-[16px] font-extrabold">
            가점이 낮다면 이쪽도 보세요
          </span>
          <AltLink title="공공분양 · 공공임대" desc="납입 횟수·소득으로 정해요" />
          <AltLink title="추첨제 물량 · 특별공급" desc="청년·신혼부부 특별공급은 가점과 따로예요" />
        </section>
        <span className="text-text-sub px-[4px] text-[13px] leading-[1.6]">
          가점제는 주로 <strong className="text-text">민영주택</strong> 청약에 쓰여요. 오늘 기준으로
          계산했고, 연월만 넣은 칸은 그 달 말일부터 세어 점수를 높게 잡지 않아요(날짜에 따라 더 높을
          수 있으면 항목에 알려요). 최종 점수는 청약홈의 확인 결과를 기준으로 해요. 넣은 값은
          저장하지 않아요.
        </span>
      </main>
    </MPage>
  );
}
