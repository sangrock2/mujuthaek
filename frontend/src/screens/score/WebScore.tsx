"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { WebHeader } from "@/components/layout/WebHeader";
import { WebMain, WebPage } from "@/components/layout/Responsive";
import {
  ScoreFields,
  scoreHelp,
  scoreItemKeys,
  scoreMax,
  ScoreStatus,
  scoreTitles,
} from "@/components/score/ScoreFields";
import { Badge } from "@/components/ui/Badge";
import { ringStyle, SCORE_MAX } from "@/features/score/score";
import { useScoreCalculator } from "@/features/score/useScoreCalculator";
import { routes } from "@/lib/routes";

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
  const calc = useScoreCalculator();
  const { profile, pointsOf, total, diff, score } = calc;

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
            내 조건으로 채울 수 있는 칸은 미리 채웠어요. 날짜를 넣으면 점수를 계산해 드려요
          </span>
        </div>

        <div className="flex flex-wrap items-start gap-[20px]">
          <section
            aria-label="가점 항목"
            className="flex min-w-0 flex-col gap-[12px]"
            style={{ flex: "999 1 560px" }}
          >
            {scoreItemKeys.map((key) => {
              const item = pointsOf(key);
              const max = scoreMax[key];
              const points = item?.points ?? null;
              return (
                <div
                  key={key}
                  className="rounded-card bg-surface flex flex-col gap-[14px] px-[26px] py-[24px]"
                >
                  <div className="flex items-baseline justify-between gap-[12px]">
                    <span className="flex flex-col gap-[2px]">
                      <span className="tracking-title text-[19px] font-extrabold">
                        {scoreTitles[key]}
                      </span>
                      <span className="text-text-sub text-[14px]">최대 {max}점</span>
                    </span>
                    <span className="tracking-h1 text-brand text-[30px] font-extrabold">
                      {points ?? "–"}
                      <span className="text-text text-[16px]">점</span>
                    </span>
                  </div>
                  <ScoreFields item={key} calc={calc} variant="web" />
                  <span className="bg-fill h-[8px] overflow-hidden rounded-[4px]">
                    <span
                      className="bg-brand block h-full rounded-[4px]"
                      style={{ width: `${Math.round(((points ?? 0) / max) * 100)}%` }}
                    />
                  </span>
                  <span className="flex flex-col gap-[2px] text-[14px] leading-[1.6]">
                    {item && <strong>{item.reason}</strong>}
                    <span className="text-text-sub">{scoreHelp[key]}</span>
                  </span>
                </div>
              );
            })}
          </section>

          <aside className="flex min-w-0 flex-col gap-[16px]" style={{ flex: "1 1 340px" }}>
            <section
              aria-label="총점"
              aria-live="polite"
              aria-busy={calc.updating}
              className="rounded-card-lg bg-surface flex flex-col items-center gap-[16px] p-[28px]"
            >
              <div
                className="rounded-pill flex size-[180px] items-center justify-center"
                style={ringStyle(total)}
              >
                <div className="rounded-pill bg-surface flex size-[146px] flex-col items-center justify-center">
                  <span className="text-[48px] leading-none font-extrabold tracking-[-0.05em]">
                    {score ? total : "–"}
                  </span>
                  <span className="text-text-sub text-[15px]">{SCORE_MAX}점 만점</span>
                </div>
              </div>
              <ScoreStatus calc={calc} className="text-center" />
              <div className="rounded-tile bg-bg box-content flex w-full flex-col gap-[6px] px-[16px] py-[14px]">
                <span className="text-text-sub flex justify-between text-[14px]">
                  <span>{profile.cutoff.label}</span>
                  <span>예시</span>
                </span>
                <span className="flex items-center justify-between">
                  <span className="text-[20px] font-extrabold">{profile.cutoff.score}점</span>
                  {score && (
                    <Badge
                      tone={diff >= 0 ? "ok" : "check"}
                      className="px-[10px] py-[4px] text-[14px] font-extrabold"
                    >
                      {diff >= 0 ? `${diff}점 넘어요` : `${-diff}점 부족해요`}
                    </Badge>
                  )}
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
              가점제는 주로 <strong className="text-text">민영주택</strong> 청약에 쓰여요. 오늘
              기준으로 계산했고, 연월만 넣은 칸은 그 달 말일부터 세어 점수를 높게 잡지 않아요(날짜에
              따라 더 높을 수 있으면 항목에 알려요). 최종 점수는 청약홈의 확인 결과를 기준으로 해요.
              넣은 값은 저장하지 않아요.
            </span>
          </aside>
        </div>
      </WebMain>
    </WebPage>
  );
}
