"use client";

import { Heart } from "lucide-react";
import { useFavoriteToggle, type FavoriteType } from "@/features/favorites/queries";
import { cn } from "@/lib/cn";

type Props = {
  type: FavoriteType;
  id: string | undefined;
  /** 관심 등록할 때(해제 말고) 부르는 일 (GA 기록 등) */
  onAdd?: () => void;
  className?: string;
};

/** 웹 상세의 큰 버튼: 관심 등록하고 마감 알림 받기 ↔ 관심 공고 · 마감 알림 받는 중 */
export function WebFavoriteButton({ type, id, onAdd, className }: Props) {
  const fav = useFavoriteToggle(type, id);
  return (
    <div className="flex flex-col gap-[6px]">
      <button
        type="button"
        aria-pressed={fav.on}
        onClick={() => {
          if (!fav.on) onAdd?.();
          void fav.toggle();
        }}
        className={cn(
          "rounded-tile flex min-h-[60px] cursor-pointer items-center justify-center gap-[8px] border-0 text-[18px] font-extrabold",
          fav.on ? "bg-brand-soft text-brand" : "bg-brand text-white",
          className,
        )}
      >
        <Heart size={20} strokeWidth={2.2} fill={fav.on ? "currentColor" : "none"} aria-hidden />
        {fav.on ? "관심 공고 · 마감 알림 받는 중" : "관심 등록하고 마감 알림 받기"}
      </button>
      {fav.message && (
        <span role="alert" className="text-danger-text text-center text-[14px]">
          {fav.message}
        </span>
      )}
    </div>
  );
}

/** 목록 카드 위의 둥근 하트 */
export function CardFavoriteHeart({ type, id, onAdd, className }: Props) {
  const fav = useFavoriteToggle(type, id);
  return (
    <button
      type="button"
      aria-label={fav.on ? "관심 해제" : "관심 등록"}
      aria-pressed={fav.on}
      title={fav.message ?? undefined}
      onClick={() => {
        if (!fav.on) onAdd?.();
        void fav.toggle();
      }}
      className={cn(
        "rounded-pill bg-surface flex size-[40px] cursor-pointer items-center justify-center border-0",
        fav.on ? "text-brand" : "text-text-sub",
        className,
      )}
    >
      <Heart size={20} fill={fav.on ? "currentColor" : "none"} aria-hidden />
    </button>
  );
}

/** 모바일 하단의 하트 버튼 */
export function MFavoriteHeart({ type, id, onAdd, className }: Props) {
  const fav = useFavoriteToggle(type, id);
  return (
    <button
      type="button"
      aria-pressed={fav.on}
      aria-label={fav.on ? "관심 해제" : "관심 등록하고 마감 알림 받기"}
      title={fav.message ?? undefined}
      onClick={() => {
        if (!fav.on) onAdd?.();
        void fav.toggle();
      }}
      className={cn(
        "rounded-control bg-fill flex min-h-[56px] w-[56px] flex-none cursor-pointer items-center justify-center border-0",
        fav.on ? "text-brand" : "text-text-sub",
        className,
      )}
    >
      <Heart size={24} fill={fav.on ? "currentColor" : "none"} aria-hidden />
    </button>
  );
}
