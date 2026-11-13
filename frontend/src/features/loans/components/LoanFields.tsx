"use client";

import { useId } from "react";
import { formatMan, isCouple, netAssetWon, wonText, type LoanMarital } from "@/features/loans/loan";
import { CHILD_MAX, type LoanCheck } from "@/features/loans/useLoanCheck";
import { Choice, CountSelect } from "@/features/profile/components/FamilyFields";
import { BirthField } from "@/features/profile/components/BirthField";
import { cn } from "@/shared/lib/cn";

type Props = { calc: LoanCheck; variant: "web" | "mobile" };

const control = (web: boolean) =>
  cn(
    "rounded-control border-line bg-surface text-text w-full border border-solid font-semibold",
    web ? "min-h-[50px] px-[14px] text-[16px]" : "min-h-[48px] px-[12px] text-[16px]",
  );

const label = "flex min-w-0 flex-col gap-[6px] text-[14px] font-bold";
const help = "text-text-sub text-[13px] leading-[1.5] font-medium";

const yesNo = [
  { value: true, label: "예" },
  { value: false, label: "아니요" },
];

/**
 * 만 원 금액 칸. 브라우저가 입력 기록을 저장하지 않게 autoComplete를 끄고 name을 두지 않아요
 */
function ManInput({
  title,
  value,
  onChange,
  web,
  hint,
  problem,
}: {
  title: string;
  value: string | undefined;
  onChange: (v: string | undefined) => void;
  web: boolean;
  hint?: string;
  problem?: string | null;
}) {
  const id = useId();
  return (
    <div className={label}>
      <label htmlFor={id}>{title}</label>
      <span className="relative flex">
        <input
          id={id}
          type="text"
          inputMode="numeric"
          autoComplete="off"
          placeholder="0"
          value={value ?? ""}
          aria-invalid={problem ? true : undefined}
          aria-describedby={hint || problem ? `${id}-help` : undefined}
          onChange={(e) => onChange(formatMan(e.target.value) || undefined)}
          className={cn(control(web), "pr-[64px] text-right", problem && "border-check-text")}
        />
        <span className="text-text-sub pointer-events-none absolute top-1/2 right-[14px] -translate-y-1/2 text-[15px] font-semibold">
          만 원
        </span>
      </span>
      {(hint || problem) && (
        <span
          id={`${id}-help`}
          role={problem ? "alert" : undefined}
          className={cn(help, problem && "text-check-text font-bold")}
        >
          {problem ?? hint}
        </span>
      )}
    </div>
  );
}

function Group({
  title,
  desc,
  web,
  children,
}: {
  title: string;
  desc?: string;
  web: boolean;
  children: React.ReactNode;
}) {
  return (
    <fieldset
      className={cn(
        "rounded-card bg-surface m-0 flex min-w-0 flex-col gap-[14px] border-0",
        web ? "px-[26px] py-[24px]" : "px-[20px] py-[18px]",
      )}
    >
      <legend className="contents">
        <span
          className={cn("tracking-title block font-extrabold", web ? "text-[19px]" : "text-[17px]")}
        >
          {title}
        </span>
      </legend>
      {desc && <span className={cn(help, "-mt-[8px]")}>{desc}</span>}
      {children}
    </fieldset>
  );
}

const maritalOptions: { value: LoanMarital; label: string }[] = [
  { value: "SINGLE", label: "미혼" },
  { value: "ENGAGED", label: "결혼 예정" },
  { value: "MARRIED", label: "기혼" },
  { value: "DIVORCED", label: "이혼" },
  { value: "WIDOWED", label: "사별" },
];

/** 나와 가족: 생년월일 · 혼인 · 자녀 · 세대 */
function FamilyFields({ calc, variant }: Props) {
  const web = variant === "web";
  const { form, set, today } = calc;
  const children = form.children;
  const setChild = (i: number, v: string) =>
    set({ children: (children ?? []).map((c, j) => (j === i ? v : c)) });
  const setCount = (n: number | undefined) =>
    set({
      children:
        n === undefined ? undefined : Array.from({ length: n }, (_, i) => children?.[i] ?? ""),
    });
  const blankChild = children?.some((c) => !c);
  return (
    <Group title="나와 가족" web={web}>
      <div className={cn("grid gap-[12px]", web ? "grid-cols-2" : "grid-cols-1")}>
        <BirthField
          value={(form.birthDate ?? "").replace(/-/g, ".")}
          onChange={(v) => set({ birthDate: v.replace(/\./g, "-") || undefined })}
          selectClassName={control(web)}
          showProblem
        />
        <label className={label}>
          세대 가구원 수 (나 포함)
          <CountSelect
            name="세대 가구원 수 (나 포함)"
            value={form.householdSize}
            min={1}
            max={10}
            onChange={(householdSize) => set({ householdSize })}
            className={control(web)}
          />
        </label>
        <div className={cn(label, web && "col-span-2")}>
          혼인
          <Choice
            name="혼인"
            value={form.marital}
            options={maritalOptions}
            onChange={(marital) => set({ marital })}
          />
          {form.marital === "ENGAGED" && (
            <span className={help}>3개월 안에 혼인신고할 예정이면 신혼부부로 봐요</span>
          )}
        </div>
        {form.marital === "MARRIED" && (
          <label className={label}>
            혼인신고일
            <input
              type="date"
              autoComplete="off"
              value={form.marriedOn ?? ""}
              max={today ?? undefined}
              onChange={(e) => set({ marriedOn: e.target.value || undefined })}
              className={control(web)}
            />
          </label>
        )}
        <label className={label}>
          자녀
          <select
            value={children === undefined ? "" : children.length}
            onChange={(e) => setCount(e.target.value === "" ? undefined : Number(e.target.value))}
            className={control(web)}
          >
            <option value="">골라 주세요</option>
            <option value={0}>없어요</option>
            {Array.from({ length: CHILD_MAX }, (_, i) => i + 1).map((n) => (
              <option key={n} value={n}>
                {n === CHILD_MAX ? `${n}명 이상` : `${n}명`}
              </option>
            ))}
          </select>
        </label>
        {children?.map((c, i) => (
          <label key={i} className={label}>
            {children.length > 1 ? `${i + 1}째 자녀 생년월일` : "자녀 생년월일"}
            <input
              type="date"
              autoComplete="off"
              value={c}
              max={today ?? undefined}
              onChange={(e) => setChild(i, e.target.value)}
              className={control(web)}
            />
          </label>
        ))}
        {blankChild && (
          <span className={cn(help, web && "col-span-2")}>
            자녀 생년월일을 모두 넣어야 자녀 조건(신생아 · 2자녀 이상)을 볼 수 있어요. 비어 있으면
            그 조건은 확인 필요로 남아요
          </span>
        )}
        <div className={cn(label, web && "col-span-2")}>
          세대원 모두 집이 없나요?
          <Choice
            name="세대원 모두 집이 없나요?"
            value={form.homeless}
            options={yesNo}
            onChange={(homeless) => set({ homeless })}
          />
          <span className={help}>
            주민등록등본에 함께 오른 가족 모두가 집이 없어야 해요 (결혼 예정이면 예비 배우자도)
          </span>
        </div>
      </div>
    </Group>
  );
}

/** 소득: 부부합산(미혼은 본인) · 본인 · 맞벌이 */
function IncomeFields({ calc, variant }: Props) {
  const web = variant === "web";
  const { form, set, problems } = calc;
  const couple = isCouple(form.marital);
  return (
    <Group
      title="연소득"
      desc="세금 떼기 전 1년 소득(근로 · 사업 · 기타)을 만 원 단위로 넣어요"
      web={web}
    >
      <div className={cn("grid gap-[12px]", web && couple ? "grid-cols-2" : "grid-cols-1")}>
        <ManInput
          title={couple ? "부부합산 연소득" : "연소득"}
          value={form.incomeMan}
          onChange={(incomeMan) => set({ incomeMan })}
          web={web}
          hint={
            couple
              ? form.marital === "ENGAGED"
                ? "나와 예비 배우자 소득을 더해요"
                : "나와 배우자 소득을 더해요"
              : undefined
          }
        />
        {couple && (
          <ManInput
            title="본인 연소득"
            value={form.myIncomeMan}
            onChange={(myIncomeMan) => set({ myIncomeMan })}
            web={web}
            hint="대출을 신청하는 사람의 소득이에요"
            problem={problems.myIncome}
          />
        )}
        {couple && (
          <div className={cn(label, web && "col-span-2")}>
            맞벌이인가요?
            <Choice
              name="맞벌이인가요?"
              value={form.dualIncome}
              options={yesNo}
              onChange={(dualIncome) => set({ dualIncome })}
            />
          </div>
        )}
      </div>
    </Group>
  );
}

/** 자산: 자산 − 부채 = 순자산 */
function AssetFields({ calc, variant }: Props) {
  const web = variant === "web";
  const { form, set } = calc;
  const net = netAssetWon(form);
  const couple = isCouple(form.marital);
  return (
    <Group
      title={couple ? "부부합산 순자산" : "순자산"}
      desc="순자산 = 자산 − 부채예요. 두 칸을 넣으면 계산해서 보내요"
      web={web}
    >
      <div className={cn("grid gap-[12px]", web ? "grid-cols-2" : "grid-cols-1")}>
        <ManInput
          title="자산 합계"
          value={form.assetMan}
          onChange={(assetMan) => set({ assetMan })}
          web={web}
          hint="부동산 · 예금 · 주식 · 자동차 · 전월세 보증금 등"
        />
        <ManInput
          title="부채 합계"
          value={form.debtMan}
          onChange={(debtMan) => set({ debtMan })}
          web={web}
          hint="대출 · 받은 보증금 등 갚아야 할 돈. 없으면 비워 두세요"
        />
      </div>
      <div
        aria-live="polite"
        className="rounded-tile bg-bg flex flex-wrap items-baseline justify-between gap-x-[12px] gap-y-[2px] px-[16px] py-[12px]"
      >
        <span className="text-text-sub text-[14px] font-semibold">
          순자산 = 자산 − 부채
          {net !== undefined && !form.debtMan && " (부채 0원)"}
        </span>
        <strong className="text-[17px]">
          {net === undefined ? "자산을 넣으면 계산해요" : wonText(net)}
        </strong>
      </div>
    </Group>
  );
}

/** 구입 대출에만 쓰는 칸 */
function PurchaseFields({ calc, variant }: Props) {
  const web = variant === "web";
  const { form, set } = calc;
  return (
    <Group title="집을 산다면" desc="디딤돌 같은 구입 대출에만 써요" web={web}>
      <div className={label}>
        생애최초 주택구입인가요?
        <Choice
          name="생애최초 주택구입인가요?"
          value={form.firstHome}
          options={yesNo}
          onChange={(firstHome: boolean) => set({ firstHome })}
        />
        <span className={help}>세대원 모두 지금까지 집을 산 적이 없으면 「예」예요</span>
      </div>
    </Group>
  );
}

/** 입력 묶음 전부 */
export function LoanFields(props: Props) {
  return (
    <>
      <FamilyFields {...props} />
      <IncomeFields {...props} />
      <AssetFields {...props} />
      <PurchaseFields {...props} />
    </>
  );
}
