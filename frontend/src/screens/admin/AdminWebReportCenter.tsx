"use client";

import { useState } from "react";
import { useAdminMe } from "@/components/admin/AdminGuard";
import { AdminTitle } from "@/components/admin/AdminShell";
import type { AdminPermission } from "@/features/admin/permissions";
import { useAdminCounts } from "@/features/admin/queries";
import { cn } from "@/lib/cn";
import { AdminWebChatReports } from "@/screens/admin/AdminWebChatReports";
import { AdminWebPolicyDuplicates } from "@/screens/admin/AdminWebPolicyDuplicates";
import { AdminWebReports } from "@/screens/admin/AdminWebReports";

type Kind = "reports" | "chat" | "duplicates";

const KINDS: {
  key: Kind;
  label: string;
  permission: AdminPermission;
  count: "newReports" | "chatReports" | "policyDuplicates";
  desc: string;
}[] = [
  {
    key: "reports",
    label: "정보 제보",
    permission: "REPORTS",
    count: "newReports",
    desc: "사용자가 '정보가 틀렸어요'로 보낸 내용이에요 · 같은 곳을 가리키는 제보는 묶어서 보여드려요",
  },
  {
    key: "chat",
    label: "채팅 신고",
    permission: "CHAT",
    count: "chatReports",
    desc: "공고 채팅에서 신고된 글이에요 · 같은 글에 들어온 신고는 묶어서 보여드려요 · 신고 3건이면 검토 전에 자동으로 가려져요",
  },
  {
    key: "duplicates",
    label: "중복 의심",
    permission: "REPORTS",
    count: "policyDuplicates",
    desc: "출처에 두 번 올라온 것 같은 창업 지원·입주 모집 사업이에요 · 같은 분야 · 같은 이름 · 같은 지역이면 올라와요 · 자동으로 지우지 않아요",
  },
];

/** 제보·신고: 정보 제보와 채팅 신고를 한 화면에서 (받은 권한의 갈래만 보여요) */
export function AdminWebReportCenter() {
  const me = useAdminMe(); // AdminGuard가 먼저 받아 둬요
  const { data: counts } = useAdminCounts();
  const permissions = me.data?.permissions ?? [];
  const kinds = KINDS.filter((k) => permissions.includes(k.permission));
  const [picked, setPicked] = useState<Kind>("reports");
  const cur = kinds.find((k) => k.key === picked) ?? kinds[0];
  if (!cur) return null; // 권한이 없으면 AdminShell이 안내해요

  const head = (
    <div className="flex flex-col gap-[14px]">
      <AdminTitle title="제보·신고" desc={cur.desc} />
      {kinds.length > 1 && (
        <div role="tablist" aria-label="제보·신고 종류" className="flex flex-wrap gap-[6px]">
          {kinds.map((k) => {
            const on = k.key === cur.key;
            const n = counts[k.count];
            return (
              <button
                key={k.key}
                type="button"
                role="tab"
                aria-selected={on}
                onClick={() => setPicked(k.key)}
                className={cn(
                  "rounded-control min-h-[42px] cursor-pointer border-0 px-[16px] text-[15px] font-bold",
                  on ? "bg-brand-deep text-white" : "bg-surface text-text-sub",
                )}
              >
                {k.label}
                {n != null && n > 0 && (
                  <span
                    className={cn(
                      "rounded-pill ml-[8px] px-[8px] py-[1px] text-[12px] font-extrabold",
                      on ? "bg-white/15 text-white" : "bg-check-bg text-check-text",
                    )}
                  >
                    {n}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );

  if (cur.key === "chat") return <AdminWebChatReports head={head} />;
  if (cur.key === "duplicates") return <AdminWebPolicyDuplicates head={head} />;
  return <AdminWebReports head={head} />;
}
