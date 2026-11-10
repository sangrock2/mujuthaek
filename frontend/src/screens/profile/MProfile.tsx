"use client";

import Link from "next/link";
import { X } from "lucide-react";
import { MBottomActions } from "@/components/layout/MBackHeader";
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
import { headOptions, marryOptions, useProfileForm } from "@/features/profile/useProfileForm";
import { useSession } from "@/features/auth/session";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

/** 받기 전·실패면 「–」 */
const count = (n: number | null) => (n === null ? "–" : n);
const titles = ["기본 정보를 알려주세요", "가족 · 소득 · 자산", "주택 · 생활권"];

const mSelect = cn(pSelect, "min-h-[54px] px-[12px] text-[16px]");
const help = "text-text-sub text-[13px] font-medium";

export function MProfile() {
  const form = useProfileForm();
  const session = useSession();
  const { options } = form.data;

  return (
    <div className="bg-surface text-text flex min-h-screen w-full flex-col">
      <header className="bg-surface flex flex-col px-[8px]">
        <div className="flex h-[56px] items-center justify-between">
          <Link
            href={routes.main}
            aria-label="나가기"
            className="text-text hover:text-text inline-flex size-[44px] items-center justify-center rounded-sm"
          >
            <X size={24} aria-hidden />
          </Link>
          <div className="flex items-center gap-[4px] pr-[4px]">
            {session.data === null && (
              <Link
                href={routes.login}
                className="text-text-sub hover:text-text-sub inline-flex min-h-[44px] items-center px-[8px] text-[14px] font-semibold no-underline"
              >
                로그인
              </Link>
            )}
            {/* 단계 이동: 웹처럼 아무 단계로나 바로 가요 */}
            <nav aria-label="단계" className="flex items-center">
              {[1, 2, 3].map((n) => (
                <button
                  key={n}
                  type="button"
                  aria-label={`${n}단계 · ${titles[n - 1]}`}
                  aria-current={form.step === n ? "step" : undefined}
                  onClick={() => form.goTo(n)}
                  className={cn(
                    "inline-flex size-[36px] cursor-pointer items-center justify-center rounded-full border-0 bg-transparent text-[15px] font-bold",
                    form.step === n ? "text-brand-strong" : "text-text-tertiary",
                  )}
                >
                  {n}
                </button>
              ))}
            </nav>
          </div>
        </div>
        <span className="bg-line mx-[12px] block h-[4px] overflow-hidden rounded-[2px]">
          <span
            className="bg-brand block h-full"
            style={{ width: `${Math.round((form.step / 3) * 100)}%` }}
          />
        </span>
      </header>

      <main className="flex flex-1 flex-col gap-[22px] px-[20px] py-[24px]">
        <div className="flex flex-col gap-[6px]">
          <h1 className="tracking-h1 m-0 text-[26px] font-extrabold">{titles[form.step - 1]}</h1>
          <span className="text-text-sub text-[15px] leading-[1.6]">
            모르는 칸은 비워도 돼요 · &apos;확인 필요&apos;로 보여드려요
          </span>
        </div>

        {form.step === 1 && (
          <div className="flex flex-col gap-[20px]">
            <BirthField
              value={form.field("birth").value}
              onChange={(birth) => form.field("birth").onChange({ target: { value: birth } })}
              showProblem={form.birthBlocked}
              selectClassName={mSelect}
            />
            <SearchRegionsField form={form} selectClassName={mSelect} />
            <ResidenceField form={form} selectClassName={mSelect} />
            <div className="flex flex-col gap-[8px]">
              <span className="text-[15px] font-bold">세대주인가요?</span>
              <ChipGroup
                label="세대주 여부"
                options={headOptions}
                value={form.head}
                onPick={form.setHead}
                className="grid-cols-2"
              />
              <span className="text-text-sub text-[13px]">주민등록등본에서 확인할 수 있어요</span>
            </div>
            <StatusChips form={form} />
          </div>
        )}

        {form.step === 2 && (
          <div className="flex flex-col gap-[20px]">
            <div className="flex flex-col gap-[8px]">
              <span className="text-[15px] font-bold">결혼 여부</span>
              <ChipGroup
                label="결혼 여부"
                options={marryOptions}
                value={form.marry}
                onPick={form.setMarry}
                className="grid-cols-3"
                chipClassName="min-h-[52px] text-[15px]"
              />
            </div>
            <div className="flex flex-col gap-[8px]">
              <span className="text-[15px] font-bold">자녀 수</span>
              <KidsStepper form={form} className="min-h-[54px]" />
            </div>
            <div className="flex flex-col gap-[8px]">
              <span className="text-[15px] font-bold">함께 사는 가족 (나 포함)</span>
              <HouseholdStepper form={form} className="min-h-[54px]" />
            </div>
            <label className={pLabel}>
              연소득 (세전)
              <UnitInput
                unit="만 원"
                placeholder="3,200"
                className="min-h-[54px]"
                {...form.sessionField("income")}
              />
              <span className={help}>작년 원천징수영수증의 총급여를 넣으면 가장 정확해요</span>
            </label>
            <div className="flex flex-col gap-[8px]">
              <label className={pLabel}>
                자산 합계 (예금 · 자동차 · 부동산)
                <UnitInput
                  unit="만 원"
                  placeholder="4,500"
                  className="min-h-[54px]"
                  {...form.sessionField("asset")}
                />
              </label>
              <label className="text-text-sub flex min-h-[32px] cursor-pointer items-center gap-[8px] text-[14px] font-medium">
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
                  className="min-h-[54px]"
                  disabled={form.noCar}
                  {...form.sessionField("car")}
                />
              </label>
              <label className="text-text-sub flex min-h-[32px] cursor-pointer items-center gap-[8px] text-[14px] font-medium">
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
            <RankCriteriaFields form={form} compact />
          </div>
        )}

        {form.step === 3 && (
          <div className="flex flex-col gap-[20px]">
            <label className={pLabel}>
              무주택 기간
              <select className={cn(mSelect, "font-medium")} {...form.field("homelessPeriod")}>
                <SelectOptions
                  items={options.homelessPeriod}
                  value={form.field("homelessPeriod").value}
                />
              </select>
            </label>
            <label className={pLabel}>
              청약통장 가입 기간
              <select className={cn(mSelect, "font-medium")} {...form.field("bankbookPeriod")}>
                <SelectOptions
                  items={options.bankbookPeriod}
                  value={form.field("bankbookPeriod").value}
                />
              </select>
            </label>
            <label className={pLabel}>
              납입 횟수
              <UnitInput
                unit="회"
                placeholder="26"
                className="min-h-[54px]"
                {...form.field("paymentCount")}
              />
            </label>
            <label className={pLabel}>
              지금 쓸 수 있는 돈
              <UnitInput
                unit="만 원"
                placeholder="1,500"
                className="min-h-[54px]"
                {...form.sessionField("available")}
              />
              <span className={help}>공고마다 &apos;내가 준비할 돈&apos;과 비교해 드려요</span>
            </label>
            <div className="flex flex-col gap-[8px]">
              <span className="text-[15px] font-bold">
                살 곳을 고를 때 중요한 것{" "}
                <span className="text-text-sub font-medium">· 여러 개 고를 수 있어요</span>
              </span>
              <PriorityChips form={form} chipClassName="px-[16px]" />
            </div>
          </div>
        )}

        <div
          role="status"
          aria-busy={form.preview.updating}
          className="bg-bg flex items-center justify-between gap-[10px] rounded-[18px] px-[16px] py-[14px]"
        >
          <span className="text-text-sub text-[14px]">지금 조건으로</span>
          <span className="flex flex-col items-end gap-[2px] text-right">
            <span
              className={cn("text-[15px] font-extrabold", form.preview.updating && "opacity-50")}
            >
              {form.preview.error
                ? "지금은 셀 수 없어요"
                : `공고 ${count(form.preview.homes)}곳 · 혜택 ${count(form.preview.benefits)}개`}
            </span>
            <span className="text-text-sub text-[12px]">
              {form.preview.error
                ? "확인하기를 누르면 홈에서 볼 수 있어요"
                : form.preview.updating
                  ? "바뀐 조건으로 세는 중이에요"
                  : `확인이 필요한 공고 ${count(form.preview.needCheck)}곳`}
            </span>
          </span>
        </div>

        {/* 이 기기에 저장: 웹처럼 모든 단계에서 켜고 끄고 지울 수 있어요 */}
        <DeviceSaveCard form={form} compact />
      </main>

      <MBottomActions>
        {form.step > 1 && (
          <button
            type="button"
            onClick={form.prev}
            className="rounded-control bg-fill text-text min-h-[56px] flex-none cursor-pointer border-0 px-[20px] text-[16px] font-bold"
          >
            이전
          </button>
        )}
        {form.isLast ? (
          <button
            type="button"
            onClick={form.submit}
            className="rounded-control bg-brand min-h-[56px] flex-1 cursor-pointer border-0 text-[17px] font-extrabold text-white"
          >
            확인하기
          </button>
        ) : (
          <button
            type="button"
            onClick={form.next}
            className="rounded-control bg-brand min-h-[56px] flex-1 cursor-pointer border-0 text-[17px] font-extrabold text-white"
          >
            다음
          </button>
        )}
      </MBottomActions>
    </div>
  );
}
