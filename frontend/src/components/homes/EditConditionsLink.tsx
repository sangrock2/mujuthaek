"use client";

import Link from "next/link";
import { Pencil } from "lucide-react";
import { useConditions } from "@/features/conditions/store";
import { cn } from "@/lib/cn";
import { profileThen, routes } from "@/lib/routes";

/** 공고 목록 위 「조건 수정」: 조건 입력(찾아볼 지역 포함) 뒤 이 목록으로 돌아와요. 조건이 없으면 「조건 입력」 */
export function EditConditionsLink({ className }: { className?: string }) {
  const conditions = useConditions();
  const has = conditions.status === "ready" && conditions.device !== null;
  return (
    <Link
      href={profileThen(routes.homes)}
      className={cn(
        "text-brand-strong hover:text-brand-strong inline-flex min-h-[36px] items-center gap-[4px] text-[14px] font-bold no-underline",
        className,
      )}
    >
      <Pencil size={14} aria-hidden />
      {has ? "조건 수정" : "조건 입력"}
    </Link>
  );
}
