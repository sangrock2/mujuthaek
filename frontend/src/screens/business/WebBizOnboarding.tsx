"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Briefcase, Info, X } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { WebMain, WebPage } from "@/components/layout/Responsive";
import { Badge } from "@/components/ui/Badge";
import {
  industryGroups,
  needOptions,
  restrictionOptions,
  statusOptions,
  validIndustryCode,
} from "@/features/business/profile";
import { useBizOnboardingForm } from "@/features/business/state";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import { applicantTypes, stageOptions, type StageOption } from "./onboarding";

const control =
  "rounded-control border-line bg-surface text-text min-h-[56px] border border-solid text-[17px]";
const pickTone = (on: boolean) =>
  on ? "border-brand bg-brand-soft text-brand-strong" : "border-line bg-surface text-text";

function UnitField({
  label,
  unit,
  placeholder,
  disabled,
  padRight,
  value,
  onChange,
}: {
  label: string;
  unit: string;
  placeholder: string;
  disabled: boolean;
  padRight: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-[8px] text-[15px] font-bold">
      {label}
      <span className="relative flex">
        <input
          type="text"
          inputMode="numeric"
          placeholder={placeholder}
          disabled={disabled}
          value={disabled ? "" : value}
          onChange={(e) => onChange(e.target.value.replace(/[^\d,]/g, ""))}
          className={cn(control, "box-content min-w-0 flex-1 pl-[16px] font-medium", padRight)}
        />
        <span className="text-text-sub pointer-events-none absolute top-1/2 right-[16px] -translate-y-1/2 text-[16px] font-semibold">
          {unit}
        </span>
      </span>
    </label>
  );
}

export function WebBizOnboarding() {
  const f = useBizOnboardingForm();
  const { draft, stage, setStage, pre, needs, toggleNeed, preview } = f;
  const router = useRouter();
  const stages: StageOption[] = stageOptions.web;
  const done = () => {
    f.save();
    router.push(routes.business);
  };

  return (
    <WebPage>
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
          <Link
            href={routes.business}
            className="text-text-sub hover:text-text-sub inline-flex min-h-[44px] items-center gap-[4px] px-[12px] text-[15px] font-semibold no-underline"
          >
            <X size={18} aria-hidden />
            나가기
          </Link>
        </div>
      </header>

      <WebMain className="gap-[28px]">
        <div className="flex flex-col gap-[8px]">
          <Badge tone="ok" className="self-start">
            사업공간
          </Badge>
          <h1 className="tracking-h1 m-0 text-[32px] font-extrabold">사업 정보를 알려주세요</h1>
          <p className="text-text-sub m-0 text-[17px] leading-[1.6]">
            창업 공간과 사업 지원을 내 조건으로 판정해요. 모르는 칸은 비워도 되고, 그 조건은
            &apos;확인 필요&apos;로 보여드려요
          </p>
        </div>

        <div className="flex flex-wrap items-start gap-[24px]">
          <section
            aria-label="사업 정보 입력"
            className="rounded-card-lg bg-surface box-content flex min-w-0 flex-col gap-[26px] p-[32px]"
            style={{ flex: "999 1 560px" }}
          >
            <div className="bg-bg flex flex-wrap items-center justify-between gap-[10px] rounded-[18px] px-[18px] py-[16px]">
              <span className="flex flex-col gap-[4px]">
                <span className="text-text-sub text-[13px] font-semibold">
                  공통 정보 · 주거와 함께 써요
                </span>
                <span className="text-[16px] font-bold">
                  {f.common ?? "나이 · 사는 곳을 아직 입력하지 않았어요"}
                </span>
              </span>
              <Link
                href={routes.profile}
                className="bg-surface text-brand-strong hover:text-brand-strong inline-flex min-h-[44px] items-center rounded-[10px] px-[14px] text-[14px] font-bold no-underline"
              >
                수정
              </Link>
            </div>

            <div className="flex flex-col gap-[8px]">
              <span className="text-[15px] font-bold">창업 상태</span>
              <div role="group" aria-label="창업 상태" className="grid grid-cols-2 gap-[8px]">
                {stages.map((o) => (
                  <button
                    key={o.key}
                    type="button"
                    aria-pressed={stage === o.key}
                    onClick={() => setStage(o.key)}
                    className={cn(
                      "rounded-tile flex min-h-[72px] cursor-pointer flex-col gap-[3px] border-2 border-solid px-[18px] py-[14px] text-left",
                      pickTone(stage === o.key),
                    )}
                  >
                    <span className="text-[17px] font-extrabold">{o.label}</span>
                    <span className="text-text-sub text-[13px] font-medium">{o.sub}</span>
                  </button>
                ))}
              </div>
            </div>

            <label className="flex flex-col gap-[8px] text-[15px] font-bold">
              업종
              <select
                value={draft.industry}
                onChange={(e) => f.set({ industry: e.target.value })}
                className={cn(control, "px-[14px] font-medium")}
              >
                <option value="">업종 선택</option>
                {industryGroups.map((g) => (
                  <optgroup key={g.group} label={g.group}>
                    {g.items.map((o) => (
                      <option key={o.key} value={o.key}>
                        {o.label}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
              <span className="text-text-sub text-[13px] font-medium">
                업종에 따라 들어갈 수 있는 공간이 달라져요
              </span>
            </label>

            <label className="flex flex-col gap-[8px] text-[15px] font-bold">
              <span>
                업종 코드{" "}
                <span className="text-text-sub font-medium">· 선택, 알면 더 정확해요</span>
              </span>
              <input
                type="text"
                inputMode="numeric"
                maxLength={5}
                placeholder="예: 58222"
                value={draft.industryCode ?? ""}
                onChange={(e) => f.set({ industryCode: e.target.value.replace(/\D/g, "") })}
                className={cn(control, "box-content min-w-0 px-[16px] font-medium")}
              />
              <span className="text-text-sub text-[13px] font-medium">
                사업자등록증의 업종 코드(한국표준산업분류 5자리)를 넣으면 업종 선택 대신 이 코드로
                판정해요 ·{" "}
                <a href="https://kssc.kostat.go.kr" target="_blank" rel="noreferrer">
                  코드 찾기
                </a>
                {draft.industryCode &&
                  !validIndustryCode(draft.industryCode) &&
                  " · 5자리 숫자로 넣어 주세요"}
              </span>
            </label>

            {!pre && (
              <div className="flex flex-col gap-[8px]">
                <span className="text-[15px] font-bold">사업자 형태</span>
                <div role="group" aria-label="사업자 형태" className="grid grid-cols-2 gap-[8px]">
                  {applicantTypes.map((o) => (
                    <button
                      key={o.key}
                      type="button"
                      aria-pressed={draft.applicantType === o.key}
                      onClick={() =>
                        f.set({ applicantType: draft.applicantType === o.key ? "" : o.key })
                      }
                      className={cn(
                        "rounded-tile min-h-[52px] cursor-pointer border-2 border-solid px-[18px] text-[16px] font-extrabold",
                        pickTone(draft.applicantType === o.key),
                      )}
                    >
                      {o.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className={cn("flex flex-col gap-[10px]", pre && "opacity-45")}>
              <div
                className="grid gap-[12px]"
                style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}
              >
                <UnitField
                  label="업력"
                  unit="개월"
                  placeholder="18"
                  disabled={pre}
                  padRight="pr-[60px]"
                  value={draft.months}
                  onChange={(v) => f.set({ months: v })}
                />
                <UnitField
                  label="직원 수 (나 포함)"
                  unit="명"
                  placeholder="3"
                  disabled={pre}
                  padRight="pr-[44px]"
                  value={draft.employees}
                  onChange={(v) => f.set({ employees: v })}
                />
                <UnitField
                  label="연 매출"
                  unit="만 원"
                  placeholder="8,000"
                  disabled={pre}
                  padRight="pr-[60px]"
                  value={f.revenue}
                  onChange={f.setRevenue}
                />
              </div>
            </div>
            <span className="text-text-sub -mt-[14px] flex items-center gap-[8px] text-[14px] font-medium">
              <Info size={16} aria-hidden />
              {pre
                ? "예비 창업이면 업력 · 직원 수 · 매출은 입력하지 않아요"
                : "업력은 사업자등록일부터 세요 · 매출은 이번 탭에서만 쓰고 저장하지 않아요 · 직원 수는 지금 공고 조건에 없어 참고용이에요"}
            </span>

            <div className="flex flex-col gap-[8px]">
              <span className="text-[15px] font-bold">{pre ? "희망 지역" : "사업장 소재지"}</span>
              <div
                className="grid gap-[10px]"
                style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}
              >
                <select
                  aria-label="시·도"
                  value={f.sidoCode}
                  onChange={(e) => f.set({ regionCode: e.target.value })}
                  className={cn(control, "px-[14px]")}
                >
                  <option value="">시·도 선택</option>
                  {f.sidos.map((o) => (
                    <option key={o.code} value={o.code}>
                      {o.name}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="시·군·구"
                  value={draft.regionCode.length === 5 ? draft.regionCode : ""}
                  onChange={(e) => f.set({ regionCode: e.target.value || f.sidoCode })}
                  disabled={!f.sidoCode}
                  className={cn(control, "px-[14px] disabled:opacity-50")}
                >
                  <option value="">{f.sidoCode ? "전체" : "시·군·구 선택"}</option>
                  {f.sigungus.map((o) => (
                    <option key={o.code} value={o.code}>
                      {o.name}
                    </option>
                  ))}
                </select>
              </div>
              <span className="text-text-sub text-[13px] font-medium">
                지역 지원금과 세액감면 비율을 판정할 때 써요
              </span>
            </div>

            <div className="flex flex-col gap-[8px]">
              <span className="text-[15px] font-bold">
                필요한 공간{" "}
                <span className="text-text-sub font-medium">· 여러 개 고를 수 있어요</span>
              </span>
              <div role="group" aria-label="필요한 공간" className="flex flex-wrap gap-[8px]">
                {needOptions.map((n) => (
                  <button
                    key={n.key}
                    type="button"
                    aria-pressed={needs.includes(n.key)}
                    onClick={() => toggleNeed(n.key)}
                    className={cn(
                      "rounded-pill min-h-[44px] cursor-pointer border-2 border-solid px-[18px] text-[15px] font-bold",
                      pickTone(needs.includes(n.key)),
                    )}
                  >
                    {n.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-[8px]">
              <span className="text-[15px] font-bold">
                해당 유형{" "}
                <span className="text-text-sub font-medium">· 공고의 대상 조건에 써요</span>
              </span>
              <div role="group" aria-label="해당 유형" className="flex flex-wrap gap-[8px]">
                <button
                  type="button"
                  aria-pressed={f.statuses?.length === 0}
                  onClick={f.toggleNoStatus}
                  className={cn(
                    "rounded-pill min-h-[44px] cursor-pointer border-2 border-solid px-[18px] text-[15px] font-bold",
                    pickTone(f.statuses?.length === 0),
                  )}
                >
                  해당 없음
                </button>
                {statusOptions.map((o) => (
                  <button
                    key={o.code}
                    type="button"
                    aria-pressed={Boolean(f.statuses?.includes(o.code))}
                    onClick={() => f.toggleStatus(o.code)}
                    className={cn(
                      "rounded-pill min-h-[44px] cursor-pointer border-2 border-solid px-[16px] text-[14px] font-semibold",
                      pickTone(Boolean(f.statuses?.includes(o.code))),
                    )}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-[8px]">
              <span className="text-[15px] font-bold">
                신청 제한 사유{" "}
                <span className="text-text-sub font-medium">· 해당하는 게 있으면 골라요</span>
              </span>
              <div role="group" aria-label="신청 제한 사유" className="flex flex-wrap gap-[8px]">
                <button
                  type="button"
                  aria-pressed={f.restrictions?.length === 0}
                  onClick={f.toggleNoRestriction}
                  className={cn(
                    "rounded-pill min-h-[44px] cursor-pointer border-2 border-solid px-[18px] text-[15px] font-bold",
                    pickTone(f.restrictions?.length === 0),
                  )}
                >
                  해당 없음
                </button>
                {restrictionOptions.map((r) => (
                  <button
                    key={r.code}
                    type="button"
                    aria-pressed={Boolean(f.restrictions?.includes(r.code))}
                    onClick={() => f.toggleRestriction(r.code)}
                    className={cn(
                      "rounded-pill min-h-[44px] cursor-pointer border-2 border-solid px-[16px] text-[14px] font-semibold",
                      pickTone(Boolean(f.restrictions?.includes(r.code))),
                    )}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
              <span className="text-text-sub text-[13px] font-medium">
                공고의 &apos;해당하면 신청할 수 없어요&apos; 조건에 써요 · 민감한 정보라 이번
                탭에서만 쓰고 저장하지 않아요
              </span>
            </div>

            <div className="border-line-soft flex flex-wrap items-center justify-between gap-[10px] border-t border-solid pt-[22px]">
              <Link
                href={routes.business}
                className="text-text-sub hover:text-text-sub inline-flex min-h-[44px] items-center text-[15px] font-semibold no-underline"
              >
                나중에 입력할게요
              </Link>
              <button
                type="button"
                onClick={done}
                className="rounded-control bg-brand inline-flex min-h-[56px] cursor-pointer items-center gap-[8px] border-0 px-[26px] text-[17px] font-extrabold text-white"
              >
                저장하고 결과 보기
                <ArrowRight size={20} strokeWidth={2.2} aria-hidden />
              </button>
            </div>
          </section>

          <aside className="flex min-w-0 flex-col gap-[16px]" style={{ flex: "1 1 300px" }}>
            <section
              aria-label="지금 조건으로"
              aria-live="polite"
              className="rounded-card bg-brand-deep flex flex-col gap-[16px] p-[26px] text-white"
            >
              <span className="text-brand-deep-text text-[15px] font-bold">지금 조건으로</span>
              <div className="flex items-baseline justify-between">
                <span className="text-[15px]">입주 지원 가능 공간</span>
                <span className="tracking-title text-[28px] font-extrabold">
                  {preview.spaces}곳
                </span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-[15px]">받을 수 있는 사업 지원</span>
                <span className="tracking-title text-[28px] font-extrabold">
                  {preview.support}개
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[15px]">확인 필요한 조건</span>
                <Badge tone="check" className="py-[4px] text-[14px] font-extrabold">
                  {preview.check}개
                </Badge>
              </div>
              <span className="text-brand-deep-text border-t border-solid border-white/14 pt-[12px] text-[13px]">
                입력할수록 정확해져요
              </span>
            </section>

            <section
              aria-label="안내"
              className="rounded-card bg-surface flex flex-col gap-[12px] px-[24px] py-[22px]"
            >
              <span className="inline-flex items-center gap-[8px] text-[16px] font-extrabold">
                <Briefcase size={20} className="text-brand" aria-hidden />
                이런 걸 찾아드려요
              </span>
              <ul className="text-text-sub m-0 flex list-disc flex-col gap-[6px] pl-[20px] text-[14px] leading-[1.55]">
                <li>창업보육센터 · 청년창업센터 입주 모집</li>
                <li>LH · SH 단지 내 상가 입찰</li>
                <li>공공기관 회의실 대관</li>
                <li>창업 지원금 · 정책자금 · 세금 감면</li>
              </ul>
            </section>
          </aside>
        </div>
      </WebMain>
    </WebPage>
  );
}
