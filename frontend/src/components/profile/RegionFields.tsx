"use client";

import type { ProfileForm } from "@/features/profile/useProfileForm";
import { useRegions } from "@/features/regions/queries";
import { cn } from "@/lib/cn";

/**
 * 시·도 → 시·군·구 두 칸. 값은 지역 코드 하나예요.
 * 시·도만 고르면 2자리, 시·군·구까지 고르면 5자리, 아무것도 안 고르면 ""
 */
function PlaceSelects({
  code,
  onChange,
  selectClassName,
  sigunguEmpty,
}: {
  code: string;
  onChange: (code: string) => void;
  selectClassName: string;
  sigunguEmpty: string;
}) {
  const regions = useRegions();
  const sidoCode = code.slice(0, 2);
  const sido = sidoCode ? regions.sido(sidoCode) : undefined;

  return (
    <div className="grid grid-cols-2 gap-[8px]">
      <select
        aria-label="시·도"
        value={sidoCode}
        onChange={(e) => onChange(e.target.value)}
        className={selectClassName}
      >
        {!sidoCode && <option value="">시·도 선택</option>}
        {regions.sidos.map((r) => (
          <option key={r.code} value={r.code}>
            {r.name}
          </option>
        ))}
      </select>
      <select
        aria-label="시·군·구"
        value={code.length === 5 ? code : ""}
        onChange={(e) => onChange(e.target.value || sidoCode)}
        disabled={!sido}
        className={cn(selectClassName, "disabled:bg-fill disabled:text-text-sub")}
      >
        <option value="">{sigunguEmpty}</option>
        {(sido?.sigungus ?? []).map((g) => (
          <option key={g.code} value={g.code}>
            {g.name}
          </option>
        ))}
      </select>
    </div>
  );
}

/** 지금 사는 곳: 거주 요건·순위 판정에만 써요 */
export function ResidenceField({
  form,
  selectClassName,
}: {
  form: ProfileForm;
  selectClassName: string;
}) {
  return (
    <div className="flex flex-col gap-[8px]">
      <span className="text-[15px] font-bold">지금 사는 곳</span>
      <PlaceSelects
        code={form.regionCode}
        onChange={form.setRegionCode}
        selectClassName={selectClassName}
        sigunguEmpty="시·군·구 선택"
      />
      <span className="text-text-sub text-[13px]">공고의 거주 요건과 순위를 확인할 때 써요</span>
    </div>
  );
}

/** 찾아볼 지역: 내 집에서 볼 공고를 골라요 (한 곳) */
export function SearchRegionsField({
  form,
  selectClassName,
}: {
  form: ProfileForm;
  selectClassName: string;
}) {
  return (
    <div className="flex flex-col gap-[8px]">
      <span className="text-[15px] font-bold">어떤 지역 공고를 찾아볼까요?</span>
      <PlaceSelects
        code={form.searchRegionCode}
        onChange={form.setSearchRegionCode}
        selectClassName={selectClassName}
        sigunguEmpty="전체"
      />
      <span className="text-text-sub text-[13px]">
        내 집에서 이 지역 공고를 먼저 보여드려요. 비워 두면 전체 지역 공고를 보여드려요
      </span>
    </div>
  );
}
