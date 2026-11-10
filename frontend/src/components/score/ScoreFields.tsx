"use client";

import {
  MAX_DEPENDENTS,
  MAX_HOMELESS,
  MAX_SUBSCRIPTION,
  type ScoreItemKey,
} from "@/features/score/score";
import type { ScoreCalculator } from "@/features/score/useScoreCalculator";
import { cn } from "@/lib/cn";

type Props = { calc: ScoreCalculator; variant: "web" | "mobile" };

/** 화면 항목 순서 (백엔드 응답 items 순서와 같아요) */
export const scoreItemKeys: ScoreItemKey[] = [
  "HOMELESS_PERIOD",
  "DEPENDENTS",
  "SUBSCRIPTION_PERIOD",
];

export const scoreMax: Record<ScoreItemKey, number> = {
  HOMELESS_PERIOD: MAX_HOMELESS,
  DEPENDENTS: MAX_DEPENDENTS,
  SUBSCRIPTION_PERIOD: MAX_SUBSCRIPTION,
};

export const scoreTitles: Record<ScoreItemKey, string> = {
  HOMELESS_PERIOD: "무주택 기간",
  DEPENDENTS: "부양가족 수",
  SUBSCRIPTION_PERIOD: "청약통장 가입 기간",
};

export const scoreHelp: Record<ScoreItemKey, string> = {
  HOMELESS_PERIOD: "만 30세부터 세요. 그 전에 혼인했다면 혼인신고일부터 세요.",
  DEPENDENTS: "나를 뺀 세대원 수예요. 직계존속은 3년 이상 같은 등본에 있어야 인정돼요.",
  SUBSCRIPTION_PERIOD: "주택청약종합저축에 처음 가입한 날부터 세요.",
};

const control = (web: boolean) =>
  cn(
    "rounded-control border-line bg-surface text-text w-full border border-solid font-semibold disabled:opacity-50",
    web ? "min-h-[50px] px-[14px] text-[16px]" : "min-h-[48px] px-[12px] text-[16px]",
  );

const label = "flex min-w-0 flex-col gap-[6px] text-[14px] font-bold";

function Choice<T extends string | boolean>({
  name,
  value,
  options,
  onChange,
}: {
  name: string;
  value: T | undefined;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div role="radiogroup" aria-label={name} className="flex flex-wrap gap-[6px]">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={String(o.value)}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.value)}
            className={cn(
              "rounded-pill min-h-[40px] cursor-pointer border-0 px-[14px] text-[14px] font-bold",
              on ? "bg-text text-white" : "bg-fill text-text-sub",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** 연월 칸: 지원하지 않는 브라우저는 글자 칸이라 「2023-05」처럼 넣어요 */
function MonthInput({
  value,
  max,
  disabled,
  web,
  onChange,
}: {
  value: string | undefined;
  max: string | undefined;
  disabled?: boolean;
  web: boolean;
  onChange: (v: string | undefined) => void;
}) {
  return (
    <input
      type="month"
      value={value ?? ""}
      max={max}
      placeholder="2023-05"
      disabled={disabled}
      onChange={(e) => onChange(e.target.value || undefined)}
      className={control(web)}
    />
  );
}

/** 무주택 기간: 생년월일 · 혼인 · 집 여부 · 무주택 시작 연월 */
export function HomelessFields({ calc, variant }: Props) {
  const web = variant === "web";
  const { form, set, today } = calc;
  const month = today?.slice(0, 7);
  return (
    <div className={cn("grid gap-[12px]", web ? "grid-cols-2" : "grid-cols-1")}>
      <label className={label}>
        생년월일
        <input
          type="date"
          value={form.birthDate ?? ""}
          max={today ?? undefined}
          onChange={(e) => set({ birthDate: e.target.value || undefined })}
          className={control(web)}
        />
      </label>
      <div className={label}>
        혼인
        <Choice
          name="혼인"
          value={form.marital}
          options={[
            { value: "SINGLE", label: "미혼" },
            { value: "MARRIED", label: "기혼" },
            { value: "ENGAGED", label: "결혼 예정" },
          ]}
          onChange={(marital) => set({ marital })}
        />
      </div>
      {form.marital === "MARRIED" && (
        <label className={label}>
          혼인신고 연월
          <MonthInput
            value={form.marriedOn}
            max={month}
            web={web}
            onChange={(marriedOn) => set({ marriedOn })}
          />
        </label>
      )}
      <div className={label}>
        지금 집이
        <Choice
          name="지금 집이"
          value={form.homeOwner}
          options={[
            { value: false, label: "없어요" },
            { value: true, label: "있어요" },
          ]}
          onChange={(homeOwner) => set({ homeOwner })}
        />
      </div>
      {form.homeOwner === false && (
        <div className={cn(label, web && "col-span-2")}>
          <label className="flex flex-col gap-[6px]">
            무주택이 된 연월
            <MonthInput
              value={form.neverOwned ? form.birthDate?.slice(0, 7) : form.homelessSince}
              max={month}
              disabled={form.neverOwned}
              web={web}
              onChange={(homelessSince) => set({ homelessSince })}
            />
          </label>
          <label className="text-text-sub flex cursor-pointer items-center gap-[8px] text-[14px] font-medium">
            <input
              type="checkbox"
              checked={Boolean(form.neverOwned)}
              onChange={(e) => set({ neverOwned: e.target.checked })}
              className="size-[18px]"
            />
            집을 가진 적이 없어요 (세대원 모두)
          </label>
        </div>
      )}
    </div>
  );
}

const DEPENDENT_MAX = 10;

/** 부양가족 수 */
export function DependentsField({ calc, variant }: Props) {
  const web = variant === "web";
  const { form, set } = calc;
  return (
    <select
      aria-label="부양가족 수"
      value={form.dependents ?? ""}
      onChange={(e) =>
        set({ dependents: e.target.value === "" ? undefined : Number(e.target.value) })
      }
      className={control(web)}
    >
      <option value="">골라 주세요</option>
      {Array.from({ length: DEPENDENT_MAX + 1 }, (_, n) => (
        <option key={n} value={n}>
          {n === DEPENDENT_MAX ? `${n}명 이상` : `${n}명`}
        </option>
      ))}
    </select>
  );
}

/** 청약통장 처음 가입한 연월 */
export function JoinedOnField({ calc, variant }: Props) {
  const web = variant === "web";
  const { form, set, today } = calc;
  return (
    <label className={label}>
      처음 가입한 연월
      <MonthInput
        value={form.joinedOn}
        max={today?.slice(0, 7)}
        web={web}
        onChange={(joinedOn) => set({ joinedOn })}
      />
    </label>
  );
}

/** 항목별 입력 */
export function ScoreFields({ item, ...props }: Props & { item: ScoreItemKey }) {
  if (item === "HOMELESS_PERIOD") return <HomelessFields {...props} />;
  if (item === "DEPENDENTS") return <DependentsField {...props} />;
  return <JoinedOnField {...props} />;
}

/** 총점 아래 안내: 다시 계산 중 · 실패 · 빈 칸이 있어 일부만 더함 */
export function ScoreStatus({ calc, className }: { calc: ScoreCalculator; className?: string }) {
  const text = calc.error
    ? "점수를 계산하지 못했어요. 잠시 뒤 다시 바꿔 보세요"
    : calc.updating
      ? "다시 계산하는 중이에요"
      : calc.partial
        ? "빈 칸이 있는 항목은 빼고 더했어요"
        : null;
  if (!text) return null;
  return (
    <span
      role={calc.error ? "alert" : undefined}
      className={cn("text-text-sub text-[13px]", calc.error && "text-check-text", className)}
    >
      {text}
    </span>
  );
}
