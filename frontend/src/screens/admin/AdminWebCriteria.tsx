"use client";

import { useState } from "react";
import { AdminTitle, AdminTitleRow } from "@/components/admin/AdminShell";
import { scheduleMedianIncome } from "@/features/admin/api";
import { useAdminCriteria, useSetAdminCounts } from "@/features/admin/queries";
import { cn } from "@/lib/cn";
import { USE_MOCKS } from "@/lib/api/config";

type Tab = "income" | "score" | "region";

const TABS: { key: Tab; label: string }[] = [
  { key: "income", label: "기준중위소득" },
  { key: "score", label: "청약 가점표" },
  { key: "region", label: "지역 구분" },
];

// 올해 값은 적용 중, 다음 해 값은 고시가 나오면 미리 넣어 둬요
const THIS_YEAR = new Date().getFullYear();
const YEARS = [
  { y: THIS_YEAR, label: `${THIS_YEAR} · 적용 중` },
  { y: THIS_YEAR + 1, label: `${THIS_YEAR + 1} · 미리 입력` },
];

const won = (v: number) => new Intl.NumberFormat("ko-KR").format(Math.round(v));

const th = "border-line border-b border-solid px-[8px] py-[10px] font-bold";
const td = "border-line-soft border-b border-solid px-[8px] py-[12px] text-right";

function IncomePanel() {
  const { data } = useAdminCriteria();
  const [year, setYear] = useState(THIS_YEAR);
  const [note, setNote] = useState<string | null>(null);
  const setCounts = useSetAdminCounts();
  // 2027년 고시값을 「적용 예약」으로 실제 기준값 API에 넣어요
  const schedule = async (form: HTMLElement | null) => {
    if (USE_MOCKS || !form) return;
    const inputs = [...form.querySelectorAll<HTMLInputElement>("input[data-household]")];
    const monthly: Record<string, number> = {};
    for (const i of inputs) {
      const v = Number(i.value.replace(/[^0-9]/g, ""));
      if (v > 0) monthly[i.dataset.household as string] = v;
    }
    if (!monthly["1"]) {
      setNote("1인 가구 값부터 넣어 주세요");
      return;
    }
    try {
      await scheduleMedianIncome(year, monthly, "관리자 화면 입력");
      setNote(`${year}년 값을 예약했어요 · ${year}년 1월 1일 0시부터 판정에 쓰여요`);
      setCounts({});
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="flex flex-wrap items-start gap-[20px]">
      <section
        aria-labelledby="inc-h"
        className="rounded-card-lg bg-surface box-content flex min-w-0 flex-col gap-[16px] px-[28px] py-[26px]"
        style={{ flex: "999 1 560px" }}
      >
        <div className="flex flex-wrap items-center justify-between gap-[12px]">
          <div className="flex flex-col gap-[4px]">
            <h2 id="inc-h" className="tracking-title m-0 text-[21px] font-extrabold">
              기준중위소득 (월)
            </h2>
            <span className="text-text-sub text-[14px]">
              보건복지부 고시 · 매년 1월 1일 바뀌어요
            </span>
          </div>
          <div role="group" aria-label="연도" className="bg-fill flex rounded-sm p-[4px]">
            {YEARS.map((y) => {
              const on = y.y === year;
              return (
                <button
                  key={y.y}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setYear(y.y)}
                  className={cn(
                    "min-h-[38px] cursor-pointer rounded-[9px] border-0 px-[14px] text-[14px] font-bold",
                    on ? "bg-surface text-text shadow-seg" : "text-text-sub bg-transparent",
                  )}
                >
                  {y.label}
                </button>
              );
            })}
          </div>
        </div>

        {year === 2026 ? (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] border-collapse text-[15px]">
                <thead>
                  <tr className="text-text-sub text-[13px]">
                    <th scope="col" className={cn(th, "text-left")}>
                      가구원 수
                    </th>
                    {["100%", "60%", "120%", "150%"].map((h) => (
                      <th key={h} scope="col" className={cn(th, "text-right")}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.incomeBase.map((v, i) => (
                    <tr key={i}>
                      <th
                        scope="row"
                        className="border-line-soft border-b border-solid px-[8px] py-[12px] text-left font-bold"
                      >
                        {i + 1}인
                      </th>
                      <td className={cn(td, "font-extrabold")}>{won(v)}</td>
                      <td className={cn(td, "text-text-sub")}>{won(v * 0.6)}</td>
                      <td className={cn(td, "text-text-sub")}>{won(v * 1.2)}</td>
                      <td className={cn(td, "text-text-sub")}>{won(v * 1.5)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <span className="text-text-sub text-[13px]">
              단위 원 · 비율 칸은 100% 값으로 자동 계산 · 7인 이상은 고시 산식으로 계산
            </span>
          </>
        ) : (
          <>
            <div className="rounded-tile bg-check-bg text-check-text px-[16px] py-[14px] text-[15px] font-bold">
              {note ?? `고시값을 입력하면 ${year}년 1월 1일 0시부터 적용돼요`}
            </div>
            <div
              className="grid gap-[12px]"
              style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}
            >
              {data.incomeBase.map((_, i) => (
                <label key={i} className="flex flex-col gap-[6px] text-[14px] font-bold">
                  {i + 1}인 가구 (100%)
                  <span className="relative flex">
                    <input
                      type="text"
                      inputMode="numeric"
                      data-household={i + 1}
                      placeholder="고시값 입력"
                      className="border-line text-text min-h-[50px] min-w-0 flex-1 rounded-sm border border-solid pr-[40px] pl-[14px] text-[16px]"
                    />
                    <span className="text-text-sub absolute top-1/2 right-[14px] -translate-y-1/2 text-[15px]">
                      원
                    </span>
                  </span>
                </label>
              ))}
            </div>
            <div className="flex flex-wrap gap-[8px]">
              <button
                type="button"
                onClick={(e) => schedule(e.currentTarget.closest("section"))}
                className="rounded-control bg-brand min-h-[50px] cursor-pointer border-0 px-[20px] text-[15px] font-extrabold text-white"
              >
                적용 예약
              </button>
              <button
                type="button"
                className="rounded-control bg-fill text-text min-h-[50px] cursor-pointer border-0 px-[18px] text-[15px] font-bold"
              >
                바뀌는 판정 미리 보기
              </button>
            </div>
          </>
        )}
      </section>

      <div className="flex min-w-0 flex-col gap-[16px]" style={{ flex: "1 1 300px" }}>
        <section
          aria-labelledby="use-h"
          className="rounded-card-lg bg-surface flex flex-col gap-[10px] p-[24px]"
        >
          <h2 id="use-h" className="m-0 text-[18px] font-extrabold">
            이 값을 쓰는 판정 틀 {data.rulesCount}개
          </h2>
          {data.rules.map((r) => (
            <span
              key={r.name}
              className="border-line-soft flex justify-between border-b border-solid py-[8px] text-[14px]"
            >
              <span>{r.name}</span>
              <span className="text-text-sub">{r.ratio}</span>
            </span>
          ))}
          {/* 실제 API는 목록을 다 주므로 「더 보기」 없음 */}
          {USE_MOCKS && (
            <a
              href="#"
              className="inline-flex min-h-[44px] items-center text-[14px] font-bold no-underline"
            >
              {data.rulesCount - data.rules.length}개 더 보기
            </a>
          )}
        </section>
        <section
          aria-labelledby="his-h"
          className="rounded-card-lg bg-surface flex flex-col gap-[8px] p-[24px]"
        >
          <h2 id="his-h" className="m-0 mb-[4px] text-[18px] font-extrabold">
            바꾼 기록
          </h2>
          {data.history.map((h, i) => (
            <span
              key={`${i}-${h.title}`}
              className={cn(
                "flex flex-col gap-[2px] py-[8px] text-[14px]",
                i < data.history.length - 1 && "border-line-soft border-b border-solid",
              )}
            >
              <span className="font-bold">{h.title}</span>
              <span className="text-text-sub">{h.meta}</span>
            </span>
          ))}
        </section>
      </div>
    </div>
  );
}

function ScorePanel() {
  const { data } = useAdminCriteria();
  return (
    <section
      aria-labelledby="sc-h"
      className="rounded-card-lg bg-surface flex flex-col gap-[18px] px-[28px] py-[26px]"
    >
      <div className="flex flex-col gap-[4px]">
        <h2 id="sc-h" className="tracking-title m-0 text-[21px] font-extrabold">
          청약 가점표 · 만점 {data.score.max}점
        </h2>
        <span className="text-text-sub text-[14px]">
          주택공급에 관한 규칙 별표 1 · 청약 가점은 이 기준으로 계산해요
        </span>
      </div>
      <div
        className="grid gap-[14px]"
        style={{ gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}
      >
        {data.score.items.map((it) => (
          <div key={it.name} className="bg-bg flex flex-col gap-[8px] rounded-[20px] p-[20px]">
            <span className="text-[15px] font-extrabold">{it.name}</span>
            <span className="text-brand-strong text-[30px] font-extrabold">{it.max}점</span>
            <span className="text-text-sub text-[14px] leading-[1.6]">{it.rule}</span>
          </div>
        ))}
      </div>
      <span className="text-text-sub text-[14px]">
        기준 {data.score.lastChecked} · 여기서는 볼 수만 있어요. 법령이 바뀌면 개발팀이 반영해요
      </span>
    </section>
  );
}

function RegionPanel() {
  const { data } = useAdminCriteria();
  return (
    <section
      aria-labelledby="rg-h"
      className="rounded-card-lg bg-surface flex flex-col gap-[6px] px-[28px] py-[26px]"
    >
      <div className="mb-[10px] flex flex-col gap-[4px]">
        <h2 id="rg-h" className="tracking-title m-0 text-[21px] font-extrabold">
          수도권 과밀억제권역
        </h2>
        <span className="text-text-sub text-[14px]">
          수도권정비계획법 · 청년 창업 세액감면 비율(50% · 100%)을 가르는 기준이에요
        </span>
      </div>
      {data.regions.map((r, i) => (
        <div
          key={r.name}
          className={cn(
            "grid gap-[12px] py-[14px] text-[15px]",
            i < data.regions.length - 1 && "border-line-soft border-b border-solid",
          )}
          style={{ gridTemplateColumns: "140px minmax(0, 1fr)" }}
        >
          <span className="font-bold">{r.name}</span>
          <span>{r.scope}</span>
        </div>
      ))}
      <span className="text-text-sub pt-[8px] text-[13px]">
        참고용 목록이에요 · 판정에는 쓰지 않고, 여기서 바꿀 수 없어요
      </span>
    </section>
  );
}

export function AdminWebCriteria() {
  const [tab, setTab] = useState<Tab>("income");

  return (
    <>
      <AdminTitleRow>
        <AdminTitle
          title="기준값"
          desc="여러 공고·정책이 함께 쓰는 값이에요 · 바꾸면 이 값을 쓰는 판정이 한꺼번에 다시 계산돼요"
        />
        <div
          role="tablist"
          aria-label="기준값 종류"
          className="rounded-control bg-surface flex p-[4px]"
        >
          {TABS.map((t) => {
            const on = t.key === tab;
            return (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={on}
                onClick={() => setTab(t.key)}
                className={cn(
                  "min-h-[42px] cursor-pointer rounded-[10px] border-0 px-[16px] text-[15px] font-bold",
                  on ? "bg-text text-white" : "text-text-sub bg-transparent",
                )}
              >
                {t.label}
              </button>
            );
          })}
        </div>
      </AdminTitleRow>

      {tab === "income" && <IncomePanel />}
      {tab === "score" && <ScorePanel />}
      {tab === "region" && <RegionPanel />}
    </>
  );
}
