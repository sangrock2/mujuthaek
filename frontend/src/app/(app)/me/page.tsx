import type { Metadata } from "next";
import { Suspense } from "react";
import { Responsive } from "@/shared/layout/Responsive";
import { MMe } from "@/features/me/screens/MMe";
import { WebMe } from "@/features/me/screens/WebMe";

export const metadata: Metadata = { title: "내 정보 | 무주택자들" };

export default function MePage() {
  // 탭을 주소(?tab=)로 읽어서 Suspense 안에서 그려요
  return (
    <Suspense fallback={null}>
      <Responsive web={<WebMe />} mobile={<MMe />} />
    </Suspense>
  );
}
