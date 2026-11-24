"use client";

import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { useLogout } from "@/features/auth/session";
import { routes } from "@/shared/lib/routes";

export function MeLogout() {
  const router = useRouter();
  const { logout, logoutError } = useLogout();

  return (
    <div className="flex min-w-0 flex-col">
      <button
        type="button"
        onClick={() =>
          void logout().then((ok) => {
            if (ok) router.push(routes.main);
          })
        }
        className="rounded-control text-text-sub hover:bg-fill hover:text-text flex min-h-[44px] w-full cursor-pointer items-center gap-2.5 px-3 text-left text-[14px] font-bold"
      >
        <LogOut size={18} className="shrink-0" aria-hidden />
        로그아웃
      </button>
      {logoutError && (
        <p role="alert" className="text-danger px-3 py-1 text-[13px]">
          {logoutError}
        </p>
      )}
    </div>
  );
}
