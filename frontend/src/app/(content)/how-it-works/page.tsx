import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MHowItWorks } from "@/features/content/screens/MHowItWorks";
import { WebHowItWorks } from "@/features/content/screens/WebHowItWorks";

export const metadata: Metadata = {
  title: "무주택자들은 어떻게 만들었나요 | 무주택자들",
  description:
    "공고 수집부터 첨부 읽기, AI 섹션 담당과 코드 검증, 지원 가능 판정, 알림까지 무주택자들이 동작하는 방식을 소개해요.",
};

export default function HowItWorksPage() {
  return <Responsive web={<WebHowItWorks />} mobile={<MHowItWorks />} />;
}
