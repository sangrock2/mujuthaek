import type { Metadata } from "next";
import { Suspense } from "react";
import { Responsive } from "@/components/layout/Responsive";
import { MMe } from "@/screens/me/MMe";
import { WebMe } from "@/screens/me/WebMe";

export const metadata: Metadata = { title: "내 정보 | 무주택자들" };

export default function MePage() {
  // 탭을 주소(?tab=)로 읽어서 Suspense 안에서 그려요
  return (
    <Suspense fallback={null}>
      <Responsive web={<WebMe />} mobile={<MMe />} />
    </Suspense>
  );
}
