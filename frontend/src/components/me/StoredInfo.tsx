"use client";

import { useSession } from "@/features/auth/session";
import { daysLeft } from "@/features/conditions/format";
import { DEVICE_TTL_MS } from "@/features/conditions/store";
import { useConditionSummary } from "@/features/conditions/useConditionSummary";
import { cn } from "@/lib/cn";

/** 이 기기에 저장한 조건의 상태: 없음 · 이 기기 · N일 뒤 삭제 · 이번 탭에서만 */
export function useDeviceStatus() {
  const conditions = useConditionSummary();
  if (conditions.status !== "ready" || !conditions.hasConditions) return "없음";
  return conditions.savedAt
    ? `이 기기 · ${daysLeft(conditions.savedAt, DEVICE_TTL_MS)}일 뒤 삭제`
    : "이번 탭에서만";
}

/** 이 기기에 조건 저장 토글의 설명 (켜짐 · 꺼짐) */
export const saveOnDeviceNote = (on: boolean) =>
  on
    ? "나이·지역·가족·주택 조건을 30일 동안 이 기기에만 저장해요"
    : "이 기기에 저장하지 않아요. 탭을 닫으면 입력한 조건이 지워져요";

/** 「저장된 정보」: 어떤 정보가 어디에 저장되는지 (웹·모바일 내 정보 공통) */
export function StoredInfoList({ compact }: { compact?: boolean }) {
  const { data: session } = useSession();
  const device = useDeviceStatus();
  const rows: [string, string, boolean?][] = [
    ["나이 · 지역 · 가족 · 주택 조건", device],
    ["소득 · 자산 · 순위 세부 조건", "저장 안 함", true],
    ["관심 공고 · 관심 조건 · 알림 설정", "계정에 저장"],
    ["연락용 이메일 (선택)", session?.email ? "계정에 저장" : "없음"],
  ];
  return (
    <div className="flex flex-col">
      <span className={cn("mb-[4px] font-extrabold", compact ? "text-[15px]" : "text-[16px]")}>
        저장된 정보
      </span>
      {rows.map(([label, value, accent], i) => (
        <div
          key={label}
          className={cn(
            "flex justify-between gap-[12px] py-[12px]",
            compact ? "text-[14px]" : "text-[15px]",
            i < rows.length - 1 && "border-line-soft border-b border-solid",
          )}
        >
          <span>{label}</span>
          <span className={cn("flex-none font-bold", accent && "text-brand-strong")}>{value}</span>
        </div>
      ))}
    </div>
  );
}
