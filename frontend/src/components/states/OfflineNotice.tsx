import { cn } from "@/lib/cn";

/** 4 · 오프라인 */
export function OfflineNotice({
  onReconnect,
  className,
}: {
  onReconnect?: () => void;
  className?: string;
}) {
  return (
    <section
      role="status"
      className={cn(
        "bg-text flex items-center gap-[10px] rounded-[18px] px-[16px] py-[14px] text-white",
        className,
      )}
    >
      <span className="flex-1 text-[14px] font-semibold">
        인터넷 연결이 끊겼어요 · 저장된 결과를 보여드려요
      </span>
      <button
        type="button"
        onClick={onReconnect}
        className="text-brand-deep-text-2 min-h-[44px] cursor-pointer border-0 bg-transparent px-[6px] text-[14px] font-extrabold"
      >
        다시 연결
      </button>
    </section>
  );
}
