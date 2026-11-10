import type { BizStage } from "@/mocks/business";

export type StageOption = { key: BizStage; label: string; sub: string };

/** 사업 중일 때 사업자 형태 (공고마다 개인 · 법인 자격이 달라요) */
export const applicantTypes = [
  { key: "INDIVIDUAL", label: "개인사업자" },
  { key: "CORPORATION", label: "법인" },
] as const;

/** 창업 상태 선택지 (PC · 모바일 문구가 달라요) */
export const stageOptions: Record<"web" | "mobile", StageOption[]> = {
  web: [
    { key: "pre", label: "예비 창업", sub: "아직 사업자등록 전이에요" },
    { key: "run", label: "사업 중", sub: "사업자등록을 했어요" },
  ],
  mobile: [
    { key: "pre", label: "예비 창업", sub: "사업자등록 전" },
    { key: "run", label: "사업 중", sub: "사업자등록 했어요" },
  ],
};
