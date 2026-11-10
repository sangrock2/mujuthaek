import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Responsive } from "@/components/layout/Responsive";
import { MStates } from "@/screens/states/MStates";
import { WebStates } from "@/screens/states/WebStates";

export const metadata: Metadata = { title: "빈 상태 · 오류 미리보기 | 무주택자들" };

/** 개발용 미리보기: 빈 상태 · 오류 부품을 디자인 캔버스처럼 모아 보여줘요 */
export default function StatesPreviewPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <Responsive web={<WebStates />} mobile={<MStates />} />;
}
