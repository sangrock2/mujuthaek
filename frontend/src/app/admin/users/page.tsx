import type { Metadata } from "next";
import { AdminWebUsers } from "@/screens/admin/AdminWebUsers";

export const metadata: Metadata = { title: "회원 | 무주택자들 관리자" };
// 관리자 화면은 권한을 확인한 뒤에 그려요(AdminGuard). 개발 모드의 즉시 이동 검사에서 빼요
export const instant = false;

export default function AdminWebUsersPage() {
  return <AdminWebUsers />;
}
