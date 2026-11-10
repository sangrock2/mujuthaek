"use client";

import Link from "next/link";
import { ArrowRight, Check, X } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import {
  ChipGroup,
  HouseholdStepper,
  KidsStepper,
  PriorityChips,
  RankCriteriaFields,
  StatusChips,
  UnitInput,
  DeviceSaveCard,
  SelectOptions,
  pLabel,
  pSelect,
} from "@/components/profile/parts";
import { BirthField } from "@/components/profile/BirthField";
import { SearchRegionsField, ResidenceField } from "@/components/profile/RegionFields";
import {
  headOptions,
  marryOptions,
  useProfileForm,
  type ProfileForm,
} from "@/features/profile/useProfileForm";
import { useSession } from "@/features/auth/session";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

const steps = [
  { n: 1, title: "기본 정보", sub: "나이 · 찾아볼 지역 · 사는 곳" },
  { n: 2, title: "가족 · 소득 · 자산", sub: "결혼 · 소득 · 자산" },
  { n: 3, title: "주택 · 생활권", sub: "무주택 · 청약 · 중요한 것" },
];

const help = "text-text-sub text-[13px] font-medium";

/** 받기 전·실패면 「–」 */
const count = (n: number | null) => (n === null ? "–" : n);
const headerLink =
  "text-text-sub hover:text-text-sub inline-flex min-h-[44px] items-center gap-[4px] px-[12px] text-[15px] font-semibold no-underline";

function Step1({ form }: { form: ProfileForm }) {
  return (
    <div className="flex flex-col gap-[20px]">
      <BirthField
        value={form.field("birth").value}
        onChange={(birth) => form.field("birth").onChange({ target: { value: birth } })}
        showProblem={form.birthBlocked}
        selectClassName={pSelect}
      />
      <SearchRegionsField form={form} selectClassName={pSelect} />
      <ResidenceField form={form} selectClassName={pSelect} />
      <div className="flex flex-col gap-[8px]">
        <span className="text-[15px] font-bold">세대주인가요?</span>
        <ChipGroup
          label="세대주 여부"
          options={headOptions}
          value={form.head}
          onPick={form.setHead}
          className="grid-cols-2"
          chipClassName="min-h-[56px]"
        />
        <span className="text-text-sub text-[13px]">주민등록등본에서 확인할 수 있어요</span>
      </div>
      <StatusChips form={form} />
    </div>
  );
}

function Step2({ form }: { form: ProfileForm }) {
  return (
    <div className="flex flex-col gap-[20px]">
      <div className="flex flex-col gap-[8px]">
        <span className="text-[15px] font-bold">결혼 여부</span>
        <ChipGroup
          label="결혼 여부"
          options={marryOptions}
          value={form.marry}
          onPick={form.setMarry}
          className="grid-cols-3"
          chipClassName="min-h-[56px]"
        />
      </div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-[12px]">
        <div className="flex flex-col gap-[8px]">
          <span className="text-[15px] font-bold">자녀 수</span>
          <KidsStepper form={form} />
        </div>
        <div className="flex flex-col gap-[8px]">
          <span className="text-[15px] font-bold">함께 사는 가족 (나 포함)</span>
          <HouseholdStepper form={form} />
        </div>
      </div>
      <label className={pLabel}>
        연소득 (세전)
        <UnitInput unit="만 원" placeholder="3,200" {...form.sessionField("income")} />
        <span className={help}>작년 원천징수영수증의 총급여를 넣으면 가장 정확해요</span>
      </label>
      <div className="flex flex-col gap-[8px]">
        <label className={pLabel}>
          자산 합계 (예금 · 자동차 · 부동산)
          <UnitInput unit="만 원" placeholder="4,500" {...form.sessionField("asset")} />
        </label>
        <label className="text-text-sub flex cursor-pointer items-center gap-[8px] text-[14px] font-medium">
          <input
            type="checkbox"
            checked={form.assetUnknown}
            onChange={(e) => form.setAssetUnknown(e.target.checked)}
            className="m-[3px_3px_3px_4px] size-[18px]"
          />{" "}
          잘 모르겠어요 · 자산 조건은 &apos;확인 필요&apos;로 보여주세요
        </label>
      </div>
      <div className="flex flex-col gap-[8px]">
        <label className={pLabel}>
          자동차 가액
          <UnitInput
            unit="만 원"
            placeholder="1,800"
            disabled={form.noCar}
            {...form.sessionField("car")}
          />
        </label>
        <label className="text-text-sub flex cursor-pointer items-center gap-[8px] text-[14px] font-medium">
          <input
            type="checkbox"
            checked={form.noCar}
            onChange={(e) => form.setNoCar(e.target.checked)}
            className="m-[3px_3px_3px_4px] size-[18px]"
          />{" "}
          차가 없어요
        </label>
        <span className={help}>
          보험개발원 차량기준가액을 넣으면 가장 정확해요. 공고의 자동차가액 기준과 비교해요
        </span>
      </div>
      <RankCriteriaFields form={form} />
    </div>
  );
}

function Step3({ form }: { form: ProfileForm }) {
  const { options } = form.data;
  return (
    <div className="flex flex-col gap-[20px]">
      <label className={pLabel}>
        무주택 기간
        <select className={cn(pSelect, "font-medium")} {...form.field("homelessPeriod")}>
          <SelectOptions
            items={options.homelessPeriod}
            value={form.field("homelessPeriod").value}
          />
        </select>
      </label>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-[12px]">
        <label className={pLabel}>
          청약통장 가입 기간
          <select className={cn(pSelect, "font-medium")} {...form.field("bankbookPeriod")}>
            <SelectOptions
              items={options.bankbookPeriod}
              value={form.field("bankbookPeriod").value}
            />
          </select>
        </label>
        <label className={pLabel}>
          납입 횟수
          <UnitInput unit="회" placeholder="26" {...form.field("paymentCount")} />
        </label>
      </div>
      <label className={pLabel}>
        지금 쓸 수 있는 돈
        <UnitInput unit="만 원" placeholder="1,500" {...form.sessionField("available")} />
        <span className={help}>공고마다 &apos;내가 준비할 돈&apos;과 비교해 드려요</span>
      </label>
      <div className="flex flex-col gap-[8px]">
        <span className="text-[15px] font-bold">
          살 곳을 고를 때 중요한 것{" "}
          <span className="text-text-sub font-medium">· 여러 개 고를 수 있어요</span>
        </span>
        <PriorityChips form={form} />
      </div>
    </div>
  );
}

export function WebProfile() {
  const form = useProfileForm();
  const session = useSession();
  const current = steps[form.step - 1];
  const primary =
    "rounded-control bg-brand inline-flex min-h-[56px] items-center gap-[8px] px-[26px] text-[17px] font-extrabold text-white";

  return (
    <div className="bg-bg text-text flex min-h-screen w-full flex-col">
      <header className="border-line bg-surface sticky top-0 z-20 border-b border-solid">
        <div className="mx-auto box-border flex min-h-[68px] w-full max-w-[1200px] items-center justify-between gap-[16px] px-[32px]">
          <Link
            href={routes.main}
            aria-label="무주택자들 소개"
            className="text-text hover:text-text inline-flex items-center gap-[9px] no-underline"
          >
            <Logo size={30} />
            <span className="tracking-logo text-[19px] font-extrabold">무주택자들</span>
          </Link>
          <div className="flex items-center gap-[8px]">
            {session.data === null && (
              <Link href={routes.login} className={headerLink}>
                로그인
              </Link>
            )}
            <Link href={routes.main} className={headerLink}>
              <X size={18} aria-hidden />
              나가기
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto box-border flex w-full max-w-[1200px] flex-1 flex-col gap-[28px] px-[32px] pt-[40px] pb-[72px]">
        <div className="flex flex-col gap-[8px]">
          <h1 className="tracking-h1 m-0 text-[32px] font-extrabold">내 조건을 알려주세요</h1>
          <p className="text-text-sub m-0 text-[17px] leading-[1.6]">
            입력한 만큼 판정해요. 모르는 칸은 비워도 되고, 그 조건은 &apos;확인 필요&apos;로
            보여드려요
          </p>
        </div>

        <div className="flex flex-wrap items-start gap-[24px]">
          <nav
            aria-label="입력 단계"
            className="flex min-w-0 flex-col gap-[6px]"
            style={{ flex: "1 1 220px" }}
          >
            {steps.map((s) => {
              const done = s.n < form.step;
              const cur = s.n === form.step;
              return (
                <button
                  key={s.n}
                  type="button"
                  onClick={() => form.goTo(s.n)}
                  aria-current={cur ? "step" : undefined}
                  className={cn(
                    "text-text flex min-h-[64px] cursor-pointer items-center gap-[12px] rounded-[16px] border-0 px-[16px] py-[14px] text-left",
                    cur ? "bg-surface" : "bg-transparent",
                  )}
                >
                  <span
                    className={cn(
                      "rounded-pill flex size-[32px] flex-none items-center justify-center text-[14px] font-extrabold",
                      done || cur ? "bg-brand text-white" : "bg-line text-text-sub",
                    )}
                  >
                    {done ? <Check size={16} strokeWidth={3} aria-label="완료" /> : s.n}
                  </span>
                  <span className="flex flex-col gap-[2px]">
                    <span className={cn("text-[16px]", cur ? "font-extrabold" : "font-semibold")}>
                      {s.title}
                    </span>
                    <span className="text-text-sub text-[13px]">{s.sub}</span>
                  </span>
                </button>
              );
            })}
          </nav>

          <section
            aria-label="입력"
            className="rounded-card-lg bg-surface flex min-w-0 flex-col gap-[24px] p-[32px]"
            style={{ flex: "999 1 520px" }}
          >
            <div className="flex items-baseline justify-between">
              <h2 className="tracking-title m-0 text-[22px] font-extrabold">{current.title}</h2>
              <span className="text-brand-strong text-[14px] font-bold">{form.step} / 3</span>
            </div>

            {form.step === 1 && <Step1 form={form} />}
            {form.step === 2 && <Step2 form={form} />}
            {form.step === 3 && <Step3 form={form} />}

            <div className="border-line-soft flex items-center justify-between gap-[10px] border-t border-solid pt-[20px]">
              {form.step > 1 && (
                <button
                  type="button"
                  onClick={form.prev}
                  className="rounded-control bg-fill text-text min-h-[56px] cursor-pointer border-0 px-[22px] text-[16px] font-bold"
                >
                  이전
                </button>
              )}
              <span className="flex-1" />
              {form.isLast ? (
                <button
                  type="button"
                  onClick={form.submit}
                  className={cn(primary, "cursor-pointer border-0")}
                >
                  확인하기
                  <ArrowRight size={20} strokeWidth={2.2} aria-hidden />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={form.next}
                  className={cn(primary, "cursor-pointer border-0")}
                >
                  다음
                  <ArrowRight size={20} strokeWidth={2.2} aria-hidden />
                </button>
              )}
            </div>
          </section>

          <aside className="flex min-w-0 flex-col gap-[16px]" style={{ flex: "1 1 280px" }}>
            <section
              aria-label="지금 조건으로"
              aria-busy={form.preview.updating}
              className="rounded-card bg-surface flex flex-col gap-[14px] p-[24px]"
            >
              <span className="text-text-sub text-[15px] font-bold">지금 조건으로</span>
              <div className="flex items-baseline justify-between">
                <span className="text-[15px]">지원 가능한 공고</span>
                <span
                  className={cn(
                    "tracking-title text-[26px] font-extrabold",
                    form.preview.updating && "opacity-50",
                  )}
                >
                  {count(form.preview.homes)}곳
                </span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-[15px]">받을 수 있는 혜택</span>
                <span
                  className={cn(
                    "tracking-title text-[26px] font-extrabold",
                    form.preview.updating && "opacity-50",
                  )}
                >
                  {count(form.preview.benefits)}개
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[15px]">확인이 필요한 공고</span>
                <span className="rounded-badge bg-check-bg text-check-text px-[10px] py-[4px] text-[14px] font-extrabold">
                  {count(form.preview.needCheck)}곳
                </span>
              </div>
              <span
                role="status"
                className="border-line-soft text-text-sub border-t border-solid pt-[12px] text-[13px]"
              >
                {form.preview.error
                  ? "지금은 셀 수 없어요. 확인하기를 누르면 홈에서 볼 수 있어요"
                  : form.preview.updating
                    ? "바뀐 조건으로 세는 중이에요"
                    : "입력할수록 정확해져요"}
              </span>
            </section>

            <DeviceSaveCard form={form} />
          </aside>
        </div>
      </main>
    </div>
  );
}
