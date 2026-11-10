"use client";

// 관심 조건: 새 공고·새 지원 정책 알림을 받을 지역·종류. 저장해야 새 공고 알림이 가요 (백엔드 saved)
import { useState } from "react";
import { X } from "lucide-react";
import { LoginPrompt, outlineChip } from "@/components/me/MePanels";
import { Toggle } from "@/components/ui/Toggle";
import { useSession } from "@/features/auth/session";
import { useConditions } from "@/features/conditions/store";
import {
  fromInterestRegion,
  toInterestRegion,
  useInterest,
  type Interest,
  type InterestKind,
} from "@/features/me/api";
import { noticeTypeLabel } from "@/features/notice/labels";
import { useRegions } from "@/features/regions/queries";
import { USE_MOCKS } from "@/lib/api/config";
import { cn } from "@/lib/cn";

const MAX_REGIONS = 30;

type Option = { key: string; label: string };

const housingTypes: Option[] = Object.entries(noticeTypeLabel).map(([key, label]) => ({
  key,
  label,
}));

const startupStages: Option[] = [
  { key: "PRE_STARTUP", label: "예비 창업" },
  { key: "OPERATING", label: "사업 중" },
];

/** 한국표준산업분류 대분류 */
const industrySections: Option[] = [
  { key: "C", label: "제조" },
  { key: "G", label: "도매·소매" },
  { key: "I", label: "숙박·음식" },
  { key: "J", label: "정보통신" },
  { key: "M", label: "전문·과학·기술" },
  { key: "N", label: "사업 지원" },
  { key: "P", label: "교육" },
  { key: "Q", label: "보건·복지" },
  { key: "R", label: "예술·스포츠·여가" },
  { key: "S", label: "수리·개인 서비스" },
  { key: "F", label: "건설" },
  { key: "H", label: "운수·창고" },
  { key: "K", label: "금융·보험" },
  { key: "L", label: "부동산" },
  { key: "A", label: "농림어업" },
];

const supportKinds: Option[] = [
  { key: "RENT", label: "월세 지원" },
  { key: "DEPOSIT_LOAN", label: "전세·보증금 대출" },
  { key: "PURCHASE_LOAN", label: "주택 구입 대출" },
  { key: "HOUSING_SUPPLY", label: "주택 공급" },
  { key: "MOVE_IN_GRANT", label: "이사·입주 지원" },
  { key: "CASH", label: "현금 지원" },
];

type Section = {
  kind: InterestKind;
  title: string;
  desc: string;
  /** 종류 칩 (비우면 모두) */
  groups: {
    field: "noticeTypes" | "industryCodes" | "startupStages" | "supportKinds";
    label: string;
    options: Option[];
  }[];
};

const sections: Section[] = [
  {
    kind: "housing",
    title: "주거 공고",
    desc: "이 지역의 새 주거 공고가 나오면 알려 드려요",
    groups: [{ field: "noticeTypes", label: "공고 유형", options: housingTypes }],
  },
  {
    kind: "support",
    title: "주거·생활 지원",
    desc: "이 지역의 새 혜택(월세·대출·주택 공급 등)이 나오면 알려 드려요",
    groups: [{ field: "supportKinds", label: "지원 종류", options: supportKinds }],
  },
  {
    kind: "business",
    title: "사업공간 · 창업 지원",
    desc: "이 지역의 새 사업공간 모집·창업 지원 사업이 나오면 알려 드려요",
    groups: [
      { field: "startupStages", label: "창업 단계", options: startupStages },
      { field: "industryCodes", label: "업종", options: industrySections },
    ],
  },
];

const control =
  "border-line bg-surface text-text min-h-[44px] rounded-sm border border-solid px-[12px] text-[15px]";

function InterestEditor({ section, defaultRegion }: { section: Section; defaultRegion: string }) {
  const interest = useInterest(section.kind);
  const regions = useRegions();
  const loaded = interest.value;
  // 처음 열면 내 조건의 지역을 넣어 둬요 (아직 저장 안 했을 때만)
  const initial = (): Interest =>
    loaded.saved
      ? loaded
      : { ...loaded, regionCodes: defaultRegion ? [toInterestRegion(defaultRegion)] : [] };
  const [draft, setDraft] = useState<Interest | null>(null);
  const value = draft ?? initial();
  const [sido, setSido] = useState("");
  const [sigungu, setSigungu] = useState("");
  const [done, setDone] = useState<string | null>(null);

  if (interest.loading) return null;

  const codes = value.regionCodes.map(fromInterestRegion);
  const edit = (patch: Partial<Interest>) => {
    setDone(null);
    setDraft({ ...value, ...patch });
  };
  const addRegion = () => {
    const code = sigungu || sido;
    if (!code || codes.includes(code) || codes.length >= MAX_REGIONS) return;
    edit({ regionCodes: [...value.regionCodes, toInterestRegion(code)] });
    setSigungu("");
  };
  const toggleOption = (field: Section["groups"][number]["field"], key: string) => {
    const list = value[field] ?? [];
    edit({ [field]: list.includes(key) ? list.filter((x) => x !== key) : [...list, key] });
  };
  const save = async () => {
    const body = {
      regionCodes: value.regionCodes,
      includeNationwide: value.includeNationwide,
      noticeTypes: value.noticeTypes,
      industryCodes: value.industryCodes,
      startupStages: value.startupStages,
      supportKinds: value.supportKinds,
    };
    await interest.save(body);
    setDraft(null);
    setDone("저장했어요");
  };
  const sigungus = sido ? (regions.sido(sido)?.sigungus ?? []) : [];

  return (
    <section
      aria-label={section.title}
      className="border-line-soft flex flex-col gap-[14px] border-b border-solid pb-[22px]"
    >
      <div className="flex flex-wrap items-center justify-between gap-[8px]">
        <span className="flex flex-col gap-[2px]">
          <span className="text-[18px] font-extrabold">{section.title}</span>
          <span className="text-text-sub text-[14px]">{section.desc}</span>
        </span>
        <span
          className={cn(
            "rounded-badge px-[10px] py-[5px] text-[13px] font-extrabold",
            loaded.saved ? "bg-brand-soft text-brand-strong" : "bg-fill text-text-sub",
          )}
        >
          {loaded.saved ? "알림 받는 중" : "저장 전 · 새 공고 알림 없음"}
        </span>
      </div>

      <div className="flex flex-col gap-[8px]">
        <span className="text-[15px] font-bold">관심 지역 (비우면 전체)</span>
        <div className="flex flex-wrap gap-[6px]">
          {codes.map((c) => (
            <span
              key={c}
              className="rounded-pill bg-brand-soft text-brand-strong inline-flex min-h-[36px] items-center gap-[4px] pr-[6px] pl-[12px] text-[14px] font-bold"
            >
              {regions.label(c) ?? c}
              <button
                type="button"
                aria-label={`${regions.label(c) ?? c} 빼기`}
                onClick={() =>
                  edit({
                    regionCodes: value.regionCodes.filter((x) => fromInterestRegion(x) !== c),
                  })
                }
                className="text-brand-strong inline-flex size-[28px] cursor-pointer items-center justify-center border-0 bg-transparent p-0"
              >
                <X size={16} aria-hidden />
              </button>
            </span>
          ))}
          {codes.length === 0 && <span className="text-text-sub text-[14px]">전체 지역</span>}
        </div>
        <div className="flex flex-wrap items-center gap-[8px]">
          <select
            aria-label="시·도"
            value={sido}
            onChange={(e) => {
              setSido(e.target.value);
              setSigungu("");
            }}
            className={control}
          >
            <option value="">시·도</option>
            {regions.sidos.map((o) => (
              <option key={o.code} value={o.code}>
                {o.name}
              </option>
            ))}
          </select>
          <select
            aria-label="시·군·구"
            value={sigungu}
            onChange={(e) => setSigungu(e.target.value)}
            disabled={!sido}
            className={cn(control, "disabled:opacity-50")}
          >
            <option value="">{sido ? "전체" : "시·군·구"}</option>
            {sigungus.map((o) => (
              <option key={o.code} value={o.code}>
                {o.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={addRegion}
            disabled={!sido || codes.length >= MAX_REGIONS}
            className="bg-fill text-text min-h-[44px] cursor-pointer rounded-sm border-0 px-[14px] text-[15px] font-bold disabled:opacity-50"
          >
            추가
          </button>
        </div>
        <div className="flex items-center gap-[10px]">
          <Toggle
            checked={value.includeNationwide}
            onChange={(v) => edit({ includeNationwide: v })}
            label="전국 공고도 받기"
          />
          <span className="text-[15px]">전국 대상 공고도 받기</span>
        </div>
      </div>

      {section.groups.map((g) => (
        <div key={g.field} className="flex flex-col gap-[8px]">
          <span className="text-[15px] font-bold">{g.label} (비우면 모두)</span>
          <div role="group" aria-label={g.label} className="flex flex-wrap gap-[6px]">
            {g.options.map((o) => {
              const on = (value[g.field] ?? []).includes(o.key);
              return (
                <button
                  key={o.key}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggleOption(g.field, o.key)}
                  className={cn(outlineChip(on), "min-h-[40px] px-[14px] text-[14px]")}
                >
                  {o.label}
                </button>
              );
            })}
          </div>
        </div>
      ))}

      <div className="flex flex-wrap items-center gap-[10px]">
        <button
          type="button"
          disabled={interest.saving}
          onClick={() => void save().catch(() => setDone(null))}
          className="bg-brand min-h-[48px] cursor-pointer rounded-sm border-0 px-[20px] text-[15px] font-extrabold text-white disabled:opacity-60"
        >
          {loaded.saved ? "바꾼 내용 저장" : "저장하고 알림 받기"}
        </button>
        {loaded.saved && (
          <button
            type="button"
            onClick={() =>
              void interest.remove().then(() => {
                setDraft(null);
                setDone("이 관심 조건을 지웠어요");
              })
            }
            className="text-text-sub min-h-[44px] cursor-pointer border-0 bg-transparent px-[6px] text-[14px] font-bold"
          >
            알림 끄기
          </button>
        )}
        {done && (
          <span role="status" className="text-brand-strong text-[14px] font-bold">
            {done}
          </span>
        )}
        {interest.saveFailed && (
          <span role="alert" className="text-danger-text text-[14px]">
            저장하지 못했어요. 잠시 뒤 다시 해 주세요
          </span>
        )}
      </div>
    </section>
  );
}

export function InterestsPanel() {
  const { data: session } = useSession();
  const conditions = useConditions();
  if (!USE_MOCKS && !session) return <LoginPrompt what="관심 조건" />;
  const defaultRegion = conditions.status === "ready" ? (conditions.device?.regionCode ?? "") : "";
  return (
    <div className="flex flex-col gap-[22px]">
      <span className="text-text-sub text-[15px] leading-[1.6]">
        고른 지역·종류의 새 공고와 지원 정책이 나오면 알림으로 알려 드려요. 지역을 비우면 전체예요.
      </span>
      {sections.map((s) => (
        <InterestEditor key={s.kind} section={s} defaultRegion={defaultRegion} />
      ))}
    </div>
  );
}
