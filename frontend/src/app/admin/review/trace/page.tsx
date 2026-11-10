import type { Metadata } from "next";
import { Suspense } from "react";
import { AdminWebTrace } from "@/screens/admin/AdminWebTrace";

export const metadata: Metadata = { title: "추출 과정 | 무주택자들 관리자" };
// 관리자 화면은 권한을 확인한 뒤에 그려요(AdminGuard). 개발 모드의 즉시 이동 검사에서 빼요
export const instant = false;

/** /admin/review/trace?job=<추출 작업 ID> */
export default function AdminWebTracePage() {
  return (
    <Suspense fallback={null}>
      <AdminWebTrace />
    </Suspense>
  );
}
