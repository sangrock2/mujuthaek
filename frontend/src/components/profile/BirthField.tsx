"use client";

import { ChevronDown } from "lucide-react";
import { useRef, useSyncExternalStore, type RefObject } from "react";
import { cn } from "@/lib/cn";

const OLDEST_YEAR = 1930;
// 프리렌더에선 시계를 읽지 않아요 (Cache Components). 브라우저에서 올해로 바꿔요
const FALLBACK_YEAR = 2026;
const noop = () => () => {};

/** 저장 값 "1997.03.15" (입력 중이면 "1997.03.") ↔ 년·월·일. 예전 "19970315" · "1997-03-15"도 읽어요 */
export function splitBirth(birth: string) {
  const digits = birth.replace(/\D/g, "");
  if (digits.length === 8 && !birth.includes(".")) {
    return { y: digits.slice(0, 4), m: digits.slice(4, 6), d: digits.slice(6, 8) };
  }
  const [y = "", m = "", d = ""] = birth.split(".");
  return { y, m, d };
}

const joinBirth = (y: string, m: string, d: string) => (y || m || d ? `${y}.${m}.${d}` : "");

/**
 * 생년월일이 다음 단계로 넘어갈 수 있는지. 문제가 있으면 안내 문구, 괜찮으면 null.
 * 해는 OLDEST_YEAR ~ 올해, 달·날까지 다 있어야 해요 (범위 밖 해는 나이를 못 세서 미입력처럼 저장돼요)
 */
export function birthProblem(birth: string, thisYear = new Date().getFullYear()) {
  const { y, m, d } = splitBirth(birth);
  if (!y && !m && !d) return "생년월일을 입력해 주세요";
  if (y.length !== 4) return "해는 네 자리로 써 주세요 (예: 1997)";
  if (Number(y) < OLDEST_YEAR || Number(y) > thisYear)
    return `${OLDEST_YEAR}년부터 ${thisYear}년 사이로 써 주세요`;
  if (!/^(0[1-9]|1[0-2])$/.test(m)) return "태어난 달을 써 주세요";
  if (!/^\d{2}$/.test(d) || Number(d) < 1 || Number(d) > lastDayOf(y, m))
    return "태어난 날을 써 주세요";
  return null;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** 그 달의 마지막 날 (해를 모르면 윤년으로 봐서 2월 29일까지) */
const lastDayOf = (y: string, m: string) =>
  m ? new Date(y.length === 4 ? Number(y) : 2000, Number(m), 0).getDate() : 31;

/**
 * 월·일 입력: 숫자만, 두 자리까지. 첫 자리로 끝이 정해지면(월 2~9, 일 4~9) 바로 0을 붙여요.
 * 끝났으면 done = true (다음 칸으로)
 */
function typeTwoDigits(raw: string, max: number): { value: string; done: boolean } {
  const digits = raw.replace(/\D/g, "").slice(0, 2);
  if (!digits) return { value: "", done: false };
  if (digits.length === 1) {
    const n = Number(digits);
    return n > Math.floor(max / 10)
      ? { value: pad(n), done: true }
      : { value: digits, done: false };
  }
  const n = Number(digits);
  if (n === 0) return { value: "0", done: false };
  return n > max ? { value: digits[0], done: false } : { value: pad(n), done: true };
}

/** 한 칸: 숫자를 바로 쓰고, 오른쪽 ▾를 누르면 기본 선택 목록(모바일은 휴대폰 선택 화면) */
function Segment({
  inputRef,
  label,
  unit,
  placeholder,
  maxLength,
  autoComplete,
  value,
  options,
  invalid,
  className,
  onType,
  onPick,
  onBackspaceEmpty,
  onLeave,
}: {
  inputRef: RefObject<HTMLInputElement | null>;
  label: string;
  unit: string;
  placeholder: string;
  maxLength: number;
  autoComplete: string;
  value: string;
  options: string[];
  invalid?: boolean;
  className: string;
  onType: (raw: string) => void;
  onPick: (value: string) => void;
  onBackspaceEmpty?: () => void;
  /** 칸을 떠날 때. 지금 칸에 보이는 값을 받아요 */
  onLeave?: (current: string) => void;
}) {
  return (
    <div
      className={cn(
        className,
        "focus-within:border-brand relative flex items-center gap-[2px] pr-[34px]",
        invalid && "border-check-text",
      )}
    >
      <input
        ref={inputRef}
        type="text"
        inputMode="numeric"
        autoComplete={autoComplete}
        aria-label={`태어난 ${label} (숫자)`}
        aria-invalid={invalid || undefined}
        placeholder={placeholder}
        maxLength={maxLength}
        value={value}
        onChange={(e) => onType(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Backspace" && !value) onBackspaceEmpty?.();
        }}
        onBlur={(e) => onLeave?.(e.currentTarget.value)}
        className="text-text placeholder:text-text-tertiary w-full min-w-0 border-0 bg-transparent p-0 text-inherit outline-none"
      />
      <span aria-hidden className="text-text-sub flex-none">
        {unit}
      </span>
      <ChevronDown
        size={18}
        aria-hidden
        className="text-text-tertiary pointer-events-none absolute top-1/2 right-[12px] -translate-y-1/2"
      />
      <select
        aria-label={`태어난 ${label} 목록에서 고르기`}
        tabIndex={-1}
        value={options.includes(value) ? value : ""}
        onChange={(e) => onPick(e.target.value)}
        className="absolute top-0 right-0 h-full w-[40px] cursor-pointer opacity-0"
      >
        <option value="">{label}</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {Number(o)}
            {unit}
          </option>
        ))}
      </select>
    </div>
  );
}

/** 생년월일: 년 · 월 · 일 한 줄. 숫자로 바로 쓰거나 ▾로 골라요 */
export function BirthField({
  value,
  onChange,
  selectClassName,
  showProblem = false,
}: {
  value: string;
  onChange: (birth: string) => void;
  /** 다음 단계로 가려다 막혔으면 true: 빈 칸·덜 쓴 칸까지 이유를 보여 줘요 */
  showProblem?: boolean;
  /** 다른 칸과 높이·글자를 맞추려고 받아요 */
  selectClassName: string;
}) {
  const thisYear = useSyncExternalStore(
    noop,
    () => new Date().getFullYear(),
    () => FALLBACK_YEAR,
  );
  const yearRef = useRef<HTMLInputElement>(null);
  const monthRef = useRef<HTMLInputElement>(null);
  const dayRef = useRef<HTMLInputElement>(null);
  const { y, m, d } = splitBirth(value);
  const lastDay = lastDayOf(y, m);

  const set = (next: { y?: string; m?: string; d?: string }) => {
    const ny = next.y ?? y;
    const nm = next.m ?? m;
    let nd = next.d ?? d;
    // 해·달을 바꿔 없는 날이 되면(2월 30일 등) 일을 비워요
    if (nd.length === 2 && Number(nd) > lastDayOf(ny, nm)) nd = "";
    onChange(joinBirth(ny, nm, nd));
  };
  // "3"처럼 한 자리로 두고 나가면 "03"으로. 값은 칸에 보이는 것을 써요: 두 자리를 다 쓰면 바로 다음 칸으로
  // 옮기는데, 그때 나가는 칸은 아직 앞 글자("1")만 아는 화면이라 그 값으로 0을 붙이면 11·12월이 01월이 돼요
  const padOnLeave = (part: "m" | "d") => (current: string) => {
    if (current.length === 1 && current !== "0") set({ [part]: pad(Number(current)) });
  };

  const years = Array.from({ length: thisYear - OLDEST_YEAR + 1 }, (_, i) => String(thisYear - i));
  const months = Array.from({ length: 12 }, (_, i) => pad(i + 1));
  const days = Array.from({ length: lastDay }, (_, i) => pad(i + 1));

  const yearInvalid =
    (y.length === 4 && (Number(y) < OLDEST_YEAR || Number(y) > thisYear)) ||
    (y.length > 0 && y.length < 4 && (Boolean(m) || showProblem));
  const problem = birthProblem(value, thisYear);
  // 쓰는 중에는 해가 틀렸을 때만, 막힌 뒤에는 남은 문제를 모두 보여 줘요
  const error = showProblem ? problem : yearInvalid ? problem : null;

  return (
    <fieldset className="m-0 flex flex-col gap-[8px] border-0 p-0">
      <legend className="mb-[8px] p-0 text-[15px] font-bold">생년월일</legend>
      <div className="grid grid-cols-3 gap-[8px]">
        <Segment
          inputRef={yearRef}
          label="해"
          unit="년"
          placeholder="1997"
          maxLength={4}
          autoComplete="bday-year"
          value={y}
          options={years}
          invalid={yearInvalid}
          className={selectClassName}
          onType={(raw) => {
            const digits = raw.replace(/\D/g, "").slice(0, 4);
            set({ y: digits });
            if (digits.length === 4) monthRef.current?.focus();
          }}
          onPick={(v) => {
            set({ y: v });
            monthRef.current?.focus();
          }}
        />
        <Segment
          inputRef={monthRef}
          label="달"
          unit="월"
          placeholder="MM"
          maxLength={2}
          autoComplete="bday-month"
          value={m}
          options={months}
          className={selectClassName}
          onType={(raw) => {
            const { value: next, done } = typeTwoDigits(raw, 12);
            set({ m: next });
            if (done) dayRef.current?.focus();
          }}
          onPick={(v) => {
            set({ m: v });
            dayRef.current?.focus();
          }}
          onBackspaceEmpty={() => yearRef.current?.focus()}
          onLeave={padOnLeave("m")}
        />
        <Segment
          inputRef={dayRef}
          label="날"
          unit="일"
          placeholder="DD"
          maxLength={2}
          autoComplete="bday-day"
          value={d}
          options={days}
          className={selectClassName}
          onType={(raw) => set({ d: typeTwoDigits(raw, lastDay).value })}
          onPick={(v) => set({ d: v })}
          onBackspaceEmpty={() => monthRef.current?.focus()}
          onLeave={padOnLeave("d")}
        />
      </div>
      {error && (
        <span role="alert" className="text-check-text text-[13px] font-semibold">
          {error}
        </span>
      )}
    </fieldset>
  );
}
