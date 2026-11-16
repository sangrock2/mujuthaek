import type { Metadata } from "next";
import { AdminGuard } from "@/features/admin/components/AdminGuard";
import { AdminShell } from "@/features/admin/components/AdminShell";

// 관리자 화면은 검색에 나오지 않게 해요 (2026-11-16 보안 감사 4장). 하위 화면 metadata에 robots를 따로 두지 않아 그대로 이어져요
export const metadata: Metadata = {
  title: "관리자 | 무주택자들",
  robots: { index: false, follow: false },
};

/** 관리자는 PC 전용 화면이라 모바일 화면을 따로 두지 않아요. 관리자 권한이 있는 회원만 들어와요 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AdminGuard>
      <AdminShell>{children}</AdminShell>
    </AdminGuard>
  );
}
