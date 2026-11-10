"use client";

import Link from "next/link";
import { Bell } from "lucide-react";
import { useUnreadCount } from "@/features/alerts/queries";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

/** 헤더의 알림 아이콘. 읽지 않은 알림이 있을 때만 초록 점 (알림 화면에서는 점 없음) */
export function AlertsBell({ className, current }: { className: string; current?: boolean }) {
  const unread = useUnreadCount();
  const showDot = unread > 0 && !current;
  return (
    <Link
      href={routes.alerts}
      aria-label={showDot ? `알림, 새 알림 ${unread}개` : "알림"}
      aria-current={current ? "page" : undefined}
      className={cn(className, "relative")}
    >
      <Bell size={22} aria-hidden />
      {showDot && (
        <span
          aria-hidden
          className="rounded-pill bg-brand absolute top-[10px] right-[11px] size-[12px] border-2 border-solid border-white"
        />
      )}
    </Link>
  );
}
