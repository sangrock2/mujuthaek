"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/features/auth/session";
import { api } from "@/shared/lib/api/client";
import { USE_MOCKS } from "@/shared/lib/api/config";
import { endpoints } from "@/shared/lib/api/endpoints";
import { routes } from "@/shared/lib/routes";
import { preparationError, preparationsKey, type Preparation } from "./api";

export function PreparationButton({ noticeId }: { noticeId: string }) {
  const router = useRouter();
  const client = useQueryClient();
  const { data: session, isPending } = useSession();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    if (USE_MOCKS) {
      setError("시연 화면에서는 준비 기록을 저장하지 않아요. 실제 API 모드에서 사용할 수 있어요.");
      return;
    }
    if (!session) {
      router.push(`${routes.login}?next=${encodeURIComponent(routes.notice(noticeId))}`);
      return;
    }
    setPending(true);
    setError(null);
    try {
      const p = await api.put<Preparation>(`${endpoints.preparations}/notices/${encodeURIComponent(noticeId)}`);
      await Promise.all([
        client.invalidateQueries({ queryKey: preparationsKey }),
        client.invalidateQueries({ queryKey: ["favorites"] }),
      ]);
      router.push(routes.preparation(p.id));
    } catch (e) {
      setError(preparationError(e));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-[6px]">
      <button
        type="button"
        onClick={() => void create()}
        disabled={pending || isPending}
        className="bg-brand rounded-control min-h-[48px] cursor-pointer border-0 px-[16px] text-[15px] font-bold text-white disabled:opacity-60"
      >
        {pending ? "준비함 여는 중…" : "신청 준비하기"}
      </button>
      {error && (
        <p role="alert" className="text-text-sub m-0 text-[14px]">
          {error}
        </p>
      )}
    </div>
  );
}
