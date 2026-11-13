"use client";

import { Choice, CountSelect } from "./FamilyFields";
import { Lock } from "lucide-react";
import { RankChip } from "@/shared/ui/Badge";
import { Toggle } from "@/shared/ui/Toggle";
import { SelectChip } from "@/shared/ui/Chip";
import type { ProfileForm } from "@/features/profile/useProfileForm";
import { cn } from "@/shared/lib/cn";

export const pLabel = "flex flex-col gap-[8px] text-[15px] font-bold";
export const pInput =
  "rounded-control border border-solid border-line bg-surface text-text min-h-[56px] min-w-0 px-[16px] text-[17px] font-medium";
export const pSelect =
  "rounded-control border border-solid border-line bg-surface text-text min-h-[56px] min-w-0 px-[14px] text-[17px]";

/** 단위가 오른쪽 안에 있는 입력칸 */
export function UnitInput({
  unit,
  placeholder,
  className,
  describedBy,
  value,
  onChange,
  disabled,
}: {
  unit: string;
  placeholder: string;
  className?: string;
  describedBy?: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  disabled?: boolean;
}) {
  return (
    <span className="relative flex">
      <input
        type="text"
        inputMode="numeric"
        placeholder={placeholder}
        aria-describedby={describedBy}
        value={value}
        onChange={onChange}
        disabled={disabled}
        className={cn(
          pInput,
          "flex-1",
          "disabled:opacity-50",
          unit.length > 1 ? "pr-[60px]" : "pr-[44px]",
          className,
        )}
      />
      <span className="text-text-sub pointer-events-none absolute top-1/2 right-[16px] -translate-y-1/2 text-[16px] font-semibold">
        {unit}
      </span>
    </span>
  );
}

/** 선택지에 지금 값이 없으면(모바일은 일부만 보여줘요) 맨 앞에 붙여요 */
export function SelectOptions({ items, value }: { items: string[]; value: string }) {
  const list = value && !items.includes(value) ? [value, ...items] : items;
  return (
    <>
      <option value="">골라 주세요 · 선택</option>
      {list.map((o) => (
        <option key={o}>{o}</option>
      ))}
    </>
  );
}

/** 이 기기에 조건 저장: 켜고 끄기 + 지우기 */
export function DeviceSaveCard({ form, compact }: { form: ProfileForm; compact?: boolean }) {
  return (
    <section
      aria-label="이 기기에 조건 저장"
      className={cn(
        "bg-brand-soft flex flex-col gap-[12px]",
        compact ? "rounded-[18px] px-[18px] py-[16px]" : "rounded-card px-[24px] py-[22px]",
      )}
    >
      <div className="flex items-center justify-between gap-[12px]">
        <span
          className={cn(
            "text-brand-strong inline-flex items-center gap-[8px] font-extrabold",
            compact ? "text-[15px]" : "text-[16px]",
          )}
        >
          <Lock size={compact ? 18 : 20} aria-hidden />이 기기에 조건 저장
        </span>
        <Toggle
          checked={form.saveOnDevice}
          onChange={form.setSaveOnDevice}
          label="이 기기에 조건 저장"
        />
      </div>
      <span
        className={cn("text-brand-strong leading-[1.6]", compact ? "text-[13px]" : "text-[14px]")}
      >
        {form.saveOnDevice
          ? "소득·자산은 저장하지 않아요. 나머지 조건은 30일 동안 이 기기에만 저장해요."
          : "이 기기에 저장하지 않아요. 탭을 닫으면 입력한 조건이 지워져요."}
      </span>
      {form.hasSaved && (
        <button
          type="button"
          onClick={form.clearSaved}
          className="text-brand-strong min-h-[44px] cursor-pointer self-start rounded-[10px] border-0 bg-white px-[14px] text-[14px] font-bold"
        >
          저장한 조건 지우기
        </button>
      )}
    </section>
  );
}

/** 자녀 수와 가구원 수는 대출 화면과 같은 선택 칸을 써요. */
export function KidsCountField({ form, className }: { form: ProfileForm; className?: string }) {
  return (
    <CountSelect
      name="자녀 수"
      value={form.kids}
      max={9}
      onChange={form.setKids}
      className={className}
    />
  );
}
export function HouseholdCountField({
  form,
  className,
}: {
  form: ProfileForm;
  className?: string;
}) {
  return (
    <CountSelect
      name="함께 사는 가족 수 (나 포함)"
      value={form.household}
      min={1}
      max={10}
      onChange={form.setHousehold}
      className={className}
    />
  );
}

/** 2px 테두리 선택 칩 묶음 */
export function ChipGroup<K extends string>({
  label,
  options,
  value,
  onPick,
  className,
}: {
  label: string;
  options: { key: K; label: string }[];
  value: K | "";
  onPick: (k: K) => void;
  className?: string;
  chipClassName?: string;
}) {
  return (
    <div className={className}>
      <Choice
        name={label}
        value={value || undefined}
        options={options.map((o) => ({ value: o.key, label: o.label }))}
        onChange={onPick}
      />
    </div>
  );
}

/** 살 곳을 고를 때 중요한 것 (알약 칩, 여러 개) */
export function PriorityChips({
  form,
  chipClassName,
}: {
  form: ProfileForm;
  chipClassName?: string;
}) {
  return (
    <div role="group" aria-label="우선순위" className="flex flex-wrap gap-[8px]">
      {form.data.options.priorities.map((p) => (
        <SelectChip
          key={p}
          selected={form.prios.includes(p)}
          onClick={() => form.togglePrio(p)}
          className={cn("rounded-pill min-h-[44px] px-[18px] text-[15px]", chipClassName)}
        >
          {p}
        </SelectChip>
      ))}
    </div>
  );
}

/** 지금 상황: 대학생 · 취업준비생 · 청년 · 신혼부부 (선택, 여러 개) */
export function StatusChips({
  form,
  chipClassName,
}: {
  form: ProfileForm;
  chipClassName?: string;
}) {
  return (
    <div className="flex flex-col gap-[8px]">
      <span className="text-[15px] font-bold">
        지금 상황 <span className="text-text-sub font-medium">· 선택 · 여러 개 고를 수 있어요</span>
      </span>
      <div role="group" aria-label="지금 상황" className="flex flex-wrap gap-[8px]">
        {form.data.statuses.map((s) => (
          <SelectChip
            key={s}
            selected={form.statuses.includes(s)}
            onClick={() => form.toggleStatus(s)}
            className={cn("rounded-pill min-h-[44px] px-[18px] text-[15px]", chipClassName)}
          >
            {s}
          </SelectChip>
        ))}
      </div>
    </div>
  );
}

const ruleText = { any: "하나라도 해당하면", all: "모두 해당하면" } as const;

/** 순위 확인용 세부 요건 (선택). 체크한 항목으로 예상 순위를 보여줘요 */
export function RankCriteriaFields({ form, compact }: { form: ProfileForm; compact?: boolean }) {
  return (
    <fieldset className="m-0 flex min-w-0 flex-col gap-[10px] border-0 p-0">
      <legend className="mb-[8px] p-0 text-[15px] font-bold">
        순위 확인용 세부 조건 <span className="text-text-sub font-medium">· 선택이에요</span>
      </legend>
      <span className="text-text-sub -mt-[4px] text-[13px]">
        공공임대 순위를 볼 때 써요. 해당하는 것만 체크해 주세요
      </span>
      {form.data.rankCriteria.map((c) => (
        <div
          key={c.rank}
          role="group"
          aria-label={`${c.rank}순위 · ${ruleText[c.rule]}`}
          className={cn("rounded-tile bg-fill flex flex-col", compact ? "p-[14px]" : "p-[16px]")}
        >
          <span className="flex items-center gap-[8px]">
            <RankChip rank={c.rank} size="md" />
            <span className="text-text-sub text-[13px] font-semibold">{ruleText[c.rule]}</span>
          </span>
          {c.items.map((it) => (
            <label
              key={it.key}
              className={cn(
                "flex min-h-[44px] cursor-pointer items-center gap-[10px] font-medium",
                compact ? "text-[14px]" : "text-[15px]",
              )}
            >
              <input
                type="checkbox"
                checked={form.rankChecks.includes(it.key)}
                onChange={() => form.toggleRankCheck(it.key)}
                className="size-[18px] flex-none"
              />
              {it.label}
            </label>
          ))}
        </div>
      ))}
      <span aria-live="polite" className="flex min-h-[28px] items-center gap-[6px]">
        {form.estimatedRank && (
          <>
            <span className="text-[14px] font-bold">체크한 항목으로 보면</span>
            <RankChip rank={form.estimatedRank} size="md" />
            <span className="text-[14px] font-bold">에 해당해요</span>
          </>
        )}
      </span>
    </fieldset>
  );
}
