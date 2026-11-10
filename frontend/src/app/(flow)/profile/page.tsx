import type { Metadata } from "next";
import { Suspense } from "react";
import { Responsive } from "@/components/layout/Responsive";
import { MProfile } from "@/screens/profile/MProfile";
import { WebProfile } from "@/screens/profile/WebProfile";

export const metadata: Metadata = { title: "조건 입력 | 무주택자들" };

export default function ProfilePage() {
  // 확인하기 뒤 갈 곳을 주소(?next=)로 읽어서 Suspense 안에서 그려요
  return (
    <Suspense fallback={null}>
      <Responsive web={<WebProfile />} mobile={<MProfile />} />
    </Suspense>
  );
}
